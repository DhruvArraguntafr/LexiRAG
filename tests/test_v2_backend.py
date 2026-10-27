from dataclasses import replace
import json
import sqlite3
import time
from unittest.mock import patch

import pymupdf
import pytest

from backend.container import Services
from backend.serialization import decode_result, encode_result
from backend.workspace_service import WorkspaceService
from core.models import LexiRAGError, SearchFilters
from core.evidence_graph import build_graph
from core.timeline_builder import extract_events
from tests.conftest import ExtractiveTestGenerator, TestEmbeddings, make_pdf
from utils.reports import markdown_pdf


@pytest.fixture
def platform(populated):
    services = Services(populated.settings, populated.embeddings, ExtractiveTestGenerator())
    ws = services.workspaces.create("Privacy and agreements", "Controlled research test")
    for doc in services.corpus.db.documents():
        services.workspaces.attach(ws, doc["id"])
    yield services, ws
    services.close()


def test_workspaces_survive_restart_and_rename(platform):
    services, ws = platform
    services.workspaces.rename(ws, "Consumer rights", "Revised focus")
    reopened = WorkspaceService(services.corpus)
    assert reopened.get(ws)["title"] == "Consumer rights"
    assert len(reopened.documents(ws)) == 2


def test_workspace_isolation_including_empty_scope(platform):
    services, ws = platform
    empty = services.workspaces.create("Unrelated issue")
    with pytest.raises(LexiRAGError, match="Add indexed"):
        services.research.search(empty, "privacy")
    ids = services.workspaces.document_ids(ws)
    other = services.workspaces.create("Third workspace")
    services.workspaces.attach(other, ids[1])
    with pytest.raises(LexiRAGError, match="outside"):
        services.research.filters(other, [ids[0]])


def test_saved_conversation_and_followup_uses_fresh_sources(platform):
    services, ws = platform
    first_id, first = services.research.ask(ws, "Which privacy obligations apply?")
    second_id, second = services.research.ask(ws, "What about the second document?")
    row, result = services.workspaces.run(ws, second_id)
    assert "Previous USER question" in row["resolved_question"]
    assert first.answer.findings[0].statement not in row["resolved_question"]
    assert result.question == "What about the second document?"
    assert len(services.workspaces.runs(ws)) == 2
    assert decode_result(encode_result(second)).answer == second.answer


def test_evidence_saved_with_exact_quote_notes_tags_and_relationship(platform):
    services, ws = platform
    run_id, result = services.research.ask(ws, "privacy consent")
    finding_id = services.evidence.save_finding(ws, run_id, 0)
    evidence = services.evidence.list(ws)[0]
    assert evidence["finding_id"] == finding_id
    services.evidence.update(ws, evidence["id"], "Review enforceability", ["consent"], "requires verification")
    saved = services.evidence.list(ws)[0]
    assert saved["notes"] == "Review enforceability"
    assert json.loads(saved["tags"]) == ["consent"]
    with pytest.raises(LexiRAGError, match="exact quotation"):
        services.evidence.save(ws, evidence["chunk_id"], "This fabricated source phrase is not in the passage.")


def test_graph_edges_have_recorded_basis_and_user_annotations(platform):
    services, ws = platform
    run_id, result = services.research.ask(ws, "privacy notice", search_mode="Balanced search")
    services.evidence.save_finding(ws, run_id, 0)
    services.evidence.save_finding(ws, run_id, 1)
    evidence = services.evidence.list(ws)
    services.evidence.link(ws, evidence[0]["id"], evidence[1]["id"], "potentially contrary", "Compare each obligation's wording")
    graph = build_graph(services.evidence, ws)
    ids = {n["id"] for n in graph["nodes"]}
    assert all(e["basis"] and e["source"] in ids and e["target"] in ids for e in graph["links"])
    assert any(e["name"] == "potentially contrary" and "User annotation" in e["basis"] for e in graph["links"])


def test_deleted_workspace_retains_original_library(platform):
    services, ws = platform
    services.research.ask(ws, "privacy")
    services.workspaces.delete(ws)
    assert len(services.corpus.db.documents()) == 2
    assert not services.workspaces.runs(ws)


