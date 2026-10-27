from nicegui import ui

from core.models import LexiRAGError
from ui.common import background, confirm, guard
from ui.simple_helpers import ensure_research, open_question, progress_text
from ui.source_viewer import source_dialog

EXAMPLES = ("What are the main points in these documents?",
            "What does the agreement say about ending the contract?",
            "Which documents discuss the right to privacy?")


def render(context):
    services = context.services
    if not context.workspace_id and services.corpus.db.documents():
        ensure_research(context)
    state = {"visible_documents": 6}
    with ui.column().classes("home-hero w-full gap-4"):
        with ui.row().classes("items-center gap-2 hero-kicker"):
            ui.icon("auto_awesome", size="17px")
            ui.label("Your documents. Clear answers.")
        ui.label("Legal research,\nmade simple.").classes("home-title whitespace-pre-line")
        ui.label("Upload your PDFs. Ask in your own words. Follow every answer back to its source.").classes("home-copy")
        with ui.row().classes("home-question w-full items-center gap-2"):
            question = ui.input(placeholder="What would you like to understand?").props("borderless aria-label='Your legal question'").classes("flex-1 min-w-0")
            @guard
            def start():
                if not question.value or not question.value.strip():
                    question.run_method("focus")
                    return
                if not context.workspace_id or not services.workspaces.documents(context.workspace_id):
                    ui.notify("Upload a PDF below first. Your question will stay here while it is prepared.", type="info")
                    return
                open_question(context, question.value)
            ui.button("Ask a question", icon="arrow_forward", on_click=start).props("unelevated")
        question.on("keydown.enter", start)
        with ui.row().classes("gap-2 items-center example-questions"):
            ui.label("Try asking:").classes("text-xs")
            for text in EXAMPLES:
                ui.button(text, on_click=lambda value=text: question.set_value(value)).props("flat dense size=sm no-caps").classes("example-question")
    with ui.element("div").classes("home-bottom w-full mt-7"):
        with ui.column().classes("panel w-full gap-3 upload-panel"):
            ui.label("Add your documents").classes("panel-title")
            ui.label("Judgments, acts, agreements or case studies. Scanned pages are read automatically.").classes("subtle")
            @guard
            async def upload(event):
                identifier = ensure_research(context)
                for file in event.files:
                    try:
                        content = await file.read()
                        await background(services.jobs.submit, file.name, content, identifier)
                    except LexiRAGError as exc:
                        ui.notify(str(exc), type="warning")
                processing.refresh()
                event.sender.reset()
            ui.upload(label="Drop PDFs here or click + to browse", multiple=True, auto_upload=True,
                      on_multi_upload=upload, on_rejected=lambda: ui.notify("Choose a PDF within the size limit.", type="warning"),
                      max_file_size=services.settings.max_upload_mb * 1024 * 1024).props("accept=.pdf flat bordered").classes("dropzone simple-upload")
            ui.label(f"PDF files · up to {services.settings.max_upload_mb} MB each").classes("fineprint")
            @ui.refreshable
            def processing():
                jobs = services.jobs.list(context.workspace_id) if context.workspace_id else []
                for job in [j for j in jobs if j["status"] != "completed"][:6]:
                    with ui.column().classes("w-full gap-1 job-row"):
                        with ui.row().classes("w-full items-center gap-2"):
                            busy = job["status"] in {"queued", "running"}
                            if busy:
                                ui.spinner(size="17px", color="primary")
                            else:
                                ui.icon("check_circle" if job["status"] in {"completed", "partial"} else "info", color="primary", size="18px")
                            ui.label(job["name"]).classes("text-xs flex-1 break-all")
                            if job["status"] in {"failed", "interrupted", "cancelled"}:
                                ui.button("Try again", on_click=guard(lambda j=job: services.jobs.retry(j["id"]))).props("flat dense size=sm")
                            if busy:
                                ui.button("Stop", on_click=guard(lambda j=job: services.jobs.cancel(j["id"]))).props("flat dense size=sm")
                        ui.label(progress_text(job)).classes("fineprint")
                        if busy:
                            total = job["total"] or 0
                            ui.linear_progress(value=min(1, job["completed"] / total) if total else 0).props("" if total else "indeterminate")
                        if job["status"] in {"failed", "partial", "interrupted"}:
                            with ui.expansion("What happened?").classes("text-xs w-full"):
                                ui.label(job["message"]).classes("fineprint")
            processing()
        with ui.column().classes("w-full gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Your documents").classes("panel-title")

            @ui.refreshable
            def documents():
                docs = services.workspaces.documents(context.workspace_id) if context.workspace_id else []
                if not docs:
                    with ui.column().classes("home-empty w-full items-center gap-3"):
                        ui.icon("description", color="primary", size="34px")
                        ui.label("Your first answer starts with a PDF.").classes("font-semibold")
                        ui.label("Add one on the left. It will appear here when it is ready.").classes("subtle text-center")
                for doc in docs[:state["visible_documents"]]:
                    with ui.column().classes("document-row w-full gap-3"):
                        with ui.row().classes("w-full items-center gap-3 no-wrap"):
                            with ui.element("div").classes("icon-tile shrink-0"):
                                ui.icon("description", size="23px")
                            with ui.column().classes("gap-1 min-w-0 flex-1"):
                                ui.label(doc["name"]).classes("font-semibold text-sm break-all")
                                ui.label(f"{doc['pages']} " + ("page" if doc["pages"] == 1 else "pages") + (" · Some pages need review" if doc["status"] == "partial" else " · Ready to research")).classes("fineprint")
                            with ui.button(icon="more_horiz").props("flat round dense aria-label='Document actions'"), ui.menu():
                                ui.menu_item("Delete document", on_click=guard(lambda d=doc: confirm("Delete this document?", "Its PDF and saved source links will be removed from all research collections.", lambda: services.corpus.delete(d["id"]))))
                        with ui.row().classes("gap-1"):
                            ui.button("Ask about this", icon="chat_bubble_outline", on_click=guard(lambda d=doc: open_question(context, document_id=d["id"]))).props("flat dense size=sm")
                            ui.button("View PDF", icon="visibility", on_click=guard(lambda d=doc: source_dialog(context, d["id"], simple=True))).props("flat dense size=sm")
                            async def summarize(d=doc):
                                with ui.dialog().props("persistent") as wait, ui.card().classes("p-7 gap-4 items-center"):
                                    ui.spinner(color="primary", size="32px")
                                    ui.label("Reading your document and preparing a summary…").classes("subtle")
                                wait.open()
                                try:
                                    await background(services.research.summarize, context.workspace_id, d["id"])
                                    ui.navigate.to(context.url("research"))
                                finally:
                                    wait.close()
                            ui.button("Summarize", icon="notes", on_click=guard(summarize)).props("flat dense size=sm")
                if len(docs) > state["visible_documents"]:
                    def more_documents():
                        state["visible_documents"] += 12
                        documents.refresh()
                    ui.button("Show more documents", on_click=more_documents).props("flat")
                if docs:
                    ui.button("Start researching", icon="arrow_forward", on_click=lambda: ui.navigate.to(context.url("research"))).props("unelevated").classes("mt-1")
            documents()
    fingerprint = {"value": None}
    def poll():
        jobs = services.jobs.list(context.workspace_id) if context.workspace_id else []
        current = tuple((j["id"], j["status"], j["completed"], j["stage"]) for j in jobs)
        if current != fingerprint["value"]:
            fingerprint["value"] = current
            processing.refresh()
            documents.refresh()
    ui.timer(1, poll)
