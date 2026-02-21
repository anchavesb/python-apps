"""Entry point for dolores-assistant service."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "dolores_assistant.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
