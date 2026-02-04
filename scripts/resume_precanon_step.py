from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "mos" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.db.models import WorkflowRun  # noqa: E402
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from app.llm.client import OpenAIResponsePendingError  # noqa: E402
from app.temporal.activities.precanon_research_activities import (  # noqa: E402
    ensure_idea_folder_activity,
    persist_artifact_activity,
)
from app.temporal.precanon import STEP_DEFINITIONS  # noqa: E402
from app.temporal.precanon.research import (  # noqa: E402
    IdeaFolderRequest,
    PersistArtifactRequest,
    PromptBuildRequest,
    build_prompt,
    parse_step_output,
)
from app.temporal.workflows.precanon_market_research import (  # noqa: E402
    _build_base_variables,
    _llm_params_for_step,
)
from temporalio.client import Client  # noqa: E402


async def _fetch_temporal_input(workflow_id: str, run_id: Optional[str]) -> Tuple[Dict[str, Any], Optional[str]]:
    client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    desc = await handle.describe()
    resolved_run_id = getattr(getattr(desc, "execution", None), "run_id", None)
    history = await handle.fetch_history()
    if not history.events:
        raise RuntimeError(f"No history events found for workflow {workflow_id}")
    started = history.events[0].workflow_execution_started_event_attributes
    if not started or not getattr(started, "input", None) or not started.input.payloads:
        raise RuntimeError(f"Workflow {workflow_id} has no start input payloads")
    payload = started.input.payloads[0]
    raw_data = payload.data
    if isinstance(raw_data, (bytes, bytearray)):
        raw_data = raw_data.decode("utf-8")
    try:
        input_data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to decode workflow input JSON for {workflow_id}: {exc}") from exc
    return input_data, resolved_run_id


def _load_json_file(path_str: str) -> Dict[str, Any]:
    path = Path(path_str).expanduser()
    if not path.exists():
        raise RuntimeError(f"Extra vars file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse JSON from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Extra vars file must contain a JSON object: {path}")
    return data


