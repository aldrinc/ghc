from __future__ import annotations

from collections.abc import Generator
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agent.funnel_tools import (
    ContextLoadBrandDocsTool,
    ContextLoadDesignTokensTool,
    ContextLoadFunnelTool,
    ContextLoadProductOfferTool,
    DraftApplyOverridesTool,
    DraftGeneratePageTool,
    DraftPersistVersionTool,
    DraftValidateTool,
    ImagesGenerateTool,
    ImagesPlanTool,
    TestimonialsGenerateAndApplyTool,
    PublishValidateReadyTool,
    PublishExecuteTool,
)
from app.agent.runtime import AgentRuntime
from app.db.enums import AgentRunStatusEnum
from app.llm.client import LLMClient
from app.services import funnel_ai as funnel_ai


DEFAULT_RULESET_VERSION = "v1"


def run_generate_page_draft_stream(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    prompt: str,
    messages: Optional[list[dict[str, str]]] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    generate_images: bool = True,
    max_images: int = 3,
    copy_pack: Optional[str] = None,
    ruleset_version: str = DEFAULT_RULESET_VERSION,
    raise_on_error: bool = False,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    """
    Tool-based objective runner for: Create or update a page draft.

    Streaming emits:
    - legacy events used by the current UI: start/status/raw/text/done/error
    - tool events for observability: tool_called/tool_result/tool_error
    """

    llm = LLMClient()
    model_id = model or llm.default_model

    runtime = AgentRuntime(session=session, org_id=org_id, user_id=user_id)
    handle = runtime.begin_run(
        objective_type="objective.page_draft",
        funnel_id=funnel_id,
        page_id=page_id,
        model=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        ruleset_version=ruleset_version,
        inputs_json={
            "prompt": prompt,
            "messages": messages or [],
            "templateId": template_id,
            "ideaWorkspaceId": idea_workspace_id,
            "generateImages": generate_images,
            "maxImages": max_images,
        },
    )

    # Legacy event for the existing frontend.
    yield {"type": "start", "model": model_id, "runId": handle.run_id}
    yield {"type": "run_started", "runId": handle.run_id, "model": model_id, "objectiveType": "page_draft"}

    try:
        # 1) Load funnel/page context
        funnel_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=ContextLoadFunnelTool(),
            raw_args={
                "orgId": org_id,
                "funnelId": funnel_id,
                "pageId": page_id,
                "currentPuckData": current_puck_data,
                "templateId": template_id,
            },
            funnel_id=funnel_id,
            page_id=page_id,
        )
        funnel_ctx = funnel_res.ui_details
        client_id = str(funnel_ctx.get("clientId") or "")
        product_id = funnel_ctx.get("productId")
        if not client_id:
            raise ValueError("Funnel is missing client_id.")
        if not product_id:
            raise ValueError("product_id is required to generate AI funnel drafts.")

        # 2) Load product/offer context
        product_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=ContextLoadProductOfferTool(),
            raw_args={"orgId": org_id, "funnelId": funnel_id, "clientId": client_id},
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        product_ctx = product_res.ui_details

        # 3) Load design system tokens
        tokens_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=ContextLoadDesignTokensTool(),
            raw_args={"orgId": org_id, "clientId": client_id, "funnelId": funnel_id, "pageId": page_id},
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        tokens_ctx = tokens_res.ui_details

        # 4) Load brand docs (Claude files)
        docs_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=ContextLoadBrandDocsTool(),
            raw_args={"orgId": org_id, "funnelId": funnel_id, "ideaWorkspaceId": idea_workspace_id},
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        docs_ctx = docs_res.ui_details

        # Normalize attachments + build vision blocks (used only for Claude structured calls).
        normalized_attachments = funnel_ai._normalize_attachment_list(attachments)
        if normalized_attachments and not model_id.lower().startswith("claude"):
            raise funnel_ai.AiAttachmentError(
                "Image attachments require a Claude model with vision support. "
                "Set model to a Claude model."
            )

        # Brand docs are stored as Claude file blocks; do not silently switch models.
        if (docs_ctx.get("documentBlocks") or []) and not model_id.lower().startswith("claude"):
            raise ValueError("Brand documents require a Claude model (model must start with 'claude').")
        attachment_summaries, attachment_blocks = funnel_ai._build_attachment_blocks(
            session=session,
            org_id=org_id,
            client_id=client_id,
            attachments=normalized_attachments,
        )

        # 5) Generate candidate draft (LLM)
        draft_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=DraftGeneratePageTool(),
            raw_args={
                "orgId": org_id,
                "funnelId": funnel_id,
                "pageId": page_id,
                "pageName": funnel_ctx.get("pageName") or "",
                "prompt": prompt,
                "messages": messages or [],
                "model": model,
                "temperature": temperature,
                "maxTokens": max_tokens,
                "templateId": funnel_ctx.get("templateId"),
                "templateKind": funnel_ctx.get("templateKind"),
                "templateMode": bool(funnel_ctx.get("templateMode")),
                "pageContext": funnel_ctx.get("pageContext") or [],
                "basePuckData": funnel_ctx.get("basePuckData"),
                "productContext": str(product_ctx.get("productContext") or ""),
                "attachmentSummaries": attachment_summaries,
                "attachmentBlocks": attachment_blocks,
                "brandDocuments": docs_ctx.get("documentBlocks") or [],
                "copyPack": copy_pack,
            },
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        draft_ctx = draft_res.ui_details
        puck_data = draft_ctx["puckData"]
        assistant_message = str(draft_ctx.get("assistantMessage") or "")
        final_model = str(draft_ctx.get("model") or model_id)

        # 6) Apply deterministic overrides
        overrides_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=DraftApplyOverridesTool(),
            raw_args={
                "orgId": org_id,
                "clientId": client_id,
                "funnelId": funnel_id,
                "pageId": page_id,
                "puckData": puck_data,
                "basePuckData": funnel_ctx.get("basePuckData"),
                "templateKind": funnel_ctx.get("templateKind"),
                "designSystemTokens": tokens_ctx.get("designSystemTokens"),
                "brandLogoAssetPublicId": tokens_ctx.get("brandLogoAssetPublicId"),
                "productId": str(product_id),
            },
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        puck_data = overrides_res.ui_details["puckData"]

        # 7) Validate draft
        validate_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=DraftValidateTool(),
            raw_args={
                "orgId": org_id,
                "puckData": puck_data,
                "allowedTypes": funnel_ctx.get("allowedTypes") or [],
                "requiredTypes": funnel_ctx.get("requiredTypes") or [],
                "templateKind": funnel_ctx.get("templateKind"),
                "pageIdSet": funnel_ctx.get("pageIdSet") or [],
                "validateTemplateImages": bool(funnel_ctx.get("templateMode") and generate_images),
            },
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        validation = validate_res.ui_details
        if not validation.get("ok"):
            errors = validation.get("errors") or []
            raise ValueError("Draft validation failed: " + "; ".join(str(e) for e in errors))

        # 8) Plan images
        image_plans: list[dict[str, Any]] = []
        if generate_images:
            plan_res = yield from runtime.invoke_tool_stream(
                handle=handle,
                tool=ImagesPlanTool(),
                raw_args={
                    "orgId": org_id,
                    "puckData": puck_data,
                    "templateMode": bool(funnel_ctx.get("templateMode")),
                    "templateKind": funnel_ctx.get("templateKind"),
                },
                client_id=client_id,
                funnel_id=funnel_id,
                page_id=page_id,
            )
            puck_data = plan_res.ui_details["puckData"]
            image_plans = plan_res.ui_details.get("imagePlans") or []

        # 9) Generate images (if enabled)
        generated_images: list[dict[str, Any]] = []
        if generate_images:
            gen_res = yield from runtime.invoke_tool_stream(
                handle=handle,
                tool=ImagesGenerateTool(),
                raw_args={
                    "orgId": org_id,
                    "clientId": client_id,
                    "funnelId": funnel_id,
                    "productId": str(product_id),
                    "puckData": puck_data,
                    "maxImages": max_images,
                },
                client_id=client_id,
                funnel_id=funnel_id,
                page_id=page_id,
            )
            puck_data = gen_res.ui_details["puckData"]
            generated_images = gen_res.ui_details.get("generatedImages") or []

        # 10) Persist draft version
        persist_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=DraftPersistVersionTool(),
            raw_args={
                "orgId": org_id,
                "userId": user_id,
                "funnelId": funnel_id,
                "pageId": page_id,
                "prompt": prompt,
                "messages": messages or [],
                "puckData": puck_data,
                "assistantMessage": assistant_message,
                "model": final_model,
                "temperature": temperature,
                "ideaWorkspaceId": docs_ctx.get("ideaWorkspaceId"),
                "templateId": funnel_ctx.get("templateId"),
                "attachmentSummaries": attachment_summaries,
                "imagePlans": image_plans,
                "generatedImages": generated_images,
                "agentRunId": handle.run_id,
            },
            client_id=client_id,
            funnel_id=funnel_id,
            page_id=page_id,
        )
        draft_version_id = persist_res.ui_details["draftVersionId"]

        final = {
            "assistantMessage": assistant_message,
            "puckData": puck_data,
            "draftVersionId": draft_version_id,
            "generatedImages": generated_images,
            "imagePlans": image_plans,
            "runId": handle.run_id,
        }

        runtime.finish_run(handle=handle, status=AgentRunStatusEnum.completed, outputs_json=final)

        yield {"type": "done", **final}
        yield {"type": "run_finished", "runId": handle.run_id}
        return final

    except Exception as exc:  # noqa: BLE001
        runtime.finish_run(handle=handle, status=AgentRunStatusEnum.failed, error=str(exc))
        yield {"type": "error", "message": str(exc), "runId": handle.run_id}
        if raise_on_error:
            raise
        return {"error": str(exc), "runId": handle.run_id}