def test_detached_document_invalidates_saved_research(platform):
    services, ws = platform
    run_id, result = services.research.ask(ws, "privacy")
    services.evidence.save_finding(ws, run_id, 0)
    document_id = next(iter(result.sources.values())).chunk.document_id
    services.workspaces.detach(ws, document_id)
    with pytest.raises(LexiRAGError, match="changed or were removed"):
        services.workspaces.run(ws, run_id)
    assert not services.evidence.findings(ws)[0]["valid_sources"]


def test_timeline_explicit_dates_and_manual_entries(platform):
    services, ws = platform
    content = make_pdf(["Clause 4 Important dates\nThis agreement is dated 15 January 2025. The service begins on 1 February 2025 and ends on 31 January 2026."])
    document_id = services.corpus.upload("Dates.pdf", content)["id"]
    services.workspaces.attach(ws, document_id)
    assert services.timeline.extract(ws) == 3
    assert len(services.timeline.list(ws)) == 3
    services.timeline.extract(ws)
    assert len(services.timeline.list(ws)) == 3
    manual_id = services.timeline.save_manual(ws, "Review meeting", "2026-11-01", "Research milestone", "User annotation")
    services.timeline.save_manual(ws, "Moved meeting", "2026-11-02", "Research milestone", event_id=manual_id)
    assert any(e["origin"] == "manual annotation" and e["event_date"] == "2026-11-02" for e in services.timeline.list(ws))
    extracted = next(e for e in services.timeline.list(ws) if e["chunk_id"])
    with pytest.raises(LexiRAGError, match="cannot be edited"):
        services.timeline.save_manual(ws, "Changed source fact", "2020-01-01", "False", event_id=extracted["id"])


def test_ambiguous_numeric_dates_not_invented(service):
    document_id = service.upload("Dates.pdf", make_pdf(["The form says 01/02/2025 and records the year 2024. No explicit full written date is provided."]))["id"]
    assert not list(extract_events(service.db.chunks(SearchFilters(document_ids=(document_id,)))))


def test_brief_selected_findings_citations_edit_export_and_stale_guard(platform):
    services, ws = platform
    run_id, result = services.research.ask(ws, "privacy")
    finding_id = services.evidence.save_finding(ws, run_id, 0)
    brief_id, content = services.briefs.generate(ws, "Privacy research", "What obligations apply?", [(finding_id, "Key findings")])
    assert "[B1]" in content and "PDF page" in content
    services.briefs.save(ws, brief_id, content + "\n\nUser review notes.")
    exported = services.briefs.export(ws, brief_id)
    assert "User review notes." in exported
    with pymupdf.open(stream=markdown_pdf(exported), filetype="pdf") as pdf:
        assert "Privacy research" in "".join(p.get_text() for p in pdf)
    ref = json.loads(services.evidence.findings(ws)[0]["refs"])[0]
    document_id = services.corpus.db.chunk(ref["chunk_id"]).document_id
    services.corpus.delete(document_id)
    with pytest.raises(LexiRAGError, match="sources have changed"):
        services.briefs.export(ws, brief_id)


