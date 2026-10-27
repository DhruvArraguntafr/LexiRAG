"""Same-process local FastAPI endpoints. Bound to loopback by the launcher."""
import asyncio
import json

from fastapi import UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel, Field

from backend.container import get_services
from backend.serialization import encode_result
from core.models import LexiRAGError


class WorkspaceInput(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = ""


class QuestionInput(BaseModel):
    question: str = Field(min_length=1, max_length=6000)
    search_mode: str = "Balanced search"
    document_ids: list[str] | None = None


def register_api(app):
    @app.exception_handler(LexiRAGError)
    async def known_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/health")
    def health():
        services = get_services()
        return {"status": "ok", "version": "2.0", "ocr": services.ocr_health,
                "gemini_configured": bool(services.settings.api_key)}

    @app.get("/api/workspaces")
    def workspaces():
        return get_services().workspaces.list()

    @app.post("/api/workspaces")
    def create_workspace(value: WorkspaceInput):
        return {"id": get_services().workspaces.create(value.title, value.description)}

    @app.post("/api/workspaces/{workspace_id}/uploads")
    async def upload(workspace_id: str, file: UploadFile = File(...)):
        services = get_services()
        limit = services.settings.max_upload_mb * 1024 * 1024
        content = await file.read(limit + 1)
        if len(content) > limit:
            raise HTTPException(413, "PDF exceeds the upload limit.")
        identifier = await asyncio.to_thread(services.jobs.submit, file.filename or "upload.pdf", content, workspace_id)
        return {"job_id": identifier}

    @app.get("/api/jobs")
    def jobs(workspace_id: str | None = None):
        # Do not expose internal filesystem paths through the UI API.
        return [{k: v for k, v in job.items() if k != "file_path"} for job in get_services().jobs.list(workspace_id)]

    @app.post("/api/jobs/{job_id}/{action}")
    def job_action(job_id: str, action: str):
        if action not in {"cancel", "retry"}:
            raise HTTPException(404)
        getattr(get_services().jobs, action)(job_id)
        return {"ok": True}

    @app.get("/api/documents")
    def documents(workspace_id: str | None = None):
        services = get_services()
        return services.workspaces.documents(workspace_id) if workspace_id else services.corpus.db.documents()

    @app.get("/api/documents/{document_id}/original")
    def original(document_id: str):
        services = get_services()
        doc = services.corpus.db.document(document_id)
        if not doc:
            raise HTTPException(404, "Document not found.")
        path = services.corpus.pdf_path(document_id)
        if not path.exists():
            raise HTTPException(404, "Original PDF missing from local storage.")
        return FileResponse(path, media_type="application/pdf", filename=doc["name"], content_disposition_type="inline")

    @app.get("/api/documents/{document_id}/pages/{page}/preview")
    async def preview(document_id: str, page: int, quote: str = Query("", max_length=6000), scale: float = 1.5):
        content, label = await asyncio.to_thread(get_services().sources.render, document_id, page, quote, scale)
        return Response(content, media_type="image/png", headers={"Cache-Control": "private, no-store"})

    @app.post("/api/workspaces/{workspace_id}/research")
    async def research(workspace_id: str, value: QuestionInput):
        identifier, result = await asyncio.to_thread(get_services().research.ask, workspace_id, value.question, value.search_mode, value.document_ids)
        return {"id": identifier, "result": json.loads(encode_result(result))}
