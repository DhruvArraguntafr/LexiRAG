"""Local OCR through RapidOCR's public API and CPU ONNX Runtime.

No Tesseract installation or Windows environment-variable configuration needed.
The bundled model is suitable for English and Chinese, not all Indian scripts.
"""
from functools import lru_cache
from pathlib import Path
from threading import RLock

from core.models import LexiRAGError


class LocalOCR:
    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)
        self.lock = RLock()
        self._engine = None

    def engine(self):
        if self._engine is None:
            from rapidocr import RapidOCR, EngineType
            self.model_dir.mkdir(parents=True, exist_ok=True)
            self._engine = RapidOCR(params={
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Cls.engine_type": EngineType.ONNXRUNTIME,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Det.model_dir": str(self.model_dir), "Cls.model_dir": str(self.model_dir),
                "Rec.model_dir": str(self.model_dir),
                "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            })
        return self._engine

    def recognize(self, image, scale_x=1.0, scale_y=1.0):
        try:
            with self.lock:
                result = self.engine()(image)
            texts = getattr(result, "txts", None)
            if not texts:
                return "", []
            scores = getattr(result, "scores", None)
            boxes = getattr(result, "boxes", None)
            blocks = []
            for index, text in enumerate(texts):
                score = float(scores[index]) if scores is not None else 0.0
                if not text.strip() or score < 0.45:
                    continue
                box = boxes[index] if boxes is not None else None
                rect = [float(min(p[0] for p in box)) * scale_x,
                        float(min(p[1] for p in box)) * scale_y,
                        float(max(p[0] for p in box)) * scale_x,
                        float(max(p[1] for p in box)) * scale_y] if box is not None else None
                blocks.append({"text": text.strip(), "bbox": rect, "confidence": score, "method": "rapidocr"})
            return "\n".join(block["text"] for block in blocks), blocks
        except Exception as exc:
            raise LexiRAGError("Automatic OCR could not read this page. Retry after checking that the local OCR models are available; other readable pages will still be indexed.") from exc

    def health_check(self):
        try:
            from PIL import Image, ImageDraw, ImageFont
            image = Image.new("RGB", (900, 160), "white")
            font_path = next((p for p in [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")] if p.exists()), None)
            font = ImageFont.truetype(str(font_path), 38) if font_path else ImageFont.load_default(size=38)
            ImageDraw.Draw(image).text((35, 45), "LEGAL OCR READY 2026", fill="black", font=font)
            text, _ = self.recognize(image)
            ready = "LEGAL" in text.upper() and "OCR" in text.upper()
            return {"ready": ready, "engine": "RapidOCR / ONNX Runtime (CPU)",
                    "languages": "English and Chinese model; other Indian scripts require validated recognition models",
                    "message": "Local OCR passed a real recognition check." if ready else "OCR loaded but did not pass its reading check. Retry setup or use a clearer scan."}
        except Exception:
            return {"ready": False, "engine": "RapidOCR / ONNX Runtime (CPU)",
                    "languages": "English default", "message": "OCR is unavailable. Reinstall project dependencies or retry model setup with an internet connection. Text PDFs remain usable."}


@lru_cache(maxsize=2)
def get_ocr(model_dir):
    return LocalOCR(model_dir)
