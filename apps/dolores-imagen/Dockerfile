FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -m -g appuser appuser

WORKDIR /app

# Install dolores-common first (shared lib)
COPY libs/dolores-common /app/libs/dolores-common
RUN pip install --no-cache-dir /app/libs/dolores-common

# Install the imagen service (CPU-only, no GPU deps)
COPY apps/dolores-imagen/pyproject.toml /app/
COPY apps/dolores-imagen/src /app/src
RUN pip install --no-cache-dir .

RUN mkdir -p /app/models && chown -R appuser:appuser /app

USER appuser

EXPOSE 8005

CMD ["uvicorn", "dolores_imagen.main:app", "--host", "0.0.0.0", "--port", "8005", "--workers", "1"]
