from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class Proposal:
    label: dict[str, Any]
    confidence: float | None
    evidence: dict[str, Any]
    status: str = "REVIEW_REQUIRED"
    provider: str = "baseline"
    def to_dict(self): return asdict(self)

class AnnotationProvider:
    name = "base"
    supported_modalities: tuple[str, ...] = ()
    def annotate(self, sample, file_path) -> Proposal:
        raise NotImplementedError
