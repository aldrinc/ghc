from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import boto3
import httpx
from botocore.config import Config


SAFE_FILE_CHARS_RE = re.compile(r"[^a-zA-Z0-9._-]+")
JSON_PATH_TOKEN_RE = re.compile(r"\.([A-Za-z0-9_]+)|\[(\d+)\]")


@dataclass(frozen=True)
class PublishedReplacement:
    slot_id: str
    item_id: str
    render_mode: str
    original_url: str
    generated_local_path: str
    public_url: str
    width: int | None
    height: int | None
    target_json_paths: list[str]


def _slugify(value: str) -> str:
    stripped = SAFE_FILE_CHARS_RE.sub("-", value.strip())
    return stripped.strip("-") or "file"


def _normalize_endpoint(endpoint: str) -> str:
    normalized = str(endpoint or "").strip()
    if not normalized:
        raise RuntimeError("Bucket endpoint is required.")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"
    return normalized.rstrip("/")


def _default_public_base_url(*, bucket: str, endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"Invalid bucket endpoint: {endpoint}")
    return f"{parsed.scheme}://{bucket}.{parsed.netloc}"


def _load_pagefly_json(pagefly_path: Path) -> tuple[str, dict[str, Any]]:
    if not pagefly_path.exists() or not pagefly_path.is_file():
        raise RuntimeError(f"PageFly export not found: {pagefly_path}")

    if pagefly_path.suffix.lower() == ".json":
        payload = json.loads(pagefly_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"PageFly JSON must be an object: {pagefly_path}")
        return pagefly_path.name, payload

    with zipfile.ZipFile(pagefly_path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(
                "Expected PageFly export zip to contain exactly one JSON file. "
                f"Found {len(names)} files."
            )
        entry_name = names[0]
        payload = json.loads(archive.read(entry_name))
        if not isinstance(payload, dict):
            raise RuntimeError(f"PageFly export payload must be a JSON object: {entry_name}")
        return entry_name, payload


def _parse_json_path(path: str) -> list[tuple[str, str | int]]:
    if not isinstance(path, str) or not path.startswith("$"):
        raise RuntimeError(f"Unsupported JSON path: {path!r}")
    tokens: list[tuple[str, str | int]] = []
    position = 1
    while position < len(path):
        match = JSON_PATH_TOKEN_RE.match(path, position)
        if not match:
            raise RuntimeError(f"Unable to parse JSON path token at offset {position}: {path!r}")
        key, index = match.groups()
        if key is not None:
            tokens.append(("key", key))
        else:
            tokens.append(("index", int(index)))
        position = match.end()
    if not tokens:
        raise RuntimeError(f"JSON path must target a nested value, not root: {path!r}")
    return tokens


def _set_json_path_value(root: Any, path: str, value: str) -> None:
    tokens = _parse_json_path(path)
    current = root
    for token_type, token_value in tokens[:-1]:
        if token_type == "key":
            if not isinstance(current, dict) or token_value not in current:
                raise RuntimeError(f"JSON path does not exist for key token {token_value!r}: {path}")
            current = current[token_value]
        else:
            if not isinstance(current, list) or not (0 <= int(token_value) < len(current)):
                raise RuntimeError(f"JSON path does not exist for index token {token_value!r}: {path}")
            current = current[int(token_value)]

    last_type, last_value = tokens[-1]
    if last_type == "key":
        if not isinstance(current, dict):
            raise RuntimeError(f"JSON path does not resolve to an object for final key token: {path}")
        current[str(last_value)] = value
        return
    if not isinstance(current, list) or not (0 <= int(last_value) < len(current)):
        raise RuntimeError(f"JSON path does not resolve to a valid final index token: {path}")
    current[int(last_value)] = value


def _build_s3_client(*, endpoint: str, access_key: str, secret_key: str, region: str) -> Any:
    return boto3.session.Session().client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def _guess_content_type(path: Path) -> str:
    guessed, _encoding = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    return "application/octet-stream"


def _verify_public_url(*, url: str) -> None:
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to verify public asset URL {url}: {exc}") from exc
    if response.status_code != 200:
        raise RuntimeError(
            f"Public asset URL is not anonymously accessible (status={response.status_code}): {url}"
        )


def _upload_public_file(
    *,
    s3_client: Any,
    bucket: str,
    public_base_url: str,
    key_prefix: str,
    pagefly_stem: str,
    slot_id: str,
    local_path: Path,
    verify_public_url: bool,
) -> str:
    if not local_path.exists() or not local_path.is_file():
        raise RuntimeError(f"Generated image not found for upload: {local_path}")
    payload = local_path.read_bytes()
    if not payload:
        raise RuntimeError(f"Generated image payload is empty: {local_path}")
    sha_prefix = hashlib.sha256(payload).hexdigest()[:12]
    content_type = _guess_content_type(local_path)
    key = "/".join(
        part.strip("/")
        for part in (
            key_prefix,
            _slugify(pagefly_stem),
            _slugify(slot_id),
            f"{sha_prefix}{local_path.suffix.lower() or '.bin'}",
        )
        if part and str(part).strip("/")
    )
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )
    public_url = f"{public_base_url.rstrip('/')}/{quote(key)}"
    if verify_public_url:
        _verify_public_url(url=public_url)
    return public_url


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"Manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Prototype manifest must be a JSON object: {path}")
    return payload


