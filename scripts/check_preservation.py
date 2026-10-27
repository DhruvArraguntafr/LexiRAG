"""Snapshot or verify existing local data without changing the source corpus.

Run before edits: python -m scripts.check_preservation snapshot
Run after checks: python -m scripts.check_preservation verify
Artifacts are stored outside data/ so they cannot affect the manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "refactor-validation"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def connect_readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def snapshot():
    ARTIFACTS.mkdir(exist_ok=True)
    manifest = ARTIFACTS / "data-before.json"
    if manifest.exists():
        raise SystemExit("Snapshot already exists; keep the original baseline.")
    files = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / "data").rglob("*")
             if p.is_file() and not p.name.endswith(("-wal", "-shm"))}
    with connect_readonly(ROOT / "data/metadata.sqlite3") as source:
        with sqlite3.connect(ARTIFACTS / "before.sqlite3") as target:
            source.backup(target)
    with zipfile.ZipFile(ARTIFACTS / "source-before.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in ("backend", "config", "core", "database", "evaluation", "scripts", "tests", "ui", "utils", ".streamlit"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(ROOT))
        for pattern in ("*.py", "*.md", "*.txt", "*.ini", "*.bat", ".env.example", ".gitignore"):
            for path in ROOT.glob(pattern):
                archive.write(path, path.relative_to(ROOT))
    manifest.write_text(json.dumps(files, indent=2), encoding="utf-8")
    print(f"Snapshotted {len(files)} data files and a credential-free source archive.")


def verify():
    files = json.loads((ARTIFACTS / "data-before.json").read_text(encoding="utf-8"))
    changed = [name for name, value in files.items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != value]
    tables = {}
    with connect_readonly(ARTIFACTS / "before.sqlite3") as before, connect_readonly(ROOT / "data/metadata.sqlite3") as after:
        for (table,) in before.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            quoted = '"' + table.replace('"', '""') + '"'
            old = before.execute(f"SELECT * FROM {quoted}").fetchall()
            current = after.execute(f"SELECT * FROM {quoted}").fetchall()
            # repr preserves vector bytes as well as all scalar SQLite values.
            unchanged = sorted(map(repr, old)) == sorted(map(repr, current))
            tables[table] = {"rows": len(old), "unchanged": unchanged}
        integrity = after.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = after.execute("PRAGMA foreign_key_check").fetchall()
    result = {"existing_files": len(files), "changed_or_missing": changed, "tables": tables,
              "integrity_check": integrity, "foreign_key_violations": len(foreign_keys)}
    (ARTIFACTS / "preservation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    assert not changed and all(t["unchanged"] for t in tables.values())
    assert integrity == "ok" and not foreign_keys


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "verify"))
    args = parser.parse_args()
    snapshot() if args.action == "snapshot" else verify()
