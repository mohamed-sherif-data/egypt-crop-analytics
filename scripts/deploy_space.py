"""Publish the service to a Hugging Face Space (Docker SDK, port 7860).

The Space needs a README with YAML front matter describing the SDK and the
port, while the repository README stays plain Markdown for GitHub. So this
script assembles a small build folder — the runtime files plus a README with
front matter — and uploads only that.

    $env:HF_TOKEN = "hf_..."
    py scripts/deploy_space.py

Nothing here touches the local working tree; the build folder lives in
``.build/space`` and is ignored by git.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".build" / "space"
REPO_ID = os.environ.get("HF_SPACE_ID", "MohamedSherif12/egypt-crop-analytics")

# Only what the container needs, plus the Space card.
SHIP = [
    "Dockerfile",
    "requirements.txt",
    "core.py",
    "api",
    "web",
    "FAOSTAT_Egypt_Agriculture_Raw.csv",
]

FRONT_MATTER = """---
title: Egypt Crop Yield Analytics
emoji: 🌾
colorFrom: yellow
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Next-year yield forecasts and decline risk for 78 Egyptian crops
---

"""


def stage() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    for name in SHIP:
        source = ROOT / name
        target = BUILD / name
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)

    body = (ROOT / "README.md").read_text(encoding="utf-8")
    (BUILD / "README.md").write_text(FRONT_MATTER + body, encoding="utf-8")

    print(f"staged {sum(1 for p in BUILD.rglob('*') if p.is_file())} files in {BUILD}")


def publish() -> str:
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("HF_TOKEN is not set — create a write token at https://huggingface.co/settings/tokens")

    api = HfApi(token=token)
    api.create_repo(repo_id=REPO_ID, repo_type="space", space_sdk="docker", exist_ok=True)

    api.upload_folder(
        folder_path=str(BUILD),
        repo_id=REPO_ID,
        repo_type="space",
        commit_message="Deploy Egypt crop yield analytics service",
    )
    return f"https://huggingface.co/spaces/{REPO_ID}"


if __name__ == "__main__":
    stage()
    space_url = publish()
    subdomain = REPO_ID.replace("/", "-").lower()
    print(f"space page: {space_url}")
    print(f"app url:    https://{subdomain}.hf.space")
