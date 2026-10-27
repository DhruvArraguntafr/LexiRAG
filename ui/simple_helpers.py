"""Small, testable helpers for the everyday research flow."""
from nicegui import app, ui


def research_collection(services, current=None):
    """Reuse data; adopt the legacy library only for the first collection.

    Existing collections remain isolated, including intentionally empty ones.
    """
    collections = services.workspaces.list()
    if current and any(w["id"] == current for w in collections):
        return current
    if collections:
        return collections[0]["id"]
    identifier = services.workspaces.create("My research")
    for document in services.corpus.db.documents():
        services.workspaces.attach(identifier, document["id"])
    return identifier


def ensure_research(context):
    context.workspace_id = research_collection(context.services, context.workspace_id)
    app.storage.user["workspace_id"] = context.workspace_id
    return context.workspace_id


def heading(title, description):
    with ui.column().classes("w-full gap-2 mb-6"):
        ui.label(title).classes("page-title")
        ui.label(description).classes("subtle")


def open_question(context, question="", document_id=None):
    ensure_research(context)
    app.storage.user["pending_question"] = {
        "workspace_id": context.workspace_id, "text": question.strip(),
        "document_id": document_id,
    }
    ui.navigate.to(context.url("research"))


def progress_text(job):
    status = job["status"]
    if status == "completed":
        return "Ready to research"
    if status == "partial":
        return "Ready — some pages need a clearer copy"
    if status in {"failed", "interrupted"}:
        return "Could not finish. Try again or upload a clearer PDF."
    if status == "cancelled":
        return "Stopped"
    if status == "queued":
        return "Waiting to read your PDF…"
    stage = job["stage"].lower()
    if any(word in stage for word in ("ocr", "extract", "reading")):
        return "Reading your pages, including any scans…"
    if "embed" in stage or "index" in stage:
        return "Preparing your document for questions…"
    return "Opening your PDF…"
