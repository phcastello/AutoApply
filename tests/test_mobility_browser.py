"""Configure and revise mobility in Chromium against isolated local data."""

import json
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from config.settings import AppConfig, load_config, save_config
from core.assisted_matching import evaluate
from core.assisted_workflow import persist_job
from core.job_discovery import normalize_job
from db.database import Database

DESTINATIONS = json.loads(
    (Path(__file__).parent / "fixtures/mobility_destinations.json").read_text(encoding="utf-8")
)


@pytest.fixture
def application(tmp_path, monkeypatch):
    import app_state
    from app import app

    monkeypatch.setattr(app_state.socketio.server.eio, "allow_upgrades", False)

    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("config.settings._check_keyring", lambda: False)
    db = Database(tmp_path / "browser.db")
    monkeypatch.setattr(app_state, "db", db)
    cfg = AppConfig(
        profile=dict(
            first_name="Pessoa",
            last_name="Fictícia",
            email="pessoa@example.invalid",
            phone="",
            city="Cidade de residência",
            state="",
            country="Brasil",
            bio="",
        ),
        search_criteria=dict(
            job_titles=[], locations=["São Paulo, SP, Brasil", "Guarapuava, PR, Brasil"]
        ),
        bot=dict(min_match_score=0, apply_mode="watch"),
    )
    save_config(cfg)
    for i, (location, mode) in enumerate(
        [
            ("Munich, Germany", "on-site"),
            ("Busan, South Korea", "hybrid"),
            ("Osaka, Japan", "on-site"),
            ("Porto, Portugal", "on-site"),
            ("Paris, France", "on-site"),
            ("Remote - Brazil", "remote"),
            ("Remote - US", "remote"),
            ("São Paulo, SP, Brasil", "hybrid"),
            ("Remote", "remote"),
        ]
    ):
        job = normalize_job(
            "greenhouse",
            "fixture",
            dict(
                id=i + 1,
                title="Software Engineer",
                location=dict(name=location),
                work_mode=mode,
                content="Python SQL Docker API development",
                absolute_url=f"https://boards.greenhouse.io/fixture/jobs/{i + 1}",
            ),
            "Empresa Fictícia",
        )
        persist_job(db, job, evaluate(cfg.profile, cfg.search_criteria, job))
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def test_mobility_configuration_persistence_badges_filtering_and_sorting(application):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=1100))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(application)
        page.locator('[data-screen="preferences"]').click()
        expect(page.locator("#assistant-mobility")).to_be_visible()
        expect(page.locator("#assistant-cities")).to_contain_text("Guarapuava")
        expect(page.locator("[data-destination-country]")).to_have_count(0)
        page.locator("#mobility-international_relocation").select_option("true")
        page.locator("#mobility-domestic_relocation").select_option("")
        for d in DESTINATIONS:
            page.locator("#mobility-new-country").fill(d["country"])
            page.locator("#mobility-new-priority").select_option(d["priority"])
            page.locator("#mobility-add-country").click()
        page.locator("#mobility-new-country").fill("Chile")
        page.locator("#mobility-new-priority").select_option("D")
        page.locator("#mobility-add-country").click()
        expect(page.locator("[data-destination-country]")).to_have_count(22)
        page.locator('[data-remove-destination="21"]').click()
        page.locator("#mobility-relocation_conditions").fill(
            "Oferta deve compensar custo de vida, contrato e mudança."
        )
        page.locator("#mobility-available_from").fill("2027-02-01")
        page.locator("#mobility-availability_notes").fill(
            "Data negociável conforme condições da oferta."
        )
        expect(page.locator("#assistant-location-summary")).to_contain_text(
            "Tier S: Países Baixos, Irlanda, Alemanha, Japão"
        )
        expect(page.locator("#assistant-location-summary")).to_contain_text("qualquer cidade")
        expect(page.locator("#assistant-location-summary")).not_to_contain_text("França")
        page.locator("#assistant-save").click()
        expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
        cfg = load_config()
        assert len(cfg.search_criteria.mobility.destinations) == 21
        assert cfg.search_criteria.mobility.available_from == "2027-02-01"
        assert cfg.profile.city == "Cidade de residência" and cfg.bot.apply_mode == "watch"
        page.reload()
        page.locator('[data-screen="preferences"]').click()
        expect(page.locator("[data-destination-country]")).to_have_count(21)
        expect(page.locator("#mobility-current-location")).to_contain_text("Cidade de residência")
        page.locator('[data-screen="assistant"]').click()
        expect(page.locator(".assistant-job")).to_have_count(9)
        expect(page.locator('[data-geography="relocation"]')).to_have_count(5)
        expect(page.locator('[data-geography="remote"]')).to_have_count(1)
        expect(page.locator('[data-geography="direct"]')).to_have_count(1)
        expect(page.locator('[data-geography="outside"]')).to_have_count(1)
        expect(page.locator('[data-geography="review"]')).to_have_count(1)
        page.locator("#assistant-geography-filter").select_option("relocation")
        expect(page.locator(".assistant-job")).to_have_count(5)
        page.locator("#assistant-sort").select_option("country")
        expect(page.locator(".assistant-job").first).to_contain_text("Tier S")
        page.locator("#assistant-geography-filter").select_option("")
        page.locator("#assistant-sort").select_option("relocation")
        assert page.locator(".assistant-job").first.get_attribute("data-geography") in (
            "direct",
            "remote",
        )
        # Reprioritize an existing destination and reevaluate the same historical rows.
        ids = page.locator(".assistant-job").evaluate_all(
            "(nodes)=>nodes.map(n=>n.dataset.jobId).sort()"
        )
        page.locator('[data-screen="preferences"]').click()
        page.locator('[data-destination-priority="20"]').select_option("S")
        page.locator("#assistant-save").click()
        expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
        page.locator('[data-screen="assistant"]').click()
        assert (
            page.locator(".assistant-job").evaluate_all(
                "(nodes)=>nodes.map(n=>n.dataset.jobId).sort()"
            )
            == ids
        )
        page.locator("#assistant-sort").select_option("professional")
        expect(page.locator(".assistant-job")).to_have_count(9)
        page.set_viewport_size(dict(width=390, height=844))
        page.locator('[data-screen="preferences"]').click()
        assert page.locator("#assistant-mobility").evaluate(
            "(node)=>node.scrollWidth<=node.clientWidth+2"
        )
        assert not errors
        browser.close()
