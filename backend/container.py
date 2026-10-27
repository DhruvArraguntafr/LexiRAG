from functools import lru_cache

from config.settings import Settings
from core.service import CorpusService
from core.ocr_engine import get_ocr
from backend.workspace_service import WorkspaceService
from backend.document_service import DocumentService
from backend.evidence_service import EvidenceService
from backend.research_service import ResearchService
from backend.timeline_service import TimelineService
from backend.brief_service import BriefService
from backend.job_manager import JobManager
from backend.source_service import SourceService


class Services:
    def __init__(self, settings=None, embeddings=None, generator=None):
        self.corpus = CorpusService(settings or Settings(), embeddings)
        self.settings = self.corpus.settings
        self.workspaces = WorkspaceService(self.corpus)
        self.documents = DocumentService(self.corpus, self.workspaces)
        self.evidence = EvidenceService(self.workspaces)
        self.research = ResearchService(self.workspaces, generator)
        self.timeline = TimelineService(self.evidence)
        self.briefs = BriefService(self.evidence)
        self.sources = SourceService(self.corpus)
        self.jobs = JobManager(self.corpus, self.workspaces, self.documents)
        self.ocr_health = {"ready": None, "message": "OCR startup check is pending.", "engine": "RapidOCR / ONNX Runtime"}

    def check_ocr(self):
        self.ocr_health = get_ocr(str(self.settings.data_dir / "ocr_models")).health_check()
        return self.ocr_health

    def close(self):
        self.jobs.shutdown()

    def reset(self):
        for job in self.jobs.list():
            if job["status"] in {"queued", "running"}:
                self.jobs.cancel(job["id"])
        self.jobs.shutdown()
        for path in self.jobs.pending.glob("*.pdf"):
            path.unlink(missing_ok=True)
        self.corpus.delete_all()
        self.sources._render.cache_clear()
        self.jobs = JobManager(self.corpus, self.workspaces, self.documents)


@lru_cache(maxsize=1)
def get_services():
    return Services()
