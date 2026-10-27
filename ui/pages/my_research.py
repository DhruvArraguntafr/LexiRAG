import json

from nicegui import ui

from core.models import LexiRAGError
from ui.common import background, empty, guard
from ui.simple_helpers import heading
from ui.source_viewer import source_dialog
from ui.research_components import render_result
from utils.reports import markdown_pdf


def render(context):
    services = context.services
    heading("My Research", "Your saved findings, past questions and reports, all in one place.")
    if not context.workspace_id:
        empty("Keep what matters", "Upload a PDF, ask a question, then choose Save finding beneath an answer.", "bookmarks",
              lambda: ui.navigate.to(context.url("home")), "Start with a PDF")
        return
    with ui.tabs().classes("w-full mb-5 research-tabs") as tabs:
        saved_tab = ui.tab("Saved findings", icon="bookmark_border")
        history_tab = ui.tab("Past questions", icon="history")
        reports_tab = ui.tab("Reports", icon="description")
    with ui.tab_panels(tabs, value=saved_tab).classes("w-full bg-transparent"):
        with ui.tab_panel(saved_tab).classes("p-0"):
            findings = services.evidence.findings(context.workspace_id)
            selected = set()
            if not findings:
                empty("Save your first finding", "Choose Save finding under an answer. You can then collect findings into a report.", "bookmark_border",
                      lambda: ui.navigate.to(context.url("research")), "Ask a question")
            else:
                with ui.column().classes("panel w-full gap-4 mb-5"):
                    ui.label("Make a research report").classes("panel-title")
                    ui.label("Tick the findings you want to include. Their supporting passages and page references will be included automatically.").classes("subtle")
                    title = ui.input("Report title", value="My research report").props("outlined dense").classes("w-full")
                    question = ui.input("Research question", placeholder="What does this report investigate?").props("outlined dense").classes("w-full")
                    export = ui.button("Export selected findings", icon="download").props("unelevated")
                    export.disable()
                    @guard
                    async def make_report():
                        if not selected:
                            raise LexiRAGError("Tick at least one finding below.")
                        export.disable()
                        try:
                            ordered = [(f["id"], "Key findings") for f in findings if f["id"] in selected]
                            identifier, _ = await background(services.briefs.generate, context.workspace_id,
                                                           title.value or "My research report",
                                                           question.value or "Research across the selected saved findings.", ordered)
                            text = await background(services.briefs.export, context.workspace_id, identifier)
                            pdf = await background(markdown_pdf, text, title.value or "My research report")
                            ui.download(pdf, "LexiRAG-research-report.pdf", "application/pdf")
                            report_list.refresh()
                            ui.notify("Report downloaded and saved under Reports", type="positive")
                        finally:
                            export.set_enabled(bool(selected))
                    export.on_click(make_report)
                for finding in reversed(findings):
                    with ui.column().classes("panel w-full gap-3 mb-4"):
                        with ui.row().classes("w-full gap-2 items-start no-wrap"):
                            def choose(event, identifier=finding["id"]):
                                if event.value:
                                    selected.add(identifier)
                                else:
                                    selected.discard(identifier)
                                export.set_enabled(bool(selected))
                            checkbox = ui.checkbox(on_change=choose).props("aria-label='Include finding in report'")
                            checkbox.set_enabled(finding["valid_sources"])
                            ui.label(finding["title"]).classes("panel-title flex-1 mt-2")
                        ui.label(finding["statement"]).classes("text-sm leading-7 whitespace-pre-wrap")
                        if finding["kind"] == "interpretation":
                            ui.label("Interpretation — check against the original text.").classes("fineprint")
                        if not finding["valid_sources"]:
                            ui.label("A source has been removed. Ask the question again before including this finding in a report.").classes("subtle")
                        else:
                            with ui.row().classes("w-full gap-2"):
                                for ref in json.loads(finding["refs"]):
                                    chunk = services.evidence.validate(context.workspace_id, ref["chunk_id"], ref["quote"])
                                    ui.button(f"{chunk.document_name} · page {chunk.page}", icon="article",
                                              on_click=guard(lambda c=chunk, q=ref["quote"]: source_dialog(context, c.document_id, c.page, q, c.id, simple=True))).props("flat dense no-caps").classes("citation-chip")
            excerpts = [e for e in services.evidence.list(context.workspace_id) if not e["finding_id"]]
            if excerpts:
                with ui.expansion("Saved passages", icon="format_quote").classes("w-full mt-5"):
                    for evidence in excerpts:
                        with ui.column().classes("panel w-full gap-3 mb-3"):
                            ui.label(evidence["quote"]).classes("quote w-full")
                            if evidence["notes"]:
                                ui.label(evidence["notes"]).classes("subtle")
                            ui.button(f"{evidence['document_name']} · page {evidence['page']}", icon="article",
                                      on_click=guard(lambda e=evidence: source_dialog(context, e["document_id"], e["page"], e["quote"], e["chunk_id"], simple=True))).props("flat dense no-caps")
        with ui.tab_panel(history_tab).classes("p-0"):
            sessions = services.workspaces.runs(context.workspace_id, limit=200)
            if not sessions:
                empty("Your questions will be saved here", "Answers and summaries are saved automatically.", "history",
                      lambda: ui.navigate.to(context.url("research")), "Ask a question")
            for session in sessions:
                with ui.expansion(session["question"], icon={"comparison": "compare_arrows", "summary": "notes"}.get(session["kind"], "chat_bubble_outline")).classes("panel w-full mb-3") as expansion:
                    ui.label(session["created_at"][:16].replace("T", " ") + " UTC").classes("fineprint mb-3")
                    content = ui.column().classes("w-full")
                loaded = {"value": False}
                @guard
                def load(event, identifier=session["id"], area=content, state=loaded):
                    if not event.value or state["value"]:
                        return
                    _, result = services.workspaces.run(context.workspace_id, identifier)
                    with area:
                        render_result(context, identifier, result)
                    state["value"] = True
                expansion.on_value_change(load)
            if len(sessions) == 200:
                ui.label("Showing your 200 most recent questions. Earlier records remain saved on this computer.").classes("fineprint")
        with ui.tab_panel(reports_tab).classes("p-0"):
            @ui.refreshable
            def report_list():
                reports = services.briefs.list(context.workspace_id)
                if not reports:
                    empty("Your reports will appear here", "Select saved findings to create a report you can download again later.", "description")
                for report in reports:
                    with ui.row().classes("panel w-full items-center gap-4 mb-3"):
                        ui.icon("description", color="primary", size="26px")
                        with ui.column().classes("flex-1 gap-1"):
                            ui.label(report["title"]).classes("panel-title")
                            ui.label(report["updated_at"][:16].replace("T", " ") + " UTC").classes("fineprint")
                        async def download(item=report):
                            text = await background(services.briefs.export, context.workspace_id, item["id"])
                            pdf = await background(markdown_pdf, text, item["title"])
                            ui.download(pdf, "LexiRAG-research-report.pdf", "application/pdf")
                        ui.button("Download PDF", icon="download", on_click=guard(download)).props("outline")
            report_list()
