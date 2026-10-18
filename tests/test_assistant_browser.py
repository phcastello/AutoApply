"""Actual Chromium/Flask smoke test with private temporary data and fake AI/ATS."""

import threading
from unittest.mock import Mock

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from config.settings import AppConfig, load_config, save_config
from core.job_discovery import normalize_job
from db.database import Database


def test_guided_workflow_in_chromium(tmp_path, monkeypatch):
    import keyring

    import app_state
    from app import app

    monkeypatch.setenv("AUTOAPPLY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app_state, "db", Database(tmp_path / "browser.db"))
    monkeypatch.setattr("config.settings._check_keyring", lambda: True)
    vault = {}
    monkeypatch.setattr(keyring, "get_password", lambda service, name: vault.get(name))
    monkeypatch.setattr(
        keyring, "set_password", lambda service, name, value: vault.update({name: value})
    )
    config = AppConfig(
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
    save_config(config)
    fake_response = Mock(status_code=200, headers={})
    fake_response.json.return_value = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}],
    }
    post = Mock(return_value=fake_response)
    monkeypatch.setattr("core.ai_engine.requests.post", post)
    fixture_job = normalize_job(
        "greenhouse",
        "fixture",
        dict(
            id=123,
            title="Software Engineer",
            location={"name": "Remote - Brazil"},
            absolute_url="https://boards.greenhouse.io/fixture/jobs/123",
            content="Requirements\nPython Flask SQLite. Remote open to residents of Brazil.",
        ),
        "Empresa de teste",
    )
    monkeypatch.setattr("core.assisted_workflow.discover", lambda criteria: ([fixture_job], []))
    monkeypatch.setattr(
        "core.assisted_workflow.verify_url",
        lambda job: dict(
            url_status="verified", url_message="Fixture de teste", availability="listed"
        ),
    )
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#contact-first_name")).to_be_visible()
            assert page.locator("#navbar a[role=tab]").count() == 4
            page.locator('[data-screen="configuration"]').click()
            page.locator("#ai-provider").select_option("openai")
            page.locator("#ai-model").fill("gpt-6.1-sol")
            page.locator("#ai-api_key").fill("fixture-only-secret")
            page.locator("#assistant-ai-test").click()
            expect(page.locator("#assistant-test-status")).to_contain_text(
                "O provedor gerou", timeout=10000
            )
            assert load_config().llm.provider == ""  # Test drafts don't require or save a profile.
            assert post.call_args.kwargs["json"]["model"] == "gpt-6.1-sol"
            page.locator("#assistant-save").click()
            expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
            assert "fixture-only-secret" not in (tmp_path / "config.json").read_text()
            page.locator('[data-screen="my-profile"]').click()
            page.locator("#contact-first_name").fill("Candidata")
            page.locator("#contact-last_name").fill("Teste")
            page.locator("#contact-email").fill("teste@example.invalid")
            # Import a real TXT through the UI and review its local structured draft.
            page.get_by_text("Importar ou recuperar informações", exact=True).click()
            page.locator("#assistant-import").set_input_files(
                {
                    "name": "perfil.txt",
                    "mimeType": "text/plain",
                    "buffer": "Projetos\n\nDesenvolvi API Python com Flask e SQLite.".encode(),
                }
            )
            expect(page.locator("#assistant-import-review")).to_be_visible()
            expect(page.locator("#assistant-facts textarea")).to_have_count(0)
            page.locator("#assistant-import-apply").click()
            expect(page.locator("#assistant-facts textarea")).to_have_count(1)
            expect(page.locator("#assistant-facts textarea")).to_contain_text(
                "Desenvolvi API Python"
            )
            page.locator("#assistant-confirm-all").click()
            page.locator('[data-screen="preferences"]').click()
            page.locator('#assistant-work-modes input[value="remote"]').check()
            page.locator('#assistant-work-modes input[value="on-site"]').check()
            page.locator("#city-name").fill("São Paulo")
            page.locator("#city-state").fill("SP")
            page.locator("#assistant-add-city").click()
            expect(page.locator("#assistant-location-summary")).to_contain_text("São Paulo")
            page.locator('[data-screen="my-profile"]').click()
            expect(page.locator("#contact-first_name")).to_have_value("Candidata")
            page.locator("#assistant-save").click()
            expect(page.locator("#assistant-save-status")).to_contain_text("salvas")
            assert load_config().profile.career_entries[0].confirmed
            page.locator('[data-screen="assistant"]').click()
            page.locator("#assistant-search").click()
            expect(page.locator(".assistant-job")).to_have_count(1, timeout=15000)
            page.locator("[data-generate]").click()
            expect(page.locator("[data-preview]")).to_have_count(1, timeout=15000)
            page.locator("[data-preview]").click()
            expect(page.locator("#assistant-preview")).to_be_visible()
            page.locator("#assistant-close-preview").click()
            with page.expect_download() as info:
                page.locator('[data-download][data-format="pdf"]').click()
            assert info.value.suggested_filename.endswith(".pdf")
            # Inspect the specific opportunity link without submitting an application.
            assert (
                page.get_by_role("link", name="Abrir vaga", exact=True)
                .get_attribute("href")
                .endswith("/123")
            )
            page.locator('[data-screen="configuration"]').click()
            expect(page.locator('[data-screen="configuration"]')).to_have_attribute(
                "aria-selected", "true"
            )
            expect(page.locator("#assistant-title")).to_have_text("Configurações")
            page.screenshot(
                path=str(tmp_path / "settings.png"), full_page=True, animations="disabled"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(
                path=str(tmp_path / "settings-mobile.png"), full_page=True, animations="disabled"
            )
            assert not errors
            browser.close()
    finally:
        server.shutdown()
