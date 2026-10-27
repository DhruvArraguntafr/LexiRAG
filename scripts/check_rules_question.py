"""Actual browser verification of the Rules deadline question and page citation."""
import asyncio
import json
from pathlib import Path
import sqlite3
from urllib.parse import urljoin

import pymupdf
from playwright.async_api import async_playwright, expect

from scripts.verify_rules_research import QUESTION


async def check():
    directory=Path("data/rule45-validation/browser")
    directory.mkdir(parents=True,exist_ok=True)
    errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",headless=True)
        page=await browser.new_page(viewport={"width":1512,"height":1050})
        page.on("pageerror",lambda error:errors.append(str(error)))
        base="http://127.0.0.1:8080"
        await page.goto(base+"/home",wait_until="networkidle")
        assert await page.locator(".app-sidebar .nav-link").count()==3
        await page.get_by_role("textbox",name="Your legal question",exact=True).fill(QUESTION)
        await page.get_by_role("button",name="Ask a question",exact=True).click()
        await page.wait_for_url("**/research?workspace=*")
        await expect(page.get_by_label("Your question",exact=True)).to_have_value("",timeout=180000)
        await expect(page.get_by_role("button",name="Ask",exact=True)).to_be_enabled(timeout=180000)
        assert not await page.get_by_text("There isn't enough information in these documents",exact=True).count()
        with sqlite3.connect("data/metadata.sqlite3") as con:
            question,value=con.execute("SELECT question,result_json FROM research_runs ORDER BY created_at DESC,rowid DESC LIMIT 1").fetchone()
        result=json.loads(value)
        assert question.strip()==QUESTION and not result["answer"]["insufficient_evidence"]
        answer=" ".join(f["heading"]+" "+f["statement"] for f in result["answer"]["findings"]).lower()
        assert "4(5)" in answer and ("48" in answer or "forty-eight" in answer) and "one month" in answer
        assert any(result["sources"][ref["source_id"]]["chunk"]["page"]==4 for f in result["answer"]["findings"] for ref in f["evidence"])
        await page.locator(".citation-chip").filter(has_text="page 4").first.click()
        await page.wait_for_function("document.querySelector('.simple-evidence .source-preview img')?.naturalWidth>0")
        await page.wait_for_timeout(700)
        href=await page.locator(".simple-evidence a").filter(has_text="Open original PDF").get_attribute("href")
        assert "#page=4" in href
        original=await page.request.get(urljoin(base,href))
        assert original.status==200 and (await original.body()).startswith(b"%PDF")
        await page.evaluate("window.scrollTo(0,0)")
        await page.screenshot(path=str(directory/"verified-answer-and-original-page.png"),full_page=True)
        async with page.expect_download() as download:
            await page.get_by_role("button",name="Export report",exact=True).click()
        await (await download.value).save_as(directory/"rules-complaint-deadlines.pdf")
        with pymupdf.open(directory/"rules-complaint-deadlines.pdf") as report:
            text=" ".join(p.get_text() for p in report)
            assert "4(5)" in text and "PDF page 4" in text
        for route in ["home","research","my-research"]:
            await page.set_viewport_size({"width":390,"height":844})
            response=await page.goto(base+"/"+route,wait_until="networkidle")
            assert response.status==200
            assert not await page.evaluate("document.documentElement.scrollWidth>innerWidth+2")
        assert not errors,errors
        output={"exact_question_succeeded":True,"rule":"4(5)","primary_pdf_page":4,
                "original_pdf_opened":True,"report_downloaded":True,"three_page_ui_verified":True,"browser_errors":errors}
        (directory/"results.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
        print(json.dumps(output,indent=2))
        await browser.close()


if __name__=="__main__":
    asyncio.run(check())
