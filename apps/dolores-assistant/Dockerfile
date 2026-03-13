## Stage 1: Export model to ONNX (PyTorch only needed here, discarded after)
FROM python:3.12-slim AS model-export

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "transformers<5" onnxscript onnxruntime tokenizers

COPY apps/dolores-assistant/scripts/download_intent_model.py /tmp/download.py
RUN python /tmp/download.py /models/intent

## Stage 2: Runtime image (no PyTorch)
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

# Copy pre-exported ONNX model from build stage (~80MB, no PyTorch needed)
COPY --from=model-export /models/intent /app/models/intent

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "dolores_assistant.main:app", "--host", "0.0.0.0", "--port", "8000"]
