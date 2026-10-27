from nicegui import app, ui

from core.models import LexiRAGError
from ui.common import background, empty, guard
from ui.simple_helpers import heading
from ui.source_viewer import SourceViewer
from ui.research_components import render_result


def render(context):
    services = context.services
    heading("Ask your documents", "Ask in your own words. Click a source beneath any answer to check the original page.")
    documents = services.workspaces.documents(context.workspace_id) if context.workspace_id else []
    if not documents:
        empty("Add a PDF to get started", "Your answers will come from the documents you upload.", "upload_file",
              lambda: ui.navigate.to(context.url("home")), "Upload PDFs")
        return
    pending = app.storage.user.pop("pending_question", None) or {}
    if pending.get("workspace_id") != context.workspace_id:
        pending = {}
    names = {d["id"]: d["name"] for d in documents}
    initial_selection = [pending["document_id"]] if pending.get("document_id") in names else list(names)
    viewer = SourceViewer(context, compact=True, simple=True)
    state = {"limit": 1, "busy": False}
    with ui.element("div").classes("simple-research w-full"):
        with ui.column().classes("w-full gap-4 research-main"):
            with ui.expansion("Choose documents", icon="description").classes("w-full simple-source-choice"):
                selected = ui.select(names, multiple=True, value=initial_selection, label="Search in").props("outlined use-chips options-dense").classes("w-full")
                ui.link("Add more PDFs", context.url("home")).classes("text-xs text-primary")
            @ui.refreshable
            def conversation():
                sessions = list(reversed(services.workspaces.runs(context.workspace_id, state["limit"])))
                if not sessions:
                    with ui.column().classes("answer-card w-full gap-3 py-8"):
                        ui.icon("auto_awesome", color="primary", size="28px")
                        ui.label("What would you like to know?").classes("text-xl font-semibold")
                        ui.label("Find a clause, understand a judgment, or ask what a document means. Your answer will include links to the pages it uses.").classes("subtle")
                if len(sessions) == state["limit"]:
                    def more():
                        state["limit"] += 4
                        conversation.refresh()
                    ui.button("Earlier answers", icon="history", on_click=more).props("flat dense")
                for session in sessions:
                    with ui.column().classes("w-full gap-3 mb-4"):
                        with ui.column().classes("question-bubble self-end"):
                            ui.label(session["question"]).classes("text-sm leading-6 whitespace-pre-wrap")
                        with ui.column().classes("answer-card w-full gap-1"):
                            with ui.row().classes("gap-2 items-center mb-2"):
                                ui.icon("auto_awesome", color="primary", size="19px")
                                ui.label("Your answer" if session["kind"] == "research" else "Your " + session["kind"]).classes("font-semibold")
                            try:
                                _, result = services.workspaces.run(context.workspace_id, session["id"])
                                render_result(context, session["id"], result, viewer)
                            except LexiRAGError:
                                ui.label("A source for this answer was removed. Ask again using your current documents.").classes("subtle")
            conversation()
            with ui.column().classes("panel question-composer w-full gap-3"):
                question = ui.textarea("Your question", value=pending.get("text", ""), placeholder="e.g. How much notice is needed to end this agreement?").props("outlined autogrow rows=2").classes("w-full")
                with ui.row().classes("w-full items-center gap-3"):
                    ui.label("Your question and relevant passages are sent to Google Gemini.").classes("fineprint flex-1")
                    send = ui.button("Ask", icon="arrow_upward").props("unelevated")
                with ui.row().classes("w-full items-center gap-2") as progress:
                    ui.spinner(color="primary", size="20px")
                    ui.label("Reading your documents and checking the supporting passages…").classes("subtle")
                progress.set_visibility(False)
                @guard
                async def ask():
                    if state["busy"]:
                        return
                    if not (question.value or "").strip():
                        raise LexiRAGError("Type a question first.")
                    if not selected.value:
                        raise LexiRAGError("Choose at least one PDF under Choose documents.")
                    state["busy"] = True
                    send.disable()
                    question.disable()
                    progress.set_visibility(True)
                    try:
                        await background(services.research.ask, context.workspace_id, question.value,
                                         selected=selected.value)
                        question.value = ""
                        conversation.refresh()
                    finally:
                        state["busy"] = False
                        send.enable()
                        question.enable()
                        progress.set_visibility(False)
                send.on_click(ask)
                question.on("keydown.ctrl.enter", ask)
            with ui.row().classes("gap-2 flex-wrap"):
                for text in ("What are the main points?", "Which clauses describe my obligations?"):
                    ui.button(text, on_click=lambda value=text: question.set_value(value)).props("flat dense size=sm")
            ui.label("Ctrl+Enter to ask · Answers can make mistakes. Check the cited pages.").classes("fineprint")
        with ui.column().classes("w-full simple-evidence"):
            viewer.render()
    if pending.get("text"):
        ui.timer(0.3, ask, once=True)
