from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_IMAGE_WORKSPACE_DIR = REPO_ROOT / "template-image-workspace"
TEMPLATE_IMAGE_ASSETS_DIR = TEMPLATE_IMAGE_WORKSPACE_DIR / "assets"
TEMPLATE_IMAGE_OUTPUT_DIR = TEMPLATE_IMAGE_WORKSPACE_DIR / "output"
TEMPLATE_IMAGE_TRACE_OUTPUT_DIR = TEMPLATE_IMAGE_OUTPUT_DIR / "trace-batch"
TEMPLATE_IMAGE_CREATIVE_PROXY_OUTPUT_DIR = TEMPLATE_IMAGE_OUTPUT_DIR / "creative-service-batch"
