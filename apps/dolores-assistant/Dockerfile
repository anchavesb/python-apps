FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -m -g appuser appuser

WORKDIR /app

# Install dolores-common first (shared lib)
COPY libs/dolores-common /app/libs/dolores-common
RUN pip install --no-cache-dir /app/libs/dolores-common

# Install the Assistant service
COPY apps/dolores-assistant/pyproject.toml /app/
COPY apps/dolores-assistant/src /app/src
RUN pip install --no-cache-dir .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "dolores_assistant.main:app", "--host", "0.0.0.0", "--port", "8000"]