def _resolve_workflow_run_id(
    session, org_id: str, workflow_id: str, run_id: Optional[str]
) -> Optional[str]:
    if run_id:
        return run_id
    if not workflow_id:
        return None
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.org_id == org_id, WorkflowRun.temporal_workflow_id == workflow_id)
        .order_by(WorkflowRun.started_at.desc())
    )
    run = session.scalars(stmt).first()
    if not run:
        return None
    return run.temporal_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume a precanon step from an OpenAI response_id.")
    parser.add_argument("--response-id", required=True, help="OpenAI response_id to resume.")
    parser.add_argument("--step-key", required=True, help="Precanon step key (e.g., 01, 015, 03, 04).")
    parser.add_argument("--workflow-id", help="Temporal workflow_id for precanon workflow.")
    parser.add_argument("--workflow-run-id", help="Temporal workflow run_id for precanon workflow.")
    parser.add_argument("--org-id", help="Org id (overrides workflow input).")
    parser.add_argument("--client-id", help="Client id (overrides workflow input).")
    parser.add_argument("--product-id", help="Product id (overrides workflow input).")
    parser.add_argument("--onboarding-payload-id", help="Onboarding payload id (overrides workflow input).")
    parser.add_argument(
        "--extra-vars-file",
        help="Path to JSON file with extra prompt variables to merge.",
    )
    parser.add_argument(
        "--prompt-override-file",
        help="Path to a prompt override file (required for step 04).",
    )
    parser.add_argument("--parent-folder-id", help="Drive parent folder id override.")

    args = parser.parse_args()

    workflow_input: Dict[str, Any] = {}
    resolved_run_id: Optional[str] = None
    if args.workflow_id:
        workflow_input, resolved_run_id = asyncio.run(_fetch_temporal_input(args.workflow_id, args.workflow_run_id))

    org_id = args.org_id or workflow_input.get("org_id")
    client_id = args.client_id or workflow_input.get("client_id")
    product_id = args.product_id or workflow_input.get("product_id")
    onboarding_payload_id = args.onboarding_payload_id or workflow_input.get("onboarding_payload_id")
    workflow_id = args.workflow_id or workflow_input.get("workflow_id")
    workflow_run_id = args.workflow_run_id or resolved_run_id

    if args.org_id and workflow_input.get("org_id") and args.org_id != workflow_input.get("org_id"):
        raise RuntimeError("Provided org_id does not match workflow input org_id.")
    if args.client_id and workflow_input.get("client_id") and args.client_id != workflow_input.get("client_id"):
        raise RuntimeError("Provided client_id does not match workflow input client_id.")
    if args.product_id and workflow_input.get("product_id") and args.product_id != workflow_input.get("product_id"):
        raise RuntimeError("Provided product_id does not match workflow input product_id.")
    if args.onboarding_payload_id and workflow_input.get("onboarding_payload_id"):
        if args.onboarding_payload_id != workflow_input.get("onboarding_payload_id"):
            raise RuntimeError("Provided onboarding_payload_id does not match workflow input onboarding_payload_id.")

    missing = [name for name, value in [
        ("org_id", org_id),
        ("client_id", client_id),
        ("onboarding_payload_id", onboarding_payload_id),
    ] if not value]
    if missing:
        raise RuntimeError(f"Missing required identifiers: {', '.join(missing)}")

    if args.step_key not in STEP_DEFINITIONS:
        raise RuntimeError(f"Unknown step_key: {args.step_key}")

    extra_vars: Dict[str, Any] = {}
    if args.extra_vars_file:
        extra_vars = _load_json_file(args.extra_vars_file)

    prompt_override = None
    if args.prompt_override_file:
        prompt_override = Path(args.prompt_override_file).expanduser().read_text(encoding="utf-8")
    if args.step_key == "04" and not prompt_override:
        raise RuntimeError("Step 04 requires --prompt-override-file.")

    session = SessionLocal()
    try:
        payload_repo = OnboardingPayloadsRepository(session)
        payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
        if not payload or not payload.data:
            raise RuntimeError("Onboarding payload not found or empty.")
        if not product_id:
            product_id = str(payload.product_id) if payload.product_id else None
        if not product_id:
            raise RuntimeError(
                "product_id is required to resume precanon; provide --product-id or ensure payload has product_id."
            )

        ads_context = {"ads_context": ""}
        base_vars = _build_base_variables(
            org_id=org_id,
            client_id=client_id,
            onboarding_payload_id=onboarding_payload_id,
            product_id=product_id,
            payload=payload.data,
            ads_context=ads_context,
        )
        vars_for_step = {**base_vars, **extra_vars}

        prompt_result = build_prompt(
            PromptBuildRequest(
                step_key=args.step_key,
                variables=vars_for_step,
                prompt_override=prompt_override,
            )
        )

        llm_params = _llm_params_for_step(args.step_key)
        include = ["web_search_call.action.sources"] if llm_params.use_web_search else None
        llm = LLMClient(default_model=llm_params.model)
        try:
            raw_output = llm.retrieve_openai_response_text(args.response_id, include=include)
        except OpenAIResponsePendingError as exc:
            raise RuntimeError(
                f"OpenAI response is still pending; retry later with response_id={exc.response_id}."
            ) from exc

        definition = STEP_DEFINITIONS[args.step_key]
        parsed = parse_step_output(
            step_key=args.step_key,
            raw_output=raw_output,
            summary_max_chars=definition.summary_max_chars,
            handoff_max_chars=definition.handoff_max_chars,
        )

        idea_folder_name = (
            base_vars.get("BUSINESS_CONTEXT")
            or base_vars.get("BUSINESS_CONTEXT_JSON")
            or "idea"
        )
        folder_result = ensure_idea_folder_activity(
            IdeaFolderRequest(
                parent_folder_id=args.parent_folder_id or os.getenv("RESEARCH_DRIVE_PARENT_FOLDER_ID") or os.getenv(
                    "PARENT_FOLDER_ID"
                ),
                idea_folder_name=idea_folder_name,
            )
        )

        effective_run_id = _resolve_workflow_run_id(session, org_id, workflow_id or "", workflow_run_id)
        persist_result = persist_artifact_activity(
            PersistArtifactRequest(
                step_key=args.step_key,
                title=definition.title,
                content=parsed.content,
                prompt_sha256=prompt_result.prompt_sha256,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=None,
                idea_workspace_id=workflow_id,
                workflow_id=workflow_id or "",
                workflow_run_id=effective_run_id,
                parent_folder_id=args.parent_folder_id,
                idea_folder_id=folder_result.idea_folder_id,
                idea_folder_url=folder_result.idea_folder_url,
                idea_folder_name=idea_folder_name,
                allow_drive_stub=False,
                allow_claude_stub=False,
            )
        )

        print("Persisted artifact:")
        print(f"  doc_id: {persist_result.doc_id}")
        print(f"  doc_url: {persist_result.doc_url}")
        print(f"  idea_folder_id: {persist_result.idea_folder_id}")
        print(f"  idea_folder_url: {persist_result.idea_folder_url}")
        print(f"  summary_chars: {len(parsed.summary)}")
        print(f"  content_chars: {len(parsed.content)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
