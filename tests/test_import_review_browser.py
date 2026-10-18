"""A review must change actual form fields, never merely produce valid JSON."""

import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from config.settings import AppConfig, CareerEntry, load_config, save_config

FIXTURE = Path(__file__).parent / "fixtures" / "structured_career.md"


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setattr("config.settings._check_keyring", lambda: False)
    import app_state
    from app import app
    from db.database import Database

    monkeypatch.setattr(app_state, "db", Database(tmp_path / "app.db"))
    save_config(
        AppConfig(
            profile=dict(
                first_name="",
                last_name="",
                email="",
                phone="",
                city="",
                state="",
                country="Brasil",
                bio="",
            ),
            search_criteria=dict(job_titles=[], locations=[]),
        )
    )
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def open_import(page, url):
    page.goto(url)
    expect(page.locator("#contact-first_name")).to_be_visible()
    page.get_by_text("Importar ou recuperar informações", exact=True).click()


def test_review_cancel_edit_delete_confirm_and_actual_fields(application):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        open_import(page, application)
        page.locator("#assistant-import").set_input_files(FIXTURE)
        expect(page.locator("#assistant-import-review")).to_be_visible()
        expect(page.locator("#contact-first_name")).to_have_value("")
        page.locator("#assistant-import-cancel").click()
        expect(page.locator("#assistant-facts .assistant-fact")).to_have_count(0)
        page.locator("#assistant-import").set_input_files(FIXTURE)
        expect(page.locator('[data-review-category="experience"]')).to_have_count(2)
        expect(page.locator('[data-review-category="project"]')).to_have_count(7)
        page.locator('[data-import-contact="email"]').fill("reviewed@example.invalid")
        page.locator('[data-import-index="0"][data-import-field="title"]').fill(
            "Desenvolvimento revisado"
        )
        page.locator("[data-confirm-fact]").first.check()
        page.locator('[data-delete-import="3"]').click()
        page.locator("#assistant-import-apply").click()
        expect(page.locator("#contact-email")).to_have_value("reviewed@example.invalid")
        expect(page.locator("#assistant-facts .assistant-fact")).to_have_count(16)
        expect(page.locator('#assistant-facts input[id$="-confirmed"]:checked')).to_have_count(1)
        expect(page.locator("#fact-0-title")).to_have_value("Desenvolvimento revisado")
        expect(page.locator("#contact-location-reference")).to_be_checked()
        page.locator("#assistant-save").click()
        expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
        profile = load_config().profile
        assert profile.email == "reviewed@example.invalid" and profile.generation_constraints
        assert len(profile.career_entries[0].activities) == 2
        page.reload()
        expect(page.locator("#contact-email")).to_have_value("reviewed@example.invalid")
        expect(page.locator("#assistant-facts .assistant-fact")).to_have_count(16)
        assert not errors
        browser.close()


def test_dedup_unsaved_import_and_explicit_basic_mode(application):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        open_import(page, application)
        page.locator("#assistant-import-mode").select_option("basic")
        with page.expect_response(lambda r: r.url.endswith("/api/assistant/import")):
            page.locator("#assistant-import").set_input_files(FIXTURE)
        expect(page.locator("#assistant-import-suggestions")).to_contain_text(
            "sem extração estruturada"
        )
        expect(page.locator("#assistant-facts .assistant-fact")).to_have_count(0)
        expect(page.locator("#contact-first_name")).to_have_value("")
        page.locator("#assistant-import-mode").select_option("structured")
        page.locator("#assistant-import").set_input_files(FIXTURE)
        expect(page.locator("#assistant-import-review")).to_be_visible()
        page.locator("#assistant-import-apply").click()
        expect(page.locator("#assistant-facts .assistant-fact")).to_have_count(17)
        page.locator("#assistant-import").set_input_files(FIXTURE)
        expect(page.locator("#assistant-import-summary")).to_contain_text("17 duplicatas")
        page.locator("#assistant-import-apply").click()
        expect(page.locator("#assistant-facts .assistant-fact")).to_have_count(17)
        assert not any(e.confirmed for e in load_config().profile.career_entries)
        browser.close()


