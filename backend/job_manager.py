from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from core.models import LexiRAGError


class JobCancelled(LexiRAGError):
    pass


class JobManager:
    def __init__(self, corpus, workspaces, documents):
        self.corpus, self.workspaces, self.documents, self.db = corpus, workspaces, documents, corpus.db
        self.pending = corpus.settings.data_dir / "pending"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lexirag-document")
        with self.db.connect() as con:
            con.execute("UPDATE jobs SET status='interrupted',message='Processing was interrupted. Choose Retry to resume safely.' WHERE status IN ('queued','running')")

    def list(self, workspace_id=None):
        with self.db.connect() as con:
            if workspace_id:
                rows = con.execute("SELECT * FROM jobs WHERE workspace_id=? ORDER BY created_at DESC,rowid DESC LIMIT 100", (workspace_id,))
            else:
                rows = con.execute("SELECT * FROM jobs ORDER BY created_at DESC,rowid DESC LIMIT 100")
            return [dict(r) for r in rows]

    def get(self, job_id):
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise LexiRAGError("Processing job not found.")
        return dict(row)

    def update(self, job_id, **values):
        allowed = {"status", "stage", "completed", "total", "message", "cancel_requested", "document_id"}
        if not set(values) <= allowed:
            raise ValueError("Invalid job update")
        with self.db.connect() as con:
            con.execute("UPDATE jobs SET " + ",".join(f"{key}=?" for key in values) + ",updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (*values.values(), job_id))

    def submit(self, name, content, workspace_id, category="Other"):
        self.workspaces.get(workspace_id)
        if not name.lower().endswith(".pdf") or not content.startswith(b"%PDF-") or len(content) > self.corpus.settings.max_upload_mb * 1024 * 1024:
            raise LexiRAGError("Upload a PDF within the configured size limit.")
        identifier = uuid4().hex
        path = self.pending / f"{identifier}.pdf"
        path.write_bytes(content)
        with self.db.connect() as con:
            con.execute("INSERT INTO jobs(id,workspace_id,name,file_path,document_type,status,stage) VALUES(?,?,?,?,?,'queued','Queued')",
                        (identifier, workspace_id, Path(name.replace('\\', '/')).name, str(path), category))
        self.pool.submit(self._run, identifier)
        return identifier

    def reindex(self, document_id, workspace_id):
        self.workspaces.assert_document(workspace_id, document_id)
        doc = self.db.document(document_id)
        identifier = uuid4().hex
        with self.db.connect() as con:
            con.execute("INSERT INTO jobs(id,workspace_id,name,file_path,document_type,status,stage,document_id) VALUES(?,?,?,?,?,'queued','Queued',?)",
                        (identifier, workspace_id, doc["name"], str(self.corpus.pdf_path(document_id)), doc["document_type"], document_id))
        self.pool.submit(self._run, identifier, True)
        return identifier

    def retry(self, job_id):
        job = self.get(job_id)
        if job["status"] in {"running", "queued"}:
            raise LexiRAGError("This job is already processing.")
        if job["document_id"]:
            with self.db.connect() as con:
                con.execute("UPDATE jobs SET file_path=? WHERE id=?", (str(self.corpus.pdf_path(job["document_id"])), job_id))
        elif not Path(job["file_path"]).exists():
            raise LexiRAGError("Upload the PDF again; the retained job file is unavailable.")
        self.update(job_id, cancel_requested=0, status="queued", stage="Queued", message="Retry queued", completed=0, total=0)
        self.pool.submit(self._run, job_id, bool(job["document_id"]))

    def cancel(self, job_id):
        self.update(job_id, cancel_requested=1)

    def _run(self, job_id, reindex=False):
        try:
            job = self.get(job_id)
            def progress(stage, completed=0, total=0, message=""):
                if self.get(job_id)["cancel_requested"] and stage != "Building search index":
                    raise JobCancelled("Cancelled at a safe processing boundary. No partial index was committed.")
                self.update(job_id, status="running", stage=stage, completed=completed, total=total, message=message)
            progress("Inspecting document")
            if reindex:
                outcome = self.documents.reindex(job["document_id"], progress)
            else:
                outcome = self.corpus.upload(job["name"], Path(job["file_path"]).read_bytes(), job["document_type"], progress=progress)
            if job["workspace_id"]:
                self.workspaces.attach(job["workspace_id"], outcome["id"])
                self.workspaces.activity(job["workspace_id"], "upload", job["name"])
            self.update(job_id, status="partial" if outcome.get("warnings") else "completed", stage="Completed",
                        document_id=outcome["id"], completed=1, total=1, message="Indexed with extraction warnings" if outcome.get("warnings") else "Ready for research")
            if not reindex:
                Path(job["file_path"]).unlink(missing_ok=True)
        except JobCancelled as exc:
            self.update(job_id, status="cancelled", stage="Cancelled", message=str(exc))
        except Exception as exc:
            message = str(exc) if isinstance(exc, LexiRAGError) else "Processing failed. Check PDF integrity and available disk space, then retry."
            self.update(job_id, status="failed", stage="Needs attention", message=message)

    def shutdown(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
