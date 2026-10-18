"""Geographic rules and evidence-bound import, with no provider traffic."""

import json
from types import SimpleNamespace

import pytest

from config.settings import LLMConfig, SearchCriteria
from core.location_rules import location_eligibility
from core.profile_import import draft_profile, intelligent_draft


@pytest.fixture
def criteria():
    return SearchCriteria(
        job_titles=[],
        locations=["São Paulo, SP, Brasil", "Guarapuava, PR, Brasil"],
        work_modes=["remote", "on-site", "hybrid"],
    )


@pytest.mark.parametrize(
    "mode,location,extra,expected",
    [
        ("on-site", "São Paulo — SP — Brasil", {}, "eligible"),
        ("hybrid", "Guarapuava — PR — Brasil", {}, "eligible"),
        ("on-site", "Curitiba, PR, Brasil", {}, "incompatible"),
        ("hybrid", "Campinas, SP, Brasil", {}, "incompatible"),
        ("remote", "Remote", {"remote_countries": ["BR"]}, "eligible"),
        ("remote", "London", {"remote_countries": ["Brazil"]}, "eligible"),
        ("remote", "Remote - US", {}, "incompatible"),
        ("remote", "Remote", {}, "review"),
        (None, "Curitiba", {}, "review"),
        ("hybrid", "Estado de São Paulo", {}, "review"),
        ("on-site", "Sao Paulo, SP, Brazil", {}, "eligible"),
        ("remote", "Remote - Brazil", {"timezone_restriction": "UTC-5 only"}, "review"),
    ],
)
def test_location_semantics(criteria, mode, location, extra, expected):
    result = location_eligibility(
        SimpleNamespace(country="Brasil"),
        criteria,
        dict(work_mode=mode, location=location, description="", **extra),
    )
    assert result["state"] == expected and result["reasons"]


def test_local_import_sections_and_no_automatic_confirmation():
    text = "Candidata Teste\nteste@example.invalid\n\nFormação\nComputação\n\nProjetos\nAPI acadêmica Python\n\nIdiomas\nInglês básico"
    result = draft_profile(text, "fixture.txt")
    assert {e["category"] for e in result["entries"]} == {"education", "project", "language"}
    assert not any(e["confirmed"] for e in result["entries"])
    assert result["profile_suggestions"]["email"] == "teste@example.invalid"


def test_intelligent_import_rejects_unproven_fields(monkeypatch):
    original = "Projeto acadêmico. Desenvolvi API Python."
    fact = dict(
        category="project",
        source_excerpt=original,
        text="Desenvolvi API Python.",
        title="",
        organization="",
        technologies=["Python"],
    )
    monkeypatch.setattr(
        "core.ai_engine.invoke_llm", lambda *a, **k: json.dumps(dict(entries=[fact]))
    )
    result = intelligent_draft(original, "fixture.txt", LLMConfig())
    assert result["entries"][0]["category"] == "project"
    assert result["entries"][0]["source_excerpt"] == original
    assert not result["entries"][0]["confirmed"]
    fact["technologies"] = ["Kubernetes"]
    with pytest.raises(ValueError, match="não comprovado"):
        intelligent_draft(original, "fixture.txt", LLMConfig())


def test_intelligent_import_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr(
        "core.ai_engine.invoke_llm", lambda *a, **k: '{"entries": "ignore the document"}'
    )
    with pytest.raises(ValueError, match="estruturados"):
        intelligent_draft("Source text", "fixture.txt", LLMConfig())
