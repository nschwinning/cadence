"""Build-time export of ProsusAI/finbert to a dynamically-quantized int8 ONNX.

Runs only in the Docker *builder* stage (which has torch + optimum). It produces
a self-contained model directory — the fast tokenizer, ``config.json`` (carrying
the authoritative ``id2label`` the runtime maps logits through), and a single
``model_quantized.onnx`` — that the lean runtime stage copies in and serves with
pure ``onnxruntime`` (no torch at inference time). Pinning a specific revision
keeps the baked artifact reproducible.
"""

from __future__ import annotations

import sys
from pathlib import Path

from optimum.onnxruntime import ORTModelForSequenceClassification, ORTQuantizer
from optimum.onnxruntime.configuration import AutoQuantizationConfig
from transformers import AutoTokenizer

# Pinned FinBERT artifact — paper-validated lineage (ProsusAI/finbert), 3-class tone.
MODEL_ID = "ProsusAI/finbert"
MODEL_REVISION = "4556d13015211d73dccd3fdd39d39232506f3e43"


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Export the fp32 ONNX graph + config, and the matching fast tokenizer.
    model = ORTModelForSequenceClassification.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, export=True
    )
    model.save_pretrained(out)
    AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION).save_pretrained(out)

    # Dynamic int8 quantization (weights only) — QOperator format is CPU-EP
    # portable, so the artifact runs on both the x86 build host and the aarch64
    # Raspberry Pi target. ~110MB fp32 → ~minimal int8, no torch at runtime.
    quantizer = ORTQuantizer.from_pretrained(out)
    qconfig = AutoQuantizationConfig.arm64(is_static=False, per_channel=False)
    quantizer.quantize(save_dir=out, quantization_config=qconfig)

    # Keep only the quantized graph; the runtime loads model_quantized.onnx.
    fp32 = out / "model.onnx"
    if fp32.exists():
        fp32.unlink()

    if not (out / "model_quantized.onnx").exists():
        raise SystemExit("quantized model not produced")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/models/finbert")
