"""Real-browser regression for the everyday UI, isolated from the main library.

Run a server with LEXIRAG_DATA_DIR=data/simple-validation/corpus, then run
python -m scripts.check_simple_ui [--live]. --live sends fictional excerpts
to the configured Gemini provider. Requires Playwright and Chromium or Edge.
"""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urljoin

import pymupdf
from playwright.async_api import async_playwright, expect

from scripts.create_ocr_fixtures import create_fixtures


async def check(url, directory, live):
    directory = directory.resolve()
    shots = directory / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    fixture_names = ["Native-Teaching.pdf", "Scanned-Teaching.pdf", "Mixed-Teaching.pdf", "Incomplete-Text.pdf"]
    fixtures = {name: directory / "fixtures" / name for name in fixture_names}
    if not all(path.exists() for path in fixtures.values()):
        fixtures = create_fixtures(directory / "fixtures")
    second = directory / "fixtures/Sixty-Day-Agreement.pdf"
    if not second.exists():
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_textbox(pymupdf.Rect(45, 60, 550, 780),
                "SYNTHETIC SIXTY DAY TEACHING AGREEMENT - NOT REAL LAW\n\nClause 7 Termination notice\n"
                "Either party may terminate this agreement by giving sixty days written notice.\n"
                "Fees for completed services remain payable.\n\nClause 8 Data retention\n"
                "Personal data must be deleted within ninety days after termination.", fontsize=14)
            pdf.save(second)
    results, errors = {}, []
    database = directory / "corpus/metadata.sqlite3"
    def rows(sql, params=()):
        with sqlite3.connect(database) as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(sql, params)]
    async with async_playwright() as playwright:
        edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
        browser = await playwright.chromium.launch(executable_path=str(edge) if edge.exists() else None, headless=True)
        page = await browser.new_page(viewport={"width": 1512, "height": 1050})
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(url, wait_until="networkidle")
        await page.get_by_text("Legal research,", exact=False).first.wait_for()
        assert await page.locator(".app-sidebar .nav-link:visible").count() == 3
        for label in ("Home", "AI Research", "My Research"):
            assert await page.locator(".app-sidebar").get_by_role("link", name=label, exact=True).count() == 1
        assert not await page.get_by_text("Compare Documents", exact=True).count()
        assert not await page.get_by_text("Top-K", exact=True).is_visible()
        await page.screenshot(path=str(shots / "home-empty.png"), full_page=True)
        await page.get_by_role("button", name="Which documents discuss the right to privacy?", exact=True).click()
        assert await page.get_by_role("textbox", name="Your legal question").input_value() == "Which documents discuss the right to privacy?"
        results["three_primary_sections_and_example_question"] = True

        # Use Quasar's actual drag/drop overlay, rather than a direct API upload.
        encoded = base64.b64encode(fixtures["Scanned-Teaching.pdf"].read_bytes()).decode()
        transfer = await page.evaluate_handle("""base64 => {
          const dt=new DataTransfer(); dt.items.add(new File([Uint8Array.from(atob(base64), c=>c.charCodeAt(0))],
          'Scanned-Teaching.pdf',{type:'application/pdf'})); return dt;
        }""", encoded)
        uploader = page.locator(".q-uploader").first
        await uploader.dispatch_event("dragenter", {"dataTransfer": transfer})
        await uploader.dispatch_event("dragover", {"dataTransfer": transfer})
        overlay = page.locator(".q-uploader__dnd").first
        await overlay.wait_for(state="visible")
        await overlay.dispatch_event("drop", {"dataTransfer": transfer})
        await page.locator('input[type="file"]').first.set_input_files([str(fixtures["Native-Teaching.pdf"]), str(second)])
        deadline = time.monotonic() + 240
        docs, workspaces = [], []
        while time.monotonic() < deadline:
            workspaces = await (await page.request.get(url + "/api/workspaces")).json()
            jobs = await (await page.request.get(url + "/api/jobs")).json()
            docs = await (await page.request.get(url + "/api/documents")).json()
            if len(jobs) >= 3 and all(j["status"] in {"completed", "partial", "failed"} for j in jobs):
                assert all(j["status"] in {"completed", "partial"} for j in jobs), "An upload failed"
                break
            await asyncio.sleep(1)
        assert len(workspaces) == 1, "First uploads should share one automatically created collection"
        assert len(docs) == 3, "Three uploaded PDFs should be ready"
        workspace = workspaces[0]["id"]
        suffix = "?workspace=" + workspace
        scan = next(d for d in docs if d["name"] == "Scanned-Teaching.pdf")
        native = next(d for d in docs if d["name"] == "Native-Teaching.pdf")
        scan_pages = rows("SELECT * FROM document_pages WHERE document_id=?", (scan["id"],))
        assert scan_pages and all("ocr" in p["method"].lower() for p in scan_pages)
        await page.wait_for_timeout(1600)
        assert await page.locator(".document-row").count() == 3
        await page.evaluate("window.scrollTo(0,0)")
        await page.screenshot(path=str(shots / "home.png"), full_page=True)
        results["automatic_collection_multiple_uploads_real_drop_and_ocr"] = True
        print("PASS: Home upload, automatic collection, real OCR and document cards", flush=True)

        if live:
            before = len(rows("SELECT id FROM research_runs"))
            await page.get_by_role("textbox", name="Your legal question").fill("How many days of written notice does the Scanned-Teaching.pdf agreement require to terminate?")
            await page.get_by_role("button", name="Ask a question", exact=True).click()
            await page.wait_for_url("**/research?workspace=*")
            deadline = time.monotonic() + 150
            while len(rows("SELECT id FROM research_runs")) == before and time.monotonic() < deadline:
                await asyncio.sleep(0.5)
            await expect(page.get_by_label("Your question", exact=True)).to_have_value("", timeout=150000)
            await expect(page.get_by_role("button", name="Ask", exact=True)).to_be_enabled(timeout=150000)
            await page.get_by_role("button", name="Export report", exact=True).last.wait_for(timeout=150000)
            assert len(rows("SELECT id FROM research_runs")) == before + 1
            latest = rows("SELECT * FROM research_runs ORDER BY created_at DESC,rowid DESC LIMIT 1")[0]
            result = json.loads(latest["result_json"])
            assert result["answer"]["findings"] and not result["answer"]["insufficient_evidence"]
            for finding in result["answer"]["findings"]:
                for ref in finding["evidence"]:
                    hit = result["sources"][ref["source_id"]]
                    assert " ".join(ref["quote"].split()).casefold() in " ".join(hit["chunk"]["text"].split()).casefold()
            await page.locator(".citation-chip").last.click()
            image = page.locator(".simple-evidence .source-preview img").first
            await image.wait_for()
            await page.wait_for_function("document.querySelector('.simple-evidence .source-preview img')?.naturalWidth > 0")
            link = page.locator(".simple-evidence a").filter(has_text="Open original PDF")
            assert "#page=" in await link.get_attribute("href")
            response = await page.request.get(urljoin(url, await link.get_attribute("href")))
            assert response.status == 200 and (await response.body()).startswith(b"%PDF")
            await page.get_by_role("button", name="Save finding", exact=True).last.click()
            await page.get_by_text("Saved to My Research", exact=True).wait_for()
            await page.evaluate("window.scrollTo(0,0)")
            await page.screenshot(path=str(shots / "research.png"), full_page=True)
            results["home_question_gemini_answer_exact_citations_original_pdf_and_save"] = True
            print("PASS: Home question, real Gemini answer, exact citation, original PDF and save", flush=True)

            async with page.expect_download() as download:
                await page.get_by_role("button", name="Export report", exact=True).last.click()
            await (await download.value).save_as(directory / "research-report.pdf")
            results["answer_report_download"] = True

            await page.goto(url + "/my-research" + suffix, wait_until="networkidle")
            for checkbox in await page.get_by_role("checkbox").all():
                if await checkbox.is_enabled():
                    await checkbox.click()
                    await expect(checkbox).to_be_checked()
            await page.get_by_label("Report title", exact=True).fill("Simple interface research check")
            await page.get_by_label("Research question", exact=True).fill("How do notice periods compare?")
            async with page.expect_download() as download:
                await page.get_by_role("button", name="Export selected findings", exact=True).click()
            await (await download.value).save_as(directory / "saved-findings-report.pdf")
            with pymupdf.open(directory / "saved-findings-report.pdf") as pdf:
                text = " ".join(p.get_text() for p in pdf)
                assert "Source references" in text and "PDF page" in text and "Simple interface research check" in text
            await page.get_by_role("tab", name="Reports", exact=True).click()
            async with page.expect_download() as download:
                await page.get_by_role("button", name="Download PDF", exact=True).first.click()
            await (await download.value).save_as(directory / "reopened-report.pdf")
            await page.get_by_role("tab", name="Past questions", exact=True).click()
            await page.get_by_text("How many days of written notice does the Scanned-Teaching.pdf agreement require to terminate?", exact=True).first.click()
            await page.get_by_role("button", name="Export report", exact=True).first.wait_for()
            await page.get_by_role("tab", name="Saved findings", exact=True).click()
            await page.wait_for_timeout(600)  # Let Quasar's panel transition finish before capture.
            await page.screenshot(path=str(shots / "my-research.png"), full_page=True)
            results["saved_findings_pdf_creation_persistent_reports_and_history"] = True
            print("PASS: Report export, saved findings and My Research history", flush=True)

            # Home's summary button must generate an actual saved, cited summary.
            await page.goto(url + "/home" + suffix, wait_until="networkidle")
            await page.locator(".document-row").filter(has_text="Scanned-Teaching.pdf").get_by_role("button", name="Summarize", exact=True).click()
            await page.wait_for_url("**/research?workspace=*", timeout=150000)
            assert rows("SELECT id FROM research_runs WHERE kind='summary'")
            before = len(rows("SELECT id FROM research_runs"))
            await page.get_by_label("Your question", exact=True).fill("Which Supreme Court decision in 2040 overrules all these teaching agreements? Give the case number.")
            await page.get_by_role("button", name="Ask", exact=True).click()
            deadline = time.monotonic() + 150
            while len(rows("SELECT id FROM research_runs")) == before and time.monotonic() < deadline:
                await asyncio.sleep(0.5)
            assert len(rows("SELECT id FROM research_runs")) == before + 1
            await page.get_by_text("There isn't enough information in these documents", exact=True).last.wait_for(timeout=150000)
            rejected = json.loads(rows("SELECT * FROM research_runs ORDER BY created_at DESC,rowid DESC LIMIT 1")[0]["result_json"])
            assert rejected["answer"]["insufficient_evidence"]
            results["cited_summary_and_unsupported_question_rejection"] = True
            print("PASS: Cited summary and insufficient-evidence answer", flush=True)

        routes = ["home", "research", "my-research"]
        for route in routes:
            response = await page.goto(url + "/" + route + suffix, wait_until="networkidle")
            assert response.status == 200
            assert not await page.get_by_text("Internal Server Error", exact=True).count(), route
            assert not await page.get_by_text("Advanced", exact=True).count()
        for removed in ["comparison", "advanced", "documents", "workspaces", "research-advanced", "comparison-advanced", "evidence", "timeline", "brief", "evaluation", "settings"]:
            await page.goto(url + "/" + removed + suffix, wait_until="networkidle")
            await page.wait_for_url("**/home")
        results["exactly_three_routes_and_removed_tools_redirect"] = True
        await page.goto(url + "/home" + suffix, wait_until="networkidle")
        await page.get_by_role("button", name="Toggle dark theme", exact=True).click()
        await page.screenshot(path=str(shots / "home-dark.png"), full_page=True)
        await page.get_by_role("button", name="Toggle dark theme", exact=True).click()
        for route in ["home", "research", "my-research"]:
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(url + "/" + route + suffix, wait_until="networkidle")
            assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"), route + " has phone overflow"
            await page.screenshot(path=str(shots / (route + "-phone.png")), full_page=True)
        results["light_dark_and_three_phone_layouts"] = True
        results["browser_errors"] = errors
        assert not errors, errors
        (directory / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        await browser.close()
        print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8082")
    parser.add_argument("--directory", type=Path, default=Path("data/simple-validation"))
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    asyncio.run(check(args.url.rstrip("/"), args.directory, args.live))
