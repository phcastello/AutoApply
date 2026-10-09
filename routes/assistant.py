"""Dashboard APIs for manual discovery and evidence-bound document preparation."""

import os
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file
from pydantic import ValidationError

import app_state
from config.settings import AppConfig, get_data_dir, load_config, save_config
from core.assisted_matching import evaluate
from core.assisted_workflow import (
    STATES,
    generate_resume,
    get_job,
    list_jobs,
    save_payload,
    search_jobs,
)
from core.document_parser import extract_text
from core.job_discovery import verify_url

assistant_bp = Blueprint("assistant", __name__)
_tasks = {}
_task_lock = threading.Lock()


def current_config():
    return load_config() or AppConfig(
        profile=dict(
            first_name="",
            last_name="",
            email="",
            phone="",
            phone_country_code="+55",
            city="",
            state="",
            country="Brasil",
            bio="",
        ),
        search_criteria=dict(job_titles=[], locations=[]),
        bot=dict(min_match_score=0, apply_mode="watch"),
    )


def _task(fn):
    with _task_lock:
        if any(t["state"] == "running" for t in _tasks.values()):
            abort(409, description="Aguarde a operação em andamento")
        # Keep recent results only; never include keys or profile data in tasks.
        while len(_tasks) >= 30:
            _tasks.pop(next(iter(_tasks)))
        task_id = uuid.uuid4().hex
        _tasks[task_id] = dict(state="running")

    def run():
        try:
            result = fn()
            _tasks[task_id] = dict(state="completed", result=result)
        except Exception as e:
            message = (
                str(e)
                if isinstance(e, ValueError)
                else f"Operação falhou ({type(e).__name__}). Confira configuração, conectividade e provedor."
            )
            _tasks[task_id] = dict(state="failed", error=message)
            app_state.db.save_feed_event("error", message=message)

    threading.Thread(target=run, daemon=True).start()
    return jsonify(task_id=task_id), 202


@assistant_bp.get("/api/assistant/config")
def get_configuration():
    config = current_config()
    data = config.model_dump()
    data["llm"]["has_api_key"] = bool(config.llm.api_key or os.environ.get("AUTOAPPLY_LLM_API_KEY"))
    data["llm"]["api_key"] = ""
    return jsonify(data)


@assistant_bp.put("/api/assistant/config")
def put_configuration():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Envie uma configuração JSON")
    existing = current_config()
    merged = existing.model_dump()
    for section in ("profile", "search_criteria", "llm", "bot"):
        if section in data:
            if not isinstance(data[section], dict):
                abort(400, description="Seção inválida")
            merged[section].update(data[section])
    if "company_blacklist" in data:
        merged["company_blacklist"] = data["company_blacklist"]
    if not data.get("llm", {}).get("api_key"):
        same_destination = (merged["llm"]["provider"], merged["llm"]["endpoint"]) == (
            existing.llm.provider,
            existing.llm.endpoint,
        )
        merged["llm"]["api_key"] = existing.llm.api_key if same_destination else ""
    try:
        config = AppConfig(**merged)
        ids = [e.id for e in config.profile.career_entries]
        if len(set(ids)) != len(ids) or any(not i.strip() for i in ids):
            raise ValueError("Informações do perfil precisam de identificadores únicos")
        if config.llm.provider not in ("", "openai", "anthropic", "google", "deepseek"):
            raise ValueError("Provedor não suportado")
        if not 0 <= config.bot.min_match_score <= 100:
            raise ValueError("Pontuação mínima deve estar entre 0 e 100")
        save_config(config)
    except ValidationError:
        abort(400, description="Campos inválidos no perfil ou preferências")
    except ValueError as e:
        abort(400, description=str(e))
    # Refresh matching when profile/preferences change, preserving history.
    for job in list_jobs(app_state.db):
        job["match"] = evaluate(
            config.profile, config.search_criteria, job, config.company_blacklist
        )
        save_payload(app_state.db, job)
    return jsonify(success=True)


@assistant_bp.get("/api/assistant/jobs")
def jobs():
    return jsonify(jobs=list_jobs(app_state.db))


@assistant_bp.post("/api/assistant/search")
def search():
    config = current_config()
    return _task(lambda: search_jobs(app_state.db, config))


@assistant_bp.get("/api/assistant/tasks/<task_id>")
def task_status(task_id):
    if task_id not in _tasks:
        abort(404)
    return jsonify(_tasks[task_id])


