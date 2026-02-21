FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install dolores-common first (shared lib)
COPY libs/dolores-common /app/libs/dolores-common
RUN pip install --no-cache-dir /app/libs/dolores-common

# Install the STT service
COPY apps/dolores-stt/pyproject.toml /app/
COPY apps/dolores-stt/src /app/src
RUN pip install --no-cache-dir .

# Create model cache directory
RUN mkdir -p /app/models && chown -R appuser:appuser /app

USER appuser

EXPOSE 8001

CMD ["uvicorn", "dolores_stt.main:app", "--host", "0.0.0.0", "--port", "8001"]
