"""Model interface. Any detector implementing this can be registered without touching the pipeline."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from app.vision.types import ObjectDetection


@dataclass(frozen=True)
class ModelInfo:
    key: str
    name: str
    model_type: str
    version: str
    licence: str
    source: str
    weights_file: str
    input_requirements: str
    processing: str
    supported_categories: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


class ObjectDetector(ABC):
    info: ModelInfo

    @abstractmethod
    def is_available(self) -> bool:
        """True when weights and runtime are present. Must not load the model."""

    @abstractmethod
    def unavailable_reason(self) -> str | None: ...

    @abstractmethod
    def detect(self, bgr: np.ndarray, confidence_threshold: float) -> list[ObjectDetection]:
        """Return detections in pixel coordinates of the given image."""
