# toxic_service.py
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List
from transformers import pipeline

# -------------------------
# 1. Inițializare API
# -------------------------
app = FastAPI(title="Toxicity Detection API",
              description="API pentru detecția de toxicitate în text, bazat pe modelul unitary/toxic-bert",
              version="1.0.0")

# -------------------------
# 2. Încarcă modelul o singură dată
# -------------------------
clf = pipeline(
    "text-classification",
    model="unitary/toxic-bert",
    tokenizer="unitary/toxic-bert",
    return_all_scores=True
)

# -------------------------
# 3. Modele Pydantic
# -------------------------
class TextIn(BaseModel):
    text: str = Field(..., example="You are so dumb!")
    threshold: float = Field(
        0.5,
        ge=0,
        le=1,
        description="Pragul peste care o etichetă este considerată toxică",
        example=0.5
    )


class ToxicLabel(BaseModel):
    label: str = Field(..., example="toxic")
    score: float = Field(..., example=0.87)


class TextOut(BaseModel):
    text: str = Field(..., example="You are so dumb!")
    threshold: float = Field(..., example=0.5)
    toxic_labels: List[ToxicLabel]

class Message(BaseModel):
    message: str = Field(..., example="Toxicity detection service is running.")

# -------------------------
# 4. Rute
# -------------------------
@app.get("/", summary="Health check",
         response_model=Message,
         response_description="Mesaj simplu de stare a serviciului")
def root():
    return Message(message="Toxicity detection service is running.")


@app.post(
    "/check",
    summary="Verifică textul pentru toxicitate",
    response_model=TextOut,
    response_description="Textul original, pragul și etichetele toxice cu scor > threshold"
)
def check_text(payload: TextIn):
    """
    Primește text și returnează etichetele toxice
    cu scor mai mare decât `threshold`.
    """
    results = clf(payload.text)[0]
    toxic = [
        {"label": r["label"], "score": r["score"]}
        for r in results
        if r["score"] >= payload.threshold
    ]
    return {
        "text": payload.text,
        "threshold": payload.threshold,
        "toxic_labels": toxic
    }
