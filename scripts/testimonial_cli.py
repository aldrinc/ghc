#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.browser_session_auth import BrowserSessionAuth
from lib.mos_api_client import MosApiClient


PDP_VARIANT_ORDER = (
    "standard_ugc",
    "qa_ugc",
    "bold_claim",
    "personal_highlight",
    "dorm_selfie",
)


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{label} must be a non-empty string.")
    return value.strip()


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object.")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be an array.")
    return value


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _prepare_output_dir(command_slug: str, output_dir: str | None) -> Path:
    if output_dir:
        target = Path(output_dir).expanduser().resolve()
    else:
        target = (Path.cwd() / "outputs" / f"{_timestamp_slug()}-{command_slug}").resolve()
    target.mkdir(parents=True, exist_ok=False)
    return target


def _content_extension(content_type: str, default_ext: str = ".bin") -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    ext = mimetypes.guess_extension(normalized) if normalized else None
    if ext == ".jpe":
        ext = ".jpg"
    return ext or default_ext


def _extract_swipe_asset_id(workflow_detail: dict[str, Any]) -> str:
    logs = _require_list(workflow_detail.get("logs"), "workflow.logs")
    for raw_log in logs:
        log = _require_dict(raw_log, "workflow.log")
        if str(log.get("step") or "").strip() != "swipe_image_ad":
            continue
        if str(log.get("status") or "").strip() != "succeeded":
            continue
        payload_out = _require_dict(log.get("payload_out"), "workflow.log.payload_out")
        asset_ids = _require_list(payload_out.get("asset_ids"), "workflow.log.payload_out.asset_ids")
        if len(asset_ids) != 1:
            raise RuntimeError(
                "Swipe workflow returned an unexpected asset count. "
                f"Expected 1, received {len(asset_ids)}."
            )
        return _require_string(asset_ids[0], "workflow.log.payload_out.asset_ids[0]")
    raise RuntimeError("Swipe workflow completed without a successful swipe_image_ad payload.")


def _workflow_failure_detail(workflow_detail: dict[str, Any]) -> str:
    logs = workflow_detail.get("logs")
    if isinstance(logs, list):
        for raw_log in logs:
            if not isinstance(raw_log, dict):
                continue
            error = raw_log.get("error")
            if isinstance(error, str) and error.strip():
                return error.strip()
    run = workflow_detail.get("run")
    if isinstance(run, dict):
        status_value = run.get("status")
        if isinstance(status_value, str) and status_value.strip():
            return f"workflow status is {status_value.strip()}"
    return "workflow failed without an error detail"


def _wait_for_workflows(
    client: MosApiClient,
    *,
    template_runs: list[dict[str, Any]],
    poll_interval_seconds: int,
) -> dict[str, dict[str, Any]]:
    pending = {
        _require_string(run.get("workflowRunId"), "templateRun.workflowRunId"): run
        for run in template_runs
    }
    completed: dict[str, dict[str, Any]] = {}

    while pending:
        for workflow_run_id in list(pending.keys()):
            workflow_detail = _require_dict(
                client.get_json(f"/workflows/{quote(workflow_run_id, safe='')}"),
                f"workflow detail for {workflow_run_id}",
            )
            run = _require_dict(workflow_detail.get("run"), f"workflow.run for {workflow_run_id}")
            status_value = _require_string(run.get("status"), f"workflow.run.status for {workflow_run_id}")
            if status_value == "completed":
                completed[workflow_run_id] = {
                    "workflow": workflow_detail,
                    "assetId": _extract_swipe_asset_id(workflow_detail),
                }
                pending.pop(workflow_run_id, None)
                continue
            if status_value in {"failed", "cancelled"}:
                raise RuntimeError(
                    f"Swipe template workflow {workflow_run_id} ended with status {status_value}: "
                    f"{_workflow_failure_detail(workflow_detail)}"
                )
        if pending:
            time.sleep(poll_interval_seconds)

    return completed


