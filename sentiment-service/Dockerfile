# Cadence sentiment-scoring sidecar — FinBERT via ONNX Runtime int8.
#
# Two stages: the builder exports + dynamically-quantizes ProsusAI/finbert to an
# int8 ONNX artifact (it needs torch + optimum, build-time only); the lean
# runtime copies that artifact in and serves it with pure onnxruntime — no torch
# — to stay RAM-light on the Raspberry Pi.

# ---- Stage 1: export + quantize (heavy, build-time only) --------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    # Fall back to plain HTTPS downloads instead of the xet CDN, which some
    # build networks cannot reach — keeps the artifact fetch reproducible.
    HF_HUB_DISABLE_XET=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# CPU-only torch keeps the builder image sane; optimum drives the ONNX export +
# dynamic quantization.
RUN pip install \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      "torch==2.5.1" \
      "optimum[onnxruntime]==1.23.3" \
      "transformers==4.46.3"

COPY export_model.py .
RUN python export_model.py /models/finbert

# ---- Stage 2: lean runtime (no torch) --------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_DIR=/models/finbert

WORKDIR /app

RUN pip install \
      "fastapi==0.115.5" \
      "uvicorn[standard]==0.32.1" \
      "onnxruntime==1.20.1" \
      "transformers==4.46.3" \
      "numpy==2.1.3"

COPY --from=builder /models/finbert /models/finbert
COPY app.py .

EXPOSE 8080

# Warm-loading /health gate: the model loads + runs a scoring pass at startup, so
# the endpoint only returns 200 once inference actually works.
HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=12 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health').status==200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
