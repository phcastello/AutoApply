"""Mobility preferences are user data; fictional vacancies exercise the shared policy."""

import copy
import json
from pathlib import Path

import pytest

from config.settings import (
    AppConfig,
    RelocationDestination,
    SearchCriteria,
    UserProfile,
    load_config,
    merge_search_criteria,
    save_config,
)
from core.assisted_matching import evaluate
from core.assisted_workflow import list_jobs, search_jobs
from core.geo_names import countries_in, country
from core.job_discovery import normalize_job
from core.location_rules import geographic_rank, location_eligibility, search_locations
from db.database import Database

DESTINATIONS = json.loads(
    (Path(__file__).parent / "fixtures/mobility_destinations.json").read_text(encoding="utf-8")
)


@pytest.fixture
def profile():
    return UserProfile(
        first_name="Pessoa",
        last_name="Fictícia",
        email="pessoa@example.invalid",
        phone="",
        city="Cidade Exemplo",
        state="",
        country="Brasil",
        bio="",
        career_entries=[
            dict(
                id="evidence",
                category="experience",
                title="Software Engineer",
                text="Python SQL Docker API development",
                confirmed=True,
            )
        ],
    )


@pytest.fixture
def criteria():
    return SearchCriteria(
        job_titles=["Software"],
        locations=[],
        work_modes=["on-site", "hybrid", "remote"],
        mobility=dict(
            direct_locations=["São Paulo, SP, Brasil", "Guarapuava, PR, Brasil"],
            international_relocation=True,
            domestic_relocation=None,
            destinations=[{k: v for k, v in d.items() if k != "location"} for d in DESTINATIONS],
            relocation_conditions="Avaliar remuneração, custo de vida, contrato e requisitos.",
            remote_enabled=True,
        ),
    )


def vacancy(location="Busan, South Korea", mode="on-site", **kwargs):
    return dict(
        title="Software Engineer",
        company="Fictitious employer",
        description="Python SQL Docker API development",
        location=location,
        work_mode=mode,
        required=[],
        preferred=[],
        salary=None,
        **kwargs,
    )


@pytest.mark.parametrize("destination", DESTINATIONS, ids=[d["country"] for d in DESTINATIONS])
@pytest.mark.parametrize("mode", ["on-site", "hybrid"])
def test_every_selected_country_accepts_any_city_without_city_registration(
    profile, criteria, destination, mode
):
    result = location_eligibility(profile, criteria, vacancy(destination["location"], mode))
    assert result["category"] == "relocation" and result["state"] == "review"
    assert result["country_tier"] == destination["priority"] and result["relocation_required"]
    assert result["immigration"]["state"] == "review"
    assert result["financial"]["code"] == "salary_missing"
    assert criteria.mobility.direct_locations == ["São Paulo, SP, Brasil", "Guarapuava, PR, Brasil"]


@pytest.mark.parametrize("location", ["São Paulo, SP, Brasil", "Guarapuava, PR, Brazil"])
def test_direct_localities_are_separate_from_residence_and_destinations(
    profile, criteria, location
):
    result = location_eligibility(profile, criteria, vacancy(location))
    assert result["category"] == "direct" and result["relocation_required"] is False
    assert result["immigration"]["state"] == "review"
    assert profile.city == "Cidade Exemplo"


@pytest.mark.parametrize("location", ["Paris, France", "Barcelona, Spain", "Wroclaw, Poland"])
def test_unselected_countries_are_outside_without_affecting_professional_fit(
    profile, criteria, location
):
    accepted = evaluate(profile, criteria, vacancy())
    result = evaluate(profile, criteria, vacancy(location))
    assert result["eligibility"]["category"] == "outside"
    assert result["professional_score"] == accepted["professional_score"]
    assert not result["blockers"]


@pytest.mark.parametrize(
    "location,extra,expected",
    [
        ("Remote - Brazil", {}, "remote"),
        ("London", {"remote_countries": ["BR"]}, "remote"),
        ("Remote - US", {}, "relocation"),
        ("Remote - Japan", {}, "relocation"),
        ("Remote", {"remote_worldwide": True}, "remote"),
        ("Remote worldwide", {"remote_countries": ["DE"]}, "relocation"),
        ("Remote - France", {}, "outside"),
        ("Remote", {}, "review"),
        ("Osaka, Japan", {}, "review"),
        (
            "Remote",
            {"remote_countries": ["BR"], "hiring_restriction": "Work authorization required"},
            "review",
        ),
        ("Remote", {"remote_countries": ["BR"], "timezone_restriction": "UTC+9"}, "review"),
        ("Remote worldwide", {"remote_restrictions": "Residents of Germany only"}, "relocation"),
        ("Remote (HQ United States)", {}, "review"),
    ],
)
def test_remote_hiring_scope_and_required_foreign_residence(
    profile, criteria, location, extra, expected
):
    result = location_eligibility(profile, criteria, vacancy(location, "remote", **extra))
    assert result["category"] == expected
    if expected == "relocation":
        assert result["relocation_required"] is True and result["immigration"]["state"] == "review"