def _resolve_assets_by_id(
    client: MosApiClient,
    *,
    campaign_id: str,
    product_id: str,
    asset_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not asset_ids:
        return {}
    query = urlencode({"campaignId": campaign_id, "productId": product_id, "assetKind": "image"})
    rows = _require_list(client.get_json(f"/assets?{query}"), "assets response")
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _require_dict(row, "asset row")
        asset_id = item.get("id")
        if isinstance(asset_id, str) and asset_id in asset_ids:
            by_id[asset_id] = item
    missing = sorted(asset_ids.difference(by_id.keys()))
    if missing:
        raise RuntimeError(
            "Failed to resolve generated asset public ids. "
            f"Missing asset ids: {', '.join(missing)}."
        )
    return by_id


def _download_public_asset(
    client: MosApiClient,
    *,
    public_id: str,
    target_path: Path,
) -> str:
    data, content_type = client.get_binary(f"/public/assets/{quote(public_id, safe='')}")
    target_path.write_bytes(data)
    return content_type


def _run_pdp_examples(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {}
    if args.draft_version_id:
        payload["draftVersionId"] = args.draft_version_id
    if args.current_puck_data:
        payload["currentPuckData"] = _require_dict(
            _load_json_file(Path(args.current_puck_data).expanduser().resolve()),
            "--current-puck-data",
        )
    if args.model:
        payload["model"] = args.model
    if args.max_tokens is not None:
        payload["maxTokens"] = args.max_tokens
    if args.max_duration_seconds is not None:
        payload["maxDurationSeconds"] = args.max_duration_seconds
    payload["temperature"] = args.temperature

    output_dir = _prepare_output_dir("pdp-examples", args.output_dir)
    with BrowserSessionAuth(
        ui_url=args.ui_url,
        jwt_template=args.jwt_template,
        profile_dir=Path(args.profile_dir),
    ) as auth:
        client = MosApiClient(base_url=args.api_base_url, auth=auth)
        response = _require_dict(
            client.post_json(
                f"/funnels/{quote(args.funnel_id, safe='')}/pages/{quote(args.page_id, safe='')}/ai/sales-pdp-examples",
                payload,
            ),
            "sales PDP response",
        )
        generated_examples = _require_list(response.get("generatedPdpExamples"), "generatedPdpExamples")

        examples_by_variant: dict[str, dict[str, Any]] = {}
        for raw_item in generated_examples:
            item = _require_dict(raw_item, "generatedPdpExamples item")
            variant_id = _require_string(item.get("variantId"), "generatedPdpExamples.variantId")
            if variant_id in examples_by_variant:
                raise RuntimeError(f"Duplicate PDP example variant returned: {variant_id}")
            examples_by_variant[variant_id] = item
        missing = [variant_id for variant_id in PDP_VARIANT_ORDER if variant_id not in examples_by_variant]
        if missing:
            raise RuntimeError(
                "Backend did not return all 5 PDP example variants. "
                f"Missing: {', '.join(missing)}."
            )

        manifest_rows: list[dict[str, Any]] = []
        for index, variant_id in enumerate(PDP_VARIANT_ORDER, start=1):
            item = examples_by_variant[variant_id]
            public_id = _require_string(item.get("publicId"), f"generatedPdpExamples[{variant_id}].publicId")
            asset_id = _require_string(item.get("assetId"), f"generatedPdpExamples[{variant_id}].assetId")
            data, content_type = client.get_binary(f"/public/assets/{quote(public_id, safe='')}")
            ext = _content_extension(content_type, default_ext=".png")
            filename = f"{index:02d}-{variant_id}-{public_id}{ext}"
            target_path = output_dir / filename
            target_path.write_bytes(data)
            manifest_rows.append(
                {
                    "variantId": variant_id,
                    "assetId": asset_id,
                    "publicId": public_id,
                    "contentType": content_type,
                    "fileName": filename,
                    "filePath": str(target_path),
                }
            )

    _write_json(output_dir / "request.json", payload)
    _write_json(output_dir / "backend-response.json", response)
    _write_json(
        output_dir / "manifest.json",
        {
            "funnelId": args.funnel_id,
            "pageId": args.page_id,
            "draftVersionId": response.get("draftVersionId"),
            "outputDir": str(output_dir),
            "examples": manifest_rows,
        },
    )
    print(json.dumps({"outputDir": str(output_dir), "count": len(manifest_rows)}, indent=2))
    return 0


def _run_swipe_template_testimonials(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {
        "campaignId": args.campaign_id,
        "assetBriefId": args.asset_brief_id,
        "aspectRatio": args.aspect_ratio,
    }
    if args.model:
        payload["model"] = args.model
    if args.render_model_id:
        payload["renderModelId"] = args.render_model_id
    if args.max_output_tokens is not None:
        payload["maxOutputTokens"] = args.max_output_tokens

    output_dir = _prepare_output_dir("swipe-template-testimonials", args.output_dir)
    with BrowserSessionAuth(
        ui_url=args.ui_url,
        jwt_template=args.jwt_template,
        profile_dir=Path(args.profile_dir),
    ) as auth:
        client = MosApiClient(base_url=args.api_base_url, auth=auth)
        response = _require_dict(
            client.post_json("/swipes/generate-template-testimonials", payload),
            "swipe template testimonials response",
        )
        template_runs = _require_list(response.get("templateRuns"), "templateRuns")
        completed = _wait_for_workflows(
            client,
            template_runs=[_require_dict(item, "templateRuns item") for item in template_runs],
            poll_interval_seconds=args.poll_interval_seconds,
        )
        asset_map = _resolve_assets_by_id(
            client,
            campaign_id=_require_string(response.get("campaignId"), "campaignId"),
            product_id=_require_string(response.get("productId"), "productId"),
            asset_ids={result["assetId"] for result in completed.values()},
        )

        manifest_rows: list[dict[str, Any]] = []
        for index, raw_run in enumerate(template_runs, start=1):
            run = _require_dict(raw_run, "templateRuns item")
            workflow_run_id = _require_string(run.get("workflowRunId"), "templateRuns.workflowRunId")
            completed_result = _require_dict(completed.get(workflow_run_id), f"completed workflow {workflow_run_id}")
            asset_id = _require_string(completed_result.get("assetId"), f"asset id for {workflow_run_id}")
            asset_row = _require_dict(asset_map.get(asset_id), f"asset row for {asset_id}")
            public_id = _require_string(asset_row.get("public_id"), f"public_id for {asset_id}")
            template_label = _require_string(run.get("templateLabel"), "templateRuns.templateLabel")
            ext = _content_extension(str(asset_row.get("content_type") or ""), default_ext=".png")
            filename = f"{index:02d}-{template_label}-{public_id}{ext}"
            target_path = output_dir / filename
            downloaded_content_type = _download_public_asset(client, public_id=public_id, target_path=target_path)
            manifest_rows.append(
                {
                    "templateFile": _require_string(run.get("templateFile"), "templateRuns.templateFile"),
                    "templateLabel": template_label,
                    "workflowRunId": workflow_run_id,
                    "temporalWorkflowId": _require_string(
                        run.get("temporalWorkflowId"),
                        "templateRuns.temporalWorkflowId",
                    ),
                    "stagedAssetId": _require_string(run.get("stagedAssetId"), "templateRuns.stagedAssetId"),
                    "stagedPublicId": _require_string(run.get("stagedPublicId"), "templateRuns.stagedPublicId"),
                    "stagedPublicUrl": _require_string(run.get("stagedPublicUrl"), "templateRuns.stagedPublicUrl"),
                    "assetId": asset_id,
                    "publicId": public_id,
                    "contentType": downloaded_content_type,
                    "fileName": filename,
                    "filePath": str(target_path),
                }
            )

    _write_json(output_dir / "request.json", payload)
    _write_json(output_dir / "start-response.json", response)
    _write_json(
        output_dir / "manifest.json",
        {
            "campaignId": response.get("campaignId"),
            "assetBriefId": response.get("assetBriefId"),
            "clientId": response.get("clientId"),
            "productId": response.get("productId"),
            "requirementIndex": response.get("requirementIndex"),
            "outputDir": str(output_dir),
            "results": manifest_rows,
        },
    )
    print(json.dumps({"outputDir": str(output_dir), "count": len(manifest_rows)}, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate testimonial outputs through backend MOS endpoints.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pdp_examples = subparsers.add_parser("pdp-examples", help="Generate the 5 Sales PDP example testimonial images.")
    pdp_examples_subparsers = pdp_examples.add_subparsers(dest="action", required=True)
    pdp_generate = pdp_examples_subparsers.add_parser("generate")
    _add_common_connection_args(pdp_generate)
    _add_common_auth_args(pdp_generate)
    pdp_generate.add_argument("--funnel-id", required=True)
    pdp_generate.add_argument("--page-id", required=True)
    pdp_generate.add_argument("--draft-version-id")
    pdp_generate.add_argument("--current-puck-data")
    pdp_generate.add_argument("--model")
    pdp_generate.add_argument("--temperature", type=float, default=0.3)
    pdp_generate.add_argument("--max-tokens", type=int)
    pdp_generate.add_argument("--max-duration-seconds", type=int)
    pdp_generate.add_argument("--output-dir")
    pdp_generate.set_defaults(func=_run_pdp_examples)

    swipe_templates = subparsers.add_parser(
        "swipe-template-testimonials",
        help="Generate swipe template testimonial images for a campaign asset brief.",
    )
    swipe_subparsers = swipe_templates.add_subparsers(dest="action", required=True)
    swipe_generate = swipe_subparsers.add_parser("generate")
    _add_common_connection_args(swipe_generate)
    _add_common_auth_args(swipe_generate)
    swipe_generate.add_argument("--campaign-id", required=True)
    swipe_generate.add_argument("--asset-brief-id", required=True)
    swipe_generate.add_argument("--aspect-ratio", default="1:1")
    swipe_generate.add_argument("--model")
    swipe_generate.add_argument("--render-model-id")
    swipe_generate.add_argument("--max-output-tokens", type=int)
    swipe_generate.add_argument("--poll-interval-seconds", type=int, default=5)
    swipe_generate.add_argument("--output-dir")
    swipe_generate.set_defaults(func=_run_swipe_template_testimonials)

    return parser


def _add_common_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-base-url", required=True, help="Base URL for the MOS backend API.")
    parser.add_argument("--ui-url", required=True, help="URL for the MOS frontend used for Clerk login.")


def _add_common_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--jwt-template", default="backend", help="Clerk JWT template to request from the browser.")
    parser.add_argument(
        "--profile-dir",
        default=str(Path.home() / ".testimonial-cli" / "chrome-profile"),
        help="Persistent Chrome profile directory used for CLI login sessions.",
    )


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
