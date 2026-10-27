from datetime import date
from uuid import uuid4

from core.models import LexiRAGError, SearchFilters
from core.timeline_builder import extract_events


class TimelineService:
    def __init__(self, evidence):
        self.evidence, self.workspaces, self.db = evidence, evidence.workspaces, evidence.db

    def extract(self, workspace_id):
        ids = self.workspaces.document_ids(workspace_id)
        if not ids:
            raise LexiRAGError("Add documents before extracting their dated events.")
        events = list(extract_events(self.db.chunks(SearchFilters(document_ids=ids))))
        with self.db.connect() as con:
            for event in events:
                self.evidence.validate(workspace_id, event["chunk_id"], event["quote"])
                con.execute("INSERT OR IGNORE INTO timeline_events(id,workspace_id,title,event_date,event_type,chunk_id,quote,origin) VALUES(?,?,?,?,?,?,?,?)",
                            (uuid4().hex, workspace_id, event["title"], event["event_date"], event["event_type"], event["chunk_id"], event["quote"], event["origin"]))
        self.workspaces.activity(workspace_id, "timeline", "Extracted explicit source dates")
        return len(events)

    def list(self, workspace_id):
        with self.db.connect() as con:
            return [dict(row) for row in con.execute("""SELECT t.*,c.document_name,c.document_id,c.page,c.locator FROM timeline_events t
                LEFT JOIN chunks c ON c.id=t.chunk_id WHERE t.workspace_id=? ORDER BY t.event_date,t.id""", (workspace_id,))]

    def save_manual(self, workspace_id, title, event_date, event_type, notes="", event_id=None):
        self.workspaces.get(workspace_id)
        try:
            date.fromisoformat(event_date)
        except ValueError as exc:
            raise LexiRAGError("Use a valid calendar date in YYYY-MM-DD format.") from exc
        if not title.strip():
            raise LexiRAGError("Give the timeline event a title.")
        event_id = event_id or uuid4().hex
        with self.db.connect() as con:
            existing = con.execute("SELECT origin,workspace_id FROM timeline_events WHERE id=?", (event_id,)).fetchone()
            if existing and existing[1] != workspace_id:
                raise LexiRAGError("This event belongs to a different workspace.")
            if existing and existing[0] != "manual annotation":
                raise LexiRAGError("Source dates cannot be edited into different facts. Add a labeled manual annotation instead.")
            con.execute("INSERT INTO timeline_events(id,workspace_id,title,event_date,event_type,notes,origin) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,event_date=excluded.event_date,event_type=excluded.event_type,notes=excluded.notes",
                        (event_id, workspace_id, title[:180], event_date, event_type[:100], notes[:5000], "manual annotation"))
        return event_id

    def delete(self, workspace_id, event_id):
        with self.db.connect() as con:
            con.execute("DELETE FROM timeline_events WHERE workspace_id=? AND id=?", (workspace_id, event_id))