def _job(job_id):
    job = get_job(app_state.db, job_id)
    if not job:
        abort(404, description="Vaga não encontrada")
    return job


@assistant_bp.patch("/api/assistant/jobs/<int:job_id>")
def status(job_id):
    _job(job_id)
    data = request.get_json(silent=True) or {}
    state = data.get("status")
    if state not in STATES:
        abort(400, description="Estado de candidatura inválido")
    app_state.db.update_status(job_id, state)
    app_state.db.save_feed_event("info", message=f"Vaga {job_id}: estado atualizado para {state}")
    return jsonify(success=True)


@assistant_bp.post("/api/assistant/jobs/<int:job_id>/verify")
def verify(job_id):
    job = _job(job_id)

    def run():
        job.update(verify_url(job))
        save_payload(app_state.db, job)
        return dict(url_status=job["url_status"], message=job["url_message"])

    return _task(run)


@assistant_bp.post("/api/assistant/jobs/<int:job_id>/resume")
def resume(job_id):
    job, config = _job(job_id), current_config()
    data = request.get_json(silent=True) or {}
    if type(data.get("use_ai", False)) is not bool or type(data.get("force", False)) is not bool:
        abort(400, description="Opções inválidas")
    return _task(
        lambda: generate_resume(
            app_state.db,
            config,
            job,
            get_data_dir(),
            use_ai=data.get("use_ai", False),
            force=data.get("force", False),
        )
    )


@assistant_bp.get("/api/assistant/resumes/<int:version_id>/<format>")
def download(version_id, format):
    if format not in ("pdf", "docx", "provenance"):
        abort(404)
    with app_state.db._connect() as conn:
        row = conn.execute(
            """SELECT v.resume_pdf_path,r.docx_path,r.provenance_path FROM assisted_resumes r
            JOIN resume_versions v ON v.id=r.version_id WHERE v.id=?""",
            (version_id,),
        ).fetchone()
    if not row:
        abort(404)
    field = {"pdf": "resume_pdf_path", "docx": "docx_path", "provenance": "provenance_path"}[format]
    path = Path(row[field]).resolve()
    if not path.is_relative_to((get_data_dir() / "outputs").resolve()) or not path.is_file():
        abort(404, description="Documento indisponível")
    if format == "pdf":
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(path))
            if not reader.pages or not any((p.extract_text() or "").strip() for p in reader.pages):
                raise ValueError("PDF inválido")
        except Exception:
            abort(422, description="PDF inválido; gere uma nova versão")
    mime = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "provenance": "application/json",
    }[format]
    return send_file(
        path,
        mimetype=mime,
        as_attachment=request.args.get("preview") != "1",
        download_name=path.name,
    )


@assistant_bp.post("/api/assistant/import")
def import_document():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        abort(400, description="Selecione um documento")
    ext = Path(upload.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".md", ".txt"):
        abort(400, description="Use PDF, DOCX, Markdown ou TXT")
    raw = upload.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        abort(400, description="Limite de importação: 5 MB")
    try:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ("document" + ext)
            path.write_bytes(raw)
            text = extract_text(path)
    except Exception:
        abort(422, description="Não foi possível extrair o texto do documento")
    if not text.strip():
        abort(422, description="Documento sem texto; PDFs digitalizados precisam de OCR externo")
    # Explicit human review. No generated resume or KB entry is automatically trusted.
    return jsonify(text=text[:100000], source=Path(upload.filename).name, confirmed=False)


@assistant_bp.get("/api/assistant/kb-suggestions")
def kb_suggestions():
    entries = app_state.db.get_kb_entries(limit=500)
    roles = {r["id"]: r for r in app_state.db.get_roles()}
    result = []
    for entry in entries:
        role = roles.get(entry.get("role_id"), {})
        result.append(
            dict(
                id=f"kb-{entry['id']}",
                category=entry["category"],
                text=entry["text"],
                title=role.get("title") or "",
                organization=role.get("company") or "",
                start_date=role.get("start_date") or "",
                end_date=role.get("end_date") or "",
                source=f"Knowledge Base #{entry['id']} (revisar origem)",
                confirmed=False,
            )
        )
    return jsonify(entries=result)


@assistant_bp.post("/api/assistant/ai/test")
def test_ai():
    from core.ai_engine import invoke_llm

    config = current_config()
    return _task(
        lambda: dict(valid=bool(invoke_llm("Reply with OK", config.llm, timeout_seconds=15)))
    )
