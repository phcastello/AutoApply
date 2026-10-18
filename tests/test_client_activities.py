"""Client evidence belongs to its contractor, including during reviewed reimports."""

import copy
import json
from pathlib import Path

import pytest

from config.settings import SearchCriteria, UserProfile
from core.assisted_matching import (
    entry_text,
    evaluate,
    professional_months,
    select_activity_evidence,
    select_entries,
    use_ai_selection,
)
from core.assisted_workflow import build_markdown
from core.profile_import import draft_profile
from core.profile_schema import reconcile_import

FIXTURE = Path(__file__).parent / "fixtures" / "client_activities.md"


def facts(text=None):
    return draft_profile(text or FIXTURE.read_text(encoding="utf-8"), "clients.md")["entries"]


def profile(entries):
    return UserProfile(
        first_name="Pessoa",
        last_name="Fictícia",
        email="test@example.invalid",
        phone="",
        city="",
        state="",
        bio="",
        career_entries=entries,
    )


@pytest.mark.parametrize("heading_level", [None, 3, 4])
def test_two_relationships_with_grouped_clients_and_approximate_dates(heading_level):
    text = FIXTURE.read_text(encoding="utf-8")
    if heading_level:
        heading = "#" * heading_level
        text = text.replace(
            "- Atuação com Grupo Horizonte: iniciada aproximadamente em maio de 2025. ",
            heading
            + " Atuação com Grupo Horizonte\n- Início: aproximadamente em maio de 2025.\n- Descrição: ",
        )
        text = text.replace(
            "- Atuação com Rede Boreal: iniciada no começo de 2026, aproximadamente entre o fim de janeiro e o início de fevereiro. ",
            heading
            + " Atuação com Rede Boreal\n- Início: começo de 2026 (janeiro/fevereiro).\n- Descrição: ",
        )
    entries = facts(text)
    assert len(entries) == 2 and all(e["category"] == "experience" for e in entries)
    first, second = entries
    assert first["start_date"] == "2025-02" and second["start_date"] == "2026-08"
    assert [a["title"] for a in first["activities"]][:2] == ["Grupo Horizonte", "Rede Boreal"]
    assert len(first["activities"]) == 3 and len(second["activities"]) == 1
    assert "aproxim" in first["activities"][0]["start_date"]
    assert "2026" in first["activities"][1]["start_date"]
    poc = first["activities"][2]
    assert poc["start_date"] == "2025-02" and "julho" in poc["end_date"]
    assert "individual" in poc["text"] and "sem contrato comercial" in poc["text"]
    assert poc["technologies"] == ["YOLO/PyTorch", "OpenCV", "FastAPI"]
    assert second["activities"][0]["title"] == "Associação Estrela"
    assert second["activities"][0]["start_date"] == "2026-09"
    assert not any("atuacao com" in n for n in first["date_notes"])
    assert professional_months(entries) == professional_months(entries[:1])


def test_local_matching_ai_selection_and_resume_keep_activity_evidence_private(monkeypatch):
    entries = facts()
    for e in entries:
        e["confirmed"] = True
        e["date_notes"].append("PRIVATE DATE NOTE")
        for a in e["activities"]:
            a["source_excerpt"] = "PRIVATE SOURCE"
            a["date_notes"] = ["PRIVATE ACTIVITY NOTE"]
    p = profile(entries)
    job = dict(
        title="Computer vision",
        description="FastAPI OpenCV YOLO PyTorch HITL",
        company="Example",
        required=["FastAPI", "OpenCV"],
        preferred=[],
    )
    assert "HITL" in entry_text(entries[0])
    assert select_entries(p, job, limit=1)[0]["organization"] == "Consultoria Aurora"
    result = evaluate(p, SearchCriteria(job_titles=[], locations=[]), job)
    assert any("fastapi" in m.lower() for m in result["matches"])
    assert not any("fastapi" in m.lower() for m in result["gaps"])
    captured = []
    monkeypatch.setattr(
        "core.ai_engine.invoke_llm",
        lambda prompt, *a, **k: captured.append(prompt) or json.dumps([entries[0]["id"]]),
    )
    chosen = use_ai_selection(entries, job, None)
    assert "HITL" in captured[0] and "YOLO/PyTorch" in captured[0]
    assert "PRIVATE" not in captured[0] and "source_excerpt" not in captured[0]
    resume = build_markdown(p, chosen, "pt-BR")
    assert resume.count("### Consultoria Aurora") == 1
    assert "Grupo Horizonte" in resume and "Rede Boreal" in resume
    assert (
        "YOLO/PyTorch" in resume
        and "HITL" in resume
        and "sem contrato comercial concluído" in resume
    )
    assert (
        "PRIVATE" not in resume
        and "Não divulgar" not in resume
        and "arquitetura proprietária" not in resume
    )
    assert "aproximadamente" in resume
    tailored = select_activity_evidence(chosen, job)
    assert len(tailored[0]["activities"]) == 1
    assert "PoC" in tailored[0]["activities"][0]["title"]
    assert tailored[0]["id"] == entries[0]["id"]
    assert len(entries[0]["activities"]) == 3
    tailored_resume = build_markdown(p, tailored, "pt-BR")
    assert "Grupo Horizonte" not in tailored_resume and "HITL" in tailored_resume


