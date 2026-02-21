"""Entry point for dolores-tts service.

CRITICAL: Must run with single worker due to CUDA/torch multiprocessing issues.
"""

try:
    import torch.multiprocessing
    torch.multiprocessing.set_start_method("spawn", force=True)
except ImportError:
    pass  # torch not installed, running without GPU support

import uvicorn


def main() -> None:
    uvicorn.run(
        "dolores_tts.main:app",
        host="0.0.0.0",
        port=8002,
        reload=False,
        workers=1,  # MUST be 1 - CUDA/uvicorn forking issue
    )


if __name__ == "__main__":
    main()
