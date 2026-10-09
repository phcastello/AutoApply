"""Real ATS/UI validation using an explicitly fictional profile in isolated storage."""

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright
from PyPDF2 import PdfReader


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / ".validation/live"
    folder.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(
        AUTOAPPLY_DATA_DIR=str(folder / ("data-" + uuid.uuid4().hex[:10])), AUTOAPPLY_PORT=str(port)
    )
    log = open(folder / "server.log", "w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(root / "run.py"), "--no-browser"],
        cwd=root,
        env=env,
        stdout=log,
        stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if requests.get(base + "/api/health", timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            if process.poll() is not None:
                raise RuntimeError("Servidor terminou; veja server.log")
            time.sleep(0.5)
        else:
            raise RuntimeError("Servidor não iniciou")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=True, viewport={"width": 1440, "height": 1000}
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base, wait_until="domcontentloaded")
            page.locator("#contact-first_name").wait_for(timeout=20000)
            fixture = json.loads((root / "examples/profile-test.json").read_text(encoding="utf-8"))
            # Use the actual profile editor for contacts and professional entries.
            for key in (
                "first_name",
                "last_name",
                "email",
                "phone_country_code",
                "phone",
                "city",
                "state",
                "country",
            ):
                page.locator("#contact-" + key).fill(fixture["profile"][key])
            for i, entry in enumerate(fixture["profile"]["career_entries"]):
                page.locator("#assistant-add-fact").click()
                page.locator(f"#fact-{i}-category").select_option(entry["category"])
                for key in (
                    "organization",
                    "title",
                    "start_date",
                    "end_date",
                    "text",
                    "proficiency",
                ):
                    if key in entry:
                        page.locator(f"#fact-{i}-{key}").fill(entry[key])
                if entry.get("technologies"):
                    page.locator(f"#fact-{i}-technologies").fill(", ".join(entry["technologies"]))
                page.locator(f"#fact-{i}-confirmed").check()
            for key, value in fixture["search_criteria"].items():
                if key == "resume_language":
                    page.locator("#pref-" + key).select_option(value)
                else:
                    page.locator("#pref-" + key).fill(
                        ", ".join(value) if isinstance(value, list) else str(value)
                    )
            page.locator("#assistant-min-score").fill("0")
            page.locator("#assistant-search").click()
            page.wait_for_function(
                "document.querySelector('#assistant-message').textContent.includes('Busca concluída')",
                timeout=180000,
            )
            page.locator(".assistant-job").first.wait_for()
            job_data = page.evaluate(
                "async()=> (await (await fetch('/api/assistant/jobs')).json()).jobs"
            )
            assert job_data and len(job_data) <= 5
            first = job_data[0]
            page.locator(f'[data-generate="{first["id"]}"]').click()
            page.wait_for_function(
                "document.querySelector('#assistant-message').textContent.includes('Currículo gerado e validado') || document.querySelector('#assistant-message').textContent.includes('Currículo recuperado')",
                timeout=90000,
            )
            card = page.locator(f'[data-job-id="{first["id"]}"]')
            with page.expect_download() as event:
                card.locator('[data-download][data-format="pdf"]').first.click()
            pdf = folder / "resume-test.pdf"
            event.value.save_as(pdf)
            text = "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)
            assert "Fictional Test Candidate" in text and "candidate@example.invalid" in text
            assert "Kubernetes" not in text
            with page.expect_download() as event:
                card.locator('[data-download][data-format="docx"]').first.click()
            event.value.save_as(folder / "resume-test.docx")
            card.locator("[data-preview]").first.click()
            page.locator("#assistant-preview").wait_for(state="visible")
            page.locator("#assistant-close-preview").click()
            # The exact vacancy href is rendered in the interface.
            assert (
                card.get_by_role("link", name="Abrir vaga").get_attribute("href")
                == first["apply_url"]
            )
            with page.expect_popup() as popup_event:
                card.get_by_role("link", name="Abrir vaga").click()
            popup = popup_event.value
            popup.wait_for_load_state("domcontentloaded", timeout=45000)
            assert first["source_id"] in popup.url
            opened_url = popup.url
            popup.close()
            card.locator("[data-job-status]").select_option("selected")
            page.wait_for_function(
                "document.querySelector('#assistant-message').textContent.includes('Estado registrado')"
            )
            # Restart the actual backend with the same SQLite/config storage.
            process.terminate()
            process.wait(timeout=10)
            process = subprocess.Popen(
                [sys.executable, str(root / "run.py"), "--no-browser"],
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for _ in range(60):
                try:
                    if requests.get(base + "/api/health", timeout=1).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            page.goto(base, wait_until="domcontentloaded")
            page.locator("#contact-first_name").wait_for()
            assert page.locator("#contact-first_name").input_value() == "Fictional Test"
            assert page.locator(f'[data-job-status="{first["id"]}"]').input_value() == "selected"
            assert (
                page.locator(
                    f'[data-job-id="{first["id"]}"] [data-download][data-format="pdf"]'
                ).count()
                > 0
            )
            page.screenshot(path=str(folder / "dashboard.png"), full_page=True)
            current = page.evaluate(
                "async()=> (await (await fetch('/api/assistant/jobs')).json()).jobs"
            )
            report = dict(
                profile="Explicit fictional test fixture; not the user",
                sources="Real public Greenhouse/Lever APIs",
                jobs=[
                    {
                        k: j.get(k)
                        for k in (
                            "id",
                            "title",
                            "company",
                            "location",
                            "source",
                            "apply_url",
                            "url_status",
                            "url_message",
                            "match",
                        )
                    }
                    for j in current
                ],
                pdf=dict(valid=True, characters=len(text), pages=len(PdfReader(str(pdf)).pages)),
                browser_errors=errors,
                backend_restart_persistence=True,
                vacancy_opened_in_browser=opened_url,
                ai="Not validated: no credentials supplied",
                manual_submission="Not performed",
            )
            (folder / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(report, ensure_ascii=True), flush=True)
            assert not errors, errors
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()


if __name__ == "__main__":
    main()
