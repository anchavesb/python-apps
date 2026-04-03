#!/usr/bin/env python3
"""Download pre-built all-MiniLM-L6-v2 ONNX model from HuggingFace Hub.

No PyTorch or transformers needed — just downloads the files directly.
Produces: model.onnx (~80MB) + tokenizer.json (~700KB)
"""

import sys
from pathlib import Path


def main():
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".cache" / "dolores-intent"
    output_dir.mkdir(parents=True, exist_ok=True)

    repo_id = "sentence-transformers/all-MiniLM-L6-v2"

    print(f"Downloading ONNX model from {repo_id}...")
    from huggingface_hub import hf_hub_download

    # Download the pre-built ONNX model
    hf_hub_download(
        repo_id=repo_id,
        filename="onnx/model.onnx",
        local_dir=str(output_dir),
        local_dir_use_symlinks=False,
    )
    # Move from onnx/ subfolder to output_dir root
    onnx_src = output_dir / "onnx" / "model.onnx"
    onnx_dst = output_dir / "model.onnx"
    if onnx_src.exists() and onnx_src != onnx_dst:
        onnx_src.rename(onnx_dst)
        # Also move .data file if present
        data_src = output_dir / "onnx" / "model.onnx_data"
        data_dst = output_dir / "model.onnx_data"
        if data_src.exists():
            data_src.rename(data_dst)
        # Clean up onnx/ subfolder
        onnx_dir = output_dir / "onnx"
        if onnx_dir.exists():
            for f in onnx_dir.iterdir():
                f.unlink()
            onnx_dir.rmdir()

    # Download tokenizer
    hf_hub_download(
        repo_id=repo_id,
        filename="tokenizer.json",
        local_dir=str(output_dir),
        local_dir_use_symlinks=False,
    )

    # Clean up any extra files (huggingface_hub may download .huggingface/)
    keep = {"model.onnx", "model.onnx_data", "tokenizer.json"}
    for item in output_dir.iterdir():
        if item.name not in keep:
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                import shutil

                shutil.rmtree(item)

    # Validate the model works
    _validate_onnx(output_dir)

    total_mb = sum(f.stat().st_size for f in output_dir.iterdir()) / (1024 * 1024)
    print(f"Done! Model dir: {output_dir} ({total_mb:.1f} MB)")


def _validate_onnx(model_dir: Path):
    """Validate ONNX model with onnxruntime at multiple batch sizes."""
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
        ["hello world"],  # batch=1
        ["hello", "world", "test"],  # batch=3
        [f"sentence {i}" for i in range(16)],  # batch=16 (matches intent examples)
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

        outputs = session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        assert outputs[0].shape[0] == batch, f"Expected batch={batch}, got {outputs[0].shape[0]}"
        assert outputs[0].shape[2] == 384, f"Expected hidden_size=384, got {outputs[0].shape[2]}"
        print(f"  batch={batch:>2} seq={max_len:>3} -> output {outputs[0].shape} OK")

    print("Validation passed!")


if __name__ == "__main__":
    main()
