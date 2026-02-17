from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from temporalio import activity
from sqlalchemy import select

from app.db.base import session_scope
from app.db.enums import FunnelPageVersionSourceEnum, FunnelPageVersionStatusEnum, FunnelStatusEnum
from app.db.models import Campaign, Funnel, FunnelPage, FunnelPageVersion
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.funnels import FunnelsRepository, FunnelPagesRepository
from app.services.funnels import generate_unique_slug
from app.services.funnel_templates import get_funnel_template, apply_template_assets
from app.agent.funnel_objectives import run_generate_page_draft
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.enums import ArtifactTypeEnum
from app.db.repositories.design_systems import DesignSystemsRepository
from app.services.design_systems import resolve_design_system_tokens



@activity.defn
def create_campaign_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    name = params.get("campaign_name")
    product_id = params.get("product_id")
    channels = params.get("channels") or []
    asset_brief_types = params.get("asset_brief_types") or []
    if not name or not str(name).strip():
        raise ValueError("campaign_name is required to create a campaign")
    if not product_id:
        raise ValueError("product_id is required to create a campaign")
    if not channels or not all(isinstance(ch, str) and ch.strip() for ch in channels):
        raise ValueError("channels must include at least one non-empty value.")
    if not asset_brief_types or not all(isinstance(t, str) and t.strip() for t in asset_brief_types):
        raise ValueError("asset_brief_types must include at least one non-empty value.")

    with session_scope() as session:
        repo = CampaignsRepository(session)
        campaign = repo.create(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            name=str(name).strip(),
            channels=channels,
            asset_brief_types=asset_brief_types,
            goal_description=params.get("goal_description"),
            objective_type=params.get("objective_type"),
            numeric_target=params.get("numeric_target"),
            baseline=params.get("baseline"),
            timeframe_days=params.get("timeframe_days"),
            budget_min=params.get("budget_min"),
            budget_max=params.get("budget_max"),
        )
        temporal_workflow_id = params.get("temporal_workflow_id")
        temporal_run_id = params.get("temporal_run_id")
        if temporal_workflow_id and temporal_run_id:
            workflows_repo = WorkflowsRepository(session)
            run = workflows_repo.get_by_temporal_ids(
                org_id=org_id,
                temporal_workflow_id=str(temporal_workflow_id),
                temporal_run_id=str(temporal_run_id),
            )
            if run and not run.campaign_id:
                run.campaign_id = campaign.id
                session.commit()
        return {"campaign_id": str(campaign.id)}


