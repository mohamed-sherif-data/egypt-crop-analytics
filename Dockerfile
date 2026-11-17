# One container, one link: the API, its docs and the interface.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so the layer is cached between code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application: the engine, the service, the interface and the data.
COPY core.py ./
COPY api ./api
COPY web ./web
COPY FAOSTAT_Egypt_Agriculture_Raw.csv ./

# Run as a non-root user.
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# 7860 is the port Hugging Face Spaces expects; Render and similar hosts
# inject PORT, which the start command prefers when it is set.
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD-SHELL python -c "import os,urllib.request,sys; port=os.environ.get('PORT','7860'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/health', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