def test_reference_location_never_confirms_remote_eligibility(profile, criteria):
    profile.location_is_reference = True
    result = location_eligibility(profile, criteria, vacancy("Remote - Brazil", "remote"))
    assert result["category"] == "review"
    assert any(p["code"] == "residence_unknown" for p in result["pending"])


@pytest.mark.parametrize(
    "location,extra",
    [("Busan", {}), ("Europe", {}), ("São Paulo", {}), ("Munich, Germany", {"country_code": "JP"})],
)
def test_ambiguous_locations_require_review_not_rejection(profile, criteria, location, extra):
    result = location_eligibility(profile, criteria, vacancy(location, **extra))
    assert result["category"] == "review" and result["state"] != "incompatible"


def test_country_only_selected_destination_is_conditional(profile, criteria):
    result = location_eligibility(profile, criteria, vacancy("Germany"))
    assert result["category"] == "relocation"
    assert any(p["code"] == "city_unknown" for p in result["pending"])


def test_personal_destinations_are_not_default_and_other_countries_are_configurable(profile):
    criteria = SearchCriteria(job_titles=[], locations=[])
    assert criteria.mobility.destinations == []
    criteria.mobility.destinations = [RelocationDestination(country="Chile", priority="D")]
    criteria = SearchCriteria.model_validate(criteria.model_dump())
    result = location_eligibility(profile, criteria, vacancy("Valdivia, Chile"))
    assert result["category"] == "relocation" and result["country_tier"] == "D"
    assert not countries_in("San Francisco, CA")
    assert (
        location_eligibility(profile, criteria, vacancy("Remote - Chile", "remote"))["category"]
        == "relocation"
    )


def test_missing_visa_salary_language_and_start_are_specific_pending_items(profile, criteria):
    result = evaluate(profile, criteria, vacancy())
    codes = {p["code"] for p in result["eligibility"]["pending"]}
    assert codes >= {
        "salary_missing",
        "sponsorship_unknown",
        "work_authorization_unknown",
        "language_requirements_unknown",
        "start_date_unknown",
        "cost_of_living",
    }
    assert result["blockers"] == []
    criteria.needs_sponsorship = True
    result = evaluate(profile, criteria, vacancy(visa_sponsorship=False))
    assert result["eligibility"]["immigration"]["state"] == "incompatible"
    assert result["eligibility"]["category"] == "relocation"
    criteria.mobility.work_authorization_countries = ["South Korea"]
    assert location_eligibility(profile, criteria, vacancy())["immigration"]["state"] == "declared"


@pytest.mark.parametrize(
    "salary,state,code",
    [
        (None, "review", "salary_missing"),
        ("EUR 90000", "review", "salary_unstructured"),
        ({"min": 90000, "currency": "USD", "period": "annual"}, "review", "salary_units_differ"),
        ({"min": 90000, "currency": "EUR", "period": "monthly"}, "review", "salary_units_differ"),
        (
            {"min": 90000, "currency": "EUR", "period": "annual"},
            "compatible",
            "salary_meets_target",
        ),
        (
            {"min": 20000, "max": 30000, "currency": "EUR", "period": "annual"},
            "below_target",
            "salary_below_target",
        ),
        (
            {"min": 60000, "max": 90000, "currency": "EUR", "period": "annual"},
            "review",
            "salary_range_crosses_target",
        ),
    ],
)
def test_financial_comparison_needs_comparable_units_and_does_not_exclude(
    profile, criteria, salary, state, code
):
    criteria.mobility.salary_min = 80000
    criteria.mobility.salary_currency = "EUR"
    criteria.mobility.salary_period = "annual"
    job = vacancy("Munich, Germany")
    job["salary"] = salary
    result = location_eligibility(profile, criteria, job)
    assert result["category"] == "relocation"
    assert result["financial"]["state"] == state and result["financial"]["code"] == code


def test_migration_preserves_existing_lists_and_explicit_clearing():
    old = dict(
        job_titles=[],
        locations=["City A"],
        attendance_cities=["City B"],
        countries=["Germany"],
        willing_to_relocate=True,
        remote_only=True,
    )
    criteria = SearchCriteria(**old)
    assert (
        criteria.locations == old["locations"]
        and criteria.attendance_cities == old["attendance_cities"]
    )
    assert criteria.mobility.direct_locations == ["City B", "City A"]
    assert criteria.mobility.destinations[0].country == "Germany"
    assert criteria.mobility.international_relocation and criteria.mobility.remote_enabled
    current = criteria.model_dump()
    merged = merge_search_criteria(
        current, dict(mobility=dict(direct_locations=[], destinations=[]))
    )
    assert SearchCriteria(**merged).mobility.direct_locations == []
    assert merged["locations"] == [] and merged["countries"] == []
    legacy = merge_search_criteria(current, dict(locations=["Other City"]))
    assert SearchCriteria(**legacy).mobility.direct_locations == ["Other City"]