def run_generate_page_draft(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    prompt: str,
    messages: Optional[list[dict[str, str]]] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    generate_images: bool = True,
    max_images: int = 3,
    copy_pack: Optional[str] = None,
    ruleset_version: str = DEFAULT_RULESET_VERSION,
) -> dict[str, Any]:
    gen = run_generate_page_draft_stream(
        session=session,
        org_id=org_id,
        user_id=user_id,
        funnel_id=funnel_id,
        page_id=page_id,
        prompt=prompt,
        messages=messages,
        attachments=attachments,
        current_puck_data=current_puck_data,
        template_id=template_id,
        idea_workspace_id=idea_workspace_id,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        generate_images=generate_images,
        max_images=max_images,
        copy_pack=copy_pack,
        ruleset_version=ruleset_version,
        raise_on_error=True,
    )
    # Drain generator and capture return value.
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            value = stop.value
            if not isinstance(value, dict):
                raise RuntimeError("Agent run returned invalid result")
            return value


def run_generate_page_testimonials_stream(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    draft_version_id: Optional[str] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    synthetic: bool = True,
    ruleset_version: str = DEFAULT_RULESET_VERSION,
    raise_on_error: bool = False,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    llm = LLMClient()
    model_id = model or llm.default_model

    runtime = AgentRuntime(session=session, org_id=org_id, user_id=user_id)
    handle = runtime.begin_run(
        objective_type="objective.page_testimonials",
        funnel_id=funnel_id,
        page_id=page_id,
        model=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        ruleset_version=ruleset_version,
        inputs_json={
            "draftVersionId": draft_version_id,
            "templateId": template_id,
            "ideaWorkspaceId": idea_workspace_id,
            "synthetic": synthetic,
        },
    )

    yield {"type": "run_started", "runId": handle.run_id, "model": model_id, "objectiveType": "page_testimonials"}

    try:
        res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=TestimonialsGenerateAndApplyTool(),
            raw_args={
                "orgId": org_id,
                "userId": user_id,
                "funnelId": funnel_id,
                "pageId": page_id,
                "draftVersionId": draft_version_id,
                "currentPuckData": current_puck_data,
                "templateId": template_id,
                "ideaWorkspaceId": idea_workspace_id,
                "model": model,
                "temperature": temperature,
                "maxTokens": max_tokens,
                "synthetic": synthetic,
                "agentRunId": handle.run_id,
            },
            funnel_id=funnel_id,
            page_id=page_id,
        )
        out = {
            "draftVersionId": res.ui_details["draftVersionId"],
            "puckData": res.ui_details["puckData"],
            "generatedTestimonials": res.ui_details.get("generatedTestimonials") or [],
            "runId": handle.run_id,
        }
        runtime.finish_run(handle=handle, status=AgentRunStatusEnum.completed, outputs_json=out)
        yield {"type": "done", **out}
        yield {"type": "run_finished", "runId": handle.run_id}
        return out
    except Exception as exc:  # noqa: BLE001
        runtime.finish_run(handle=handle, status=AgentRunStatusEnum.failed, error=str(exc))
        yield {"type": "error", "message": str(exc), "runId": handle.run_id}
        if raise_on_error:
            raise
        return {"error": str(exc), "runId": handle.run_id}


