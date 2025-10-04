from pydantic import BaseModel
from typing import List

class ToxicLabel(BaseModel):
    label: str
    score: float

class ToxicityResponse(BaseModel):
    text: str
    threshold: float
    toxic_labels: List[ToxicLabel]