@activity.defn
def create_funnel_drafts_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    product_id = params.get("product_id")
    experiment_spec_id = params.get("experiment_spec_id")
    funnel_name = params.get("funnel_name")
    pages: List[Dict[str, Any]] = params.get("pages") or []
    experiment = params.get("experiment")
    variant = params.get("variant")
    strategy_sheet = params.get("strategy_sheet") or {}
    asset_briefs = params.get("asset_briefs") or []
    idea_workspace_id = params.get("idea_workspace_id")
    actor_user_id = params.get("actor_user_id") or "workflow"
    generate_ai_drafts = bool(params.get("generate_ai_drafts", False))
    generate_testimonials = bool(params.get("generate_testimonials", False))
    workflow_run_id = params.get("workflow_run_id")

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as log_session:
            WorkflowsRepository(log_session).log_activity(
                workflow_run_id=workflow_run_id,
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

    if not campaign_id:
        raise ValueError("campaign_id is required to create funnel drafts")
    if not pages:
        raise ValueError("pages are required to create funnel drafts")
    if generate_ai_drafts and (not experiment or not variant):
        raise ValueError("experiment and variant are required when generate_ai_drafts is enabled")

    if not product_id:
        raise ValueError("product_id is required to create funnel drafts")

    with session_scope() as session:
        campaign = session.scalars(
            select(Campaign).where(Campaign.org_id == org_id, Campaign.id == campaign_id)
        ).first()
        if not campaign:
            raise ValueError("Campaign not found for funnel draft creation")
        if campaign.product_id and str(campaign.product_id) != str(product_id):
            raise ValueError("product_id does not match campaign product_id")

        design_systems_repo = DesignSystemsRepository(session)

        def resolve_template_tokens(page_spec: Dict[str, Any]) -> Optional[dict[str, Any]]:
            design_system_id = page_spec.get("design_system_id") or page_spec.get("designSystemId")
            if design_system_id:
                design_system = design_systems_repo.get(
                    org_id=org_id,
                    design_system_id=str(design_system_id),
                )
                if not design_system:
                    raise ValueError(f"Design system not found: {design_system_id}")
                tokens = design_system.tokens
                if tokens is None:
                    raise ValueError("Design system tokens are required to apply brand assets.")
                if not isinstance(tokens, dict):
                    raise ValueError("Design system tokens must be a JSON object.")
                return tokens
            tokens = resolve_design_system_tokens(session=session, org_id=org_id, client_id=client_id)
            if tokens is not None and not isinstance(tokens, dict):
                raise ValueError("Design system tokens must be a JSON object.")
            return tokens

        funnels_repo = FunnelsRepository(session)
        pages_repo = FunnelPagesRepository(session)
        resolved_funnel_name = funnel_name or "Launch"
        existing_funnel = session.scalars(
            select(Funnel)
            .where(
                Funnel.org_id == org_id,
                Funnel.client_id == client_id,
                Funnel.campaign_id == campaign_id,
                Funnel.experiment_spec_id == experiment_spec_id,
                Funnel.name == resolved_funnel_name,
            )
            .order_by(Funnel.created_at.desc())
        ).first()

        funnel = existing_funnel
        if not funnel:
            funnel = funnels_repo.create(
                org_id=org_id,
                client_id=client_id,
                campaign_id=campaign_id,
                product_id=product_id,
                experiment_spec_id=experiment_spec_id,
                name=resolved_funnel_name,
                status=FunnelStatusEnum.draft,
            )

        existing_pages = pages_repo.list(funnel_id=str(funnel.id)) if funnel else []
        existing_pages_by_slug = {page.slug: page for page in existing_pages}

        created_pages: list[dict[str, str]] = []
        resolved_pages: list[FunnelPage] = []
        for idx, page_spec in enumerate(pages):
            template_id = page_spec.get("template_id") or page_spec.get("templateId")
            if not template_id:
                raise ValueError("template_id is required for each funnel page")
            template = get_funnel_template(template_id)
            if not template:
                raise ValueError(f"Funnel template not found: {template_id}")

            page_name = page_spec.get("name") or template.name
            desired_slug = page_spec.get("slug") or page_name
            slug = desired_slug
            page = existing_pages_by_slug.get(desired_slug)
            if not page:
                slug = generate_unique_slug(session, funnel_id=str(funnel.id), desired_slug=desired_slug)
            design_system_tokens = resolve_template_tokens(page_spec)
            puck_data = apply_template_assets(
                session=session,
                org_id=org_id,
                client_id=client_id,
                template=template,
                design_system_tokens=design_system_tokens,
            )

            if page:
                if page.template_id != template_id:
                    page = pages_repo.update(page_id=str(page.id), template_id=template_id) or page
                if page.ordering != idx:
                    page = pages_repo.update(page_id=str(page.id), ordering=idx) or page
            else:
                page = pages_repo.create(
                    funnel_id=str(funnel.id),
                    name=page_name,
                    slug=slug,
                    ordering=idx,
                    template_id=template_id,
                    design_system_id=page_spec.get("design_system_id") or page_spec.get("designSystemId"),
                )

            version = FunnelPageVersion(
                page_id=page.id,
                status=FunnelPageVersionStatusEnum.draft,
                puck_data=puck_data,
                source=FunnelPageVersionSourceEnum.human,
                created_at=datetime.now(timezone.utc),
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            created_pages.append({"page_id": str(page.id), "draft_version_id": str(version.id)})
            resolved_pages.append(page)

            if generate_ai_drafts:
                prompt = _build_funnel_prompt(
                    strategy_sheet=strategy_sheet,
                    experiment=experiment,
                    variant=variant,
                    asset_briefs=asset_briefs,
                    page_name=page_name,
                    template_id=template_id,
                )
                log_activity(
                    "funnel_page_draft",
                    "started",
                    payload_in={
                        "page_id": str(page.id),
                        "template_id": template_id,
                        "funnel_id": str(funnel.id),
                    },
                )
                if generate_testimonials:
                    log_activity(
                        "funnel_page_testimonials",
                        "started",
                        payload_in={"page_id": str(page.id), "funnel_id": str(funnel.id)},
                    )
                try:
                    result = run_generate_page_draft(
                        session=session,
                        org_id=org_id,
                        user_id=str(actor_user_id),
                        funnel_id=str(funnel.id),
                        page_id=str(page.id),
                        prompt=prompt,
                        current_puck_data=puck_data,
                        template_id=template_id,
                        idea_workspace_id=idea_workspace_id,
                        generate_testimonials=generate_testimonials,
                    )
                    draft_version_id = result.get("draftVersionId") or ""
                    generated_images = result.get("generatedImages") or []
                    if not draft_version_id:
                        raise RuntimeError("AI draft generation returned no draftVersionId.")
                    image_errors = [
                        item for item in generated_images if isinstance(item, dict) and item.get("error")
                    ]
                    if image_errors:
                        first_error = image_errors[0].get("error") or "Unknown error."
                        raise RuntimeError(
                            f"Image generation failed for {len(image_errors)} image(s): {first_error}"
                        )
                except Exception as exc:  # noqa: BLE001
                    log_activity(
                        "funnel_page_draft",
                        "failed",
                        error=str(exc),
                        payload_in={
                            "page_id": str(page.id),
                            "template_id": template_id,
                            "funnel_id": str(funnel.id),
                        },
                    )
                    if generate_testimonials:
                        error_text = str(exc)
                        if "testimonial" in error_text.lower():
                            log_activity(
                                "funnel_page_testimonials",
                                "failed",
                                error=error_text,
                                payload_in={"page_id": str(page.id), "funnel_id": str(funnel.id)},
                            )
                        else:
                            log_activity(
                                "funnel_page_testimonials",
                                "skipped",
                                payload_in={
                                    "page_id": str(page.id),
                                    "funnel_id": str(funnel.id),
                                    "reason": "Draft generation failed before testimonial step.",
                                },
                            )
                    raise
                else:
                    log_activity(
                        "funnel_page_draft",
                        "completed",
                        payload_out={
                            "page_id": str(page.id),
                            "draft_version_id": draft_version_id,
                            "funnel_id": str(funnel.id),
                        },
                    )
                    if generate_testimonials:
                        log_activity(
                            "funnel_page_testimonials",
                            "completed",
                            payload_out={
                                "page_id": str(page.id),
                                "funnel_id": str(funnel.id),
                                "draft_version_id": draft_version_id,
                                "mode": "inline_page_draft",
                            },
                        )
                    else:
                        log_activity(
                            "funnel_page_testimonials",
                            "skipped",
                            payload_in={
                                "page_id": str(page.id),
                                "funnel_id": str(funnel.id),
                                "reason": "Synthetic testimonials generation disabled for this run.",
                            },
                        )
        if created_pages:
            funnels_repo.update(
                org_id=org_id,
                funnel_id=str(funnel.id),
                entry_page_id=created_pages[0]["page_id"],
            )

        if resolved_pages:
            pre_sales_pages = [page for page in resolved_pages if page.template_id == "pre-sales-listicle"]
            sales_pages = [page for page in resolved_pages if page.template_id == "sales-pdp"]
            if pre_sales_pages:
                if len(sales_pages) != 1:
                    raise ValueError(
                        "Default next page wiring requires exactly one sales page. "
                        "Add a sales page or set nextPageId explicitly."
                    )
                sales_page_id = str(sales_pages[0].id)
                for page in pre_sales_pages:
                    if page.next_page_id:
                        continue
                    pages_repo.update(page_id=str(page.id), next_page_id=sales_page_id)

        return {
            "funnel_id": str(funnel.id),
            "entry_page_id": created_pages[0]["page_id"] if created_pages else None,
            "pages": created_pages,
        }


def _build_funnel_prompt(
    *,
    strategy_sheet: Dict[str, Any],
    experiment: Dict[str, Any],
    variant: Dict[str, Any],
    asset_briefs: List[Dict[str, Any]],
    page_name: str,
    template_id: Optional[str],
) -> str:
    experiment_name = experiment.get("name") or experiment.get("id")
    variant_name = variant.get("name") or variant.get("id")
    return f"""
You are generating funnel page copy for a marketing experiment.

Campaign goal: {strategy_sheet.get("goal")}
Campaign hypothesis: {strategy_sheet.get("hypothesis")}
Channel plan: {strategy_sheet.get("channelPlan") or []}
Messaging pillars: {strategy_sheet.get("messaging") or []}
Risks: {strategy_sheet.get("risks") or []}
Mitigations: {strategy_sheet.get("mitigations") or []}

Experiment: {experiment_name}
Experiment hypothesis: {experiment.get("hypothesis")}
Variant: {variant_name}
Variant description: {variant.get("description")}
Variant channels: {variant.get("channels") or []}
Variant guardrails: {variant.get("guardrails") or []}

Asset briefs (requirements + concepts):
{asset_briefs}

Page to generate: {page_name}
Template: {template_id}

Instructions:
- Align copy and structure to the experiment variant angle.
- Use brand voice, constraints, and claims from the attached context documents.
- Keep claims compliant and avoid medical promises.
- Do NOT invent product facts or policy specifics (warranty length, return window, price, FDA status, clinical study outcomes, time-to-results, session length, brightness levels).
- Do NOT include any numbers anywhere unless the number is explicitly present in the attached product/offer context (if absent, rewrite without numbers).
- If the base template contains numeric placeholders (review counts, star ratings, trial durations, discounts), remove or replace them with non-numeric phrasing.
- Provide concrete, conversion-focused copy for the template sections.
"""


@activity.defn
def create_funnels_from_experiments_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    campaign_id = params.get("campaign_id")
    experiment_specs: List[Dict[str, Any]] = params.get("experiment_specs") or []
    pages: List[Dict[str, Any]] = params.get("pages") or []
    funnel_name_prefix = params.get("funnel_name_prefix")
    idea_workspace_id = params.get("idea_workspace_id")
    actor_user_id = params.get("actor_user_id") or "workflow"
    generate_ai_drafts = bool(params.get("generate_ai_drafts", False))
    generate_testimonials = bool(params.get("generate_testimonials", False))
    temporal_workflow_id = params.get("temporal_workflow_id")
    temporal_run_id = params.get("temporal_run_id")

    workflow_run_id: Optional[str] = None
    if temporal_workflow_id and temporal_run_id:
        with session_scope() as session:
            wf_repo = WorkflowsRepository(session)
            run = wf_repo.get_by_temporal_ids(
                org_id=org_id,
                temporal_workflow_id=str(temporal_workflow_id),
                temporal_run_id=str(temporal_run_id),
            )
            if run:
                workflow_run_id = str(run.id)

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as session:
            wf_repo = WorkflowsRepository(session)
            wf_repo.log_activity(
                workflow_run_id=workflow_run_id,
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

    if not campaign_id:
        raise ValueError("campaign_id is required to create funnels from experiments")
    if not product_id:
        raise ValueError("product_id is required to create funnels from experiments")
    if not experiment_specs:
        raise ValueError("experiment_specs are required to create funnels from experiments")
    if not pages:
        raise ValueError("pages are required to create funnels from experiments")

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        strategy = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id, campaign_id=campaign_id, artifact_type=ArtifactTypeEnum.strategy_sheet
        )
        briefs_artifact = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=org_id, campaign_id=campaign_id, artifact_type=ArtifactTypeEnum.asset_brief
        )

    if not strategy:
        raise ValueError("Strategy sheet not found for funnel generation")

    strategy_sheet = strategy.data if isinstance(strategy.data, dict) else {}
    asset_briefs_all: list[dict[str, Any]] = []
    if briefs_artifact and isinstance(briefs_artifact.data, dict):
        raw_briefs = briefs_artifact.data.get("asset_briefs") or []
        if isinstance(raw_briefs, list):
            asset_briefs_all = [b for b in raw_briefs if isinstance(b, dict)]

    results = []
    for experiment in experiment_specs:
        if not isinstance(experiment, dict):
            raise ValueError("Experiment specs must be objects.")
        experiment_id = experiment.get("id")
        if not experiment_id:
            raise ValueError("Experiment spec missing id.")
        variants = experiment.get("variants") or []
        if not variants:
            raise ValueError(f"Experiment {experiment_id} has no variants.")
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError(f"Variant spec for experiment {experiment_id} must be an object.")
            variant_id = variant.get("id")
            if not variant_id:
                raise ValueError(f"Variant missing id for experiment {experiment_id}.")

            funnel_label = funnel_name_prefix or "Funnel"
            funnel_name = (
                f"{funnel_label} · {experiment.get('name') or experiment_id} · "
                f"{variant.get('name') or variant_id}"
            )

            log_activity(
                "funnel_draft",
                "started",
                payload_in={
                    "experiment_id": experiment_id,
                    "variant_id": variant_id,
                    "funnel_name": funnel_name,
                    "template_ids": [page.get("template_id") or page.get("templateId") for page in pages],
                },
            )
            try:
                matching_briefs = [
                    b
                    for b in asset_briefs_all
                    if b.get("experimentId") == experiment_id and b.get("variantId") == variant_id
                ]
                funnel_result = create_funnel_drafts_activity(
                    {
                        "org_id": org_id,
                        "client_id": client_id,
                        "product_id": product_id,
                        "campaign_id": campaign_id,
                        "experiment_spec_id": experiment_id,
                        "funnel_name": funnel_name,
                        "pages": pages,
                        "experiment": experiment,
                        "variant": variant,
                        "strategy_sheet": strategy_sheet,
                        "asset_briefs": matching_briefs,
                        "idea_workspace_id": idea_workspace_id,
                        "actor_user_id": actor_user_id,
                        "generate_ai_drafts": generate_ai_drafts,
                        "generate_testimonials": generate_testimonials,
                        "workflow_run_id": workflow_run_id,
                    }
                )
                log_activity(
                    "funnel_draft",
                    "completed",
                    payload_out={
                        "experiment_id": experiment_id,
                        "variant_id": variant_id,
                        "funnel_id": funnel_result.get("funnel_id") if isinstance(funnel_result, dict) else None,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log_activity(
                    "funnel_draft",
                    "failed",
                    error=str(exc),
                    payload_in={
                        "experiment_id": experiment_id,
                        "variant_id": variant_id,
                        "funnel_name": funnel_name,
                    },
                )
                raise

            results.append({"experiment_id": experiment_id, "variant_id": variant_id, "funnel": funnel_result})

    return {"funnels": results}