def run_generate_page_testimonials(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    page_id: str,
    draft_version_id: Optional[str] = None,
    current_puck_data: Optional[dict[str, Any]] = None,
    template_id: Optional[str] = None,
    idea_workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    synthetic: bool = True,
    ruleset_version: str = DEFAULT_RULESET_VERSION,
) -> dict[str, Any]:
    gen = run_generate_page_testimonials_stream(
        session=session,
        org_id=org_id,
        user_id=user_id,
        funnel_id=funnel_id,
        page_id=page_id,
        draft_version_id=draft_version_id,
        current_puck_data=current_puck_data,
        template_id=template_id,
        idea_workspace_id=idea_workspace_id,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        synthetic=synthetic,
        ruleset_version=ruleset_version,
        raise_on_error=True,
    )
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            value = stop.value
            if not isinstance(value, dict):
                raise RuntimeError("Agent run returned invalid result")
            return value


def run_publish_funnel_stream(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    ruleset_version: str = DEFAULT_RULESET_VERSION,
    raise_on_error: bool = False,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    runtime = AgentRuntime(session=session, org_id=org_id, user_id=user_id)
    handle = runtime.begin_run(
        objective_type="objective.publish_funnel",
        funnel_id=funnel_id,
        model=None,
        temperature=None,
        max_tokens=None,
        ruleset_version=ruleset_version,
        inputs_json={"funnelId": funnel_id},
    )

    yield {"type": "run_started", "runId": handle.run_id, "objectiveType": "publish_funnel"}
    try:
        ready_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=PublishValidateReadyTool(),
            raw_args={"orgId": org_id, "funnelId": funnel_id},
            funnel_id=funnel_id,
        )
        ready = ready_res.ui_details
        if not ready.get("ok"):
            errors = ready.get("errors") or []
            raise ValueError("Funnel is not ready to publish: " + "; ".join(str(e) for e in errors))

        exec_res = yield from runtime.invoke_tool_stream(
            handle=handle,
            tool=PublishExecuteTool(),
            raw_args={"orgId": org_id, "userId": user_id, "funnelId": funnel_id},
            funnel_id=funnel_id,
        )
        out = {"publicationId": exec_res.ui_details["publicationId"], "runId": handle.run_id}
        runtime.finish_run(handle=handle, status=AgentRunStatusEnum.completed, outputs_json=out)
        yield {"type": "done", **out}
        yield {"type": "run_finished", "runId": handle.run_id}
        return out
    except Exception as exc:  # noqa: BLE001
        runtime.finish_run(handle=handle, status=AgentRunStatusEnum.failed, error=str(exc))
        yield {"type": "error", "message": str(exc), "runId": handle.run_id}
        if raise_on_error:
            raise
        return {"error": str(exc), "runId": handle.run_id}


def run_publish_funnel(
    *,
    session: Session,
    org_id: str,
    user_id: str,
    funnel_id: str,
    ruleset_version: str = DEFAULT_RULESET_VERSION,
) -> dict[str, Any]:
    gen = run_publish_funnel_stream(
        session=session,
        org_id=org_id,
        user_id=user_id,
        funnel_id=funnel_id,
        ruleset_version=ruleset_version,
        raise_on_error=True,
    )
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            value = stop.value
            if not isinstance(value, dict):
                raise RuntimeError("Agent run returned invalid result")
            return value
