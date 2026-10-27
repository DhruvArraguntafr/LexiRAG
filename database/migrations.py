"""Additive v2 migration. Existing document/vector IDs and rows are preserved."""
import sqlite3


def migrate(connection, path):
    if connection.execute("PRAGMA user_version").fetchone()[0] >= 2:
        return
    backup = path.with_name(path.stem + ".pre-v2.sqlite3")
    if not backup.exists():
        with sqlite3.connect(backup) as destination:
            connection.backup(destination)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    additions = []
    for name, declaration in {"status": "TEXT NOT NULL DEFAULT 'ready'", "byte_size": "INTEGER NOT NULL DEFAULT 0"}.items():
        if name not in columns:
            additions.append(f"ALTER TABLE documents ADD COLUMN {name} {declaration};")
    connection.executescript("BEGIN IMMEDIATE;\n" + "\n".join(additions) + """
        UPDATE documents SET status=CASE WHEN warnings='[]' THEN 'ready' ELSE 'partial' END;
        CREATE TABLE IF NOT EXISTS document_pages (
          document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          page INTEGER NOT NULL, text TEXT NOT NULL, method TEXT NOT NULL,
          quality TEXT NOT NULL, warnings TEXT NOT NULL, blocks TEXT NOT NULL,
          width REAL NOT NULL, height REAL NOT NULL, PRIMARY KEY(document_id,page));
        CREATE TABLE IF NOT EXISTS workspaces (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        CREATE TABLE IF NOT EXISTS workspace_documents (
          workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          PRIMARY KEY(workspace_id,document_id));
        CREATE TABLE IF NOT EXISTS research_runs (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          question TEXT NOT NULL, resolved_question TEXT NOT NULL, kind TEXT NOT NULL,
          result_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        CREATE INDEX IF NOT EXISTS runs_workspace ON research_runs(workspace_id,created_at);
        CREATE TABLE IF NOT EXISTS findings (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          run_id TEXT REFERENCES research_runs(id) ON DELETE SET NULL, title TEXT NOT NULL,
          statement TEXT NOT NULL, kind TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
          tags TEXT NOT NULL DEFAULT '[]', relation TEXT NOT NULL DEFAULT 'supports',
          verification TEXT NOT NULL DEFAULT 'requires review',
          refs TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        CREATE TABLE IF NOT EXISTS evidence (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          finding_id TEXT REFERENCES findings(id) ON DELETE CASCADE,
          chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
          quote TEXT NOT NULL, question TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
          tags TEXT NOT NULL DEFAULT '[]', relation TEXT NOT NULL DEFAULT 'supports',
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        CREATE TABLE IF NOT EXISTS evidence_links (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          source_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
          target_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
          relation TEXT NOT NULL, note TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'user annotation');
        CREATE TABLE IF NOT EXISTS timeline_events (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          title TEXT NOT NULL, event_date TEXT NOT NULL, event_type TEXT NOT NULL,
          chunk_id TEXT REFERENCES chunks(id) ON DELETE CASCADE,
          quote TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL,
          UNIQUE(workspace_id,chunk_id,event_date,quote));
        CREATE TABLE IF NOT EXISTS briefs (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          title TEXT NOT NULL, question TEXT NOT NULL, content TEXT NOT NULL,
          finding_ids TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
          name TEXT NOT NULL, file_path TEXT NOT NULL, document_type TEXT NOT NULL,
          status TEXT NOT NULL, stage TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
          total INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
          cancel_requested INTEGER NOT NULL DEFAULT 0, document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        CREATE TABLE IF NOT EXISTS research_activity (
          id INTEGER PRIMARY KEY, workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, title TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        PRAGMA user_version=2;
        COMMIT;
    """)