def test_priorities_change_ranking_without_changing_fit_or_excluding_selected_countries(
    profile, criteria
):
    germany = evaluate(profile, criteria, vacancy("Munich, Germany"))
    portugal = evaluate(profile, criteria, vacancy("Porto, Portugal"))
    assert germany["score"] == portugal["score"]
    assert geographic_rank(germany) > geographic_rank(portugal)
    next(d for d in criteria.mobility.destinations if d.country == "Portugal").priority = "S"
    next(d for d in criteria.mobility.destinations if d.country == "Alemanha").priority = "D"
    assert geographic_rank(
        evaluate(profile, criteria, vacancy("Porto, Portugal"))
    ) > geographic_rank(evaluate(profile, criteria, vacancy("Munich, Germany")))
    assert {"Alemanha", "Japão", "Coreia do Sul", "Portugal"} <= set(search_locations(criteria))


@pytest.mark.parametrize("engine", ["linkedin", "indeed"])
def test_legacy_searchers_include_country_wide_destinations(criteria, monkeypatch, engine):
    from bot.search.indeed import IndeedSearcher
    from bot.search.linkedin import LinkedInSearcher

    searcher = LinkedInSearcher() if engine == "linkedin" else IndeedSearcher()
    queried = []
    monkeypatch.setattr(
        searcher,
        "_search_page",
        lambda page, title, location, *args: queried.append(location) or iter([]),
    )
    list(searcher.search(criteria, page=object()))
    assert {"Alemanha", "Japão", "Coreia do Sul", "Portugal", "Remote"} <= set(queried)
    assert not any("Busan" in q for q in queried)


def test_duplicate_country_alias_migration_does_not_lose_legacy_values():
    data = dict(job_titles=[], locations=["Old City"], countries=["Germany", "Japan", "Alemanha"])
    result = SearchCriteria(**data)
    assert result.countries == data["countries"]
    assert [d.country for d in result.mobility.destinations] == ["Germany", "Japan"]


def test_state_codes_and_mixed_workplace_labels_remain_ambiguous(profile, criteria):
    assert not countries_in("Dover, DE")
    assert location_eligibility(profile, criteria, vacancy("Dover, DE"))["category"] == "review"
    job = normalize_job(
        "greenhouse",
        "fictional",
        dict(
            id="mixed",
            title="Software Engineer",
            location=dict(name="Remote / Hybrid - Brazil"),
            content="Python SQL",
            absolute_url="https://boards.greenhouse.io/fictional/jobs/mixed",
        ),
    )
    assert job["work_mode"] is None
    assert location_eligibility(profile, criteria, job)["category"] == "review"


def test_explicit_us_residence_words_are_not_ordinary_origin(profile, criteria):
    job = vacancy("Remote", "remote")
    job["description"] = "US residents only."
    assert location_eligibility(profile, criteria, job)["category"] == "relocation"


@pytest.mark.parametrize(
    "interval,period",
    [
        ("per-year-salary", "annual"),
        ("per-month-salary", "monthly"),
        ("per-hour-wage", "hourly"),
        ("one-time", None),
    ],
)
def test_ats_salary_units_and_country_metadata_are_preserved(interval, period):
    job = normalize_job(
        "lever",
        "fictional",
        dict(
            id="salary",
            text="Software Engineer",
            categories=dict(location="Busan"),
            country="KR",
            workplaceType="on-site",
            descriptionPlain="Python SQL",
            hostedUrl="https://jobs.lever.co/fictional/salary",
            salaryRange=dict(min=80000, max=90000, currency="EUR", interval=interval),
        ),
    )
    assert job["country"] == "KR" and job["work_mode"] == "on-site"
    assert job["salary"] == dict(
        min=80000, max=90000, currency="EUR", period=period, source_interval=interval
    )


def test_greenhouse_regional_salary_bands_remain_reviewable(profile, criteria):
    bands = [
        dict(min_cents=8000000, max_cents=9000000, currency_type="USD", title="Example region")
    ]
    job = normalize_job(
        "greenhouse",
        "fictional",
        dict(
            id="salary",
            title="Software Engineer",
            location=dict(name="Busan, South Korea"),
            content="Python SQL",
            work_mode="on-site",
            absolute_url="https://boards.greenhouse.io/fictional/jobs/salary",
            pay_input_ranges=bands,
        ),
    )
    assert job["salary_ranges"] == bands
    result = location_eligibility(profile, criteria, job)
    assert (
        result["financial"]["code"] == "salary_context_unknown"
        and result["category"] == "relocation"
    )


