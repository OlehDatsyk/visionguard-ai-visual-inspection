"""Plain data structures shared by the vision modules."""
from dataclasses import dataclass, field

SCORE_MODEL = "model_confidence"
SCORE_HEURISTIC = "heuristic_anomaly"
SCORE_QUALITY = "image_quality"


def confidence_band(score: float, score_type: str) -> str:
    """Translate a score to a UI band.

    Model confidences use the full scale. Heuristic scores are uncalibrated measurements of how
    unusual a region looks, so they can never reach "high"; they top out at "medium".
    """
    if score_type == SCORE_MODEL:
        return "high" if score >= 0.70 else "medium" if score >= 0.45 else "low" if score >= 0.25 else "unverified"
    if score_type == SCORE_HEURISTIC:
        return "medium" if score >= 0.70 else "low" if score >= 0.45 else "unverified"
    return "unverified"


@dataclass
class Box:
    x: float
    y: float
    width: float
    height: float

    def scaled(self, factor: float) -> "Box":
        return Box(self.x * factor, self.y * factor, self.width * factor, self.height * factor)

    def iou(self, other: "Box") -> float:
        ix = max(0.0, min(self.x + self.width, other.x + other.width) - max(self.x, other.x))
        iy = max(0.0, min(self.y + self.height, other.y + other.height) - max(self.y, other.y))
        inter = ix * iy
        union = self.width * self.height + other.width * other.height - inter
        return inter / union if union > 0 else 0.0


@dataclass
class ObjectDetection:
    label: str
    confidence: float
    box: Box
    polygon: list[list[float]] | None = None
    segmentation_method: str | None = None


@dataclass
class DefectCandidate:
    category: str
    score: float
    score_type: str
    box: Box
    method: str
    explanation: str
    polygon: list[list[float]] | None = None
    metrics: dict = field(default_factory=dict)
    finding_type: str = "potential_defect"


@dataclass
class PipelineResult:
    objects: list[ObjectDetection]
    findings: list[DefectCandidate]
    quality: dict
    notes: list[str]
    unsupported: list[dict]
    processing_ms: dict
