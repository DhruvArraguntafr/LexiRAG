from nicegui import ui

from ui.common import background, guard
from ui.source_viewer import source_dialog
from utils.reports import report_markdown, report_pdf


def render_result(context, run_id, result, viewer=None):
    services = context.services
    saved = {(f["run_id"], f["title"], f["statement"]) for f in services.evidence.findings(context.workspace_id)}
    if result.answer.insufficient_evidence:
        with ui.row().classes("items-start p-4 rounded-lg w-full").style("background:var(--soft)"):
            ui.icon("info", color="primary")
            with ui.column().classes("gap-1 flex-1"):
                ui.label("There isn't enough information in these documents").classes("font-semibold")
                ui.label("Try a more specific question or add a document that covers this topic.").classes("subtle")
    for index, finding in enumerate(result.answer.findings):
        with ui.column().classes("gap-2 w-full py-3"):
            with ui.row().classes("w-full items-start justify-between gap-2"):
                ui.label(finding.heading).classes("font-semibold text-base flex-1")
            ui.label(finding.statement).classes("text-sm leading-7 whitespace-pre-wrap")
            if finding.kind == "interpretation":
                ui.label("This is an interpretation of the text. Check the source before relying on it.").classes("fineprint")
            with ui.row().classes("gap-2 w-full flex-wrap"):
                for ref in finding.evidence:
                    hit = result.sources[ref.source_id]
                    def inspect(h=hit, q=ref.quote):
                        if viewer:
                            viewer.open(h.chunk.document_id, h.chunk.page, q, h.chunk.id)
                        else:
                            source_dialog(context, h.chunk.document_id, h.chunk.page, q, h.chunk.id, simple=True)
                    label = f"{hit.chunk.document_name} · page {hit.chunk.page}"
                    ui.button(label, icon="article", on_click=guard(inspect)).props("flat dense no-caps").classes("citation-chip").tooltip(hit.chunk.locator or "View original PDF page")
            with ui.row().classes("gap-1"):
                already_saved = (run_id, finding.heading, finding.statement) in saved
                save_button = ui.button("Saved" if already_saved else "Save finding", icon="bookmark" if already_saved else "bookmark_add").props("flat dense size=sm")
                save_button.set_enabled(not already_saved)
                async def save_finding(i=index, button=save_button):
                    button.disable()
                    try:
                        await background(services.evidence.save_finding, context.workspace_id, run_id, i)
                    except Exception:
                        button.enable()
                        raise
                    button.set_text("Saved")
                    button.props("icon=bookmark")
                    ui.notify("Saved to My Research", type="positive")
                save_button.on_click(guard(save_finding))
    if result.answer.limitations:
        with ui.expansion("Important limitations", icon="policy", value=result.answer.insufficient_evidence).classes("w-full text-sm"):
            for limitation in result.answer.limitations:
                ui.label("• " + limitation).classes("subtle")
    with ui.row().classes("w-full gap-2 pt-3 items-center"):
        ui.button("Copy answer", icon="content_copy", on_click=lambda: ui.clipboard.write(report_markdown(result))).props("flat dense size=sm")
        async def download():
            content = await background(report_pdf, result)
            ui.download(content, "LexiRAG-research.pdf", "application/pdf")
            services.workspaces.activity(context.workspace_id, "report", result.question)
        ui.button("Export report", icon="download", on_click=guard(download)).props("flat dense size=sm")
