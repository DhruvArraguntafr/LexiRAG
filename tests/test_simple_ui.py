"""Regression checks for the simplified flow and legacy-library migration."""
import pytest

from backend.container import Services
from tests.conftest import ExtractiveTestGenerator
from ui.layout import NAVIGATION
from ui.simple_helpers import progress_text, research_collection


@pytest.fixture
def platform(populated):
    services = Services(populated.settings, populated.embeddings, ExtractiveTestGenerator())
    yield services
    services.close()


def test_exactly_three_destinations_and_no_advanced_routes():
    assert [label for _, label, _ in NAVIGATION] == ["Home", "AI Research", "My Research"]
    import ast
    from pathlib import Path
    module = ast.parse(Path("main.py").read_text(encoding="utf-8"))
    routes = next(node.value for node in module.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PAGES" for t in node.targets))
    assert {key.value for key in routes.keys} == {route for route, _, _ in NAVIGATION}


def test_first_collection_adopts_legacy_pdfs_and_is_reused(platform):
    identifier = research_collection(platform)
    assert set(platform.workspaces.document_ids(identifier)) == {d["id"] for d in platform.corpus.db.documents()}
    assert research_collection(platform, identifier) == identifier
    assert research_collection(platform) == identifier
    assert len(platform.workspaces.list()) == 1


def test_empty_existing_collection_keeps_its_scope(platform):
    identifier = platform.workspaces.create("Deliberately empty")
    assert research_collection(platform, identifier) == identifier
    assert not platform.workspaces.document_ids(identifier)
    # A stale browser pointer reuses existing research instead of merging data.
    assert research_collection(platform, "removed-id") == identifier
    assert not platform.workspaces.document_ids(identifier)


@pytest.mark.parametrize("status,stage,expected", [
    ("queued", "Queued", "Waiting"), ("completed", "Completed", "Ready"),
    ("partial", "Completed", "clearer copy"), ("failed", "Error", "Try again"),
    ("interrupted", "Error", "Try again"), ("cancelled", "Cancelled", "Stopped"),
    ("running", "OCR page", "Reading"), ("running", "Building search index", "Preparing"),
])
def test_upload_progress_uses_plain_language(status, stage, expected):
    text = progress_text({"status": status, "stage": stage})
    assert expected in text
    assert not any(word in text for word in ("Tesseract", "embeddings", "index", "OCR"))
