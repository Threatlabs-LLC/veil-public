# ============================================================
# Stage 1: Build frontend
# ============================================================
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit
COPY frontend/ ./
RUN npm run build

# ============================================================
# Stage 2: Python backend + static frontend
# ============================================================
FROM python:3.12-slim

# Build arg: install NER deps (presidio + spaCy)
ARG INSTALL_NER=true

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps — copy full project for editable install
COPY pyproject.toml ./
COPY backend/ ./backend/

# Install base + optional NER deps
RUN pip install --no-cache-dir -e ".[dev]" && \
    if [ "$INSTALL_NER" = "true" ]; then \
        pip install --no-cache-dir -e ".[ner]" && \
        python -m spacy download en_core_web_md; \
    fi

# Frontend static files
COPY --from=frontend-build /app/frontend/dist ./static/

# Data + keys directories
RUN mkdir -p /app/data /app/keys

# Environment defaults
ENV VEILCHAT_DATABASE_URL="sqlite+aiosqlite:///./data/veilchat.db"
ENV VEILCHAT_DATA_DIR="/app/data"

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/live')"

# Run with uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
