#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


API_VERSION = "2026-04"
MAX_FILES_PER_BATCH = 25
MAX_BATCH_BYTES = 2_000_000
SHOPIFY_THEME_ROOT_DIRECTORIES = {
    "assets",
    "config",
    "layout",
    "locales",
    "sections",
    "snippets",
    "templates",
}


@dataclass(frozen=True)
class LocalZipFile:
    filename: str
    raw_bytes: bytes
    sha256: str
    body_type: str
    body_value: str
    body_size_hint: int


def _fail(message: str) -> None:
    raise RuntimeError(message)


def _load_shop_installation(
    *,
    db_path: Path,
    client_id: str | None,
) -> tuple[str, str]:
    if not db_path.exists():
        _fail(f"Shopify DB file does not exist: {db_path}")

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        if client_id:
            cursor.execute(
                """
                SELECT shop_domain, admin_access_token
                FROM shop_installations
                WHERE client_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (client_id,),
            )
        else:
            cursor.execute(
                """
                SELECT shop_domain, admin_access_token
                FROM shop_installations
                ORDER BY updated_at DESC
                LIMIT 1
                """
            )
        row = cursor.fetchone()
    finally:
        connection.close()

    if not row:
        scope = f"client_id={client_id}" if client_id else "any client"
        _fail(f"No Shopify installation found for {scope}.")

    shop_domain, access_token = row
    if not isinstance(shop_domain, str) or not shop_domain.strip():
        _fail("Shopify installation row is missing shop_domain.")
    if not isinstance(access_token, str) or not access_token.strip():
        _fail("Shopify installation row is missing admin_access_token.")
    return shop_domain.strip(), access_token.strip()


def _graphql_request(
    *,
    endpoint: str,
    access_token: str,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.post(
        endpoint,
        headers={
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": variables or {}},
        timeout=120,
    )
    if response.status_code != 200:
        _fail(
            "Shopify GraphQL request failed: "
            f"status={response.status_code}, response_prefix={response.text[:500]!r}"
        )
    payload = response.json()
    if payload.get("errors"):
        _fail(f"Shopify GraphQL returned errors: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        _fail("Shopify GraphQL response is missing data payload.")
    return data


def _rest_post(
    *,
    endpoint: str,
    access_token: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = requests.post(
        f"{endpoint}{path}",
        headers={
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    if response.status_code not in {200, 201}:
        _fail(
            "Shopify REST request failed: "
            f"path={path}, status={response.status_code}, response_prefix={response.text[:500]!r}"
        )
    parsed = response.json()
    if not isinstance(parsed, dict):
        _fail(f"Shopify REST response for path={path} is not an object.")
    return parsed


def _create_fresh_validation_theme(
    *,
    admin_rest_endpoint: str,
    access_token: str,
) -> tuple[str, str]:
    theme_name = "codex-zip-validate-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    payload = _rest_post(
        endpoint=admin_rest_endpoint,
        access_token=access_token,
        path="/themes.json",
        payload={"theme": {"name": theme_name, "role": "unpublished"}},
    )
    theme = payload.get("theme")
    if not isinstance(theme, dict):
        _fail("Theme create response is missing theme payload.")
    theme_id = theme.get("id")
    if isinstance(theme_id, int):
        theme_id_str = str(theme_id)
    elif isinstance(theme_id, str) and theme_id.strip():
        theme_id_str = theme_id.strip()
    else:
        _fail("Theme create response is missing theme.id.")
    return theme_id_str, theme_name


def _theme_gid(theme_id: str) -> str:
    return f"gid://shopify/OnlineStoreTheme/{theme_id}"


def _list_theme_filenames(
    *,
    graphql_endpoint: str,
    access_token: str,
    theme_id: str,
) -> list[str]:
    query = """
    query themeFiles($id: ID!, $first: Int!, $after: String) {
      theme(id: $id) {
        id
        files(first: $first, after: $after) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            filename
          }
        }
      }
    }
    """
    filenames: list[str] = []
    after: str | None = None
    while True:
        data = _graphql_request(
            endpoint=graphql_endpoint,
            access_token=access_token,
            query=query,
            variables={"id": _theme_gid(theme_id), "first": 250, "after": after},
        )
        theme = data.get("theme")
        if not isinstance(theme, dict):
            _fail(f"Theme not found for id={theme_id}.")
        files_conn = theme.get("files")
        if not isinstance(files_conn, dict):
            _fail(f"Theme files payload missing for id={theme_id}.")
        nodes = files_conn.get("nodes")
        if not isinstance(nodes, list):
            _fail(f"Theme files nodes payload invalid for id={theme_id}.")
        for node in nodes:
            if not isinstance(node, dict):
                continue
            filename = node.get("filename")
            if isinstance(filename, str) and filename:
                filenames.append(filename)
        page_info = files_conn.get("pageInfo")
        if not isinstance(page_info, dict):
            _fail(f"Theme files pageInfo payload missing for id={theme_id}.")
        has_next = page_info.get("hasNextPage")
        if has_next is True:
            after = page_info.get("endCursor")
            if not isinstance(after, str) or not after:
                _fail("Theme files pagination indicated next page but no endCursor was returned.")
            continue
        if has_next is False:
            break
        _fail("Theme files pagination payload has invalid hasNextPage value.")
    return filenames


def _load_zip_files(zip_path: Path) -> tuple[list[LocalZipFile], list[str]]:
    if not zip_path.exists():
        _fail(f"ZIP file does not exist: {zip_path}")

    entries: list[LocalZipFile] = []
    skipped_filenames: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(name for name in archive.namelist() if not name.endswith("/"))
        if not names:
            _fail(f"ZIP contains no files: {zip_path}")
        for filename in names:
            root = filename.split("/", 1)[0].strip().lower()
            if root not in SHOPIFY_THEME_ROOT_DIRECTORIES:
                skipped_filenames.append(filename)
                continue
            raw = archive.read(filename)
            sha = hashlib.sha256(raw).hexdigest()
            try:
                text = raw.decode("utf-8")
                entries.append(
                    LocalZipFile(
                        filename=filename,
                        raw_bytes=raw,
                        sha256=sha,
                        body_type="TEXT",
                        body_value=text,
                        body_size_hint=len(raw),
                    )
                )
            except UnicodeDecodeError:
                b64 = base64.b64encode(raw).decode("ascii")
                entries.append(
                    LocalZipFile(
                        filename=filename,
                        raw_bytes=raw,
                        sha256=sha,
                        body_type="BASE64",
                        body_value=b64,
                        body_size_hint=len(b64),
                    )
                )
    if not entries:
        _fail(
            "ZIP has no Shopify-uploadable theme files under supported roots: "
            f"{sorted(SHOPIFY_THEME_ROOT_DIRECTORIES)}"
        )
    return entries, skipped_filenames


def _upsert_theme_files(
    *,
    graphql_endpoint: str,
    access_token: str,
    theme_id: str,
    zip_files: list[LocalZipFile],
) -> int:
    mutation = """
    mutation upsertThemeFiles($themeId: ID!, $files: [OnlineStoreThemeFilesUpsertFileInput!]!) {
      themeFilesUpsert(themeId: $themeId, files: $files) {
        upsertedThemeFiles {
          filename
        }
        userErrors {
          field
          message
        }
        job {
          id
          done
        }
      }
    }
    """

    uploaded_count = 0
    current_batch: list[dict[str, Any]] = []
    current_batch_filenames: list[str] = []
    current_batch_size = 0

    def flush_batch() -> None:
        nonlocal uploaded_count, current_batch, current_batch_filenames, current_batch_size
        if not current_batch:
            return
        data = _graphql_request(
            endpoint=graphql_endpoint,
            access_token=access_token,
            query=mutation,
            variables={"themeId": _theme_gid(theme_id), "files": current_batch},
        )
        upsert_payload = data.get("themeFilesUpsert")
        if not isinstance(upsert_payload, dict):
            _fail("themeFilesUpsert response is missing payload.")
        user_errors = upsert_payload.get("userErrors")
        if isinstance(user_errors, list) and user_errors:
            _fail(
                "themeFilesUpsert returned userErrors for batch: "
                f"first_file={current_batch_filenames[0]!r}, errors={user_errors}"
            )
        upserted = upsert_payload.get("upsertedThemeFiles")
        if not isinstance(upserted, list):
            _fail("themeFilesUpsert response is missing upsertedThemeFiles.")
        got = sorted(
            item.get("filename")
            for item in upserted
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        )
        expected = sorted(current_batch_filenames)
        if got != expected:
            missing = sorted(set(expected) - set(got))
            extra = sorted(set(got) - set(expected))
            _fail(
                "themeFilesUpsert did not confirm expected files in batch. "
                f"missing={missing[:20]}, extra={extra[:20]}, "
                f"expected_count={len(expected)}, got_count={len(got)}"
            )
        uploaded_count += len(expected)
        current_batch = []
        current_batch_filenames = []
        current_batch_size = 0

    for entry in zip_files:
        next_file = {
            "filename": entry.filename,
            "body": {
                "type": entry.body_type,
                "value": entry.body_value,
            },
        }

        if entry.body_size_hint > MAX_BATCH_BYTES:
            flush_batch()
            current_batch = [next_file]
            current_batch_filenames = [entry.filename]
            current_batch_size = entry.body_size_hint
            flush_batch()
            continue

        needs_flush = (
            len(current_batch) + 1 > MAX_FILES_PER_BATCH
            or current_batch_size + entry.body_size_hint > MAX_BATCH_BYTES
        )
        if needs_flush:
            flush_batch()

        current_batch.append(next_file)
        current_batch_filenames.append(entry.filename)
        current_batch_size += entry.body_size_hint

    flush_batch()
    return uploaded_count


def _fetch_theme_file_bodies(
    *,
    graphql_endpoint: str,
    access_token: str,
    theme_id: str,
    filenames: list[str],
) -> dict[str, bytes]:
    query = """
    query themeFileBodies($id: ID!, $filenames: [String!]!) {
      theme(id: $id) {
        files(first: 250, filenames: $filenames) {
          nodes {
            filename
            body {
              __typename
              ... on OnlineStoreThemeFileBodyText {
                content
              }
              ... on OnlineStoreThemeFileBodyBase64 {
                contentBase64
              }
            }
          }
        }
      }
    }
    """
    if not filenames:
        return {}
    data = _graphql_request(
        endpoint=graphql_endpoint,
        access_token=access_token,
        query=query,
        variables={"id": _theme_gid(theme_id), "filenames": filenames},
    )
    theme = data.get("theme")
    if not isinstance(theme, dict):
        _fail(f"Theme not found while fetching file bodies for id={theme_id}.")
    files_payload = theme.get("files")
    if not isinstance(files_payload, dict):
        _fail("Theme file body response is missing files payload.")
    nodes = files_payload.get("nodes")
    if not isinstance(nodes, list):
        _fail("Theme file body response is missing nodes payload.")
    output: dict[str, bytes] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        filename = node.get("filename")
        body = node.get("body")
        if not isinstance(filename, str) or not filename:
            continue
        if not isinstance(body, dict):
            _fail(f"Theme file body response is missing body for filename={filename}.")
        body_type = body.get("__typename")
        if body_type == "OnlineStoreThemeFileBodyText":
            content = body.get("content")
            if not isinstance(content, str):
                _fail(f"Text file body content missing for filename={filename}.")
            output[filename] = content.encode("utf-8")
            continue
        if body_type == "OnlineStoreThemeFileBodyBase64":
            content_b64 = body.get("contentBase64")
            if not isinstance(content_b64, str):
                _fail(f"Base64 file body content missing for filename={filename}.")
            output[filename] = base64.b64decode(content_b64)
            continue
        _fail(
            "Unsupported theme file body type for validation. "
            f"filename={filename}, body_type={body_type!r}"
        )
    return output


def _validate_full_content_parity(
    *,
    graphql_endpoint: str,
    access_token: str,
    theme_id: str,
    zip_files: list[LocalZipFile],
) -> None:
    local_by_filename = {entry.filename: entry for entry in zip_files}
    filenames = sorted(local_by_filename.keys())
    chunk_size = 50
    for index in range(0, len(filenames), chunk_size):
        chunk = filenames[index : index + chunk_size]
        remote_payloads = _fetch_theme_file_bodies(
            graphql_endpoint=graphql_endpoint,
            access_token=access_token,
            theme_id=theme_id,
            filenames=chunk,
        )
        if sorted(remote_payloads.keys()) != sorted(chunk):
            missing = sorted(set(chunk) - set(remote_payloads.keys()))
            extra = sorted(set(remote_payloads.keys()) - set(chunk))
            _fail(
                "Remote file-body lookup mismatch. "
                f"missing={missing[:20]}, extra={extra[:20]}"
            )
        for filename in chunk:
            local_sha = local_by_filename[filename].sha256
            remote_sha = hashlib.sha256(remote_payloads[filename]).hexdigest()
            if local_sha != remote_sha:
                _fail(
                    "Remote file checksum mismatch. "
                    f"filename={filename}, expected_sha={local_sha}, got_sha={remote_sha}"
                )


def _upload_order_key(entry: LocalZipFile) -> tuple[int, int, str]:
    root = entry.filename.split("/", 1)[0].strip().lower()
    extension = Path(entry.filename).suffix.lower()

    root_priority = {
        "assets": 10,
        "snippets": 20,
        "sections": 30,
        "layout": 40,
        "config": 50,
        "locales": 60,
        "templates": 70,
    }.get(root, 90)

    if extension == ".liquid":
        extension_priority = 0
    elif extension == ".json":
        extension_priority = 2
    else:
        extension_priority = 1

    return root_priority, extension_priority, entry.filename


def _probe_preview_routes(
    *,
    shop_domain: str,
    theme_id: str,
) -> dict[str, dict[str, Any]]:
    base_url = f"https://{shop_domain}"
    preview_suffix = f"?preview_theme_id={theme_id}"
    probe_urls = {
        "home": f"{base_url}/{preview_suffix}",
        "missing_path": f"{base_url}/this-route-should-not-exist-codex{preview_suffix}",
        "missing_product": f"{base_url}/products/non-existent-product{preview_suffix}",
    }
    statuses: dict[str, dict[str, Any]] = {}
    for key, url in probe_urls.items():
        response = requests.get(url, timeout=60)
        text_lower = response.text.lower()
        statuses[key] = {
            "url": url,
            "status": response.status_code,
            "final_url": response.url,
            "content_length": len(response.text),
            "contains_page_not_found_text": "page not found" in text_lower,
            "title_present": "<title" in text_lower,
        }
    return statuses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a fresh unpublished Shopify validation theme, upload all files "
            "from a local ZIP, and verify remote parity."
        )
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        required=True,
        help="Path to Shopify theme ZIP to upload.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("shopify-funnel-app/shopify_funnel_app.db"),
        help="Path to Shopify app SQLite DB with shop_installations.",
    )
    parser.add_argument(
        "--client-id",
        type=str,
        default=None,
        help="Optional client ID to select a specific shop_installation row.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=Path("shopify-funnel-app/theme/last_upload_validation.json"),
        help="Path to write validation result JSON.",
    )
    parser.add_argument(
        "--theme-id",
        type=str,
        default=None,
        help=(
            "Optional existing Shopify theme ID to sync into. "
            "When omitted, a fresh unpublished validation theme is created."
        ),
    )
    parser.add_argument(
        "--theme-name",
        type=str,
        default=None,
        help="Optional display name used in result output when --theme-id is provided.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    shop_domain, access_token = _load_shop_installation(
        db_path=args.db_path,
        client_id=args.client_id,
    )
    admin_rest_endpoint = f"https://{shop_domain}/admin/api/{API_VERSION}"
    graphql_endpoint = f"{admin_rest_endpoint}/graphql.json"

    zip_files, skipped_zip_files = _load_zip_files(args.zip_path)
    zip_files = sorted(zip_files, key=_upload_order_key)
    zip_filenames = sorted(entry.filename for entry in zip_files)

    if isinstance(args.theme_id, str) and args.theme_id.strip():
        theme_id = args.theme_id.strip()
        if args.theme_name and args.theme_name.strip():
            theme_name = args.theme_name.strip()
        else:
            theme_name = f"existing-theme-{theme_id}"
    else:
        theme_id, theme_name = _create_fresh_validation_theme(
            admin_rest_endpoint=admin_rest_endpoint,
            access_token=access_token,
        )

    initial_filenames = _list_theme_filenames(
        graphql_endpoint=graphql_endpoint,
        access_token=access_token,
        theme_id=theme_id,
    )
    created_fresh_theme = not (
        isinstance(args.theme_id, str) and args.theme_id.strip()
    )
    if created_fresh_theme and initial_filenames:
        _fail(
            "Fresh validation theme was expected to be empty but has files. "
            f"theme_id={theme_id}, sample={sorted(initial_filenames)[:20]}"
        )

    uploaded_count = _upsert_theme_files(
        graphql_endpoint=graphql_endpoint,
        access_token=access_token,
        theme_id=theme_id,
        zip_files=zip_files,
    )

    remote_filenames = sorted(
        _list_theme_filenames(
            graphql_endpoint=graphql_endpoint,
            access_token=access_token,
            theme_id=theme_id,
        )
    )
    if remote_filenames != zip_filenames:
        missing = sorted(set(zip_filenames) - set(remote_filenames))
        extra = sorted(set(remote_filenames) - set(zip_filenames))
        _fail(
            "Remote theme filenames do not exactly match ZIP filenames. "
            f"missing_count={len(missing)}, extra_count={len(extra)}, "
            f"missing_sample={missing[:20]}, extra_sample={extra[:20]}"
        )

    _validate_full_content_parity(
        graphql_endpoint=graphql_endpoint,
        access_token=access_token,
        theme_id=theme_id,
        zip_files=zip_files,
    )

    preview_url = f"https://{shop_domain}/?preview_theme_id={theme_id}"
    route_status = _probe_preview_routes(shop_domain=shop_domain, theme_id=theme_id)

    result = {
        "shopDomain": shop_domain,
        "themeId": theme_id,
        "themeName": theme_name,
        "createdFreshTheme": created_fresh_theme,
        "initialThemeFileCount": len(initial_filenames),
        "zipFileCount": len(zip_filenames),
        "skippedZipFileCount": len(skipped_zip_files),
        "skippedZipFiles": skipped_zip_files,
        "uploadedFileCount": uploaded_count,
        "remoteFileCount": len(remote_filenames),
        "filenameParity": True,
        "contentParity": True,
        "previewUrl": preview_url,
        "routeStatus": route_status,
        "validatedAt": datetime.now(UTC).isoformat(),
    }

    args.result_path.parent.mkdir(parents=True, exist_ok=True)
    args.result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
