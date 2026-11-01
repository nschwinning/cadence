"""Cadence sentiment-scoring sidecar.

A thin FastAPI service in front of a dynamically-quantized int8 FinBERT ONNX
model (baked into the image at build time). The Cadence backend reaches it only
through its ``SentimentScorer`` HTTP client:

- ``POST /score`` with ``{"texts": [...]}`` → ``{"scores": [{positive, neutral,
  negative}, ...]}``, one row per input text, in order (softmaxed probabilities).
- ``GET /health`` warm-loads the model at startup and reports healthy only once a
  real scoring pass has succeeded, so Compose gates the backend on a ready model.

Inference is pure ``onnxruntime`` + a fast tokenizer — no torch — to stay lean on
the Raspberry Pi. Logit columns are mapped to canonical tone names via the
model's own ``id2label``, never positional guesswork.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from transformers import AutoTokenizer

logger = logging.getLogger("sentiment-service")
logging.basicConfig(level=logging.INFO)

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/models/finbert"))
MAX_LENGTH = int(os.environ.get("MAX_LENGTH", "512"))
_CANONICAL = ("positive", "neutral", "negative")

app = FastAPI(title="Cadence sentiment service")

# Module-level model state, populated at startup. `ready` stays False until a
# warm scoring pass succeeds, which is what `/health` gates on.
_state: dict[str, Any] = {
    "ready": False,
    "session": None,
    "tokenizer": None,
    "input_names": set(),
    "columns": {},
}


class ScoreRequest(BaseModel):
    texts: list[str]


class Score(BaseModel):
    positive: float
    neutral: float
    negative: float


class ScoreResponse(BaseModel):
    scores: list[Score]


def _label_columns() -> dict[str, int]:
    """Map canonical tone names → logit column index from the model config."""
    config = json.loads((MODEL_DIR / "config.json").read_text())
    id2label = config.get("id2label") or {}
    columns: dict[str, int] = {}
    for idx, label in id2label.items():
        name = str(label).strip().lower()
        if name in _CANONICAL:
            columns[name] = int(idx)
    missing = [name for name in _CANONICAL if name not in columns]
    if missing:
        raise RuntimeError(f"model config missing tone labels: {missing}")
    return columns


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


def _score_texts(texts: list[str]) -> list[Score]:
    tokenizer = _state["tokenizer"]
    session: ort.InferenceSession = _state["session"]
    columns: dict[str, int] = _state["columns"]
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=MAX_LENGTH,
        return_tensors="np",
    )
    feed = {
        name: value.astype(np.int64)
        for name, value in encoded.items()
        if name in _state["input_names"]
    }
    logits = np.asarray(session.run(None, feed)[0], dtype=np.float32)
    probs = _softmax(logits)
    return [
        Score(
            positive=float(row[columns["positive"]]),
            neutral=float(row[columns["neutral"]]),
            negative=float(row[columns["negative"]]),
        )
        for row in probs
    ]


@app.on_event("startup")
def _load_model() -> None:
    try:
        tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
        session = ort.InferenceSession(
            str(MODEL_DIR / "model_quantized.onnx"),
            providers=["CPUExecutionProvider"],
        )
        _state.update(
            tokenizer=tokenizer,
            session=session,
            input_names={inp.name for inp in session.get_inputs()},
            columns=_label_columns(),
        )
        # Warm scoring pass — only flip ready once the model can actually score.
        _score_texts(["The company reported record quarterly earnings."])
        _state["ready"] = True
        logger.info("sentiment model loaded and warmed")
    except Exception:  # noqa: BLE001 - log and stay unhealthy, do not crash the server
        logger.exception("failed to load sentiment model")


@app.get("/health")
def health() -> Any:
    if not _state["ready"]:
        return JSONResponse(status_code=503, content={"status": "loading"})
    return {"status": "ok"}


@app.post("/score", response_model=ScoreResponse)
def score(request: ScoreRequest) -> ScoreResponse:
    if not _state["ready"]:
        raise HTTPException(status_code=503, detail="model not ready")
    if not request.texts:
        return ScoreResponse(scores=[])
    return ScoreResponse(scores=_score_texts(request.texts))
