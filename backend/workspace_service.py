from uuid import uuid4

from core.models import LexiRAGError
from backend.serialization import encode_result, decode_result


class WorkspaceService:
    def __init__(self, corpus):
        self.corpus, self.db = corpus, corpus.db

    def create(self, title, description=""):
        if not title.strip() or len(title) > 180:
            raise LexiRAGError("Give the workspace a title of 1–180 characters.")
        identifier = uuid4().hex
        with self.db.connect() as con:
            con.execute("INSERT INTO workspaces(id,title,description) VALUES(?,?,?)", (identifier, title.strip(), description[:2000]))
        return identifier

    def get(self, identifier):
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM workspaces WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise LexiRAGError("Workspace no longer exists. Choose another workspace.")
            return dict(row)

    def list(self):
        with self.db.connect() as con:
            return [dict(row) for row in con.execute("""SELECT w.*,
                (SELECT count(*) FROM workspace_documents d WHERE d.workspace_id=w.id) documents,
                (SELECT count(*) FROM findings f WHERE f.workspace_id=w.id) findings,
                (SELECT count(*) FROM research_runs r WHERE r.workspace_id=w.id) questions
                FROM workspaces w ORDER BY updated_at DESC,created_at DESC""")]

    def rename(self, identifier, title, description=""):
        self.get(identifier)
        if not title.strip() or len(title) > 180:
            raise LexiRAGError("Use a workspace title of 1–180 characters.")
        with self.db.connect() as con:
            con.execute("UPDATE workspaces SET title=?,description=?,updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (title.strip(), description[:2000], identifier))

    def delete(self, identifier):
        with self.db.connect() as con:
            con.execute("DELETE FROM workspaces WHERE id=?", (identifier,))

    def attach(self, workspace_id, document_id):
        self.get(workspace_id)
        if not self.db.document(document_id):
            raise LexiRAGError("Document is not indexed yet.")
        with self.db.connect() as con:
            con.execute("INSERT OR IGNORE INTO workspace_documents VALUES(?,?)", (workspace_id, document_id))
            con.execute("UPDATE workspaces SET updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (workspace_id,))

    def detach(self, workspace_id, document_id):
        with self.db.connect() as con:
            con.execute("DELETE FROM workspace_documents WHERE workspace_id=? AND document_id=?", (workspace_id, document_id))
            con.execute("DELETE FROM evidence WHERE workspace_id=? AND chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (workspace_id, document_id))
            con.execute("DELETE FROM timeline_events WHERE workspace_id=? AND chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (workspace_id, document_id))

    def documents(self, workspace_id):
        with self.db.connect() as con:
            ids = {r[0] for r in con.execute("SELECT document_id FROM workspace_documents WHERE workspace_id=?", (workspace_id,))}
        return [doc for doc in self.db.documents() if doc["id"] in ids]

    def document_ids(self, workspace_id):
        return tuple(doc["id"] for doc in self.documents(workspace_id))

    def assert_document(self, workspace_id, document_id):
        if document_id not in self.document_ids(workspace_id):
            raise LexiRAGError("This document is outside the current workspace.")

    def record_run(self, workspace_id, question, resolved, result, kind="research"):
        self.get(workspace_id)
        identifier = uuid4().hex
        with self.db.connect() as con:
            con.execute("INSERT INTO research_runs(id,workspace_id,question,resolved_question,kind,result_json) VALUES(?,?,?,?,?,?)",
                        (identifier, workspace_id, question, resolved, kind, encode_result(result)))
        self.activity(workspace_id, kind, question[:180])
        return identifier

    def runs(self, workspace_id, limit=60):
        with self.db.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM research_runs WHERE workspace_id=? ORDER BY created_at DESC,rowid DESC LIMIT ?", (workspace_id, limit))]

    def run(self, workspace_id, run_id):
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM research_runs WHERE workspace_id=? AND id=?", (workspace_id, run_id)).fetchone()
        if not row:
            raise LexiRAGError("Research session not found.")
        result = decode_result(row["result_json"])
        allowed = set(self.document_ids(workspace_id))
        if any(not self.db.chunk(h.chunk.id) or h.chunk.document_id not in allowed for h in result.sources.values()):
            raise LexiRAGError("Sources for this saved research have changed or were removed. Run the question again to refresh its evidence.")
        for hit in result.sources.values():
            hit.chunk = self.db.chunk(hit.chunk.id)
        return dict(row), result

    def activity(self, workspace_id, kind, title):
        with self.db.connect() as con:
            con.execute("INSERT INTO research_activity(workspace_id,kind,title) VALUES(?,?,?)", (workspace_id, kind, title[:180]))
            con.execute("UPDATE workspaces SET updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (workspace_id,))

    def recent_activity(self, workspace_id=None, limit=15):
        with self.db.connect() as con:
            if workspace_id:
                rows = con.execute("SELECT * FROM research_activity WHERE workspace_id=? ORDER BY id DESC LIMIT ?", (workspace_id, limit))
            else:
                rows = con.execute("SELECT * FROM research_activity ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in rows]