def test_reimport_proposes_additions_preserves_id_manual_corrections_and_confirmation():
    incoming = facts()
    old = copy.deepcopy(incoming)
    old[0].update(
        id="existing-history-id",
        title="Cargo corrigido manualmente",
        text="Descrição revisada",
        confirmed=True,
        import_key="old-parser-key",
    )
    old[0]["activities"] = [old[0]["activities"][2]]
    old[0]["activities"][0]["title"] = "PoC de visão computacional"
    old[0]["activities"][0]["text"] = "PoC revisada manualmente"
    old[0]["date_notes"].append(
        "atuacao com grupo horizonte: iniciada aproximadamente em maio de 2025"
    )
    snapshot = copy.deepcopy(old)
    new, updates, duplicates = reconcile_import(incoming, old)
    assert old == snapshot and new == [] and duplicates == 1
    assert len(updates) == 1
    proposed = updates[0]["proposed"]
    assert proposed["id"] == old[0]["id"] and proposed["title"] == old[0]["title"]
    assert proposed["text"] == "Descrição revisada" and proposed["confirmed"] is False
    assert proposed["activities"][0]["text"] == "PoC revisada manualmente"
    assert len(proposed["activities"]) == 3 and "atuacao com" not in " ".join(
        proposed["date_notes"]
    )
    assert reconcile_import(incoming, [proposed, old[1]]) == ([], [], 2)


def test_same_employer_new_role_or_period_does_not_merge():
    incoming = facts()
    old = copy.deepcopy(incoming[:1])
    old[0].update(title="Another role", source_document_id="other-document", import_key="other-key")
    assert len(reconcile_import(incoming, old)[0]) == 2
    old[0].update(title=incoming[0]["title"], start_date="2024-01")
    assert len(reconcile_import(incoming, old)[0]) == 2


@pytest.mark.parametrize("ai", [False, True])
def test_generated_pdf_docx_and_provenance_use_relevant_grouped_activities(
    tmp_path, monkeypatch, ai
):
    from docx import Document

    from config.settings import AppConfig
    from core.assisted_workflow import generate_resume, get_job, persist_job
    from core.document_parser import extract_text
    from core.job_discovery import normalize_job
    from db.database import Database

    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("config.settings._check_keyring", lambda: False)
    entries = facts()
    for entry in entries:
        entry["confirmed"] = True
    p = profile(entries)
    cfg = AppConfig(
        profile=p, search_criteria=dict(job_titles=[], locations=[], resume_language="pt-BR")
    )
    db = Database(tmp_path / "test.db")
    job = normalize_job(
        "greenhouse",
        "fixture",
        dict(
            id=99,
            title="Computer vision",
            location={"name": "Remote"},
            absolute_url="https://boards.greenhouse.io/fixture/jobs/99",
            content="<h3>Requirements</h3><p>YOLO PyTorch OpenCV FastAPI HITL</p>",
        ),
        "Empresa Fictícia",
    )
    job_id = persist_job(db, job, evaluate(p, cfg.search_criteria, job))
    monkeypatch.setattr(
        "core.assisted_workflow.use_ai_selection", lambda available, *a: [available[0]]
    )
    result = generate_resume(db, cfg, get_job(db, job_id), tmp_path, use_ai=ai)
    assert result["validation"]["valid"]
    version = db.get_resume_version(result["version_id"])
    folder = Path(version["resume_pdf_path"]).parent
    pdf = extract_text(Path(version["resume_pdf_path"]))
    word = "\n".join(p.text for p in Document(folder / "resume.docx").paragraphs)
    for text in (pdf, word):
        assert "HITL" in text and "YOLO/PyTorch" in text and "sem contrato comercial" in text
        assert text.count("Consultoria Aurora") == 1
        assert "Grupo Horizonte" not in text and "Rede Boreal" not in text
        assert "Não divulgar" not in text and "arquitetura proprietária" not in text
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))[
        "selected_facts"
    ]
    first = next(e for e in provenance if e["organization"] == "Consultoria Aurora")
    assert len(first["activities"]) == 1 and first["id"] == entries[0]["id"]
    assert len(cfg.profile.career_entries[0].activities) == 3
