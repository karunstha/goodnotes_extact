FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    OLLAMA_URL=http://host.docker.internal:11434 \
    OLLAMA_MODEL=llama3.2-vision \
    OUTPUT_DIR=/app/output

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["python", "-m", "goodnotes_ocr.mcp_server"]
