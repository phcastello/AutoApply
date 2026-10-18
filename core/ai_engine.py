"""AI Engine — generates tailored resumes and cover letters via LLM APIs.

Implements: FR-031 (AI availability check), FR-032 (document generation),
            FR-074 (multi-provider LLM).

Supports Anthropic, OpenAI, Google (Gemini), and DeepSeek as providers.
Falls back to static templates when no API key is configured.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests

from config.ai_destination import API_ENDPOINTS, DEFAULT_MODELS, destination
from config.settings import LLMConfig, environment_credential

logger = logging.getLogger(__name__)

RESUME_PROMPT = """
You are an expert resume writer. Create a tailored, ATS-optimised resume for this specific job.

Instructions:
- Read ALL experience files below carefully
- Select only experiences and skills most relevant to THIS job
- Quantify achievements wherever numbers appear in the raw notes
- Use strong action verbs
- Keep content to one page worth of text
- Do NOT invent or exaggerate anything not present in the experience files

Output format — Markdown only, no preamble, no explanation:

# [Full Name]
[email] | [phone] | [location] | [linkedin if provided] | [portfolio if provided]

## Summary
2-3 sentences tailored specifically to this role and company.

## Experience
### [Job Title] — [Company] ([Start Year] - [End Year or Present])
- Achievement bullet using numbers where available
- Achievement bullet
...

## Skills
Comma-separated, relevant skills only.

## Education
[Degree] — [Institution] ([Year])

Omit any section for which there is no information.

---
EXPERIENCE FILES:
{experience_files_content}

---
JOB DESCRIPTION:
{job_description}

---
APPLICANT:
Name: {full_name}
Email: {email}
Phone: {phone}
Location: {location}
LinkedIn: {linkedin_url}
Portfolio: {portfolio_url}
"""

KB_RESUME_PROMPT = """
You are an expert resume writer. Create a polished, ATS-optimised resume using ONLY the data provided below.

STRICT RULES:
- Use ONLY the experiences, skills, education, projects, and certifications listed below
- Do NOT invent, fabricate, or embellish ANY information
- Do NOT add companies, roles, skills, or achievements not present in the data
- Do NOT guess dates, locations, or titles — use exactly what is provided
- You MAY rephrase and reword bullets for clarity, readability, impact, and ATS optimization
- You MAY use synonyms from the job description to better align bullet phrasing
- You MAY combine or split related bullets from the same role for better flow
- You MAY reorder content to best match the job description
- You MAY omit entries that are clearly irrelevant to this specific job
- Quantify achievements where numbers are already present in the data

PAGE LENGTH RULES — THIS IS CRITICAL:
- The resume MUST fill exactly ONE full US Letter page (no more, no less)
- Use the highest-ranked data first, then include lower-ranked data until the page is full
- Every experience role MUST have at least 2 bullet points — expand by rephrasing or splitting if needed
- If space remains, add more bullet points to the most relevant roles or include additional projects
- If too long, trim the least relevant bullets from the bottom — but keep at least 2 per role

Output format — Markdown only, no preamble, no explanation:

# {full_name}
{email} | {phone} | {location}{linkedin_line}

## Summary
{summary_text}

## Education
### [Institution] | [Location]
[Degree] | [Dates]

## Skills
**[Category]**: [comma-separated skills]

## Experience
### [Company] | [Location]
**[Job Title]** | [Dates]
- Achievement bullet (from provided data only)
- At least 2 bullets per role

## Projects
### [Project Name]
- Description bullet (from provided data only)

## Certifications
- [Certification name]

Omit any section that has no data.

---
JOB DESCRIPTION:
{job_description}

---
PROVIDED RESUME DATA (use ONLY this — do not add anything else):

{kb_data}
"""

COVER_LETTER_PROMPT = """
You are an expert career coach. Write a cover letter for this job application.