def _manifest_slot_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    slots = manifest.get("pagefly_slots")
    if not isinstance(slots, list):
        raise RuntimeError("Manifest is missing pagefly_slots.")
    mapped: dict[str, dict[str, Any]] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_id = slot.get("slotId")
        if isinstance(slot_id, str) and slot_id.strip():
            mapped[slot_id] = slot
    return mapped


def _collect_replacements_from_manifests(
    *,
    manifests: list[dict[str, Any]],
    s3_client: Any,
    bucket: str,
    public_base_url: str,
    key_prefix: str,
    pagefly_stem: str,
    verify_public_url: bool,
) -> list[PublishedReplacement]:
    replacements: list[PublishedReplacement] = []
    replaced_item_ids: set[str] = set()

    for manifest in manifests:
        slot_map = _manifest_slot_map(manifest)
        selected_slot_id = str(manifest.get("selected_sample_slot_id") or "").strip()
        if not selected_slot_id:
            raise RuntimeError("Manifest is missing selected_sample_slot_id.")
        selected_slot = slot_map.get(selected_slot_id)
        if selected_slot is None:
            raise RuntimeError(f"Selected slot {selected_slot_id} is not present in manifest pagefly_slots.")

        item_id = str(selected_slot.get("itemId") or "").strip()
        if not item_id:
            raise RuntimeError(f"Selected slot is missing itemId: {selected_slot_id}")
        if item_id in replaced_item_ids:
            raise RuntimeError(
                f"Multiple manifests attempt to replace the same PageFly item_id {item_id}. "
                "Each PageFly image item should map to one generated output."
            )

        generated_paths = manifest.get("generated_image_paths")
        if not isinstance(generated_paths, list) or not generated_paths:
            raise RuntimeError(f"Manifest has no generated_image_paths for selected slot {selected_slot_id}.")
        generated_path = Path(str(generated_paths[0])).expanduser().resolve()
        public_url = _upload_public_file(
            s3_client=s3_client,
            bucket=bucket,
            public_base_url=public_base_url,
            key_prefix=key_prefix,
            pagefly_stem=pagefly_stem,
            slot_id=selected_slot_id,
            local_path=generated_path,
            verify_public_url=verify_public_url,
        )

        target_json_paths = sorted(
            {
                str(slot.get("jsonPath")).strip()
                for slot in slot_map.values()
                if isinstance(slot, dict) and str(slot.get("itemId") or "").strip() == item_id
            }
        )
        if not target_json_paths:
            raise RuntimeError(f"No target json paths found for selected slot {selected_slot_id}.")

        replacements.append(
            PublishedReplacement(
                slot_id=selected_slot_id,
                item_id=item_id,
                render_mode=str(manifest.get("selected_sample_render_mode") or "").strip() or "unknown",
                original_url=str(selected_slot.get("imageUrl") or "").strip(),
                generated_local_path=str(generated_path),
                public_url=public_url,
                width=(
                    int(selected_slot["dimensions"]["width"])
                    if isinstance(selected_slot.get("dimensions"), dict)
                    and isinstance(selected_slot["dimensions"].get("width"), int)
                    else None
                ),
                height=(
                    int(selected_slot["dimensions"]["height"])
                    if isinstance(selected_slot.get("dimensions"), dict)
                    and isinstance(selected_slot["dimensions"].get("height"), int)
                    else None
                ),
                target_json_paths=target_json_paths,
            )
        )
        replaced_item_ids.add(item_id)

    return replacements


