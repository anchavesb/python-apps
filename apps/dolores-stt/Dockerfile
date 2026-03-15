FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -m -g appuser appuser

WORKDIR /app

# Install dolores-common first (shared lib)
COPY libs/dolores-common /app/libs/dolores-common
RUN pip install --no-cache-dir /app/libs/dolores-common

# Install the STT service
COPY apps/dolores-stt/pyproject.toml /app/
COPY apps/dolores-stt/src /app/src
RUN pip install --no-cache-dir . && \
    pip uninstall -y webrtcvad && \
    pip install --no-cache-dir "webrtcvad-wheels>=2.0.12"

# Create model cache and data directories
RUN mkdir -p /app/models /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8001

CMD ["uvicorn", "dolores_stt.main:app", "--host", "0.0.0.0", "--port", "8001"]
