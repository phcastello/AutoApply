"""Read-only discovery through public Greenhouse and Lever job-board APIs."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests


def now():
    return datetime.now(timezone.utc).isoformat()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = _Text()
    parser.feed(html.unescape(html.unescape(value or "")))
    return "\n".join(x.strip() for x in "".join(parser.parts).splitlines() if x.strip())


def canonical_url(value):
    u = urlsplit(value or "")
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        return ""
    query = [
        (k, v)
        for k, v in parse_qsl(u.query)
        if not k.lower().startswith("utm_") and k.lower() not in {"source", "ref", "lever-source"}
    ]
    return urlunsplit(
        (u.scheme, u.netloc.lower(), u.path.rstrip("/"), urlencode(sorted(query)), "")
    )


def fingerprint(job):
    parts = [
        re.sub(r"\W+", " ", str(job.get(k, "")).lower()).strip()
        for k in ("company", "title", "location")
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def requirements(text):
    """Only classify explicitly headed requirements; preserve unknown sections."""
    required, preferred = [], []
    target = None
    for line in text.splitlines():
        low = line.lower().strip(" :")
        if len(line) < 110 and any(
            x in low
            for x in (
                "nice to have",
                "preferred qualifications",
                "desejáveis",
                "diferenciais",
                "bonus points",
            )
        ):
            target = preferred
            continue
        if len(line) < 110 and any(
            x in low
            for x in (
                "minimum qualifications",
                "required qualifications",
                "requirements",
                "requisitos",
                "what you bring",
                "what we're looking for",
                "basic qualifications",
            )
        ):
            target = required
            continue
        if len(line) < 90 and any(
            x in low
            for x in (
                "benefits",
                "benefícios",
                "about us",
                "responsibilities",
                "what you'll do",
                "compensation",
            )
        ):
            target = None
        if target is not None:
            target.append(line)
    return required, preferred


def normalize_job(source, board, item, company=None):
    if source == "greenhouse":
        title, location = item.get("title", ""), item.get("location", {}).get("name", "")
        description = plain_text(item.get("content", ""))
        original = item.get("absolute_url", "")
        apply_url = original
        published = item.get("first_published")  # updated_at is NOT a publication date
        employment = None
        mode = None
    else:
        title, location = item.get("text", ""), item.get("categories", {}).get("location", "")
        description = item.get("descriptionPlain") or plain_text(item.get("description", ""))
        for section in item.get("lists", []):
            description += (
                "\n" + section.get("text", "") + "\n" + plain_text(section.get("content", ""))
            )
        description += "\n" + (
            item.get("additionalPlain") or plain_text(item.get("additional", ""))
        )
        original, apply_url = (
            item.get("hostedUrl", ""),
            item.get("applyUrl") or item.get("hostedUrl", ""),
        )
        timestamp = item.get("createdAt")
        published = (
            datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat()
            if timestamp
            else None
        )
        employment = item.get("categories", {}).get("commitment")
        mode = item.get("workplaceType")
    url = canonical_url(apply_url)
    # Generic pages cannot masquerade as an opportunity.
    if not item.get("id") or not title or not url or not description.strip():
        raise ValueError("Vaga sem identificador, descrição ou URL específica")
    u = urlsplit(url)
    if len([p for p in u.path.split("/") if p]) < 2 and not any(
        k in dict(parse_qsl(u.query)) for k in ("gh_jid", "job_id")
    ):
        raise ValueError("URL genérica de carreiras")
    if mode not in ("on-site", "onsite", "hybrid", "remote"):
        mode = None
    if not mode:
        mode = {
            "on-site": "on-site",
            "onsite": "on-site",
            "hybrid": "hybrid",
            "remote": "remote",
        }.get(item.get("workplaceType") or item.get("work_mode"))
    if not mode:
        inferred = {
            value
            for value, pattern in (
                ("remote", r"\b(?:remote|remoto)\b"),
                ("hybrid", r"\b(?:hybrid|híbrido)\b"),
                ("on-site", r"\b(?:on[- ]site|presencial)\b"),
            )
            if re.search(pattern, location, re.I)
        }
        if len(inferred) == 1:
            mode = inferred.pop()
    seniority = next(
        (
            level
            for level in (
                "intern",
                "trainee",
                "junior",
                "senior",
                "staff",
                "principal",
                "estágio",
                "júnior",
                "sênior",
                "pleno",
            )
            if re.search(r"\b" + re.escape(level) + r"\b", title, re.I)
        ),
        None,
    )
    required, preferred = requirements(description)
    job = dict(
        external_id=f"{board}:{item['id']}",
        source=source,
        board=board,
        source_id=str(item["id"]),
        company=company or item.get("company_name") or board,
        title=title,
        location=location,
        work_mode=mode,
        seniority=seniority,
        description=description.strip(),
        required=required,
        preferred=preferred,
        original_url=original,
        apply_url=apply_url,
        canonical_url=url,
        published_at=published,
        discovered_at=now(),
        availability="listed",
        employment_type=employment,
        salary=None,
        language=item.get("language"),
        url_status="unverified",
        url_message="Publicada na API; página ainda não verificada",
    )
    job["fingerprint"] = fingerprint(job)
    # Preserve explicit published restrictions; never substitute headquarters.
    for key in (
        "country",
        "country_code",
        "attendance_country",
        "attendance_location",
        "remote_countries",
        "remote_excluded_countries",
        "remote_worldwide",
        "remote_restrictions",
        "timezone_restriction",
        "hiring_restriction",
        "visa_sponsorship",
        "sponsorship_available",
        "required_languages",
        "start_date",
    ):
        if key in item:
            job[key] = item[key]
    if isinstance(item.get("salary"), dict):
        job["salary"] = item["salary"]
    elif isinstance(item.get("salaryRange"), dict):
        band = item["salaryRange"]
        interval = band.get("interval")
        job["salary"] = dict(
            min=band.get("min"),
            max=band.get("max"),
            currency=band.get("currency"),
            period={
                "per-year-salary": "annual",
                "per-month-salary": "monthly",
                "per-hour-wage": "hourly",
            }.get(interval),
            source_interval=interval,
        )
    if item.get("pay_input_ranges"):
        # Preserve bands without guessing their applicable region or payment period.
        job["salary_ranges"] = item["pay_input_ranges"]
    return job


def fetch_board(source, board):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", board):
        raise ValueError("Identificador de board inválido")
    session = requests.Session()
    session.headers["User-Agent"] = "AutoApply-Assisted/1.0 (public job discovery)"
    if source == "greenhouse":
        root = f"https://boards-api.greenhouse.io/v1/boards/{board}"
        r = session.get(root + "/jobs", params={"content": "true"}, timeout=25)
        r.raise_for_status()
        items = r.json()["jobs"]
        company = board
        try:
            metadata = session.get(root, timeout=10)
            if metadata.ok:
                company = metadata.json().get("name") or board
        except (requests.RequestException, ValueError):
            pass
    else:
        r = session.get(
            f"https://api.lever.co/v0/postings/{board}", params={"mode": "json"}, timeout=25
        )
        r.raise_for_status()
        items, company = r.json(), board
    jobs = []
    for item in items:
        try:
            jobs.append(normalize_job(source, board, item, company))
        except (ValueError, TypeError, KeyError):
            continue
    return jobs


def discover(criteria):
    boards = [
        (s, b)
        for s, entries in (
            ("greenhouse", criteria.greenhouse_boards),
            ("lever", criteria.lever_boards),
        )
        for b in entries
    ]
    if not boards or len(boards) > 12:
        raise ValueError("Configure entre 1 e 12 boards Greenhouse/Lever")
    jobs, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = {pool.submit(fetch_board, s, b): (s, b) for s, b in boards}
        for task in as_completed(tasks):
            s, b = tasks[task]
            try:
                jobs.extend(task.result())
            except Exception as e:
                # Do not include raw external response bodies or credentials.
                errors.append(f"{s}/{b}: falha na consulta ({type(e).__name__})")
    return jobs, errors


def _public_url(url):
    u = urlsplit(url)
    if not canonical_url(url) or u.port not in (None, 443):
        raise ValueError("URL HTTPS inválida")
    addresses = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("Destino não público")


def verify_url(job):
    """Check every redirect, the specific vacancy identity and closed markers."""
    url = job["apply_url"]
    try:
        for _ in range(6):
            _public_url(url)
            r = requests.get(
                url,
                timeout=12,
                allow_redirects=False,
                headers={"User-Agent": "AutoApply-Assisted/1.0"},
            )
            if r.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, r.headers.get("Location", ""))
                continue
            if r.status_code in (404, 410):
                return dict(
                    url_status="closed",
                    availability="closed",
                    url_message=f"Página retornou HTTP {r.status_code}",
                    checked_at=now(),
                )
            if r.status_code != 200:
                break
            text = plain_text(r.text).lower()
            if any(
                x in text
                for x in (
                    "this job is no longer available",
                    "this job is no longer accepting",
                    "this position has been filled",
                    "vaga encerrada",
                )
            ):
                return dict(
                    url_status="closed",
                    availability="closed",
                    url_message="Página informa vaga encerrada",
                    checked_at=now(),
                )
            title_tokens = re.findall(r"\w+", job["title"].lower())
            matches = sum(t in text for t in title_tokens)
            if job["source_id"] in r.text and matches >= max(1, len(title_tokens) // 2):
                return dict(
                    url_status="verified",
                    apply_url=url,
                    canonical_url=canonical_url(url),
                    url_message="HTTP 200, identificador e cargo encontrados na página",
                    checked_at=now(),
                )
            break
    except (requests.RequestException, ValueError, OSError):
        pass
    return dict(
        url_status="unverified",
        url_message="Não foi possível confirmar a página e sua correspondência; abra e confira manualmente",
        checked_at=now(),
    )
