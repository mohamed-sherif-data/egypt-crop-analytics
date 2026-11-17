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

# 7860 is the port Hugging Face Spaces expects.
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/v1/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
