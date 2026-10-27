import json
from uuid import uuid4

from core.citation_manager import normalize, verify_ref
from core.models import LexiRAGError

RELATIONS = ["supports", "potentially contrary", "requires verification"]


class EvidenceService:
    def __init__(self, workspaces):
        self.workspaces, self.db = workspaces, workspaces.db

    def validate(self, workspace_id, chunk_id, quote):
        chunk = self.db.chunk(chunk_id)
        if not chunk:
            raise LexiRAGError("The source passage was deleted or reindexed.")
        self.workspaces.assert_document(workspace_id, chunk.document_id)
        if len(quote.strip()) < 12 or normalize(quote) not in normalize(chunk.text):
            raise LexiRAGError("Save an exact quotation of at least 12 characters from the selected passage.")
        return chunk

    def save(self, workspace_id, chunk_id, quote, question="", notes="", tags=None, relation="supports", finding_id=None):
        self.validate(workspace_id, chunk_id, quote)
        if relation not in RELATIONS:
            raise LexiRAGError("Choose a supported evidence relationship.")
        identifier = uuid4().hex
        with self.db.connect() as con:
            if finding_id and not con.execute("SELECT id FROM findings WHERE id=? AND workspace_id=?", (finding_id, workspace_id)).fetchone():
                raise LexiRAGError("Finding does not belong to this workspace.")
            con.execute("INSERT INTO evidence(id,workspace_id,finding_id,chunk_id,quote,question,notes,tags,relation) VALUES(?,?,?,?,?,?,?,?,?)",
                        (identifier, workspace_id, finding_id, chunk_id, quote.strip(), question[:6000], notes[:10000], json.dumps(tags or []), relation))
        self.workspaces.activity(workspace_id, "evidence", "Saved source evidence")
        return identifier

    def save_finding(self, workspace_id, run_id, finding_index):
        _, result = self.workspaces.run(workspace_id, run_id)
        if not 0 <= finding_index < len(result.answer.findings):
            raise LexiRAGError("Finding is no longer available.")
        finding = result.answer.findings[finding_index]
        refs = []
        for ref in finding.evidence:
            if not verify_ref(ref, result.sources):
                raise LexiRAGError("Citation verification failed; this finding was not saved.")
            hit = result.sources[ref.source_id]
            self.validate(workspace_id, hit.chunk.id, ref.quote)
            refs.append({"chunk_id": hit.chunk.id, "quote": ref.quote})
        identifier = uuid4().hex
        with self.db.connect() as con:
            con.execute("INSERT INTO findings(id,workspace_id,run_id,title,statement,kind,refs) VALUES(?,?,?,?,?,?,?)",
                        (identifier, workspace_id, run_id, finding.heading, finding.statement, finding.kind, json.dumps(refs)))
        for ref in refs:
            self.save(workspace_id, ref["chunk_id"], ref["quote"], result.question, finding_id=identifier)
        return identifier

    def list(self, workspace_id):
        with self.db.connect() as con:
            return [dict(r) for r in con.execute("""SELECT e.*,c.document_id,c.document_name,c.page,c.locator,c.text FROM evidence e
               JOIN chunks c ON c.id=e.chunk_id JOIN workspace_documents w ON w.document_id=c.document_id AND w.workspace_id=e.workspace_id
               WHERE e.workspace_id=? ORDER BY e.created_at DESC,e.rowid DESC""", (workspace_id,))]

    def findings(self, workspace_id):
        with self.db.connect() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM findings WHERE workspace_id=? ORDER BY created_at,rowid", (workspace_id,))]
        for row in rows:
            row["valid_sources"] = True
            for ref in json.loads(row["refs"]):
                try:
                    self.validate(workspace_id, ref["chunk_id"], ref["quote"])
                except LexiRAGError:
                    row["valid_sources"] = False
        return rows

    def update(self, workspace_id, evidence_id, notes, tags, relation):
        if relation not in RELATIONS:
            raise LexiRAGError("Choose a supported evidence relationship.")
        with self.db.connect() as con:
            con.execute("UPDATE evidence SET notes=?,tags=?,relation=? WHERE id=? AND workspace_id=?", (notes[:10000], json.dumps(tags), relation, evidence_id, workspace_id))

    def delete(self, workspace_id, evidence_id):
        with self.db.connect() as con:
            con.execute("DELETE FROM evidence WHERE id=? AND workspace_id=?", (evidence_id, workspace_id))

    def link(self, workspace_id, source_id, target_id, relation, note):
        records = {e["id"] for e in self.list(workspace_id)}
        if source_id not in records or target_id not in records or source_id == target_id or not note.strip():
            raise LexiRAGError("Choose two different saved passages and explain the basis for the relationship.")
        if relation not in RELATIONS:
            raise LexiRAGError("Unknown evidence relationship.")
        identifier = uuid4().hex
        with self.db.connect() as con:
            con.execute("INSERT INTO evidence_links(id,workspace_id,source_id,target_id,relation,note) VALUES(?,?,?,?,?,?)", (identifier, workspace_id, source_id, target_id, relation, note[:2000]))
        return identifier