def wait_job(services, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = services.jobs.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    raise AssertionError("Background document job did not finish")


def test_background_upload_retries_and_no_partial_metadata(platform):
    services, ws = platform
    initial = len(services.corpus.db.documents())
    job_id = services.jobs.submit("Damaged.pdf", b"%PDF-broken", ws)
    assert wait_job(services, job_id)["status"] == "failed"
    assert len(services.corpus.db.documents()) == initial
    path = services.jobs.get(job_id)["file_path"]
    from pathlib import Path
    Path(path).write_bytes(make_pdf(["Clause 9 Privacy\nNew consent and privacy obligations are contained in this document."]))
    services.jobs.retry(job_id)
    assert wait_job(services, job_id)["status"] == "completed"
    assert len(services.workspaces.documents(ws)) == initial + 1


def test_reindex_keeps_membership_and_valid_evidence(platform):
    services, ws = platform
    doc_id = services.workspaces.document_ids(ws)[0]
    before = {c.id for c in services.corpus.db.chunks(SearchFilters(document_ids=(doc_id,)))}
    services.documents.reindex(doc_id)
    after = {c.id for c in services.corpus.db.chunks(SearchFilters(document_ids=(doc_id,)))}
    assert before == after
    assert doc_id in services.workspaces.document_ids(ws)


def test_source_coordinates_and_page_render(platform):
    services, ws = platform
    run_id, result = services.research.ask(ws, "termination notice")
    ref = result.answer.findings[0].evidence[0]
    chunk = result.sources[ref.source_id].chunk
    rects, label = services.sources.locations(chunk.document_id, chunk.page, ref.quote)
    assert rects and "native" in label
    png, label = services.sources.render(chunk.document_id, chunk.page, ref.quote)
    assert png.startswith(b"\x89PNG")
    with pytest.raises(LexiRAGError, match="Invalid source page"):
        services.sources.render(chunk.document_id, 999)


def test_v2_api_workspace_creation_and_upload(platform, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import register_api
    services, ws = platform
    monkeypatch.setattr("backend.api.get_services", lambda: services)
    app = FastAPI()
    register_api(app)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["version"] == "2.0"
        created = client.post("/api/workspaces", json={"title": "API test"}).json()["id"]
        response = client.post(f"/api/workspaces/{created}/uploads", files={"file": ("API.pdf", make_pdf(["Privacy obligations are confirmed in this teaching API document."]), "application/pdf")})
        assert response.status_code == 200
        assert wait_job(services, response.json()["job_id"])["status"] == "completed"
        assert len(client.get("/api/documents", params={"workspace_id": created}).json()) == 1
        assert client.post(f"/api/workspaces/{created}/comparison", json={"question": "Compare"}).status_code == 404
        assert client.post(f"/api/workspaces/{created}/compare", json={"question": "Compare"}).status_code == 404


def test_additive_migration_preserves_existing_records_and_backup(tmp_path):
    from database.store import Database
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as con:
        con.executescript("""CREATE TABLE documents (
            id TEXT PRIMARY KEY,name TEXT NOT NULL,pages INTEGER NOT NULL,document_type TEXT NOT NULL,
            jurisdiction TEXT,legal_date TEXT,metadata_origin TEXT NOT NULL DEFAULT 'user supplied',
            embedding_model TEXT NOT NULL,uploaded_at TEXT NOT NULL DEFAULT '2026-01-01',warnings TEXT NOT NULL,scanned_pages TEXT NOT NULL);
            CREATE TABLE chunks(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            document_name TEXT NOT NULL,page INTEGER NOT NULL,text TEXT NOT NULL,locator TEXT,ordinal INTEGER NOT NULL,vector BLOB NOT NULL,dimension INTEGER NOT NULL);
            CREATE TABLE state(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL);
            INSERT INTO state VALUES(1,7);""")
        con.execute("INSERT INTO documents(id,name,pages,document_type,embedding_model,warnings,scanned_pages) VALUES(?,?,?,?,?,?,?)", ("a" * 64, "Legacy.pdf", 1, "Other", "test-only", "[]", "[]"))
        con.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?)", ("b" * 64, "a" * 64, "Legacy.pdf", 1, "Original privacy obligations remain intact.", None, 0, b"\0\0\x80?", 1))
    migrated = Database(path)
    assert migrated.revision() == 7
    assert migrated.documents()[0]["id"] == "a" * 64
    assert migrated.chunk("b" * 64).text == "Original privacy obligations remain intact."
    backup = path.with_name("legacy.pre-v2.sqlite3")
    assert backup.exists()
    Database(path)
    assert len(migrated.documents()) == 1
    with sqlite3.connect(backup) as con:
        assert con.execute("SELECT vector FROM chunks").fetchone()[0] == b"\0\0\x80?"


def test_background_cancellation_before_commit(platform):
    import threading
    services, ws = platform
    entered, release = threading.Event(), threading.Event()
    original = services.corpus.processor.process
    def controlled(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    before = len(services.corpus.db.documents())
    with patch.object(services.corpus.processor, "process", side_effect=controlled):
        job_id = services.jobs.submit("Cancel.pdf", make_pdf(["A teaching privacy contract with cancel-safe indexing."]), ws)
        assert entered.wait(5)
        services.jobs.cancel(job_id)
        release.set()
        assert wait_job(services, job_id)["status"] == "cancelled"
    assert len(services.corpus.db.documents()) == before


def test_reset_clears_active_research_and_can_accept_new_uploads(platform):
    services, ws = platform
    services.research.ask(ws, "privacy")
    services.reset()
    assert not services.workspaces.list()
    assert not services.corpus.db.documents()
    new = services.workspaces.create("New research")
    job_id = services.jobs.submit("New.pdf", make_pdf(["Privacy terms support a fresh research workspace after reset."]), new)
    assert wait_job(services, job_id)["status"] == "completed"
