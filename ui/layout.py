from dataclasses import dataclass

from nicegui import ui, app

from backend.container import get_services
from ui.common import target
from ui.theme import install_theme

NAVIGATION = [
    ("home", "Home", "home"), ("research", "AI Research", "chat_bubble_outline"),
    ("my-research", "My Research", "bookmarks"),
]

@dataclass
class PageContext:
    services: object
    workspace_id: str | None
    section: str

    def url(self, path):
        return target(path, self.workspace_id)


def global_search(context):
    with ui.dialog() as dialog, ui.card().classes("w-[650px] p-5"):
        query = ui.input("Search your research", placeholder="Document, collection or saved passage…").props("outlined autofocus clearable").classes("w-full")
        @ui.refreshable
        def results():
            needle = (query.value or "").casefold()
            items = 0
            for workspace in context.services.workspaces.list():
                if needle and needle not in workspace["title"].casefold():
                    continue
                ui.link("Collection · " + workspace["title"], target("research", workspace["id"])).classes("p-2 text-primary")
                items += 1
            for doc in context.services.corpus.db.documents():
                if needle and needle not in doc["name"].casefold():
                    continue
                ui.link("Document · " + doc["name"], context.url("home")).classes("p-2 text-primary")
                items += 1
                if items >= 15:
                    break
            if context.workspace_id and needle:
                for evidence in context.services.evidence.list(context.workspace_id):
                    if needle in (evidence["quote"] + evidence["notes"]).casefold():
                        ui.link("Passage · " + evidence["quote"][:100], context.url("my-research")).classes("p-2 text-primary")
                        items += 1
                        if items >= 20:
                            break
            if not items:
                ui.label("No matches yet. Try another document title or saved passage.").classes("subtle p-4")
        query.on_value_change(lambda: results.refresh())
        results()
        ui.label("Ctrl+K to search · Escape to close").classes("fineprint mt-2")
    dialog.open()


def shell(section, workspace_id=None):
    install_theme()
    services = get_services()
    workspaces = services.workspaces.list()
    valid = {w["id"] for w in workspaces}
    chosen = workspace_id if workspace_id in valid else app.storage.user.get("workspace_id")
    if chosen not in valid:
        chosen = workspaces[0]["id"] if workspaces else None
    if chosen:
        app.storage.user["workspace_id"] = chosen
    context = PageContext(services, chosen, section)
    theme = ui.dark_mode(value=bool(app.storage.user.get("dark", False)))
    with ui.left_drawer(value=False).props("width=248 breakpoint=1000 show-if-above").classes("app-sidebar") as drawer:
        with ui.row().classes("gap-3 items-center px-3 mb-1"):
            ui.icon("balance", color="#8ed5cf", size="29px")
            ui.label("LexiRAG").classes("brand")
            ui.badge("2.0").props("outline").style("color:#8ed5cf;font-size:9px")
        ui.label("Clarity in every document.").classes("brand-small px-3 mb-9")
        for route, label, icon in NAVIGATION:
            with ui.link(target=context.url(route)).classes("nav-link" + (" nav-active" if section == route else "")):
                ui.icon(icon, size="19px")
                ui.label(label)
        ui.space()
        with ui.column().classes("px-3 mt-7 gap-2"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("shield", size="16px", color="#75b9ae")
                ui.label("Stored on your computer").classes("text-xs").style("color:#b4c9d8")
            ui.label("Selected evidence is sent to Gemini when you ask for AI analysis.").classes("text-[10px] leading-5").style("color:#7796aa")
    with ui.header().classes("topbar items-center px-5 lg:px-9 gap-4"):
        ui.button(icon="menu", on_click=drawer.toggle).props("flat round dense aria-label='Toggle navigation'")
        with ui.row().classes("items-center gap-2 text-sm"):
            ui.label(next((label for route, label, _ in NAVIGATION if route == section), "Home")).classes("font-semibold")
        ui.space()
        ui.button("Search research", icon="search", on_click=lambda: global_search(context)).props("flat no-caps").classes("global-search").style("color:var(--muted)")
        def toggle_theme():
            theme.toggle()
            app.storage.user["dark"] = theme.value
        ui.button(icon="dark_mode", on_click=toggle_theme).props("flat round dense aria-label='Toggle dark theme'").tooltip("Switch light / dark theme")
    def key(e):
        if e.action.keydown and (e.modifiers.ctrl or e.modifiers.meta) and str(e.key).lower() == "k":
            global_search(context)
    ui.keyboard(on_key=key)
    return context
