"""Check original rows against the pre-change backup; never rewrite records."""
import hashlib
import json
from pathlib import Path
import sqlite3


def audit():
    root=Path("data/cross-document-validation")
    result={}
    with sqlite3.connect(f"file:{root.as_posix()}/before.sqlite3?mode=ro",uri=True) as before, sqlite3.connect(
        "file:data/metadata.sqlite3?mode=ro",uri=True) as after:
        for table in ("documents","chunks","document_pages","workspace_documents","research_runs","findings","evidence","briefs"):
            columns=before.execute(f"PRAGMA table_info({table})").fetchall()
            key_columns=[i for i,c in enumerate(columns) if c[5]]
            old=before.execute(f"SELECT * FROM {table}").fetchall()
            current=after.execute(f"SELECT * FROM {table}").fetchall()
            by_key={tuple(row[i] for i in key_columns):row for row in current}
            unchanged=all(by_key.get(tuple(row[i] for i in key_columns))==row for row in old)
            result[table]={"before":len(old),"after":len(current),"original_rows_unchanged":unchanged}
        result["revision_unchanged"]=before.execute("SELECT revision FROM state").fetchone()==after.execute("SELECT revision FROM state").fetchone()
    # Original bytes remain associated with their original content hash.
    with sqlite3.connect("file:data/metadata.sqlite3?mode=ro",uri=True) as con:
        ids=[r[0] for r in con.execute("SELECT id FROM documents")]
    result["original_pdf_hashes_valid"]=all(hashlib.sha256((Path("data/uploads")/(i+".pdf")).read_bytes()).hexdigest()==i for i in ids)
    root.joinpath("preservation.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
    assert all(value.get("original_rows_unchanged",True) for value in result.values() if isinstance(value,dict))
    assert result["revision_unchanged"] and result["original_pdf_hashes_valid"]


if __name__=="__main__":
    audit()
