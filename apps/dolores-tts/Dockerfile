FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -m -g appuser appuser

WORKDIR /app

# Install dolores-common first (shared lib)
COPY libs/dolores-common /app/libs/dolores-common
RUN pip install --no-cache-dir /app/libs/dolores-common

# Install the TTS service
COPY apps/dolores-tts/pyproject.toml /app/
COPY apps/dolores-tts/src /app/src
RUN pip install --no-cache-dir .

# Create data directories
RUN mkdir -p /app/data/voices /app/models && chown -R appuser:appuser /app

USER appuser

EXPOSE 8002

# MUST use single worker due to CUDA/torch multiprocessing issues
CMD ["uvicorn", "dolores_tts.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
