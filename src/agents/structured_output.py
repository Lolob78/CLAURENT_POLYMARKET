from dataclasses import dataclass
from typing import Literal


@dataclass
class AgentOutput:
    prob_true_yes: float
    confidence: int
    edge: float
    rationale: str
    side: Literal["YES", "NO"]

    def __post_init__(self):
        self.prob_true_yes = max(0.0, min(1.0, float(self.prob_true_yes)))
        self.confidence = max(0, min(100, int(self.confidence)))
        if self.side not in ("YES", "NO"):
            self.side = "YES"
