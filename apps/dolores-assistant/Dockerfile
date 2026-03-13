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

# Pre-download the intent classification model (~80MB) into the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Model cache lives in /root/.cache — move it to appuser's home
RUN cp -r /root/.cache /home/appuser/.cache && \
    chown -R appuser:appuser /app /home/appuser/.cache

USER appuser

EXPOSE 8000

CMD ["uvicorn", "dolores_assistant.main:app", "--host", "0.0.0.0", "--port", "8000"]
