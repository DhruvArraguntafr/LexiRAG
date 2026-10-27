from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from core.citation_manager import citation_label


def report_markdown(result):
    parts = ["# LexiRAG — Legal Research Report", "## Research question", result.question]
    if result.answer.insufficient_evidence:
        parts.append("Evidence is insufficient for a complete answer.")
    for finding in result.answer.findings:
        refs = ", ".join(f"[{r.source_id}]" for r in finding.evidence)
        parts.extend([f"## {finding.heading}", f"{finding.kind.title()}: {finding.statement} {refs}"])
        for ref in finding.evidence:
            parts.append(f"> [{ref.source_id}] {ref.quote}")
    if result.comparison_rows:
        parts.append("## Comparison findings")
        for row in result.comparison_rows:
            parts.extend(f"**{key}:** {value}" for key, value in row.items())
    parts.append("## Supporting evidence and citations")
    used = {ref.source_id for finding in result.answer.findings for ref in finding.evidence}
    for sid, hit in result.sources.items():
        if sid in used:
            parts.extend([citation_label(sid, hit), hit.chunk.text])
    parts.extend(["## Limitations and uncertainty", *result.answer.limitations,
                  "This system assists legal research and does not replace professional legal advice. "
                  "PDF page numbers refer to file pages, not printed reporter pagination. Citations validate provenance, not legal correctness."])
    return "\n\n".join(parts)


def _font():
    # Use an available Unicode TTF without downloading or adding binary assets.
    candidates = [(Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
                  (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))]
    for path, bold_path in candidates:
        if path.exists():
            if "LexiUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("LexiUnicode", str(path)))
                pdfmetrics.registerFont(TTFont("LexiUnicodeBold", str(bold_path if bold_path.exists() else path)))
                pdfmetrics.registerFontFamily("LexiUnicode", normal="LexiUnicode", bold="LexiUnicodeBold",
                                              italic="LexiUnicode", boldItalic="LexiUnicodeBold")
            return "LexiUnicode"
    return "Helvetica"


def report_pdf(result):
    return markdown_pdf(report_markdown(result), "LexiRAG Legal Research Report")


def markdown_pdf(markdown, title="LexiRAG Research Brief"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(21 * cm, 29.7 * cm), rightMargin=1.8 * cm, leftMargin=1.8 * cm,
                            title=title, author="LexiRAG")
    styles = getSampleStyleSheet()
    font = _font()
    for style in styles.byName.values():
        style.fontName = font
        style.alignment = TA_LEFT
        style.wordWrap = "CJK"
    styles["Normal"].leading = 15
    styles.add(ParagraphStyle("Evidence", parent=styles["Normal"], leftIndent=12,
                             textColor=colors.HexColor("#31556d")))
    story = []
    for block in markdown.split("\n\n"):
        style = "Title" if block.startswith("# ") else "Heading2" if block.startswith(("## ", "### ")) else "Evidence" if block.startswith("> ") else "Normal"
        text = block.lstrip("# ") if style in {"Title", "Heading2"} else block[2:] if style == "Evidence" else block
        # Escape untrusted content before introducing the limited markup that
        # this exporter supports. Markdown labels should not leak into the PDF.
        markup = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text)).replace("\n", "<br/>")
        paragraph = Paragraph(markup, styles[style])
        spacer = Spacer(1, 0.18 * cm)
        if style in {"Title", "Heading2"}:
            paragraph.keepWithNext = True
            spacer.keepWithNext = True
        story.extend([paragraph, spacer])

    def footer(canvas, document):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#496175"))
        canvas.drawString(1.8 * cm, cm, "LexiRAG | Evidence-backed legal research")
        canvas.drawRightString(19.2 * cm, cm, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
