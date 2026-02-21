"""Entry point for dolores-stt service."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "dolores_stt.main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
    )


if __name__ == "__main__":
    main()
