"""Fixtures are intentionally fictional; no external site is needed for these tests."""

import io
import json
from pathlib import Path

import pytest
from docx import Document

from config.settings import AppConfig, load_config, save_config
from core.assisted_matching import evaluate, select_entries, use_ai_selection
from core.assisted_workflow import (
    generate_resume,
    get_job,
    list_jobs,
    persist_job,
    search_jobs,
    validate_pdf,
)
from core.job_discovery import canonical_url, normalize_job, verify_url
from db.database import Database


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("config.settings._check_keyring", lambda: False)
    return AppConfig(
        profile=dict(
            first_name="Candidata",
            last_name="Teste",
            email="teste@example.invalid",
            phone="11999990000",
            phone_country_code="+55",
            city="São Paulo",
            state="SP",
            country="Brasil",
            bio="",
            career_entries=[
                dict(
                    id="p1",
                    category="project",
                    title="API acadêmica",
                    text="Desenvolvi API Python com Flask e SQLite.",
                    technologies=["Python", "Flask"],
                    confirmed=True,
                ),
                dict(
                    id="e1",
                    category="education",
                    organization="Instituição Fictícia",
                    title="Computação",
                    start_date="2021",
                    end_date="2025",
                    text="Projeto acadêmico de software.",
                    confirmed=True,
                ),
                dict(id="x1", category="skill", text="Kubernetes", confirmed=False),
            ],
        ),
        search_criteria=dict(job_titles=["Software"], locations=[], max_results=5),
        bot=dict(min_match_score=0),
    )


@pytest.fixture
def job():
    return normalize_job(
        "greenhouse",
        "fixture",
        dict(
            id=123,
            title="Software Engineer",
            location={"name": "Remote"},
            absolute_url="https://boards.greenhouse.io/fixture/jobs/123?utm_source=test",
            content="<h3>Requirements</h3><ul><li>Python and Flask experience</li></ul><h3>Nice to have</h3><ul><li>Kubernetes</li></ul><h3>Benefits</h3><p>Flexible hours</p>",
        ),
        "Empresa Fictícia",
    )


def test_profile_preferences_round_trip(configuration):
    configuration.search_criteria.weekly_hours = 30
    configuration.search_criteria.needs_sponsorship = True
    save_config(configuration)
    loaded = load_config()
    assert loaded.profile.career_entries == configuration.profile.career_entries
    assert loaded.search_criteria.weekly_hours == 30
    assert loaded.search_criteria.needs_sponsorship is True
    assert loaded.bot.apply_mode == "watch"


def test_normalization_no_fabricated_metadata(job):
    assert job["source_id"] == "123"
    assert job["published_at"] is None
    assert job["salary"] is None
    assert job["url_status"] == "unverified"
    assert job["required"] == ["Python and Flask experience"]
    assert job["preferred"] == ["Kubernetes"]
    assert "Flexible hours" not in job["preferred"]


def test_lever_normalization():
    job = normalize_job(
        "lever",
        "fixture",
        dict(
            id="abc",
            text="Engineer",
            categories={"location": "Brazil", "commitment": "Full-time"},
            descriptionPlain="Build APIs",
            lists=[dict(text="Requirements", content="<li>Python</li>")],
            hostedUrl="https://jobs.lever.co/fixture/abc",
            applyUrl="https://jobs.lever.co/fixture/abc/apply",
        ),
    )
    assert job["apply_url"].endswith("/abc/apply")
    assert job["published_at"] is None
    assert "Python" in job["description"]


def test_reject_generic_or_unsafe_url():
    assert canonical_url("javascript:alert(1)") == ""
    assert canonical_url("https://user:password@example.org/jobs/1") == ""
    with pytest.raises(ValueError):
        normalize_job(
            "greenhouse",
            "x",
            dict(
                id=1, title="Test", content="Real text", absolute_url="https://example.org/careers"
            ),
        )


def test_dedup_id_url_and_metadata(configuration, job, tmp_path):
    db = Database(tmp_path / "test.db")
    analysis = evaluate(configuration.profile, configuration.search_criteria, job)
    one = persist_job(db, job.copy(), analysis)
    assert persist_job(db, job.copy(), analysis) == one
    other = job.copy()
    other.update(
        external_id="other:999",
        source="lever",
        canonical_url="https://jobs.lever.co/other/999",
        apply_url="https://jobs.lever.co/other/999",
    )
    assert persist_job(db, other, analysis) == one
    assert len(list_jobs(Database(tmp_path / "test.db"))) == 1
    db.update_status(one, "applied")
    persist_job(db, job.copy(), analysis)
    assert get_job(db, one)["status"] == "applied"


def test_matching_confirmed_full_profile(configuration, job):
    match = evaluate(configuration.profile, configuration.search_criteria, job)
    assert 0 <= match["score"] <= 100
    assert any("python" in m for m in match["matches"])
    assert any("kubernetes" in g and "Desejável" in g for g in match["gaps"])
    assert not match["blockers"]
    assert any("p1" in m for m in match["matches"])
    assert not any("Kubernetes" in e["text"] for e in select_entries(configuration.profile, job))


