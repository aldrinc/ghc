from __future__ import annotations

import json
from dataclasses import dataclass
from copy import deepcopy
import mimetypes
from pathlib import Path
from typing import Any, Optional

import httpx

from app.services.funnels import create_funnel_upload_asset
from app.db.repositories.assets import AssetsRepository
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class FunnelTemplate:
    template_id: str
    name: str
    description: Optional[str]
    preview_image: Optional[str]
    puck_data: dict[str, Any]
    asset_base_path: Optional[str]
    asset_prefix: Optional[str]


def _template_dir() -> Path:
    # backend/app/services -> backend/app
    return Path(__file__).resolve().parents[1] / "templates" / "funnels"


def _load_template(path: Path) -> FunnelTemplate:
    data = json.loads(path.read_text(encoding="utf-8"))
    template_id = data.get("id")
    name = data.get("name")
    puck_data = data.get("puckData")
    if not isinstance(template_id, str) or not template_id:
        raise ValueError(f"Template {path} missing required id")
    if not isinstance(name, str) or not name:
        raise ValueError(f"Template {path} missing required name")
    if not isinstance(puck_data, dict):
        raise ValueError(f"Template {path} missing required puckData")
    asset_base_path = data.get("assetBasePath")
    if isinstance(asset_base_path, str) and asset_base_path and not Path(asset_base_path).is_absolute():
        repo_root = _template_dir().parents[3]
        asset_base_path = str(repo_root / asset_base_path)

    return FunnelTemplate(
        template_id=template_id,
        name=name,
        description=data.get("description"),
        preview_image=data.get("previewImage"),
        puck_data=puck_data,
        asset_base_path=asset_base_path if isinstance(asset_base_path, str) else None,
        asset_prefix=data.get("assetPrefix"),
    )


def _load_templates() -> dict[str, FunnelTemplate]:
    templates: dict[str, FunnelTemplate] = {}
    directory = _template_dir()
    if not directory.exists():
        return templates
    for path in sorted(directory.glob("*.json")):
        template = _load_template(path)
        templates[template.template_id] = template
    return templates


def list_funnel_templates() -> list[FunnelTemplate]:
    return list(_load_templates().values())


def get_funnel_template(template_id: str) -> Optional[FunnelTemplate]:
    return _load_templates().get(template_id)


def _is_data_uri(value: str) -> bool:
    return value.startswith("data:")


def _resolve_asset_bytes(
    *,
    src: str,
    asset_base_path: Optional[str],
    asset_prefix: Optional[str],
) -> tuple[Optional[bytes], Optional[str], Optional[str]]:
    if _is_data_uri(src):
        return None, None, None
    if src.startswith("http://") or src.startswith("https://"):
        resp = httpx.get(src, timeout=30.0)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type")
        return resp.content, content_type, src
    if asset_base_path and asset_prefix and src.startswith(asset_prefix):
        rel = src[len(asset_prefix) :].lstrip("/")
        path = Path(asset_base_path) / rel
        if not path.exists():
            return None, None, None
        content = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0]
        return content, content_type, str(path)
    return None, None, None


def _apply_brand_logo_overrides(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    puck_data: dict[str, Any],
    design_system_tokens: dict[str, Any],
) -> None:
    if not isinstance(design_system_tokens, dict):
        raise ValueError("Design system tokens must be a JSON object to apply brand assets.")

    brand = design_system_tokens.get("brand")
    if brand is None:
        raise ValueError("Design system tokens missing brand configuration for template assets.")
    if not isinstance(brand, dict):
        raise ValueError("Design system brand configuration must be a JSON object.")

    logo_public_id = brand.get("logoAssetPublicId")
    if not isinstance(logo_public_id, str) or not logo_public_id.strip():
        raise ValueError("Design system brand.logoAssetPublicId is required to apply brand assets.")
    logo_public_id = logo_public_id.strip()
    if logo_public_id == "__LOGO_ASSET_PUBLIC_ID__":
        raise ValueError(
            "Design system brand.logoAssetPublicId is a placeholder and must be replaced with a real asset public id."
        )

    assets_repo = AssetsRepository(session)
    asset = assets_repo.get_by_public_id(org_id=org_id, client_id=client_id, public_id=logo_public_id)
    if not asset:
        raise ValueError("Brand logo asset not found for this workspace.")

    logo_alt = brand.get("logoAlt")
    logo_alt_value = logo_alt.strip() if isinstance(logo_alt, str) and logo_alt.strip() else None

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key == "logo" and isinstance(value, dict):
                    value["assetPublicId"] = logo_public_id
                    if logo_alt_value:
                        value["alt"] = logo_alt_value
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(puck_data)


def apply_template_assets(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    template: FunnelTemplate,
    design_system_tokens: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Clone template puckData and replace image src fields with uploaded Funnel assets.
    Stores assetPublicId / thumbAssetPublicId / swatchAssetPublicId alongside originals.
    """
    cloned = deepcopy(template.puck_data)
    asset_base_path = template.asset_base_path
    asset_prefix = template.asset_prefix or "/assets/"
    cache: dict[str, str] = {}

    if design_system_tokens is not None:
        _apply_brand_logo_overrides(
            session=session,
            org_id=org_id,
            client_id=client_id,
            puck_data=cloned,
            design_system_tokens=design_system_tokens,
        )

    def resolve_public_id(src: str, alt: Optional[str] = None) -> Optional[str]:
        if src in cache:
            return cache[src]
        content, content_type, origin = _resolve_asset_bytes(
            src=src,
            asset_base_path=asset_base_path,
            asset_prefix=asset_prefix,
        )
        if content is None:
            return None
        filename = None
        if origin and origin.startswith(str(asset_base_path or "")):
            filename = Path(origin).name
        elif origin and origin.startswith("http"):
            filename = Path(origin.split("?")[0]).name
        asset = create_funnel_upload_asset(
            session=session,
            org_id=org_id,
            client_id=client_id,
            content_bytes=content,
            filename=filename,
            content_type=content_type,
            alt=alt,
            usage_context={"kind": "funnel_template"},
            tags=["funnel", "template"],
        )
        cache[src] = str(asset.public_id)
        return cache[src]

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(value, str) and value:
                    alt = None
                    if key in ("src", "thumbSrc", "swatchImageSrc", "iconSrc"):
                        if key == "src" and "assetPublicId" in node:
                            continue
                        if key == "thumbSrc" and "thumbAssetPublicId" in node:
                            continue
                        if key == "swatchImageSrc" and "swatchAssetPublicId" in node:
                            continue
                        if key == "iconSrc" and "iconAssetPublicId" in node:
                            continue
                        if key == "iconSrc":
                            if isinstance(node.get("iconAlt"), str):
                                alt = node.get("iconAlt")
                        elif isinstance(node.get("alt"), str):
                            alt = node.get("alt")
                        public_id = resolve_public_id(value, alt)
                        if public_id:
                            if key == "src" and "assetPublicId" not in node:
                                node["assetPublicId"] = public_id
                            elif key == "thumbSrc" and "thumbAssetPublicId" not in node:
                                node["thumbAssetPublicId"] = public_id
                            elif key == "swatchImageSrc" and "swatchAssetPublicId" not in node:
                                node["swatchAssetPublicId"] = public_id
                            elif key == "iconSrc" and "iconAssetPublicId" not in node:
                                node["iconAssetPublicId"] = public_id
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(cloned)
    return cloned
