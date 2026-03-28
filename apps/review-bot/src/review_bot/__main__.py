"""Entry point for review-bot service."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "review_bot.main:app",
        host="0.0.0.0",
        port=8004,
        reload=False,
    )


if __name__ == "__main__":
    main()
