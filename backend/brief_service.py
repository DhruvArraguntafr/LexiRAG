import json
from uuid import uuid4

from core.models import LexiRAGError

BRIEF_SECTIONS = ["Background", "Relevant legal provisions", "Relevant judgments", "Key findings",
                  "Evidence analysis", "Potentially contrary evidence", "Limitations and unresolved questions", "Conclusion"]


class BriefService:
    def __init__(self, evidence):
        self.evidence, self.workspaces, self.db = evidence, evidence.workspaces, evidence.db

    def generate(self, workspace_id, title, question, selections):
        """Compose a fully editable document from selected VERIFIED source refs.

        No extra model call invents text to fill absent brief sections.
        selections is ordered [(finding_id, section_name), ...].
        """
        if not title.strip() or not question.strip() or not selections:
            raise LexiRAGError("Add a title, research question and at least one selected finding.")
        available = {f["id"]: f for f in self.evidence.findings(workspace_id)}
        grouped, sources, source_numbers = {}, {}, {}
        for finding_id, section in selections:
            finding = available.get(finding_id)
            if not finding or not finding["valid_sources"]:
                raise LexiRAGError("A selected finding has unavailable evidence. Review it and regenerate research.")
            if section not in BRIEF_SECTIONS:
                raise LexiRAGError("Unknown brief section.")
            refs = []
            for ref in json.loads(finding["refs"]):
                chunk = self.evidence.validate(workspace_id, ref["chunk_id"], ref["quote"])
                key = chunk.id, ref["quote"]
                sid = source_numbers.setdefault(key, f"B{len(source_numbers) + 1}")
                refs.append(f"[{sid}]")
                sources[sid] = f"[{sid}] {chunk.document_name} · PDF page {chunk.page}" + (f" · {chunk.locator}" if chunk.locator else "") + f"\n\n> {ref['quote']}"
            grouped.setdefault(section, []).append(f"### {finding['title']}\n\n{finding['kind'].title()} — {finding['statement']} {' '.join(refs)}")
        parts = [f"# {title.strip()}", f"## Research question\n\n{question.strip()}"]
        for section in BRIEF_SECTIONS:
            if section in grouped:
                parts.extend([f"## {section}", *grouped[section]])
        parts.extend(["## Limitations and unresolved questions",
                      "Prepared from the selected saved findings only. Unfilled sections lack selected evidence. Interpretations require review; this is research support, not legal advice.",
                      "## Source references", *sources.values()])
        content = "\n\n".join(parts)
        identifier = uuid4().hex
        with self.db.connect() as con:
            con.execute("INSERT INTO briefs(id,workspace_id,title,question,content,finding_ids) VALUES(?,?,?,?,?,?)",
                        (identifier, workspace_id, title.strip(), question.strip(), content, json.dumps([f for f, _ in selections])))
        self.workspaces.activity(workspace_id, "brief", title)
        return identifier, content

    def list(self, workspace_id):
        with self.db.connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM briefs WHERE workspace_id=? ORDER BY updated_at DESC", (workspace_id,))]

    def save(self, workspace_id, brief_id, content):
        if len(content) > 250000:
            raise LexiRAGError("Keep the brief below 250,000 characters.")
        with self.db.connect() as con:
            con.execute("UPDATE briefs SET content=?,updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE workspace_id=? AND id=?", (content, workspace_id, brief_id))

    def export(self, workspace_id, brief_id):
        brief = next((b for b in self.list(workspace_id) if b["id"] == brief_id), None)
        if not brief:
            raise LexiRAGError("Brief not found.")
        valid = {f["id"] for f in self.evidence.findings(workspace_id) if f["valid_sources"]}
        if not set(json.loads(brief["finding_ids"])) <= valid:
            raise LexiRAGError("Brief sources have changed or been removed. Regenerate the brief with current findings before export.")
        self.workspaces.activity(workspace_id, "report", brief["title"])
        return brief["content"]
