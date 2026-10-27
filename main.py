"""LexiRAG 2.0. Start one local process: python main.py."""
import asyncio
import os
import secrets

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from nicegui import ui, app, background_tasks

from backend.container import get_services
from backend.api import register_api
from core.models import LexiRAGError
from ui.layout import shell
from ui.pages import home, research, my_research
from core.retrieval_diagnostics import configure as configure_diagnostics

PAGES = {"home": home.render, "research": research.render, "my-research": my_research.render}

register_api(app)


def render_page(section, workspace=None):
    if section not in PAGES:
        ui.navigate.to("/home")
        return
    context = shell(section, workspace)
    with ui.column().classes("page-wrap gap-0"):
        try:
            PAGES[section](context)
        except LexiRAGError as exc:
            ui.label(str(exc)).classes("panel w-full")
        with ui.row().classes("w-full mt-10 pt-5 items-center justify-between").style("border-top:1px solid var(--line)"):
            ui.label("LexiRAG · Your documents, clearly understood.").classes("fineprint")
            ui.label("Research support, not professional legal advice.").classes("fineprint")


@ui.page("/")
def index(workspace: str | None = None):
    render_page("home", workspace)


@ui.page("/{section}")
def page(section: str, workspace: str | None = None):
    render_page(section, workspace)


async def startup():
    services = get_services()
    configure_diagnostics(services.settings.data_dir)
    background_tasks.create(asyncio.to_thread(services.check_ocr), name="ocr-health")


app.on_startup(startup)
app.on_shutdown(lambda: get_services().close())


def run():
    service = get_services()
    secret_file = service.settings.data_dir / ".session_secret"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    ui.run(host="127.0.0.1", port=int(os.getenv("LEXIRAG_PORT", "8080")), title="LexiRAG · Legal Research Workspace",
           favicon="⚖", reload=False, show=False, storage_secret=secret_file.read_text(encoding="utf-8"),
           uvicorn_logging_level="warning", show_welcome_message=True)


if __name__ == "__main__":
    run()
