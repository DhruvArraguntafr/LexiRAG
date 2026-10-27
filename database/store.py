from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import sqlite3

import numpy as np

from core.models import Chunk, LexiRAGError, SearchFilters


class Database:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO state VALUES(1,0);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, pages INTEGER NOT NULL,
                    document_type TEXT NOT NULL, jurisdiction TEXT, legal_date TEXT,
                    metadata_origin TEXT NOT NULL DEFAULT 'user-supplied; verify against PDF',
                    embedding_model TEXT NOT NULL, uploaded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                    warnings TEXT NOT NULL, scanned_pages TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    document_name TEXT NOT NULL, page INTEGER NOT NULL CHECK(page>0), text TEXT NOT NULL,
                    locator TEXT, ordinal INTEGER NOT NULL, vector BLOB NOT NULL, dimension INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(document_id, ordinal);
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, latency REAL NOT NULL, mode TEXT NOT NULL,
                    rejected INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                );
            """)
            from database.migrations import migrate
            migrate(con, self.path)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def revision(self):
        with self.connect() as con:
            return con.execute("SELECT revision FROM state WHERE id=1").fetchone()[0]

    def documents(self):
        with self.connect() as con:
            return [dict(r) for r in con.execute("SELECT d.*, COUNT(c.id) AS chunks FROM documents d LEFT JOIN chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.uploaded_at DESC,d.name")]

    def document(self, doc_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def add(self, processed, vectors, model, document_type, jurisdiction, legal_date):
        if legal_date:
            try:
                date.fromisoformat(legal_date)
            except ValueError as exc:
                raise LexiRAGError("Legal date must be a verified ISO date (YYYY-MM-DD).") from exc
        vectors = np.ascontiguousarray(vectors, dtype="float32")
        if vectors.ndim != 2 or vectors.shape[0] != len(processed.chunks) or not np.isfinite(vectors).all():
            raise LexiRAGError("Invalid document embedding matrix.")
        if vectors.shape[1] == 0 or np.any(np.linalg.norm(vectors, axis=1) == 0):
            raise LexiRAGError("Embedding model returned empty or zero vectors.")
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        with self.connect() as con:
            con.execute("""INSERT INTO documents(id,name,pages,document_type,jurisdiction,legal_date,embedding_model,warnings,scanned_pages) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET pages=excluded.pages,embedding_model=excluded.embedding_model,warnings=excluded.warnings,scanned_pages=excluded.scanned_pages""", (
                processed.document_id, processed.name, processed.pages, document_type,
                jurisdiction or None, legal_date or None, model,
                json.dumps(processed.warnings), json.dumps(processed.scanned_pages),
            ))
            expected_ids = {chunk.id for chunk in processed.chunks}
            stale = [r[0] for r in con.execute("SELECT id FROM chunks WHERE document_id=?", (processed.document_id,)) if r[0] not in expected_ids]
            con.executemany("DELETE FROM chunks WHERE id=?", [(cid,) for cid in stale])
            for chunk, vector in zip(processed.chunks, vectors):
                con.execute("""INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    document_name=excluded.document_name,vector=excluded.vector,dimension=excluded.dimension""", (
                    chunk.id, chunk.document_id, chunk.document_name, chunk.page, chunk.text,
                    chunk.locator, chunk.ordinal, vector.astype("float32").tobytes(), len(vector),
                ))
            con.execute("DELETE FROM document_pages WHERE document_id=?", (processed.document_id,))
            for page in getattr(processed, "page_details", []):
                con.execute("INSERT INTO document_pages VALUES(?,?,?,?,?,?,?,?,?)", (
                    processed.document_id, page["page"], page["text"], page["method"], page["quality"],
                    json.dumps(page["warnings"]), json.dumps(page["blocks"]), page["width"], page["height"],
                ))
            status = "partial" if processed.warnings else "ready"
            con.execute("UPDATE documents SET status=? WHERE id=?", (status, processed.document_id))
            con.execute("UPDATE state SET revision=revision+1 WHERE id=1")

    def delete(self, doc_id):
        with self.connect() as con:
            con.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            con.execute("UPDATE state SET revision=revision+1 WHERE id=1")

    def chunks(self, filters: SearchFilters | None = None, with_vectors=False):
        filters = filters or SearchFilters()
        where, params = [], []
        if filters.document_ids:
            where.append("d.id IN (" + ",".join("?" for _ in filters.document_ids) + ")")
            params.extend(filters.document_ids)
        for field, value, operator in (
            ("document_type", filters.document_type, "="), ("jurisdiction", filters.jurisdiction, "="),
            ("legal_date", filters.date_from, ">="), ("legal_date", filters.date_to, "<="),
        ):
            if value:
                where.append(f"d.{field} {operator} ?")
                params.append(value)
        sql = "SELECT c.* FROM chunks c JOIN documents d ON c.document_id=d.id"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.document_id,c.ordinal"
        with self.connect() as con:
            rows = con.execute(sql, params).fetchall()
        chunks = [Chunk(**{key: row[key] for key in Chunk.__dataclass_fields__}) for row in rows]
        if not with_vectors:
            return chunks
        vectors = [np.frombuffer(row["vector"], dtype="float32").copy() for row in rows]
        if vectors and (len({len(v) for v in vectors}) != 1 or not all(np.isfinite(v).all() for v in vectors)):
            raise LexiRAGError("Stored embeddings are inconsistent. Restore the database or delete and re-upload affected documents.")
        return chunks, np.stack(vectors) if vectors else np.empty((0, 0), dtype="float32")

    def record_activity(self, kind, latency, mode, rejected=False):
        # Deliberately excludes user questions, answers and confidential excerpts.
        with self.connect() as con:
            con.execute("INSERT INTO activity(kind,latency,mode,rejected) VALUES(?,?,?,?)", (kind, latency, mode, int(rejected)))

    def analytics(self):
        with self.connect() as con:
            counts = dict(con.execute("SELECT COUNT(*) documents, COALESCE(SUM(pages),0) file_pages FROM documents").fetchone())
            counts["pages"] = con.execute("SELECT COUNT(*) FROM (SELECT DISTINCT document_id,page FROM chunks)").fetchone()[0]
            counts["chunks"] = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            counts["queries"] = con.execute("SELECT COUNT(*) FROM activity WHERE kind='research'").fetchone()[0]
            counts["categories"] = [dict(r) for r in con.execute("SELECT document_type, COUNT(*) count FROM documents GROUP BY document_type")]
            counts["recent"] = [dict(r) for r in con.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 20")]
            return counts

    def purge_activity(self):
        with self.connect() as con:
            con.execute("DELETE FROM activity")

    def clear_corpus(self):
        with self.connect() as con:
            con.execute("DELETE FROM workspaces")
            con.execute("DELETE FROM jobs")
            con.execute("DELETE FROM documents")
            con.execute("DELETE FROM activity")
            con.execute("UPDATE state SET revision=revision+1 WHERE id=1")

    def page(self, doc_id, page):
        with self.connect() as con:
            row = con.execute("SELECT * FROM document_pages WHERE document_id=? AND page=?", (doc_id, page)).fetchone()
            return dict(row) if row else None

    def chunk(self, chunk_id):
        with self.connect() as con:
            row = con.execute("SELECT id,document_id,document_name,page,text,locator,ordinal FROM chunks WHERE id=?", (chunk_id,)).fetchone()
            return Chunk(**dict(row)) if row else None
