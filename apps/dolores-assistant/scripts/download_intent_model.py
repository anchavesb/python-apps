#!/usr/bin/env python3
"""Download and export all-MiniLM-L6-v2 to ONNX format.

Run during Docker build to avoid runtime downloads.
Produces: model.onnx (~80MB) + tokenizer.json (~700KB)
No PyTorch needed at runtime — only onnxruntime + tokenizers.
"""

import sys
from pathlib import Path

def main():
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".cache" / "dolores-intent"
    output_dir.mkdir(parents=True, exist_ok=True)

    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    print(f"Downloading {model_name}...")
    from transformers import AutoTokenizer, AutoModel
    import torch

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    # Save tokenizer (HuggingFace fast tokenizer → tokenizer.json)
    tokenizer.save_pretrained(str(output_dir))
    print(f"Saved tokenizer to {output_dir}")

    # Export to ONNX
    dummy_input = tokenizer("hello world", return_tensors="pt")
    onnx_path = output_dir / "model.onnx"

    print(f"Exporting ONNX to {onnx_path}...")
    torch.onnx.export(
        model,
        (dummy_input["input_ids"], dummy_input["attention_mask"], dummy_input["token_type_ids"]),
        str(onnx_path),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "token_type_ids": {0: "batch", 1: "seq"},
            "last_hidden_state": {0: "batch", 1: "seq"},
        },
        opset_version=14,
        dynamo=False,  # Use legacy TorchScript exporter for correct dynamic axes
    )

    # Validate the exported model works with various batch sizes
    _validate_onnx(output_dir)

    # Clean up files we don't need at runtime
    # Keep model.onnx, model.onnx.data (if split), and tokenizer.json
    keep = {"model.onnx", "model.onnx.data", "tokenizer.json"}
    for f in output_dir.iterdir():
        if f.name not in keep and f.is_file():
            f.unlink()

    total_mb = sum(f.stat().st_size for f in output_dir.iterdir()) / (1024 * 1024)
    print(f"Done! Model dir: {output_dir} ({total_mb:.1f} MB)")


def _validate_onnx(model_dir: Path):
    """Validate exported ONNX model with onnxruntime at multiple batch sizes."""
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    print("Validating ONNX model...")
    session = ort.InferenceSession(
        str(model_dir / "model.onnx"),
        providers=["CPUExecutionProvider"],
    )
    tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))

    test_cases = [
        ["hello world"],                          # batch=1
        ["hello", "world", "test"],               # batch=3
        [f"sentence {i}" for i in range(16)],     # batch=16 (matches intent examples)
    ]

    for texts in test_cases:
        encodings = tok.encode_batch(texts)
        max_len = max(len(e.ids) for e in encodings)
        batch = len(texts)

        input_ids = np.zeros((batch, max_len), dtype=np.int64)
        attention_mask = np.zeros((batch, max_len), dtype=np.int64)
        token_type_ids = np.zeros((batch, max_len), dtype=np.int64)

        for i, enc in enumerate(encodings):
            length = len(enc.ids)
            input_ids[i, :length] = enc.ids
            attention_mask[i, :length] = enc.attention_mask

        outputs = session.run(None, {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        })

        assert outputs[0].shape[0] == batch, \
            f"Expected batch={batch}, got {outputs[0].shape[0]}"
        assert outputs[0].shape[2] == 384, \
            f"Expected hidden_size=384, got {outputs[0].shape[2]}"
        print(f"  batch={batch:>2} seq={max_len:>3} -> output {outputs[0].shape} OK")

    print("Validation passed!")


if __name__ == "__main__":
    main()
