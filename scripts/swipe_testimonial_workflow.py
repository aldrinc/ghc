#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import functools
import http.server
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterator


_LOCAL_HOSTS = {"127.0.0.1", "localhost"}
_IMAGE_KEYS = {
    "assetPublicId",
    "src",
    "thumbAssetPublicId",
    "thumbSrc",
    "referenceAssetPublicId",
    "testimonialTemplate",
    "imageSource",
    "alt",
}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{field_name} must be an object.")
    return value


def _require_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be an array.")
    return value


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeError(f"{field_name} must be a boolean.")
    return value


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _require_optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field_name)


def _require_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"{field_name} must be an integer.")
    return value


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _encode_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _resolve_json_pointer(root: Any, pointer: str) -> Any:
    if pointer == "":
        return root
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise RuntimeError(f"JSON pointer must start with '/'. Received: {pointer!r}")
    current = root
    for raw_token in pointer.split("/")[1:]:
        token = _decode_pointer_token(raw_token)
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError as exc:
                raise RuntimeError(f"JSON pointer token {token!r} is not a list index for {pointer!r}.") from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise RuntimeError(f"JSON pointer index {index} is out of range for {pointer!r}.") from exc
            continue
        if isinstance(current, dict):
            if token not in current:
                raise RuntimeError(f"JSON pointer token {token!r} was not found in {pointer!r}.")
            current = current[token]
            continue
        raise RuntimeError(f"JSON pointer {pointer!r} walks into a non-container value.")
    return current