def test_missing_preferences_are_not_restrictions(configuration, job):
    configuration.search_criteria.locations = []
    configuration.search_criteria.experience_levels = []
    job["seniority"] = "senior"
    assert not evaluate(configuration.profile, configuration.search_criteria, job)["blockers"]


def test_pdf_docx_provenance_cache_and_restart(configuration, job, tmp_path):
    db = Database(tmp_path / "test.db")
    job_id = persist_job(
        db, job, evaluate(configuration.profile, configuration.search_criteria, job)
    )
    saved = get_job(db, job_id)
    result = generate_resume(db, configuration, saved, tmp_path)
    assert result["validation"]["valid"]
    version = db.get_resume_version(result["version_id"])
    text = __import__("core.document_parser", fromlist=["extract_text"]).extract_text(
        Path(version["resume_pdf_path"])
    )
    assert "Candidata Teste" in text and "teste@example.invalid" in text
    assert "Kubernetes" not in text and "AWS" not in text
    assert "Instituição Fictícia" in text
    folder = Path(version["resume_pdf_path"]).parent
    facts = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))["selected_facts"]
    assert all(f["confirmed"] for f in facts)
    assert {f["id"] for f in facts} == {"p1", "e1"}
    assert "Candidata Teste" in " ".join(
        p.text for p in Document(folder / "resume.docx").paragraphs
    )
    cached = generate_resume(Database(tmp_path / "test.db"), configuration, saved, tmp_path)
    assert cached["cached"] and cached["version_id"] == result["version_id"]
    fresh = generate_resume(db, configuration, saved, tmp_path, force=True)
    assert fresh["version_id"] != result["version_id"]
    assert get_job(db, job_id)["status"] == "resume_prepared"


def test_no_facts_no_resume(configuration, job, tmp_path):
    configuration.profile.career_entries = []
    with pytest.raises(ValueError, match="Confirme"):
        generate_resume(Database(tmp_path / "t.db"), configuration, {**job, "id": 1}, tmp_path)


def test_ai_cannot_invent_fact_ids(configuration, job, monkeypatch):
    monkeypatch.setattr("core.ai_engine.invoke_llm", lambda *a, **k: '["invented-qualification"]')
    with pytest.raises(ValueError, match="referências inexistentes"):
        use_ai_selection(select_entries(configuration.profile, job), job, configuration.llm)


def test_ai_selects_original_text_without_contacts(configuration, job, monkeypatch):
    def invoke(prompt, *a, **k):
        assert "teste@example.invalid" not in prompt
        return '["p1"]'

    monkeypatch.setattr("core.ai_engine.invoke_llm", invoke)
    assert (
        use_ai_selection(select_entries(configuration.profile, job), job, configuration.llm)[0][
            "text"
        ]
        == configuration.profile.career_entries[0].text
    )


def test_search_failure_reported_and_persisted(configuration, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.assisted_workflow.discover",
        lambda c: ([], ["greenhouse/test: falha na consulta (Timeout)"]),
    )
    db = Database(tmp_path / "t.db")
    result = search_jobs(db, configuration)
    assert not result["job_ids"] and result["errors"]
    assert any(e.event_type == "error" for e in db.get_feed_events())


@pytest.mark.parametrize("code,expected", [(403, "unverified"), (404, "closed"), (410, "closed")])
def test_url_statuses(job, monkeypatch, code, expected):
    monkeypatch.setattr("core.job_discovery._public_url", lambda u: None)
    monkeypatch.setattr(
        "core.job_discovery.requests.get",
        lambda *a, **k: type("R", (), dict(status_code=code, headers={}, text=""))(),
    )
    assert verify_url(job)["url_status"] == expected


def test_verified_url_requires_job_identity(job, monkeypatch):
    monkeypatch.setattr("core.job_discovery._public_url", lambda u: None)
    monkeypatch.setattr(
        "core.job_discovery.requests.get",
        lambda *a, **k: type(
            "R", (), dict(status_code=200, headers={}, text="<h1>Software Engineer</h1> job 123")
        )(),
    )
    assert verify_url(job)["url_status"] == "verified"
    job["source_id"] = "999"
    assert verify_url(job)["url_status"] == "unverified"


