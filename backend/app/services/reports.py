"""PDF inspection reports built from stored records only."""
import io
from datetime import UTC, datetime

import cv2
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from xml.sax.saxutils import escape

from app.core.storage import StorageError, get_storage
from app.models import ComparisonResult, InspectionProject, InspectionReport
from app.vision.comparison import LIMITATIONS, METRIC_EXPLANATIONS
from app.vision.detectors.registry import get_detector
from app.vision.profiles import CATEGORIES

NAVY = colors.HexColor("#0F1B2D")
ACCENT = colors.HexColor("#0E7C9B")
MUTED = colors.HexColor("#5B6878")
LINE = colors.HexColor("#D5DBE3")
PALE = colors.HexColor("#F2F5F8")

_base = getSampleStyleSheet()
BODY = ParagraphStyle("VGBody", parent=_base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=NAVY)
SMALL = ParagraphStyle("VGSmall", parent=BODY, fontSize=8, leading=10.5, textColor=MUTED)
CELL = ParagraphStyle("VGCell", parent=BODY, fontSize=8, leading=10.2)
CELL_HEAD = ParagraphStyle("VGCellHead", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
H1 = ParagraphStyle("VGH1", parent=BODY, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=12, spaceAfter=6, textColor=NAVY)
H2 = ParagraphStyle("VGH2", parent=BODY, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=4, textColor=ACCENT)
TITLE = ParagraphStyle("VGTitle", parent=BODY, fontName="Helvetica-Bold", fontSize=22, leading=27, alignment=TA_LEFT, textColor=NAVY)

REVIEW_LABELS = {
    "unreviewed": "Not reviewed", "confirmed": "Confirmed", "false_positive": "False positive",
    "needs_review": "Needs review", "resolved": "Resolved",
}
DISCLAIMER = [
    "VisionGuard AI is an AI-assisted inspection tool. It is not certified for safety-critical, medical, structural "
    "or regulatory inspections. Qualified people must verify findings before any important technical or safety decision.",
    "Potential defects are image-processing heuristics that measure visual unusualness. Unless a reviewer's decision "
    "says otherwise, they are unverified and must not be read as confirmed defects.",
    "Scores are not probabilities of correctness. Heuristic scores are uncalibrated, and object-detector confidence is "
    "an internal model score. Absence of a finding does not mean absence of a defect.",
    "Only visible surfaces in the supplied photos were analysed. Lighting, angle, focus and resolution affect results.",
]


def _p(text, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _table(rows: list[list], widths: list[float]) -> Table:
    data = [[_p(c, CELL_HEAD) for c in rows[0]]] + [[_p(c, CELL) for c in row] for row in rows[1:]]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return table


def _picture(data: bytes, max_w: float, max_h: float) -> RLImage:
    width, height = ImageReader(io.BytesIO(data)).getSize()
    ratio = min(max_w / width, max_h / height)
    return RLImage(io.BytesIO(data), width * ratio, height * ratio)


def _heatmap_small(data: bytes) -> bytes:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    scale = min(1.0, 1100 / max(image.shape[:2]))
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes()


class _NumberedCanvas(Canvas):
    """Adds branding and 'page X of Y' to every page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            width, height = A4
            self.setFillColor(NAVY)
            self.rect(0, height - 12 * mm, width, 12 * mm, stroke=0, fill=1)
            self.setFillColor(colors.white)
            self.setFont("Helvetica-Bold", 10)
            self.drawString(18 * mm, height - 8 * mm, "VisionGuard AI")
            self.setFont("Helvetica", 8)
            self.drawRightString(width - 18 * mm, height - 8 * mm, "Intelligent Visual Inspection Platform")
            self.setFillColor(MUTED)
            self.drawString(18 * mm, 9 * mm, "AI-assisted findings require human verification.")
            self.drawRightString(width - 18 * mm, 9 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def build_report_pdf(db, project: InspectionProject, title: str, final_notes: str) -> tuple[bytes, int]:
    storage = get_storage()
    images = [i for i in project.images if i.kind == "inspection"]
    all_findings = [f for image in images for f in image.findings]
    potential = [f for f in all_findings if f.finding_type == "potential_defect"]
    manual = [f for f in all_findings if f.finding_type == "manual_inspection"]
    objects = [o for image in images for o in image.objects]
    reviewed = [f for f in all_findings if f.review_status != "unreviewed"]
    insufficient = [f for f in potential if f.confidence_band == "unverified"]
    content_width = A4[0] - 36 * mm
    now = datetime.now(UTC)
    story: list = [Spacer(1, 6 * mm), _p(title, TITLE), Spacer(1, 3 * mm)]
    story.append(_p(f"Report generated {now:%d %B %Y, %H:%M} UTC", SMALL))
    if project.workspace.is_demo:
        story.append(_p("DEMONSTRATION DATA: this report uses generated sample records, not a real inspection.", H2))

    story.append(_p("Project information", H1))
    info = [
        ["Field", "Value"], ["Project", project.name],
        ["Inspection type", CATEGORIES.get(project.category, {}).get("label", project.category)],
        ["Status", project.status.replace("_", " ").capitalize()],
        ["Project created", f"{project.created_at:%d %B %Y}"],
        ["Last analysis", max((f"{i.analysed_at:%d %B %Y}" for i in images if i.analysed_at), default="Not analysed")],
        ["Images", str(len(images))],
    ]
    if project.description:
        info.append(["Description", project.description])
    story.append(_table(info, [40 * mm, content_width - 40 * mm]))

    story.append(_p("Analysis summary", H1))
    story.append(_table([
        ["Measure", "Count"], ["Images analysed", sum(1 for i in images if i.status == "analysed")],
        ["Objects detected", len(objects)], ["Potential defects (unverified until reviewed)", len(potential)],
        ["Potential defects with insufficient confidence", len(insufficient)],
        ["Areas requiring manual inspection", len(manual)],
        ["Findings with a recorded review decision", f"{len(reviewed)} of {len(all_findings)}"],
    ], [content_width - 30 * mm, 30 * mm]))
    detector = get_detector()
    state = "installed" if detector.is_available() else "not installed, so object detection did not run"
    story.append(Spacer(1, 2 * mm))
    story.append(_p(f"Object detector: {detector.info.name} ({state}). Defect methods: OpenCV image-processing heuristics.", SMALL))

    for number, image in enumerate(images, start=1):
        story.append(PageBreak())
        story.append(_p(f"Image {number}: {image.filename}", H1))
        meta = image.image_metadata
        story.append(_p(f"{meta.width} x {meta.height} px, {meta.file_format}, {meta.file_size / 1024:.0f} KB. SHA-256 {meta.checksum_sha256[:16]}...", SMALL))
        if image.description:
            story.append(_p(image.description, SMALL))
        story.append(Spacer(1, 2 * mm))
        try:
            original = _picture(storage.read(image.display_key), content_width / 2 - 2 * mm, 62 * mm)
            processed_data = storage.read(image.processed_key) if image.processed_key else None
            processed = _picture(processed_data, content_width / 2 - 2 * mm, 62 * mm) if processed_data else _p("Not analysed", SMALL)
            story.append(Table(
                [[_p("Uploaded image", SMALL), _p("Highlighted regions", SMALL)], [original, processed]],
                colWidths=[content_width / 2, content_width / 2],
                style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")],
            ))
        except StorageError:
            story.append(_p("An image file for this record is unavailable from storage.", SMALL))
        for note in image.analysis_notes or []:
            story.append(_p(f"Note: {note}", SMALL))
        if image.objects:
            story.append(_p("Detected objects", H2))
            rows = [["Object", "Model confidence", "Band", "Location (x, y, w, h)", "Outline"]]
            rows += [
                [o.label, f"{o.confidence:.2f}", o.confidence_band.capitalize(),
                 f"{o.x:.0f}, {o.y:.0f}, {o.width:.0f}, {o.height:.0f}",
                 "GrabCut (approximate)" if o.polygon else "Box only"]
                for o in sorted(image.objects, key=lambda o: -o.confidence)[:20]
            ]
            story.append(_table(rows, [38 * mm, 26 * mm, 22 * mm, 42 * mm, content_width - 128 * mm]))
        defects = [f for f in image.findings if f.finding_type == "potential_defect"]
        if defects:
            story.append(_p("Potential defects", H2))
            rows = [["ID", "Category", "Heuristic score", "Band", "Location", "Review decision"]]
            rows += [
                [f.code, f.category.replace("_", " "), f"{f.score:.2f}", f.confidence_band.capitalize(),
                 f"{f.x:.0f}, {f.y:.0f}, {f.width:.0f}, {f.height:.0f}", REVIEW_LABELS.get(f.review_status, f.review_status)]
                for f in defects
            ]
            story.append(_table(rows, [28 * mm, 34 * mm, 22 * mm, 20 * mm, 36 * mm, content_width - 140 * mm]))
            noted = [
                r for f in defects for r in f.reviews if r.note
            ]
            for review in noted[:10]:
                story.append(_p(f"Reviewer note ({review.decision.replace('_', ' ')}): {review.note}", SMALL))
        areas = [f for f in image.findings if f.finding_type == "manual_inspection"]
        if areas:
            story.append(_p("Areas requiring manual inspection", H2))
            for area in areas:
                story.append(_p(f"{area.code}: {area.explanation}", SMALL))
        if image.status == "analysed" and not image.objects and not image.findings:
            story.append(Spacer(1, 2 * mm))
            story.append(_p("No objects or findings were reported. This does not prove the absence of defects.", BODY))
        if image.unsupported_checks:
            story.append(_p("Not assessed", H2))
            for item in image.unsupported_checks:
                story.append(_p(f"{item['check'].replace('_', ' ').capitalize()}: {item['reason']}", SMALL))

    comparisons = list(db.scalars(
        select(ComparisonResult).where(ComparisonResult.project_id == project.id, ComparisonResult.status == "completed")
    ))
    if comparisons:
        story.append(PageBreak())
        story.append(_p("Image comparison results", H1))
        for comparison in comparisons:
            block: list = [_p(comparison.name, H2)]
            metrics = comparison.metrics
            block.append(_table([
                ["Metric", "Value", "Meaning"],
                ["SSIM", metrics.get("ssim"), METRIC_EXPLANATIONS["ssim"]],
                ["Changed area", f"{metrics.get('changed_area_pct')}%", METRIC_EXPLANATIONS["changed_area_pct"]],
                ["Alignment", str(metrics.get("alignment_status", "")).replace("_", " "), METRIC_EXPLANATIONS["feature_inlier_ratio"]],
            ], [28 * mm, 22 * mm, content_width - 50 * mm]))
            try:
                block.append(Spacer(1, 2 * mm))
                block.append(_picture(_heatmap_small(storage.read(f"{comparison.storage_prefix}/heatmap.jpg")), content_width, 70 * mm))
            except StorageError:
                pass
            for warning in comparison.warnings:
                block.append(_p(f"Warning: {warning}", SMALL))
            story.append(KeepTogether(block))
        for limitation in LIMITATIONS:
            story.append(_p(limitation, SMALL))

    story.append(PageBreak())
    story.append(_p("Final inspection notes", H1))
    notes = final_notes or project.notes
    story.append(_p(notes if notes else "No final notes were recorded."))
    story.append(_p("Limitations and disclaimers", H1))
    for line in DISCLAIMER:
        story.append(_p(line))
        story.append(Spacer(1, 1.5 * mm))

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=16 * mm,
        title=title, author="VisionGuard AI", subject="AI-assisted visual inspection report",
    )
    document.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue(), document.page


def create_report(db, project: InspectionProject, title: str | None, final_notes: str) -> InspectionReport:
    report_title = title or f"Inspection report: {project.name}"
    pdf, pages = build_report_pdf(db, project, report_title, final_notes)
    report = InspectionReport(
        project_id=project.id, title=report_title, final_notes=final_notes, storage_key="", file_size=len(pdf), page_count=pages,
    )
    db.add(report)
    db.flush()
    report.storage_key = f"{project.workspace.owner_id}/{project.workspace_id}/reports/{report.id}.pdf"
    get_storage().save(report.storage_key, pdf, "application/pdf")
    return report
