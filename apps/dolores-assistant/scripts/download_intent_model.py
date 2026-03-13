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
    )

    # Clean up files we don't need at runtime
    for f in output_dir.iterdir():
        if f.name not in ("model.onnx", "tokenizer.json"):
            if f.is_file():
                f.unlink()

    total_mb = sum(f.stat().st_size for f in output_dir.iterdir()) / (1024 * 1024)
    print(f"Done! Model dir: {output_dir} ({total_mb:.1f} MB)")


if __name__ == "__main__":
    main()
