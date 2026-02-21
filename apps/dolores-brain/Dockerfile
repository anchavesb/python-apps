FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install dolores-common first (shared lib)
COPY libs/dolores-common /app/libs/dolores-common
RUN pip install --no-cache-dir /app/libs/dolores-common

# Install the Brain service
COPY apps/dolores-brain/pyproject.toml /app/
COPY apps/dolores-brain/src /app/src
RUN pip install --no-cache-dir .

# Create data directory for SQLite
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8003

CMD ["uvicorn", "dolores_brain.main:app", "--host", "0.0.0.0", "--port", "8003"]
