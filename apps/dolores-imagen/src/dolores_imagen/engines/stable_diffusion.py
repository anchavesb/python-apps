"""Stable Diffusion image generation backend."""

from __future__ import annotations

import io
import os
import time

from dolores_common.logging import get_logger

from ..engine import ImageGenProvider

log = get_logger(__name__)

# Reduce CUDA memory fragmentation — must be set before torch initializes
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


class StableDiffusionProvider(ImageGenProvider):
    """Stable Diffusion pipeline with MPS/CUDA/CPU device auto-detection."""

    def __init__(self, model_id: str = "runwayml/stable-diffusion-v-1-5") -> None:
        self._model_id = model_id
        self._pipeline = None

    @property
    def name(self) -> str:
        return "stable_diffusion"

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load(self) -> None:
        """Load Stable Diffusion pipeline. Imports diffusers/torch inside to keep service importable without GPU deps."""
        import torch
        from diffusers import StableDiffusionPipeline

        from dolores_imagen.config import settings

        device_name = settings.device
        if device_name == "auto":
            if torch.cuda.is_available():
                device = torch.device("cuda")
                dtype = torch.float16
            elif torch.backends.mps.is_available():
                device = torch.device("mps")
                dtype = torch.float16
            else:
                device = torch.device("cpu")
                dtype = torch.float32
        else:
            device = torch.device(device_name)
            dtype = torch.float16 if device_name in ["cuda", "mps"] else torch.float32

        log.info("loading_sd_model", model_id=self._model_id, device=str(device))
        start = time.monotonic()

        local_files_only = os.environ.get("HF_HUB_OFFLINE", "0") == "1" or os.environ.get("TRANSFORMERS_OFFLINE", "0") == "1"
        self._pipeline = StableDiffusionPipeline.from_pretrained(
            self._model_id,
            torch_dtype=dtype,
            local_files_only=local_files_only,
        )

        if device.type == "cuda":
            # Model-level CPU offload: moves whole sub-models (text encoder, UNet, VAE)
            # to CPU between steps rather than individual layers. Uses ~1 GB more VRAM
            # than sequential offload but preserves output quality and is faster.
            self._pipeline.enable_model_cpu_offload()
        else:
            self._pipeline = self._pipeline.to(device)

        # Slice attention into chunks to reduce peak VRAM — no visible quality impact.
        # VAE slicing is intentionally omitted: it decodes in strips which can
        # produce seam artifacts at tile boundaries.
        self._pipeline.enable_attention_slicing()

        log.info("sd_model_loaded", elapsed_seconds=round(time.monotonic() - start, 2))

    def generate(self, prompt: str, width: int = 512, height: int = 512) -> bytes:
        """Generate image synchronously. Intended to be called via asyncio.to_thread()."""
        import torch

        if self._pipeline is None:
            raise RuntimeError("StableDiffusionProvider not loaded; call load() first")

        try:
            image = self._pipeline(
                prompt=prompt,
                height=height,
                width=width,
            ).images[0]
        except torch.OutOfMemoryError:
            log.warning("sd_oom_clearing_cache_and_retrying")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            image = self._pipeline(
                prompt=prompt,
                height=height,
                width=width,
            ).images[0]
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
