"""FLUX.1-schnell image generation backend."""

from __future__ import annotations

import io
import os
import time

from dolores_common.logging import get_logger

from ..engine import ImageGenProvider

log = get_logger(__name__)

# Reduce CUDA memory fragmentation — must be set before torch initializes
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


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

        from dolores_imagen.config import settings

        device_name = settings.device
        if device_name == "auto":
            if torch.cuda.is_available():
                device = torch.device("cuda")
                dtype = torch.bfloat16
            elif torch.backends.mps.is_available():
                device = torch.device("mps")
                # bfloat16 is required for FLUX on MPS to avoid NaNs (black images)
                dtype = torch.bfloat16
            else:
                device = torch.device("cpu")
                dtype = torch.float32
        else:
            device = torch.device(device_name)
            dtype = torch.bfloat16 if device_name in ["cuda", "mps"] else torch.float32

        log.info("loading_flux_model", model_id=self._model_id, device=str(device))
        start = time.monotonic()

        self._pipeline = FluxPipeline.from_pretrained(
            self._model_id,
            torch_dtype=dtype,
        )

        if device.type == "cuda":
            # Model-level CPU offload: moves whole sub-models (text encoder, UNet, VAE)
            # to CPU between steps. Preserves quality vs sequential offload, and is faster.
            self._pipeline.enable_model_cpu_offload()
        else:
            self._pipeline = self._pipeline.to(device)

        # Slice attention into chunks to reduce peak VRAM — no visible quality impact.
        # VAE slicing is intentionally omitted: it decodes in strips which can
        # produce seam artifacts at tile boundaries.
        self._pipeline.enable_attention_slicing()

        log.info("flux_model_loaded", elapsed_seconds=round(time.monotonic() - start, 2))

    def generate(self, prompt: str, width: int = 512, height: int = 512) -> bytes:
        """Generate image synchronously. Intended to be called via asyncio.to_thread()."""
        import torch

        if self._pipeline is None:
            raise RuntimeError("FLUXProvider not loaded; call load() first")

        log.info("generating_flux_image", width=width, height=height)
        start = time.monotonic()
        try:
            image = self._pipeline(
                prompt=prompt,
                num_inference_steps=4,
                height=height,
                width=width,
                guidance_scale=0.0,  # FLUX.1-schnell is guidance-distilled
            ).images[0]
        except torch.OutOfMemoryError:
            # Free fragmented cache and retry once before propagating
            log.warning("flux_oom_clearing_cache_and_retrying")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            image = self._pipeline(
                prompt=prompt,
                num_inference_steps=4,
                height=height,
                width=width,
                guidance_scale=0.0,
            ).images[0]
        finally:
            # Always free unreferenced CUDA tensors after generation
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        elapsed = time.monotonic() - start
        log.info("flux_image_generated", elapsed_seconds=round(elapsed, 2))

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