def _write_pagefly_outputs(
    *,
    original_pagefly_path: Path,
    entry_name: str,
    rewritten_payload: dict[str, Any],
    replacements: list[PublishedReplacement],
    out_dir: Path,
) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rewritten_json_path = out_dir / f"{_slugify(original_pagefly_path.stem)}-rewritten.json"
    rewritten_json_path.write_text(
        json.dumps(rewritten_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    rewritten_pagefly_path = out_dir / f"{_slugify(original_pagefly_path.stem)}-rewritten.pagefly"
    with zipfile.ZipFile(rewritten_pagefly_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry_name, rewritten_json_path.read_text(encoding="utf-8"))

    upload_manifest_path = out_dir / "pagefly_uploaded_asset_map.json"
    upload_manifest_path.write_text(
        json.dumps(
            [
                {
                    "slotId": replacement.slot_id,
                    "itemId": replacement.item_id,
                    "renderMode": replacement.render_mode,
                    "originalUrl": replacement.original_url,
                    "generatedLocalPath": replacement.generated_local_path,
                    "publicUrl": replacement.public_url,
                    "width": replacement.width,
                    "height": replacement.height,
                    "targetJsonPaths": replacement.target_json_paths,
                }
                for replacement in replacements
            ],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return rewritten_json_path, rewritten_pagefly_path, upload_manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload generated PageFly prototype images to a public Hetzner bucket and rewrite the PageFly export."
    )
    parser.add_argument(
        "--manifest",
        action="append",
        required=True,
        help="Prototype manifest(s) to publish. Provide one per generated slot run.",
    )
    parser.add_argument(
        "--pagefly",
        default=None,
        help="Optional original PageFly export path. Defaults to pagefly_export from the first manifest.",
    )
    parser.add_argument("--bucket-name", required=True, help="Public Hetzner bucket name.")
    parser.add_argument("--bucket-endpoint", required=True, help="Hetzner S3 endpoint host or URL.")
    parser.add_argument("--bucket-region", default="hel1", help="Hetzner bucket region (default: hel1).")
    parser.add_argument("--bucket-access-key", required=True, help="Hetzner bucket access key.")
    parser.add_argument("--bucket-secret-key", required=True, help="Hetzner bucket secret key.")
    parser.add_argument(
        "--public-base-url",
        default=None,
        help="Public base URL for uploaded objects. Defaults to https://<bucket>.<endpoint-host>.",
    )
    parser.add_argument(
        "--key-prefix",
        default="pagefly-generated",
        help="Object key prefix inside the bucket.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for the rewritten PageFly artifacts.",
    )
    parser.add_argument(
        "--skip-public-url-verification",
        action="store_true",
        help="Skip anonymous GET verification for uploaded object URLs.",
    )
    args = parser.parse_args()

    manifest_paths = [Path(item).expanduser().resolve() for item in args.manifest]
    manifests = [_load_manifest(path) for path in manifest_paths]
    first_manifest = manifests[0]

    pagefly_path = (
        Path(args.pagefly).expanduser().resolve()
        if isinstance(args.pagefly, str) and args.pagefly.strip()
        else Path(str(first_manifest.get("pagefly_export") or "")).expanduser().resolve()
    )
    if not str(pagefly_path):
        raise RuntimeError("Unable to resolve PageFly export path.")

    for manifest in manifests[1:]:
        manifest_pagefly = Path(str(manifest.get("pagefly_export") or "")).expanduser().resolve()
        if manifest_pagefly != pagefly_path:
            raise RuntimeError(
                "All manifests must point at the same PageFly export. "
                f"Expected {pagefly_path}, found {manifest_pagefly}."
            )

    entry_name, pagefly_payload = _load_pagefly_json(pagefly_path)

    endpoint = _normalize_endpoint(args.bucket_endpoint)
    public_base_url = (
        str(args.public_base_url).strip().rstrip("/")
        if isinstance(args.public_base_url, str) and args.public_base_url.strip()
        else _default_public_base_url(bucket=args.bucket_name, endpoint=endpoint)
    )
    s3_client = _build_s3_client(
        endpoint=endpoint,
        access_key=args.bucket_access_key,
        secret_key=args.bucket_secret_key,
        region=str(args.bucket_region).strip(),
    )

    replacements = _collect_replacements_from_manifests(
        manifests=manifests,
        s3_client=s3_client,
        bucket=args.bucket_name,
        public_base_url=public_base_url,
        key_prefix=str(args.key_prefix).strip(),
        pagefly_stem=pagefly_path.stem,
        verify_public_url=not args.skip_public_url_verification,
    )

    rewritten_payload = json.loads(json.dumps(pagefly_payload))
    replaced_paths: list[str] = []
    for replacement in replacements:
        for json_path in replacement.target_json_paths:
            _set_json_path_value(rewritten_payload, json_path, replacement.public_url)
            replaced_paths.append(json_path)

    out_root = (
        Path(args.out_dir).expanduser().resolve()
        if isinstance(args.out_dir, str) and args.out_dir.strip()
        else Path(__file__).resolve().parents[1] / "tmp" / "pagefly-published"
    )
    run_dir = out_root / f"{_slugify(pagefly_path.stem)}-{time.strftime('%Y%m%d-%H%M%S')}"
    rewritten_json_path, rewritten_pagefly_path, upload_manifest_path = _write_pagefly_outputs(
        original_pagefly_path=pagefly_path,
        entry_name=entry_name,
        rewritten_payload=rewritten_payload,
        replacements=replacements,
        out_dir=run_dir,
    )

    result = {
        "pagefly_export": str(pagefly_path),
        "rewritten_json_path": str(rewritten_json_path),
        "rewritten_pagefly_path": str(rewritten_pagefly_path),
        "upload_manifest_path": str(upload_manifest_path),
        "public_base_url": public_base_url,
        "replacement_count": len(replacements),
        "replaced_json_path_count": len(replaced_paths),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