Instructions:
- 3 paragraphs, professional but not stiff
- Reference specific details from the job description
- Use relevant experiences from the experience files
- Do NOT use filler phrases like "I am excited to apply" or "I am a perfect fit"
- Do NOT repeat the resume — add context and personality
- Match tone to the company culture inferred from the job description
- Output ONLY the cover letter body — no date, no address, no salutation header, no sign-off

---
EXPERIENCE FILES:
{experience_files_content}

---
JOB DESCRIPTION:
{job_description}

---
APPLICANT:
Name: {full_name}
Bio / tone preference: {bio}
"""


class AIError(RuntimeError):
    """Only curated diagnostics cross the HTTP/task/log boundary."""

    def __init__(self, category, message, *, status=None, code=None, param=None, request_id=None):
        super().__init__(message)
        self.details = dict(
            category=category,
            message=message,
            http_status=status,
            code=code,
            param=param,
            request_id=request_id,
        )

    def as_dict(self):
        return self.details.copy()


def check_ai_available(llm_config) -> bool:
    if not llm_config or not llm_config.provider:
        return False
    try:
        url, _ = destination(
            llm_config.provider,
            getattr(llm_config, "endpoint", ""),
            getattr(llm_config, "protocol", "auto"),
        )
        key, _ = environment_credential(llm_config)
        return bool(
            llm_config.api_key
            or key
            or (urlsplit(url).hostname in ("localhost", "127.0.0.1", "::1"))
        )
    except ValueError:
        return False


def validate_api_key(provider: str, api_key: str, model: str | None = None) -> bool:
    """Compatibility wrapper; HTTP clients use test_configuration for diagnostics."""
    return test_configuration(LLMConfig(provider=provider, api_key=api_key, model=model or ""))[
        "valid"
    ]


def test_configuration(llm_config):
    model = llm_config.model or DEFAULT_MODELS.get(llm_config.provider, "")
    context = dict(provider=llm_config.provider, model=model)
    try:
        url, protocol = destination(llm_config.provider, llm_config.endpoint, llm_config.protocol)
        context.update(endpoint=url, protocol=protocol)
        invoke_llm(
            "Reply with OK. No explanation.",
            llm_config,
            timeout_seconds=60,
            max_output_tokens=4096,
            test_request=True,
        )
        return dict(
            valid=True, message="O provedor gerou uma resposta com esta configuração.", **context
        )
    except AIError as e:
        return dict(valid=False, error=e.as_dict(), **context)
    except ValueError:
        return dict(
            valid=False,
            error=AIError(
                "configuration", "Confira provedor, modelo, protocolo e URL do servidor."
            ).as_dict(),
            **context,
        )
    except Exception:
        return dict(
            valid=False,
            error=AIError(
                "application",
                "Falha interna ao processar o teste de IA. Confira o protocolo e tente novamente.",
            ).as_dict(),
            **context,
        )


# Legacy entry points retained for existing callers and other providers.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _call_llm(provider, api_key, model, prompt, timeout=120, **options):
    retries = options.pop("retries", MAX_RETRIES)
    deadline = time.monotonic() + timeout
    for attempt in range(retries + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AIError("timeout", "Tempo total de resposta da IA esgotado. Tente novamente.")
        try:
            if options.get("endpoint") or provider in ("openai", "deepseek", "compatible"):
                return _call_openai_compatible(
                    provider, api_key, model, prompt, remaining, **options
                )
            if provider == "anthropic":
                return _call_anthropic(api_key, model, prompt, remaining)
            if provider == "google":
                return _call_google(api_key, model, prompt, remaining)
            raise AIError("configuration", "Unsupported LLM provider / provedor não suportado")
        except AIError as e:
            if (
                e.details["http_status"] not in RETRYABLE_STATUS_CODES
                and e.details["category"] not in ("connection", "timeout")
            ) or attempt >= retries:
                raise
        except (requests.ConnectionError, requests.Timeout):
            if attempt >= retries:
                raise AIError(
                    "connection", "Não foi possível conectar ao provedor de IA."
                ) from None
        delay = RETRY_BASE_DELAY * (2**attempt)
        if time.monotonic() + delay >= deadline:
            raise AIError("timeout", "Tempo total de resposta da IA esgotado.")
        time.sleep(delay)
    raise AIError("provider", "O provedor não respondeu.")


def _post(url, *, timeout, **kwargs):
    # A wall-clock bound also covers slow/trickling bodies. No redirects with secrets.
    result = queue.Queue(maxsize=1)

    def run():
        try:
            result.put(
                requests.post(
                    url, timeout=(min(10, timeout), timeout), allow_redirects=False, **kwargs
                )
            )
        except Exception as e:
            result.put(e)

    threading.Thread(target=run, daemon=True).start()
    try:
        response = result.get(timeout=timeout)
    except queue.Empty:
        raise AIError(
            "timeout", "Tempo total de resposta da IA esgotado. Tente novamente."
        ) from None
    if isinstance(response, requests.Timeout):
        raise AIError("timeout", "O provedor excedeu o tempo de resposta.") from None
    if isinstance(response, Exception):
        raise AIError(
            "connection", "Falha de conexão com o provedor. Confira rede, TLS e destino."
        ) from None
    return response


def _json(resp):
    try:
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, TypeError):
        raise AIError(
            "invalid_response", "O endpoint não retornou JSON válido no protocolo selecionado."
        ) from None


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise AIError(
            "empty_response",
            "O modelo não produziu texto. Confira o protocolo e o orçamento de saída.",
        )
    return value.strip()


def _call_anthropic(api_key, model, prompt, timeout):
    resp = _post(
        API_ENDPOINTS["anthropic"],
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        _raise_api_error("Anthropic", resp)
    data = _json(resp)
    return _text(
        "".join(
            x.get("text", "") for x in data.get("content", []) if x.get("type", "text") == "text"
        )
    )


def _call_openai_compatible(
    provider,
    api_key,
    model,
    prompt,
    timeout,
    *,
    endpoint="",
    protocol="auto",
    max_output_tokens=8192,
    test_request=False,
    response_format=None,
):
    url, protocol = destination(provider, endpoint, protocol)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {"model": model}
    if protocol == "responses":
        body.update(
            input=[{"role": "user", "content": prompt}],
            max_output_tokens=max_output_tokens,
            store=False,
        )
        if test_request and (model == "gpt-6.1-sol" or model.startswith("gpt-6.1-sol-")):
            body["reasoning"] = {"effort": "low"}
        if response_format:
            body["text"] = {"format": response_format}
    else:
        body["messages"] = [{"role": "user", "content": prompt}]
        # Compatible vendors keep their documented Chat Completions parameter.
        official = provider == "openai" and url == "https://api.openai.com/v1/chat/completions"
        body["max_completion_tokens" if official else "max_tokens"] = max_output_tokens
        if official:
            body["store"] = False
        if response_format:
            if response_format.get("type") == "json_schema" and "schema" in response_format:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {k: v for k, v in response_format.items() if k != "type"},
                }
            else:
                body["response_format"] = response_format
    resp = _post(url, headers=headers, json=body, timeout=timeout)
    if resp.status_code != 200:
        _raise_api_error(provider.title(), resp)
    data = _json(resp)
    if protocol == "responses":
        if data.get("status") == "incomplete":
            raise AIError(
                "output_limit",
                "Resposta incompleta: orçamento de saída esgotado ou resposta interrompida.",
            )
        if data.get("status") in ("failed", "cancelled"):
            raise AIError("provider", "O provedor encerrou a geração sem uma resposta.")
        parts = [
            p
            for item in data.get("output", [])
            if item.get("type") == "message"
            for p in item.get("content", [])
        ]
        if any(p.get("type") == "refusal" for p in parts):
            raise AIError("refusal", "O modelo recusou este pedido.")
        return _text("".join(p.get("text", "") for p in parts if p.get("type") == "output_text"))
    try:
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise AIError("output_limit", "Resposta incompleta: limite de saída atingido.")
        if choice.get("message", {}).get("refusal"):
            raise AIError("refusal", "O modelo recusou este pedido.")
        return _text(choice["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise AIError(
            "invalid_response",
            "Resposta incompatível com Chat Completions. Confira endpoint e protocolo.",
        ) from None


def _call_google(api_key, model, prompt, timeout):
    resp = _post(
        API_ENDPOINTS["google"].format(model=model),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 4096},
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        _raise_api_error("Google", resp)
    try:
        return _text(
            "".join(p.get("text", "") for p in _json(resp)["candidates"][0]["content"]["parts"])
        )
    except (KeyError, IndexError, TypeError):
        raise AIError("invalid_response", "Resposta incompatível com Google Gemini.") from None


def _raise_api_error(provider, resp):
    try:
        error = resp.json().get("error", {})
        if not isinstance(error, dict):
            error = {}
    except (ValueError, TypeError, AttributeError):
        error = {}
    # Never relay an arbitrary remote body: providers can echo keys and personal data.
    known_codes = {
        "invalid_api_key",
        "insufficient_quota",
        "rate_limit_exceeded",
        "model_not_found",
        "unsupported_parameter",
        "unsupported_value",
        "invalid_request_error",
        "permission_denied",
        "model_access_denied",
        "authentication_error",
        "context_length_exceeded",
        "billing_hard_limit_reached",
    }
    code = error.get("code") if error.get("code") in known_codes else None
    param = (
        error.get("param")
        if error.get("param")
        in {
            "max_tokens",
            "max_completion_tokens",
            "max_output_tokens",
            "model",
            "reasoning.effort",
            "temperature",
            "response_format",
            "text.format",
        }
        else None
    )
    status = resp.status_code
    category, message = "provider", "Falha no provedor de IA. Tente novamente mais tarde."
    if status == 401:
        category, message = (
            "authentication",
            "Credencial recusada pelo provedor. Confira a chave e o projeto.",
        )
    elif status == 403:
        category, message = (
            "permission",
            "Acesso negado: confira permissões do projeto e acesso ao modelo.",
        )
    elif code == "model_not_found" or status == 404:
        category, message = (
            "model_unavailable",
            "Modelo ou endpoint indisponível neste contexto. Confira o ID, o protocolo e o acesso da conta.",
        )
    elif code in {"insufficient_quota", "billing_hard_limit_reached"}:
        category, message = (
            "quota",
            "Cota ou saldo do projeto insuficiente. Confira o faturamento no provedor.",
        )
    elif status == 429:
        category, message = (
            "rate_limit",
            "Limite de requisições do provedor atingido. Aguarde antes de testar novamente.",
        )
    elif status in (400, 422):
        category, message = "request", "O provedor recusou os parâmetros da requisição."
    elif 300 <= status < 400:
        category, message = (
            "endpoint",
            "O endpoint redirecionou a requisição. Informe o destino final; a chave não foi encaminhada.",
        )
    if code in ("permission_denied", "model_access_denied"):
        category, message = "permission", "O projeto não tem permissão para esta chamada ou modelo."
    if code:
        message += " Código: " + code + "."
    if param:
        message += " Parâmetro: " + param + "."
    message = f"{provider} API ({status}): " + message
    request_id = resp.headers.get("x-request-id", "")
    request_id = (
        request_id
        if isinstance(request_id, str) and re.fullmatch(r"req_[a-zA-Z0-9_-]{1,100}", request_id)
        else None
    )
    raise AIError(category, message, status=status, code=code, param=param, request_id=request_id)


def invoke_llm(
    prompt,
    llm_config,
    timeout_seconds=120,
    *,
    max_output_tokens=8192,
    test_request=False,
    response_format=None,
):
    if not llm_config or not llm_config.provider:
        raise AIError("configuration", "No AI provider configured. Configure a IA para continuar.")
    endpoint = getattr(llm_config, "endpoint", "")
    protocol = getattr(llm_config, "protocol", "auto")
    url, _ = destination(llm_config.provider, endpoint, protocol)
    env_key, _ = environment_credential(llm_config)
    api_key = llm_config.api_key or env_key
    local = urlsplit(url).hostname in ("localhost", "127.0.0.1", "::1")
    if not api_key and not local:
        raise AIError(
            "credential_missing",
            "No AI provider credential configured. Informe uma chave para este provedor e destino.",
        )
    model = llm_config.model or DEFAULT_MODELS.get(llm_config.provider, "")
    if not model:
        raise AIError("configuration", "Informe o ID do modelo.")
    # All production operations use one request, with a total deadline and no paid retries.
    return _call_llm(
        llm_config.provider,
        api_key,
        model,
        prompt,
        timeout_seconds,
        endpoint=endpoint,
        protocol=protocol,
        max_output_tokens=max_output_tokens,
        test_request=test_request,
        response_format=response_format,
        retries=0,
    )


# Names retained for consumers of the guided configuration API.
AIProviderError = AIError
diagnose_provider = test_configuration


def read_all_experience_files(experience_dir: Path) -> str:
    """Read all .txt files from experience directory, excluding README.txt.

    Files are sorted alphabetically and concatenated with section separators.

    Args:
        experience_dir: Path to directory containing .txt files.

    Returns:
        Concatenated content string, or empty string if no files found.
    """
    if not experience_dir.exists():
        return ""

    parts: list[str] = []
    for f in sorted(experience_dir.glob("*.txt")):
        if f.name.lower() == "readme.txt":
            continue
        try:
            content = f.read_text(encoding="utf-8")
            parts.append(f"=== {f.name} ===\n{content}")
        except (UnicodeDecodeError, OSError) as e:
            logger.warning("Skipping unreadable experience file %s: %s", f.name, e)

    return "\n\n".join(parts)


def generate_documents(
    job,
    profile,
    experience_dir: Path,
    output_dir_resumes: Path,
    output_dir_cover_letters: Path,
    llm_config=None,
    skip_cover_letter: bool = False,
) -> tuple[Path, Path | None, dict]:
    """Generate tailored resume and cover letter for a job application.

    Reads experience files, calls the configured LLM for resume (and
    optionally cover letter), saves outputs to disk, and returns paths
    plus version metadata.

    Args:
        job: Object with ``.id`` (str), ``.raw.company`` (str),
             ``.raw.description`` (str).
        profile: UserProfile with full_name, email, phone, location,
                 linkedin_url, portfolio_url, bio.
        experience_dir: Path to experience .txt files.
        output_dir_resumes: Where to save resume .md and .pdf files.
        output_dir_cover_letters: Where to save cover letter .txt files.
        llm_config: LLMConfig with provider, api_key, model.
        skip_cover_letter: If True, skip cover letter generation.

    Returns:
        Tuple of (resume_pdf_path, cover_letter_txt_path | None, version_meta).
        version_meta contains resume_md_path, resume_pdf_path, llm_provider,
        and llm_model for resume version recording (FR-118).

    Raises:
        RuntimeError: If LLM invocation fails.
    """
    from core.resume_renderer import render_resume_to_pdf

    experience_content = read_all_experience_files(experience_dir)

    safe_company = job.raw.company.replace(" ", "-").lower()
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_name = f"{job.id}_{safe_company}_{date_str}"

    # Ensure output directories exist
    output_dir_resumes.mkdir(parents=True, exist_ok=True)
    output_dir_cover_letters.mkdir(parents=True, exist_ok=True)

    # Capture LLM provider/model for version tracking (FR-118)
    llm_provider = getattr(llm_config, "provider", None) if llm_config else None
    llm_model = getattr(llm_config, "model", None) if llm_config else None

    # Generate resume via LLM
    resume_md_text = invoke_llm(
        RESUME_PROMPT.format(
            experience_files_content=experience_content,
            job_description=job.raw.description,
            full_name=profile.full_name,
            email=profile.email,
            phone=profile.phone_full,
            location=profile.location,
            linkedin_url=profile.linkedin_url or "N/A",
            portfolio_url=profile.portfolio_url or "N/A",
        ),
        llm_config,
    )

    # Save resume Markdown + PDF
    resume_md_path = output_dir_resumes / f"{base_name}.md"
    resume_pdf_path = output_dir_resumes / f"{base_name}.pdf"
    resume_md_path.write_text(resume_md_text, encoding="utf-8")
    render_resume_to_pdf(resume_md_text, resume_pdf_path)

    # Generate and save cover letter (unless disabled)
    cl_path = None
    if not skip_cover_letter:
        cover_letter_text = invoke_llm(
            COVER_LETTER_PROMPT.format(
                experience_files_content=experience_content,
                job_description=job.raw.description,
                full_name=profile.full_name,
                bio=profile.bio,
            ),
            llm_config,
        )
        cl_path = output_dir_cover_letters / f"{base_name}.txt"
        cl_path.write_text(cover_letter_text, encoding="utf-8")

    version_meta = {
        "resume_md_path": str(resume_md_path),
        "resume_pdf_path": str(resume_pdf_path),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    }

    return resume_pdf_path, cl_path, version_meta


def _format_kb_data_for_prompt(context: dict) -> str:
    """Format structured KB context into a text block for the LLM prompt.

    Takes the same context dict produced by resume_assembler._build_context()
    and serializes it into a human-readable text block that the LLM can use.
    """
    lines: list[str] = []

    # Education
    for entry in context.get("education", []):
        inst = entry.get("institution", "")
        loc = entry.get("location", "")
        degree = entry.get("degree", "")
        dates = entry.get("dates", "")
        lines.append(f"EDUCATION: {inst} | {loc} | {degree} | {dates}")

    # Skills
    for group in context.get("skills", []):
        cat = group.get("category", "")
        entries = group.get("entries", "")
        lines.append(f"SKILLS ({cat}): {entries}")

    # Experience
    for comp in context.get("experience", []):
        company = comp.get("company", "")
        loc = comp.get("location", "")
        for role in comp.get("roles", []):
            title = role.get("title", "")
            dates = role.get("dates", "")
            lines.append(f"EXPERIENCE: {company} | {loc} | {title} | {dates}")
            for bullet in role.get("bullets", []):
                lines.append(f"  - {bullet}")

    # Projects
    for proj in context.get("projects", []):
        name = proj.get("name", "")
        lines.append(f"PROJECT: {name}")
        for bullet in proj.get("bullets", []):
            lines.append(f"  - {bullet}")

    # Certifications
    for entry in context.get("certifications", []):
        lines.append(f"CERTIFICATION: {entry.get('text', '')}")

    return "\n".join(lines)


def generate_resume_from_kb(
    context: dict,
    jd_text: str,
    llm_config,
) -> str:
    """Generate a resume markdown from structured KB data via LLM.

    The LLM is strictly instructed to use ONLY the provided KB data
    and not invent any experiences, skills, or achievements.

    Args:
        context: Structured context dict from _build_context() with
            name, email, phone, location, summary, experience, education,
            skills, projects, certifications.
        jd_text: Job description to tailor against.
        llm_config: LLMConfig with provider, api_key, model.

    Returns:
        Resume content as markdown string.

    Raises:
        RuntimeError: If LLM invocation fails.
    """
    kb_data = _format_kb_data_for_prompt(context)
    summary = context.get("summary", "")
    linkedin = context.get("linkedin_url", "")
    linkedin_line = f" | {linkedin}" if linkedin else ""

    prompt = KB_RESUME_PROMPT.format(
        full_name=context.get("name", ""),
        email=context.get("email", ""),
        phone=context.get("phone", ""),
        location=context.get("location", ""),
        linkedin_line=linkedin_line,
        summary_text=summary
        if summary
        else "Write a 2-3 sentence summary tailored to the job, based ONLY on the provided data.",
        job_description=jd_text,
        kb_data=kb_data,
    )

    return invoke_llm(prompt, llm_config)