def _is_image_like_object(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if _IMAGE_KEYS.intersection(value.keys()):
        return True
    value_type = value.get("type")
    if value_type in {"image", "video"} and any(key in value for key in ("src", "assetPublicId", "alt")):
        return True
    return False


def _iter_image_slots(value: Any, *, pointer: str = "") -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if _is_image_like_object(value):
            yield {
                "pointer": pointer,
                "keys": sorted(value.keys()),
                "alt": value.get("alt"),
                "assetPublicId": value.get("assetPublicId"),
                "src": value.get("src"),
                "thumbAssetPublicId": value.get("thumbAssetPublicId"),
                "thumbSrc": value.get("thumbSrc"),
                "testimonialTemplate": value.get("testimonialTemplate"),
                "type": value.get("type"),
            }
        for key, child in value.items():
            child_pointer = f"{pointer}/{_encode_pointer_token(str(key))}"
            yield from _iter_image_slots(child, pointer=child_pointer)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            yield from _iter_image_slots(child, pointer=child_pointer)


class _JsonApiClient:
    def __init__(self, *, base_url: str, auth_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token

    def _request(self, *, method: str, path: str, payload: Any = None) -> Any:
        url = f"{self.base_url}{path}"
        body: bytes | None = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"{method} {path} failed with status {exc.code}: {detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{method} {path} returned invalid JSON.") from exc

    def get(self, path: str) -> Any:
        return self._request(method="GET", path=path)

    def post(self, path: str, payload: Any) -> Any:
        return self._request(method="POST", path=path, payload=payload)

    def put(self, path: str, payload: Any) -> Any:
        return self._request(method="PUT", path=path, payload=payload)


def _extract_zip(zip_path: Path, destination_root: Path) -> list[str]:
    if not zip_path.exists():
        raise RuntimeError(f"sourceZip does not exist: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise RuntimeError(f"sourceZip is not a zip archive: {zip_path}")

    usable_members: list[tuple[zipfile.ZipInfo, Path]] = []
    destination_root_resolved = destination_root.resolve()
    extracted_files: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename
            if not name or name.endswith("/"):
                continue
            member_path = Path(name)
            if member_path.parts and member_path.parts[0] == "__MACOSX":
                continue
            if member_path.name in {".DS_Store"} or member_path.name.startswith("._"):
                continue
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"Unsafe zip member path: {name}")
            usable_members.append((member, member_path))

        strip_leading_directory = False
        top_levels = {member_path.parts[0] for _, member_path in usable_members}
        if usable_members and len(top_levels) == 1 and all(len(member_path.parts) >= 2 for _, member_path in usable_members):
            strip_leading_directory = True

        for member, member_path in usable_members:
            relative_path = Path(*member_path.parts[1:]) if strip_leading_directory else member_path
            output_path = (destination_root / relative_path).resolve()
            if destination_root_resolved not in output_path.parents and output_path != destination_root_resolved:
                raise RuntimeError(f"Zip member escapes extraction root: {name}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, output_path.open("wb") as dst:
                dst.write(src.read())
            extracted_files.append(str(relative_path.as_posix()))
    if not extracted_files:
        raise RuntimeError(f"sourceZip did not contain any usable files: {zip_path}")
    return extracted_files


def _collect_template_files(template_root: Path) -> list[str]:
    if not template_root.exists():
        raise RuntimeError(f"templateImagesDir does not exist: {template_root}")
    if not template_root.is_dir():
        raise RuntimeError(f"templateImagesDir must be a directory: {template_root}")

    files: list[str] = []
    for path in template_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(template_root).as_posix()
        if relative.startswith("__MACOSX/"):
            continue
        if path.name.startswith("."):
            continue
        files.append(relative)
    if not files:
        raise RuntimeError(f"templateImagesDir does not contain any usable files: {template_root}")
    return sorted(files)


def _resolve_template_member(*, template_files: list[str], template_file: str) -> str:
    normalized = template_file.strip().replace("\\", "/")
    if normalized in template_files:
        return normalized

    basename_matches = [entry for entry in template_files if Path(entry).name == normalized]
    if not basename_matches:
        raise RuntimeError(
            f"templateFile {template_file!r} was not found in templateImagesDir. "
            f"Available files: {', '.join(sorted(template_files))}"
        )
    if len(basename_matches) > 1:
        raise RuntimeError(
            f"templateFile {template_file!r} is ambiguous in templateImagesDir. "
            f"Matches: {', '.join(sorted(basename_matches))}"
        )
    return basename_matches[0]


class _StaticServer:
    def __init__(self, *, root: Path, host: str, port: int) -> None:
        class _QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

        handler = functools.partial(_QuietHandler, directory=str(root))
        self._server = http.server.ThreadingHTTPServer((host, port), handler)
        self.host = host
        self.port = int(self._server.server_port)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_StaticServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.port}"


def _token_from_env(env_var_name: str) -> str:
    token = os.getenv(env_var_name, "").strip()
    if not token:
        raise RuntimeError(f"Environment variable {env_var_name} is required and was not set.")
    return token


def _fetch_page_puck(client: _JsonApiClient, *, funnel_id: str, page_id: str, page_source: str) -> dict[str, Any]:
    detail = client.get(f"/funnels/{funnel_id}/pages/{page_id}")
    detail_obj = _require_dict(detail, "page detail response")
    latest_draft = detail_obj.get("latestDraft")
    latest_approved = detail_obj.get("latestApproved")

    if page_source == "latestDraft":
        draft = _require_dict(latest_draft, f"latestDraft for funnelId={funnel_id} pageId={page_id}")
        puck = draft.get("puck_data")
    elif page_source == "latestApproved":
        approved = _require_dict(latest_approved, f"latestApproved for funnelId={funnel_id} pageId={page_id}")
        puck = approved.get("puck_data")
    elif page_source == "latestDraftOrApproved":
        if isinstance(latest_draft, dict):
            puck = latest_draft.get("puck_data")
        elif isinstance(latest_approved, dict):
            puck = latest_approved.get("puck_data")
        else:
            raise RuntimeError(
                f"Neither latestDraft nor latestApproved exists for funnelId={funnel_id} pageId={page_id}."
            )
    else:
        raise RuntimeError(
            f"pageSource must be one of latestDraft, latestApproved, latestDraftOrApproved. Received: {page_source!r}"
        )

    return copy.deepcopy(_require_dict(puck, f"puckData for funnelId={funnel_id} pageId={page_id}"))


def _assets_by_id(
    client: _JsonApiClient,
    *,
    campaign_id: str,
    product_id: str,
    required_asset_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not required_asset_ids:
        return {}
    query = urllib.parse.urlencode(
        {
            "campaignId": campaign_id,
            "productId": product_id,
            "assetKind": "image",
        }
    )
    response = client.get(f"/assets?{query}")
    rows = _require_list(response, "assets response")
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _require_dict(row, "asset row")
        asset_id = _require_optional_string(item.get("id"), "asset.id")
        if asset_id and asset_id in required_asset_ids:
            by_id[asset_id] = item
    missing = sorted(required_asset_ids.difference(by_id.keys()))
    if missing:
        raise RuntimeError(
            "Failed to resolve asset public ids for generated assets. "
            f"Missing asset ids: {', '.join(missing)}"
        )
    return by_id


def _apply_asset_to_pointer(
    *,
    puck_data: dict[str, Any],
    slot_pointer: str,
    public_id: str,
    alt: str | None,
    write_public_id_fields: list[str],
    clear_fields: list[str],
) -> None:
    target = _resolve_json_pointer(puck_data, slot_pointer)
    if not isinstance(target, dict):
        raise RuntimeError(f"slotPointer must resolve to an object. Received: {slot_pointer!r}")
    for field_name in write_public_id_fields:
        target[field_name] = public_id
    for field_name in clear_fields:
        target.pop(field_name, None)
    if alt is not None:
        target["alt"] = alt


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    rows = _require_list(value, field_name)
    normalized: list[str] = []
    for index, item in enumerate(rows):
        normalized.append(_require_string(item, f"{field_name}[{index}]"))
    return normalized


def _merged_generation_payload(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(defaults)
    if overrides:
        merged.update(overrides)

    org_id = _require_string(merged.get("orgId"), "generation.orgId")
    client_id = _require_string(merged.get("clientId"), "generation.clientId")
    product_id = _require_string(merged.get("productId"), "generation.productId")
    campaign_id = _require_string(merged.get("campaignId"), "generation.campaignId")
    asset_brief_id = _require_string(merged.get("assetBriefId"), "generation.assetBriefId")
    requirement_index = _require_int(merged.get("requirementIndex"), "generation.requirementIndex")
    model = _require_optional_string(merged.get("model"), "generation.model")
    render_model_id = _require_optional_string(merged.get("renderModelId"), "generation.renderModelId")
    aspect_ratio = _require_string(merged.get("aspectRatio"), "generation.aspectRatio")
    count = _require_int(merged.get("count"), "generation.count")
    if count != 1:
        raise RuntimeError("generation.count must be exactly 1 for slot-based page application.")

    payload = {
        "orgId": org_id,
        "clientId": client_id,
        "productId": product_id,
        "campaignId": campaign_id,
        "assetBriefId": asset_brief_id,
        "requirementIndex": requirement_index,
        "aspectRatio": aspect_ratio,
        "count": count,
    }
    if model is not None:
        payload["model"] = model
    if render_model_id is not None:
        payload["renderModelId"] = render_model_id
    return payload


def _swipe_generation_request_payload(generation: dict[str, Any], swipe_image_url: str) -> dict[str, Any]:
    payload = {
        "clientId": generation["clientId"],
        "productId": generation["productId"],
        "campaignId": generation["campaignId"],
        "assetBriefId": generation["assetBriefId"],
        "requirementIndex": generation["requirementIndex"],
        "swipeImageUrl": swipe_image_url,
        "aspectRatio": generation["aspectRatio"],
        "count": generation["count"],
    }
    if "model" in generation:
        payload["model"] = generation["model"]
    if "renderModelId" in generation:
        payload["renderModelId"] = generation["renderModelId"]
    return payload


def _start_swipe_generation(client: _JsonApiClient, *, payload: dict[str, Any]) -> dict[str, str]:
    response = _require_dict(
        client.post("/swipes/generate-image-ad", payload),
        "swipe generation response",
    )
    return {
        "workflowRunId": _require_string(response.get("workflow_run_id"), "swipe generation workflow_run_id"),
        "temporalWorkflowId": _require_string(
            response.get("temporal_workflow_id"),
            "swipe generation temporal_workflow_id",
        ),
    }


def _extract_completed_swipe_result(workflow_response: dict[str, Any]) -> dict[str, str]:
    logs = _require_list(workflow_response.get("logs"), "workflow logs")
    for raw_log in logs:
        log = _require_dict(raw_log, "workflow log")
        step = str(log.get("step") or "").strip()
        status = str(log.get("status") or "").strip()
        if step != "swipe_image_ad" or status != "succeeded":
            continue
        payload_out = _require_dict(log.get("payload_out"), "swipe_image_ad success payload_out")
        asset_ids = _normalize_string_list(payload_out.get("asset_ids"), "swipe_image_ad payload_out.asset_ids")
        if len(asset_ids) != 1:
            raise RuntimeError(
                "Swipe generation completed but returned an unexpected number of assets. "
                f"Expected exactly 1, received {len(asset_ids)}."
            )
        return {
            "jobId": _require_string(payload_out.get("job_id"), "swipe_image_ad payload_out.job_id"),
            "assetId": asset_ids[0],
        }
    raise RuntimeError("Swipe generation completed but no successful swipe_image_ad log entry was found.")


def _workflow_failure_detail(workflow_response: dict[str, Any]) -> str:
    logs = workflow_response.get("logs")
    if isinstance(logs, list):
        for raw_log in logs:
            if not isinstance(raw_log, dict):
                continue
            error = raw_log.get("error")
            if isinstance(error, str) and error.strip():
                return error.strip()
    run = workflow_response.get("run")
    if isinstance(run, dict):
        status = run.get("status")
        if isinstance(status, str) and status.strip():
            return f"workflow status is {status.strip()}"
    return "workflow failed without an error detail"


def _wait_for_swipe_generation(
    client: _JsonApiClient,
    *,
    workflow_run_id: str,
    timeout_seconds: int = 1200,
    poll_interval_seconds: int = 5,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise RuntimeError("timeout_seconds must be greater than zero.")
    if poll_interval_seconds <= 0:
        raise RuntimeError("poll_interval_seconds must be greater than zero.")

    deadline = time.monotonic() + timeout_seconds
    while True:
        workflow_response = _require_dict(
            client.get(f"/workflows/{urllib.parse.quote(workflow_run_id, safe='')}"),
            "workflow detail response",
        )
        run = _require_dict(workflow_response.get("run"), "workflow detail response.run")
        status = _require_string(run.get("status"), "workflow detail response.run.status")
        if status == "completed":
            return workflow_response
        if status in {"failed", "cancelled"}:
            raise RuntimeError(
                f"Swipe generation workflow {workflow_run_id} ended with status {status}: "
                f"{_workflow_failure_detail(workflow_response)}"
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Timed out waiting for swipe generation workflow {workflow_run_id} "
                f"after {timeout_seconds} seconds."
            )
        time.sleep(poll_interval_seconds)


def _prepare_templates(args: argparse.Namespace) -> int:
    zip_path = Path(args.zip).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = _extract_zip(zip_path, output_dir)
    print(
        json.dumps(
            {
                "zipPath": str(zip_path),
                "outputDir": str(output_dir),
                "templateFiles": sorted(extracted),
            },
            indent=2,
        )
    )
    return 0


def _run_workflow(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    config = _require_dict(_load_json(config_path), "workflow config")

    mos_base_url = _require_string(config.get("mosBaseUrl"), "mosBaseUrl")
    auth_token_env = _require_string(config.get("authTokenEnv"), "authTokenEnv")
    template_images_dir = Path(
        _require_string(config.get("templateImagesDir"), "templateImagesDir")
    ).expanduser().resolve()
    generation_defaults = _require_dict(config.get("generationDefaults"), "generationDefaults")
    pages = _require_list(config.get("pages"), "pages")
    patched_output_dir_raw = config.get("patchedOutputDir")
    patched_output_dir = (
        Path(_require_string(patched_output_dir_raw, "patchedOutputDir")).expanduser().resolve()
        if patched_output_dir_raw is not None
        else None
    )
    serve_host = str(config.get("sourceServeHost") or "127.0.0.1").strip()
    serve_port_raw = config.get("sourceServePort", 0)
    if not isinstance(serve_port_raw, int) or serve_port_raw < 0:
        raise RuntimeError("sourceServePort must be a non-negative integer.")
    serve_port = int(serve_port_raw)

    mos_host = urllib.parse.urlparse(mos_base_url).hostname or ""
    if mos_host not in _LOCAL_HOSTS and serve_host in _LOCAL_HOSTS:
        raise RuntimeError(
            "mosBaseUrl does not point to a local backend, but sourceServeHost is local-only. "
            "Choose a sourceServeHost reachable from the MOS backend or run against a local MOS backend."
        )

    client = _JsonApiClient(base_url=mos_base_url, auth_token=_token_from_env(auth_token_env))
    summary: dict[str, Any] = {
        "configPath": str(config_path),
        "templateImagesDir": str(template_images_dir),
        "pages": [],
    }
    template_files = _collect_template_files(template_images_dir)

    generation_cache: dict[str, dict[str, Any]] = {}

    with _StaticServer(root=template_images_dir, host=serve_host, port=serve_port) as static_server:
        summary["templateBaseUrl"] = static_server.base_url

        for page_index, raw_page in enumerate(pages):
            page_cfg = _require_dict(raw_page, f"pages[{page_index}]")
            funnel_id = _require_string(page_cfg.get("funnelId"), f"pages[{page_index}].funnelId")
            page_id = _require_string(page_cfg.get("pageId"), f"pages[{page_index}].pageId")
            page_source = _require_string(page_cfg.get("pageSource"), f"pages[{page_index}].pageSource")
            save_draft = _require_bool(page_cfg.get("saveDraft"), f"pages[{page_index}].saveDraft")
            placements = _require_list(page_cfg.get("placements"), f"pages[{page_index}].placements")
            if not placements:
                raise RuntimeError(f"pages[{page_index}].placements must not be empty.")
            if not save_draft and patched_output_dir is None:
                raise RuntimeError("patchedOutputDir is required when any page has saveDraft=false.")

            puck_data = _fetch_page_puck(
                client,
                funnel_id=funnel_id,
                page_id=page_id,
                page_source=page_source,
            )
            page_summary: dict[str, Any] = {
                "funnelId": funnel_id,
                "pageId": page_id,
                "pageSource": page_source,
                "saveDraft": save_draft,
                "placements": [],
            }

            for placement_index, raw_placement in enumerate(placements):
                placement_cfg = _require_dict(
                    raw_placement,
                    f"pages[{page_index}].placements[{placement_index}]",
                )
                placement_name = _require_string(
                    placement_cfg.get("name"),
                    f"pages[{page_index}].placements[{placement_index}].name",
                )
                template_file = _require_string(
                    placement_cfg.get("templateFile"),
                    f"pages[{page_index}].placements[{placement_index}].templateFile",
                )
                slot_pointer = _require_string(
                    placement_cfg.get("slotPointer"),
                    f"pages[{page_index}].placements[{placement_index}].slotPointer",
                )
                write_public_id_fields = _normalize_string_list(
                    placement_cfg.get("writePublicIdFields"),
                    f"pages[{page_index}].placements[{placement_index}].writePublicIdFields",
                )
                clear_fields = _normalize_string_list(
                    placement_cfg.get("clearFields", []),
                    f"pages[{page_index}].placements[{placement_index}].clearFields",
                )
                alt = _require_optional_string(
                    placement_cfg.get("alt"),
                    f"pages[{page_index}].placements[{placement_index}].alt",
                )
                generation_overrides = placement_cfg.get("generation")
                if generation_overrides is not None:
                    generation_overrides = _require_dict(
                        generation_overrides,
                        f"pages[{page_index}].placements[{placement_index}].generation",
                    )
                generation = _merged_generation_payload(generation_defaults, generation_overrides)
                template_member = _resolve_template_member(
                    template_files=template_files,
                    template_file=template_file,
                )
                template_url = f"{static_server.base_url}/{urllib.parse.quote(template_member)}"
                payload = _swipe_generation_request_payload(generation, template_url)
                cache_key = json.dumps(payload, sort_keys=True)

                if cache_key not in generation_cache:
                    workflow_ref = _start_swipe_generation(
                        client,
                        payload=payload,
                    )
                    workflow_response = _wait_for_swipe_generation(
                        client,
                        workflow_run_id=workflow_ref["workflowRunId"],
                    )
                    swipe_result = _extract_completed_swipe_result(workflow_response)
                    asset_id = _require_string(
                        swipe_result.get("assetId"),
                        "swipe generation assetId",
                    )
                    asset_map = _assets_by_id(
                        client,
                        campaign_id=generation["campaignId"],
                        product_id=generation["productId"],
                        required_asset_ids={asset_id},
                    )
                    resolved_asset = {
                        "assetId": asset_id,
                        "publicId": _require_string(
                            asset_map[asset_id].get("public_id"),
                            f"asset public_id for {asset_id}",
                        ),
                    }
                    generation_cache[cache_key] = {
                        "workflowRunId": workflow_ref["workflowRunId"],
                        "temporalWorkflowId": workflow_ref["temporalWorkflowId"],
                        "jobId": _require_string(swipe_result.get("jobId"), "swipe generation jobId"),
                        "templateMember": template_member,
                        "templateUrl": template_url,
                        "asset": resolved_asset,
                        "generation": generation,
                    }

                generation_result = generation_cache[cache_key]
                generated_asset = _require_dict(generation_result.get("asset"), "generation asset")
                public_id = _require_string(generated_asset.get("publicId"), "generated asset publicId")

                _apply_asset_to_pointer(
                    puck_data=puck_data,
                    slot_pointer=slot_pointer,
                    public_id=public_id,
                    alt=alt,
                    write_public_id_fields=write_public_id_fields,
                    clear_fields=clear_fields,
                )

                page_summary["placements"].append(
                    {
                        "name": placement_name,
                        "slotPointer": slot_pointer,
                        "templateFile": template_file,
                        "resolvedTemplateMember": generation_result["templateMember"],
                        "workflowRunId": generation_result["workflowRunId"],
                        "temporalWorkflowId": generation_result["temporalWorkflowId"],
                        "jobId": generation_result["jobId"],
                        "assetId": generated_asset["assetId"],
                        "publicId": public_id,
                    }
                )

            if save_draft:
                saved = _require_dict(
                    client.put(
                        f"/funnels/{funnel_id}/pages/{page_id}",
                        {"puckData": puck_data},
                    ),
                    "save draft response",
                )
                page_summary["savedDraftVersionId"] = _require_string(saved.get("id"), "saved draft id")
            else:
                assert patched_output_dir is not None
                output_path = patched_output_dir / f"{funnel_id}_{page_id}.json"
                _write_json(output_path, puck_data)
                page_summary["patchedPuckPath"] = str(output_path)

            summary["pages"].append(page_summary)

    if args.output:
        _write_json(Path(args.output).expanduser().resolve(), summary)
    else:
        print(json.dumps(summary, indent=2))
    return 0


def _inspect_page(args: argparse.Namespace) -> int:
    base_url = _require_string(args.base_url, "--base-url")
    auth_token_env = _require_string(args.auth_token_env, "--auth-token-env")
    funnel_id = _require_string(args.funnel_id, "--funnel-id")
    page_id = _require_string(args.page_id, "--page-id")
    page_source = _require_string(args.page_source, "--page-source")

    client = _JsonApiClient(base_url=base_url, auth_token=_token_from_env(auth_token_env))
    puck_data = _fetch_page_puck(
        client,
        funnel_id=funnel_id,
        page_id=page_id,
        page_source=page_source,
    )
    slots = list(_iter_image_slots(puck_data))
    print(json.dumps(slots, indent=2))
    return 0


def _inspect_puck(args: argparse.Namespace) -> int:
    puck_data = _require_dict(_load_json(Path(args.input).expanduser().resolve()), "puckData file")
    slots = list(_iter_image_slots(puck_data))
    print(json.dumps(slots, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a wrapper workflow that uses repo-stored template images as swipe inputs "
            "for page-specific image placements."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_templates = subparsers.add_parser(
        "prepare-templates",
        help="Extract a template image zip into a repo directory for swipe generation.",
    )
    prepare_templates.add_argument("--zip", required=True, help="Path to the source zip archive.")
    prepare_templates.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the template images should be extracted.",
    )
    prepare_templates.set_defaults(func=_prepare_templates)

    inspect_page = subparsers.add_parser(
        "inspect-page",
        help="Fetch a MOS funnel page and list image-like JSON pointers for slot mapping.",
    )
    inspect_page.add_argument("--base-url", required=True)
    inspect_page.add_argument("--auth-token-env", required=True)
    inspect_page.add_argument("--funnel-id", required=True)
    inspect_page.add_argument("--page-id", required=True)
    inspect_page.add_argument(
        "--page-source",
        required=True,
        choices=["latestDraft", "latestApproved", "latestDraftOrApproved"],
    )
    inspect_page.set_defaults(func=_inspect_page)

    inspect_puck = subparsers.add_parser(
        "inspect-puck",
        help="List image-like JSON pointers from a local puckData JSON file.",
    )
    inspect_puck.add_argument("--input", required=True)
    inspect_puck.set_defaults(func=_inspect_puck)

    run_parser = subparsers.add_parser(
        "run",
        help="Use templateImagesDir for swipe generation and optionally save patched drafts.",
    )
    run_parser.add_argument("--config", required=True, help="Path to the workflow config JSON.")
    run_parser.add_argument(
        "--output",
        help="Optional path for a JSON summary file. Defaults to stdout.",
    )
    run_parser.set_defaults(func=_run_workflow)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
