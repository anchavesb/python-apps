"""Entry point for dolores-brain service."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "dolores_brain.main:app",
        host="0.0.0.0",
        port=8003,
        reload=False,
    )


if __name__ == "__main__":
    main()
