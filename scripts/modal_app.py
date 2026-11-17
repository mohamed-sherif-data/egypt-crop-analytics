"""Deploy the service to Modal (serverless, free monthly compute, no card).

    py -m modal deploy scripts/modal_app.py

Modal builds the image from the same files the Dockerfile copies, so the
behaviour is identical; only the port handling is Modal's. The ASGI app is
mounted at the endpoint label below, and Modal scales to zero when idle.
"""

from __future__ import annotations

from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .workdir("/app")
    .pip_install(
        "fastapi>=0.115",
        "uvicorn>=0.30",
        "pandas>=2.2,<4",
        "numpy>=1.26,<3",
        "scikit-learn>=1.4,<2",
    )
    # Local files must come last: Modal mounts them at container start instead
    # of baking them into the image, so a code change does not rebuild it.
    .add_local_file(ROOT / "core.py", "/app/core.py")
    .add_local_file(ROOT / "FAOSTAT_Egypt_Agriculture_Raw.csv", "/app/FAOSTAT_Egypt_Agriculture_Raw.csv")
    .add_local_dir(ROOT / "api", "/app/api", ignore=["__pycache__", "*.pyc"])
    .add_local_dir(ROOT / "web", "/app/web")
)

app = modal.App("egypt-crop-analytics", image=image)


@app.function(min_containers=0, max_containers=1)
@modal.asgi_app(label="crop-api")
def crop_api():
    """The FastAPI application, exactly as served locally and in Docker."""
    from api.main import app as web_app

    return web_app
