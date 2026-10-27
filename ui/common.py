from functools import wraps
import inspect
import logging
from urllib.parse import urlencode

from nicegui import ui, run

from core.models import LexiRAGError


def guard(function):
    @wraps(function)
    async def protected(*args, **kwargs):
        try:
            value = function(*args, **kwargs)
            return await value if inspect.isawaitable(value) else value
        except LexiRAGError as exc:
            ui.notify(str(exc), type="warning", timeout=8000, close_button=True)
        except Exception as exc:
            logging.getLogger("lexirag").error("UI operation failed (%s)", type(exc).__name__)
            ui.notify("The operation could not finish. Check storage or connectivity and try again.", type="negative", close_button=True)
    return protected


async def background(function, *args, **kwargs):
    return await run.io_bound(function, *args, **kwargs)


def empty(title, description, icon="search", action=None, action_label="Get started"):
    with ui.column().classes("empty-state"):
        with ui.element("div").classes("icon-tile"):
            ui.icon(icon, size="24px")
        ui.label(title).classes("panel-title")
        ui.label(description).classes("subtle max-w-md")
        if action:
            ui.button(action_label, on_click=guard(action)).props("unelevated no-caps")


async def confirm(title, message, action):
    with ui.dialog() as dialog, ui.card().classes("w-96 p-6"):
        ui.label(title).classes("panel-title")
        ui.label(message).classes("subtle mt-2")
        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            @guard
            async def execute():
                await background(action)
                dialog.close()
                ui.navigate.reload()
            ui.button("Confirm", on_click=execute).props("unelevated color=negative")
    dialog.open()


def target(path, workspace_id=None):
    return "/" + path + ("?" + urlencode({"workspace": workspace_id}) if workspace_id else "")


