# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Create a non-root user and working directory
RUN useradd -m appuser
WORKDIR /app

# Copy only what's needed to install the app (leverages Docker layer caching)
COPY pyproject.toml ./
COPY src ./src

# Install dependencies and the app
RUN python -m pip install --upgrade pip wheel \
    && python -m pip install gunicorn \
    && python -m pip install -e .

# Runtime configuration
ENV PORT=5000
EXPOSE 5000
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

# Use gunicorn with a WSGI module
# Alternatively, you can use the app factory form: todo_app:create_app()
CMD ["sh", "-c", "exec gunicorn -w ${GUNICORN_WORKERS:-2} -b 0.0.0.0:${PORT:-5000} todo_app.wsgi:app"]