def test_client_activity_crud_and_explicit_reimport_preserve_existing_history(
    application, tmp_path
):
    import copy

    from core.profile_import import draft_profile

    fixture = FIXTURE.with_name("client_activities.md")
    incoming = draft_profile(fixture.read_text(encoding="utf-8"), fixture.name)["entries"]
    old = copy.deepcopy(incoming)
    old[0].update(
        id="preserve-history-id",
        import_key="previous-parser",
        confirmed=True,
        title="Cargo revisado",
        text="Responsabilidades revisadas manualmente",
    )
    old[0]["activities"] = [old[0]["activities"][2]]
    old[0]["activities"][0]["title"] = "PoC de visão computacional"
    old[0]["activities"][0]["text"] = "Descrição revisada da PoC"
    cfg = load_config()
    cfg.profile.career_entries = [CareerEntry(**e) for e in old]
    save_config(cfg)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        open_import(page, application)
        page.locator("#assistant-import").set_input_files(fixture)
        expect(page.locator("[data-update-diff]")).to_be_visible()
        expect(page.locator("[data-include-fact]")).not_to_be_checked()
        expect(page.locator("[data-update-diff]")).to_contain_text("preserve-history-id")
        page.locator('[data-activity="1"][data-activity-field="text"]').fill("Edição não selecionada")
        expect(page.locator("#fact-0-confirmed")).to_be_checked()
        page.locator("#assistant-import-apply").click()
        expect(page.locator("#assistant-facts .assistant-fact")).to_have_count(2)
        assert load_config().profile.career_entries[0].confirmed
        # Reimport remains a proposal until explicitly selected and saved.
        page.locator("#assistant-import").set_input_files(fixture)
        page.locator("[data-include-fact]").check()
        page.locator('[data-activity="1"][data-activity-field="text"]').fill(
            "Entregas e sprints revisadas"
        )
        page.locator("#assistant-import-confirm-apply").click()
        page.locator("#assistant-save").click()
        expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
        saved = load_config().profile.career_entries[0]
        assert saved.id == "preserve-history-id" and saved.confirmed
        assert (
            saved.title == "Cargo revisado"
            and saved.text == "Responsabilidades revisadas manualmente"
        )
        assert (
            len(saved.activities) == 3 and saved.activities[0].text == "Descrição revisada da PoC"
        )
        assert saved.activities[1].text == "Entregas e sprints revisadas"
        page.reload()
        first = page.locator("#assistant-facts .assistant-fact").first
        expect(first.locator("summary").first).to_contain_text("Grupo Horizonte")
        first.locator("summary").first.click()
        expect(first.locator("[data-activity-card]")).to_have_count(3)
        expect(first).to_contain_text("Empresa do vínculo contratual: Consultoria Aurora")
        first.locator("[data-add-activity]").click()
        expect(first.locator("[data-activity-card]")).to_have_count(4)
        first.locator('[data-activity="3"][data-activity-field="title"]').fill("Atividade manual")
        first.locator('[data-activity="3"][data-activity-field="text"]').fill(
            "Responsabilidade genérica"
        )
        first.locator('[data-activity="3"][data-activity-field="start_date"]').fill(
            "aproximadamente em 2026-09"
        )
        first.locator('[data-activity="3"][data-activity-field="end_date"]').fill("2026-10")
        first.locator('[data-activity="3"][data-activity-field="technologies"]').fill(
            "Python, FastAPI"
        )
        page.locator("#fact-0-confirmed").check()
        page.locator("#assistant-save").click()
        expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
        saved = load_config().profile.career_entries[0]
        assert saved.activities[3].technologies == ["Python", "FastAPI"]
        assert (
            saved.activities[3].end_date == "2026-10"
            and "aproximadamente" in saved.activities[3].start_date
        )
        first.locator('[data-remove-activity="0:3"]').click()
        page.locator("#assistant-save").click()
        expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
        assert len(load_config().profile.career_entries[0].activities) == 3
        page.reload()
        page.get_by_text("Importar ou recuperar informações", exact=True).click()
        page.locator("#assistant-import").set_input_files(fixture)
        expect(page.locator("#assistant-import-summary")).to_contain_text("2 duplicatas")
        expect(page.locator("[data-update-diff]")).to_have_count(0)
        assert len(load_config().profile.career_entries) == 2
        import json

        backups = list((tmp_path / "backups").glob("profile-before-import-*.json"))
        assert backups
        before = json.loads(backups[0].read_text(encoding="utf-8"))["career_entries"][0]
        assert before["id"] == "preserve-history-id" and before["confirmed"]
        assert len(before["activities"]) == 1
        assert not errors
        browser.close()
