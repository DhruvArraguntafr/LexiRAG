import json
from urllib.parse import urlencode

from nicegui import ui

from ui.common import guard, background, empty


class SourceViewer:
    def __init__(self, context, compact=False, *, simple=False):
        self.context, self.compact = context, compact
        self.simple = simple
        self.document_id, self.page, self.quote, self.chunk_id = None, 1, "", None
        self.scale = 1.5
        self.collapsed = False

    def open(self, document_id, page=1, quote="", chunk_id=None):
        self.document_id, self.page, self.quote, self.chunk_id = document_id, page, quote, chunk_id
        self.collapsed = False
        self.render.refresh()
        if self.simple:
            ui.run_javascript("document.querySelector('.simple-evidence')?.scrollIntoView({behavior:'smooth',block:'nearest'})")

    def move(self, page):
        self.page, self.quote = int(page), ""
        self.render.refresh()

    @ui.refreshable
    def render(self):
        services = self.context.services
        with ui.column().classes("panel w-full gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Original source" if self.simple else "Source inspector").classes("panel-title")
                if self.compact:
                    def toggle():
                        self.collapsed = not self.collapsed
                        self.render.refresh()
                    ui.button(icon="expand_more" if self.collapsed else "expand_less", on_click=toggle).props("flat dense round aria-label='Collapse or expand source inspector'")
                else:
                    ui.icon("verified_user", color="primary").tooltip("Original local PDF and extracted evidence")
            if self.collapsed:
                ui.label("Select a citation to reopen its source.").classes("fineprint")
                return
            if not self.document_id:
                empty("Follow the evidence", "Click any citation to open the original page and its exact quotation.", "find_in_page")
                return
            doc = services.corpus.db.document(self.document_id)
            if not doc:
                ui.label("The source document has been removed.").classes("subtle")
                return
            ui.label(doc["name"]).classes("font-semibold text-sm break-all")
            with ui.row().classes("items-center w-full gap-2"):
                ui.button(icon="chevron_left", on_click=guard(lambda: self.move(max(1, self.page - 1)))).props("flat dense aria-label='Previous PDF page'")
                ui.number("Page", value=self.page, min=1, max=doc["pages"], step=1,
                          on_change=guard(lambda e: self.move(min(doc["pages"], max(1, int(e.value or 1)))))).props("outlined dense").classes("w-24")
                ui.label(f"of {doc['pages']}").classes("subtle")
                ui.button(icon="chevron_right", on_click=guard(lambda: self.move(min(doc["pages"], self.page + 1)))).props("flat dense aria-label='Next PDF page'")
            _, label = services.sources.locations(self.document_id, self.page, self.quote)
            if self.simple:
                label = ("Highlighted passage" if "native" in label.lower() else
                         "Highlighted lines — check the original page" if "OCR" in label else
                         "Check the passage against this original page")
            ui.label(label).classes("fineprint")
            query = urlencode({"quote": self.quote, "scale": self.scale})
            with ui.element("div").classes("source-preview w-full"):
                ui.image(f"/api/documents/{self.document_id}/pages/{self.page}/preview?{query}").props("fit=contain").classes("w-full")
            with ui.row().classes("w-full items-center justify-between"):
                ui.link("Open original PDF ↗", f"/api/documents/{self.document_id}/original#page={self.page}", new_tab=True).classes("text-xs text-primary")
                ui.select({1.0: "Standard", 1.5: "Detailed", 2.0: "High resolution"}, value=self.scale,
                          on_change=lambda e: self.zoom(e.value)).props("dense outlined").classes("w-36")
            if self.quote:
                ui.label("Supporting passage" if self.simple else "EXACT EXTRACTED QUOTATION").classes("font-semibold text-sm mt-2")
                ui.label(self.quote).classes("quote w-full")
                if self.context.workspace_id and self.chunk_id:
                    ui.button("Save excerpt", icon="bookmark_add", on_click=guard(self.save)).props("flat dense no-caps")
            detail = services.corpus.db.page(self.document_id, self.page)
            if detail and not self.simple:
                with ui.expansion("Extraction details", icon="info").classes("w-full text-xs"):
                    ui.label(f"Method: {detail['method']} · {detail['quality']}").classes("fineprint")
                    for warning in json.loads(detail["warnings"]):
                        ui.label(warning).classes("fineprint")
                    auxiliary = [b for b in json.loads(detail["blocks"]) if b.get("auxiliary") and b.get("method") == "layout_markdown"]
                    if auxiliary:
                        with ui.expansion("Readable layout view").classes("w-full"):
                            ui.label("Layout-assisted reading view. Citations retain their original extracted quotations.").classes("fineprint")
                            ui.markdown(auxiliary[0]["text"]).classes("w-full")
                    ui.label("PDF file pages are used; printed reporter numbering may differ.").classes("fineprint")

    def zoom(self, value):
        self.scale = float(value)
        self.render.refresh()

    async def save(self):
        await background(self.context.services.evidence.save, self.context.workspace_id, self.chunk_id, self.quote)
        ui.notify("Passage saved to My Research", type="positive")


def source_dialog(context, doc_id, page=1, quote="", chunk_id=None, *, simple=False):
    with ui.dialog() as dialog, ui.card().classes("w-[900px] p-0"):
        with ui.row().classes("w-full justify-end px-3 pt-2"):
            ui.button(icon="close", on_click=dialog.close).props("flat round dense aria-label='Close source viewer'")
        viewer = SourceViewer(context, simple=simple)
        viewer.document_id, viewer.page, viewer.quote, viewer.chunk_id = doc_id, page, quote, chunk_id
        viewer.render()
    dialog.open()
