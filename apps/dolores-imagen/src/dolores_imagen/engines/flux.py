"""FLUX.1-schnell image generation backend."""

from __future__ import annotations

import io
import time

from dolores_common.logging import get_logger

from ..engine import ImageGenProvider

log = get_logger(__name__)


class FLUXProvider(ImageGenProvider):
    """FLUX.1-schnell diffusion pipeline with MPS/CUDA/CPU device auto-detection."""

    def __init__(self, model_id: str = "black-forest-labs/FLUX.1-schnell") -> None:
        self._model_id = model_id
        self._pipeline = None

    @property
    def name(self) -> str:
        return "flux"

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load(self) -> None:
        """Load FLUX pipeline. Imports diffusers/torch inside to keep service importable without GPU deps."""
        import torch
        from diffusers import FluxPipeline

        if torch.cuda.is_available():
            device = torch.device("cuda")
            dtype = torch.bfloat16
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
            # float16 is generally faster than bfloat16 on most Metal GPUs
            dtype = torch.float16
        else:
            device = torch.device("cpu")
            dtype = torch.float32

        log.info("loading_flux_model", model_id=self._model_id, device=str(device))
        start = time.monotonic()

        self._pipeline = FluxPipeline.from_pretrained(self._model_id, torch_dtype=dtype)
        self._pipeline = self._pipeline.to(device)

        log.info("flux_model_loaded", elapsed_seconds=round(time.monotonic() - start, 2))

    def generate(self, prompt: str, width: int = 512, height: int = 512) -> bytes:
        """Generate image synchronously. Intended to be called via asyncio.to_thread()."""
        if self._pipeline is None:
            raise RuntimeError("FLUXProvider not loaded; call load() first")

        log.info("generating_flux_image", width=width, height=height)
        start = time.monotonic()
        image = self._pipeline(
            prompt=prompt,
            num_inference_steps=4,
            height=height,
            width=width,
        ).images[0]
        elapsed = time.monotonic() - start
        log.info("flux_image_generated", elapsed_seconds=round(elapsed, 2))

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
