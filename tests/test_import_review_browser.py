"""A review must change actual form fields, never merely produce valid JSON."""

import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from config.settings import AppConfig, load_config, save_config

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
        assert len(profile.career_entries[0].activities) == 1
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