def test_redirect_private_address_rejected(job, monkeypatch):
    monkeypatch.setattr(
        "core.job_discovery.socket.getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    assert verify_url(job)["url_status"] == "unverified"


def test_invalid_pdf_not_validated(configuration, tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        validate_pdf(path, configuration.profile)


def test_api_profile_import_credentials_and_download(configuration, tmp_path, monkeypatch):
    import app_state
    from app import app

    monkeypatch.setattr(app_state, "db", Database(tmp_path / "api.db"))
    client = app.test_client()
    response = client.put("/api/assistant/config", json=configuration.model_dump())
    assert response.status_code == 200
    assert client.get("/api/assistant/config").json["profile"]["career_entries"][0]["id"] == "p1"
    assert client.get("/api/assistant/config").json["llm"]["api_key"] == ""
    result = client.post(
        "/api/assistant/import",
        data={"file": (io.BytesIO(b"Python project"), "career.txt")},
        content_type="multipart/form-data",
    )
    assert result.status_code == 200 and result.json["confirmed"] is False
    assert client.get("/api/assistant/resumes/999/pdf").status_code == 404
    assert client.patch("/api/assistant/jobs/999", json={"status": "applied"}).status_code == 404
    assert client.get("/").status_code == 200
    assert "Meu perfil" in client.get("/").get_data(as_text=True)


def test_keys_never_fallback_to_plaintext(configuration, tmp_path):
    configuration.llm.api_key = "fixture-secret"
    with pytest.raises(ValueError, match="Keyring"):
        save_config(configuration)
    assert not (tmp_path / "config.json").exists()


def test_academic_years_do_not_satisfy_professional_requirement(configuration, job):
    job["required"] = ["At least 5 years of professional experience"]
    result = evaluate(configuration.profile, configuration.search_criteria, job)
    assert any("5 anos" in item and "0 meses" in item for item in result["blockers"])
    assert result["recommendation"] == "Revisar requisitos antes de candidatar"


def test_overlap_professional_periods_not_counted_twice(configuration):
    from core.assisted_matching import professional_months

    entries = [
        dict(category="experience", start_date="2020-01", end_date="2023-01"),
        dict(category="experience", start_date="2021-01", end_date="2023-01"),
    ]
    assert professional_months(entries) == (36, False)


def test_company_years_not_treated_as_candidate_requirement(configuration, job):
    job["description"] += "\nWe have 30 years of experience in consulting."
    result = evaluate(configuration.profile, configuration.search_criteria, job)
    assert not any("30 anos" in item for item in result["unknowns"] + result["blockers"])


def test_credentials_scoped_to_provider_and_endpoint(configuration, monkeypatch):
    import sys
    from unittest.mock import MagicMock

    from config.settings import _credential_name

    vault = {}
    keyring = MagicMock()
    keyring.set_password.side_effect = lambda service, key, value: vault.__setitem__(key, value)
    keyring.get_password.side_effect = lambda service, key: vault.get(key)
    monkeypatch.setitem(sys.modules, "keyring", keyring)
    monkeypatch.setattr("config.settings._check_keyring", lambda: True)
    configuration.llm.provider = "openai"
    configuration.llm.api_key = "fixture-private-key"
    save_config(configuration)
    assert load_config().llm.api_key == "fixture-private-key"
    saved = json.loads(
        (
            __import__("config.settings", fromlist=["get_data_dir"]).get_data_dir() / "config.json"
        ).read_text()
    )
    assert "fixture-private-key" not in json.dumps(saved)
    configuration.llm.provider = "anthropic"
    configuration.llm.api_key = ""
    save_config(configuration)
    assert load_config().llm.api_key == ""
    original_name = _credential_name(configuration.llm)
    configuration.llm.endpoint = "https://example.invalid/v1/chat/completions"
    assert original_name != _credential_name(configuration.llm)


def test_api_never_returns_existing_key(configuration, monkeypatch):
    from app import app

    configuration.llm.api_key = "fixture-sensitive-key"
    monkeypatch.setattr("routes.assistant.current_config", lambda: configuration)
    monkeypatch.setattr("routes.config.load_config", lambda: configuration)
    for url in ("/api/config", "/api/assistant/config"):
        response = app.test_client().get(url)
        assert response.status_code == 200
        assert "fixture-sensitive-key" not in response.get_data(as_text=True)


def test_pdf_download_and_source_registration(configuration, job, tmp_path, monkeypatch):
    import app_state
    from app import app

    db = Database(tmp_path / "download.db")
    monkeypatch.setattr(app_state, "db", db)
    job_id = persist_job(
        db, job, evaluate(configuration.profile, configuration.search_criteria, job)
    )
    result = generate_resume(db, configuration, get_job(db, job_id), tmp_path)
    client = app.test_client()
    for extension, mime in [
        ("pdf", "application/pdf"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("provenance", "application/json"),
    ]:
        response = client.get(f"/api/assistant/resumes/{result['version_id']}/{extension}")
        assert response.status_code == 200 and mime in response.content_type
    pdf = client.get(f"/api/assistant/resumes/{result['version_id']}/pdf")
    assert pdf.data.startswith(b"%PDF")
    assert (
        client.patch(f"/api/assistant/jobs/{job_id}", json={"status": "applied"}).status_code == 200
    )
    assert get_job(db, job_id)["status"] == "applied"