def test_unknown_language_and_dates_do_not_invent_mismatch(profile, criteria):
    from config.settings import CareerEntry

    profile.career_entries.append(
        CareerEntry(
            id="language",
            category="language",
            title="Português",
            text="Português nativo",
            confirmed=True,
        )
    )
    job = vacancy()
    job["description"] += " English fluency required."
    criteria.mobility.available_from = "2027-01-01"
    job["start_date"] = "2026-12-01"
    result = evaluate(profile, criteria, job)
    assert not result["blockers"]
    assert any("Inglês" in p for p in result["unknowns"])
    assert any(p["code"] == "start_date_conflict" for p in result["eligibility"]["pending"])
    job["start_date"] = "Flexible"
    assert any(
        p["code"] == "start_date_ambiguous"
        for p in location_eligibility(profile, criteria, job)["pending"]
    )


@pytest.mark.parametrize(
    "description,scope,expected",
    [
        ("HQ in Germany. Open to residents of Brazil.", {}, "remote"),
        ("Must reside in Germany.", {"remote_countries": ["BR"]}, "review"),
        ("Remote worldwide. Not hiring in Brazil.", {}, "relocation"),
        ("Not remote worldwide.", {}, "review"),
        ("Remote worldwide.", {"remote_excluded_countries": ["BR"]}, "relocation"),
    ],
)
def test_remote_scope_never_converts_hq_or_negative_clauses_to_permission(
    profile, criteria, description, scope, expected
):
    job = vacancy("Remote", "remote", **scope)
    job["description"] = description
    assert location_eligibility(profile, criteria, job)["category"] == expected


@pytest.mark.parametrize("route", ["/api/assistant/config", "/api/config"])
def test_search_ranks_before_limit_and_preference_changes_reevaluate_history(
    profile, criteria, tmp_path, monkeypatch, route
):
    import app_state
    from app import app

    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("config.settings._check_keyring", lambda: False)
    db = Database(tmp_path / "mobility.db")
    monkeypatch.setattr(app_state, "db", db)
    cfg = AppConfig(
        profile=profile, search_criteria=criteria, bot=dict(min_match_score=0, apply_mode="watch")
    )
    save_config(cfg)
    locations = [
        "Busan, South Korea",
        "Munich, Germany",
        "Osaka, Japan",
        "Porto, Portugal",
        "Paris, France",
    ]
    jobs = [
        normalize_job(
            "greenhouse",
            "fixture",
            dict(
                id=i + 1,
                title="Software Engineer",
                location={"name": loc},
                content="Python SQL Docker API development",
                work_mode="on-site",
                absolute_url=f"https://boards.greenhouse.io/fixture/jobs/{i + 1}",
            ),
        )
        for i, loc in enumerate(locations)
    ]
    monkeypatch.setattr("core.assisted_workflow.discover", lambda c: (copy.deepcopy(jobs), []))
    monkeypatch.setattr(
        "core.assisted_workflow.verify_url",
        lambda job: dict(url_status="verified", url_message="fixture"),
    )
    result = search_jobs(db, cfg)
    assert result["received"] == result["matching"] == 5
    saved = list_jobs(db)
    assert len(saved) == 5
    assert sum(j["match"]["eligibility"]["category"] == "relocation" for j in saved) == 4
    first_id = next(j["id"] for j in saved if "Busan" in j["location"])
    db.update_status(first_id, "selected")
    with db._connect() as conn:
        before = conn.execute(
            "SELECT discovered_at FROM discovered_jobs WHERE application_id=?", (first_id,)
        ).fetchone()[0]
    destinations = [
        d.model_dump()
        for d in cfg.search_criteria.mobility.destinations
        if country(d.country) != "coreia do sul"
    ]
    response = app.test_client().put(
        route, json=dict(search_criteria=dict(mobility=dict(destinations=destinations)))
    )
    assert response.status_code == 200
    history = list_jobs(db)
    same = next(j for j in history if j["id"] == first_id)
    assert same["status"] == "selected" and same["match"]["eligibility"]["category"] == "outside"
    with db._connect() as conn:
        assert (
            conn.execute(
                "SELECT discovered_at FROM discovered_jobs WHERE application_id=?", (first_id,)
            ).fetchone()[0]
            == before
        )
    assert load_config().bot.apply_mode == "watch"
    cfg.search_criteria.max_results = 2
    limited = search_jobs(Database(tmp_path / "limited.db"), cfg)
    assert limited["matching"] == 5 and len(limited["job_ids"]) == 2
