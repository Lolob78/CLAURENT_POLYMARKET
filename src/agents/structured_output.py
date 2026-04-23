from pydantic import BaseModel, Field
from typing import Literal

class AgentOutput(BaseModel):
    prob_true_yes: float = Field(..., ge=0, le=1)
    confidence: int = Field(..., ge=0, le=100)
    edge: float
    rationale: str
    side: Literal["YES", "NO"]