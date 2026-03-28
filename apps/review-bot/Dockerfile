FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -m -g appuser appuser

WORKDIR /app

# Install dolores-common first (shared lib)
COPY libs/dolores-common /app/libs/dolores-common
RUN pip install --no-cache-dir /app/libs/dolores-common

# Install the review-bot service
COPY apps/review-bot/pyproject.toml /app/
COPY apps/review-bot/src /app/src
COPY apps/review-bot/prompts /app/prompts
COPY apps/review-bot/config /app/config
RUN pip install --no-cache-dir .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8004

CMD ["uvicorn", "review_bot.main:app", "--host", "0.0.0.0", "--port", "8004"]
