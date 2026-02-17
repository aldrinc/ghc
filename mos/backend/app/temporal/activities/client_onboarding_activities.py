from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from temporalio import activity

from sqlalchemy import select

from app.db.enums import ArtifactTypeEnum, WorkflowStatusEnum
from app.db.models import Product
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.design_systems import DesignSystemsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.client_canon import ClientCanon
from app.schemas.metric_schema import MetricSchema, MetricDefinition, EventDefinition
from app.db.base import session_scope
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.services.design_system_generation import DesignSystemGenerationContext, generate_design_system_tokens
from app.services.funnels import create_funnel_image_asset


@activity.defn
def build_client_canon_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    onboarding_payload_id = params["onboarding_payload_id"]
    precanon_research = params.get("precanon_research") or {}
    with session_scope() as session:
        payload_repo = OnboardingPayloadsRepository(session)
        payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
        payload_data = payload.data if payload else {}

    # TODO: load onboarding payload and use LLM to enrich canon.
    research_summaries = precanon_research.get("step_summaries", {}) if isinstance(precanon_research, dict) else {}
    # Prefer onboarding story, then deep research summary if present.
    story = payload_data.get("brand_story") or research_summaries.get("04")
    if not story:
        raise ValueError("Missing brand_story and deep research summary for client canon generation.")

    canon = ClientCanon(
        clientId=client_id,
        brand={
            "story": story,
            "values": [],
            "toneOfVoice": {"do": [], "dont": []},
        },
    )
    canon_dict = canon.model_dump()
    if product_id:
        canon_dict["product_id"] = product_id
    canon_dict["precanon_research"] = precanon_research
    if research_summaries:
        canon_dict["research_highlights"] = research_summaries
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=ArtifactTypeEnum.client_canon,
            data=canon_dict,
        )
    return canon_dict


@activity.defn
def build_metric_schema_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    onboarding_payload_id = params["onboarding_payload_id"]
    with session_scope() as session:
        payload_repo = OnboardingPayloadsRepository(session)
        payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
        payload_data = payload.data if payload else {}

    metric_schema = _build_metric_schema(payload_data, client_id)
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=ArtifactTypeEnum.metric_schema,
            data=metric_schema.model_dump(),
        )
    return metric_schema.model_dump()


def _build_metric_schema(payload_data: Dict[str, Any], client_id: str) -> MetricSchema:
    goals = payload_data.get("goals") or []
    offers = payload_data.get("offers") or []
    product_name = payload_data.get("product_name") or ""
    product_description = payload_data.get("product_description") or ""
    business_type = (payload_data.get("business_type") or "").lower()

    offer_text = " ".join(str(o) for o in offers + [product_name, product_description]).lower()
    goal_text = " ".join(str(g) for g in goals).lower()
    lead_intent = any(term in offer_text for term in ["lead", "newsletter", "free", "ebook", "guide"]) or "lead" in goal_text
    subscription_intent = "subscription" in offer_text or "membership" in offer_text

    traffic_metrics = [
        MetricDefinition(id="click_through_rate", name="Click-through rate", unit="%"),
        MetricDefinition(id="cost_per_click", name="Cost per click", unit="USD"),
        MetricDefinition(id="landing_page_view_rate", name="Landing page view rate", unit="%"),
    ]
    commerce_metrics = [
        MetricDefinition(id="purchase_rate", name="Purchase conversion rate", unit="%"),
        MetricDefinition(id="cost_per_purchase", name="Cost per purchase", unit="USD"),
        MetricDefinition(id="purchase_count", name="Purchases", unit="count"),
        MetricDefinition(id="revenue", name="Revenue", unit="USD"),
        MetricDefinition(id="add_to_cart_rate", name="Add to cart rate", unit="%"),
    ]
    lead_metrics = [
        MetricDefinition(id="lead_count", name="Leads", unit="count"),
        MetricDefinition(id="cost_per_lead", name="Cost per lead", unit="USD"),
        MetricDefinition(id="lead_conversion_rate", name="Lead conversion rate", unit="%"),
    ]
    retention_metrics = [
        MetricDefinition(id="trial_to_paid_rate", name="Trial to paid conversion rate", unit="%"),
        MetricDefinition(id="monthly_recurring_revenue", name="Monthly recurring revenue", unit="USD"),
        MetricDefinition(id="churn_rate", name="Churn rate", unit="%"),
    ]

    events = [
        EventDefinition(
            id="traffic",
            name="Traffic",
            description="Top-of-funnel traffic and engagement.",
            metrics=traffic_metrics,
        ),
        EventDefinition(
            id="checkout",
            name="Checkout",
            description="Commerce intent and purchase completion.",
            metrics=commerce_metrics,
        ),
    ]

    primary_kpis = ["purchase_rate", "cost_per_purchase"]
    secondary_kpis = ["click_through_rate", "cost_per_click", "add_to_cart_rate"]

    if lead_intent:
        events.append(
            EventDefinition(
                id="lead",
                name="Lead capture",
                description="Lead magnet or list growth funnel.",
                metrics=lead_metrics,
            )
        )
        primary_kpis = ["lead_conversion_rate", "cost_per_lead"]
        secondary_kpis.append("landing_page_view_rate")

    if subscription_intent or business_type == "subscription":
        events.append(
            EventDefinition(
                id="retention",
                name="Retention",
                description="Subscription conversion and retention.",
                metrics=retention_metrics,
            )
        )
        if "trial_to_paid_rate" not in primary_kpis:
            primary_kpis = ["trial_to_paid_rate", "monthly_recurring_revenue"]
        if "churn_rate" not in secondary_kpis:
            secondary_kpis.append("churn_rate")

    if not primary_kpis:
        raise ValueError("Metric schema cannot be generated without clear KPI intent in onboarding payload.")

    return MetricSchema(
        clientId=client_id,
        events=events,
        primaryKpis=primary_kpis,
        secondaryKpis=secondary_kpis,
    )


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _resolve_existing_logo_public_id(*, session, org_id: str, client_id: str) -> str | None:
    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=org_id, client_id=client_id)
    if not client or not client.design_system_id:
        return None

    ds_repo = DesignSystemsRepository(session)
    design_system = ds_repo.get(org_id=org_id, design_system_id=str(client.design_system_id))
    tokens = design_system.tokens if design_system else None
    if not isinstance(tokens, dict):
        return None

    brand = tokens.get("brand")
    if not isinstance(brand, dict):
        return None

    logo_public_id = brand.get("logoAssetPublicId")
    if not isinstance(logo_public_id, str) or not logo_public_id.strip():
        return None

    assets_repo = AssetsRepository(session)
    asset = assets_repo.get_by_public_id(org_id=org_id, client_id=client_id, public_id=logo_public_id.strip())
    if not asset:
        return None
    return logo_public_id.strip()


def _build_logo_prompt(*, client_name: str, industry: str | None, product_name: str, story: str) -> str:
    industry_line = f"Industry: {industry}." if industry else ""
    return (
        "Create an ORIGINAL brand logo for a new business.\n"
        f"Brand name: {client_name}.\n"
        f"{industry_line}\n"
        f"Product: {product_name}.\n"
        f"Brand story/context: {story}\n\n"
        "Design requirements:\n"
        "- Simple, bold, highly legible at small sizes (40px tall).\n"
        "- Clean modern wordmark OR monogram + wordmark.\n"
        "- Flat design, no photorealism.\n"
        "- Transparent background.\n"
        "- Centered with generous padding.\n"
        "- No taglines.\n"
        "- Do not imitate any existing brand or copyrighted logo.\n"
    ).strip()


@activity.defn
def build_design_system_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    onboarding_payload_id = params["onboarding_payload_id"]
    precanon_research = params.get("precanon_research") or {}
    canon = params.get("canon") or {}

    if not isinstance(product_id, str) or not product_id.strip():
        raise ValueError("product_id is required to build a design system.")

    with session_scope() as session:
        payload_repo = OnboardingPayloadsRepository(session)
        payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
        payload_data = payload.data if payload and isinstance(payload.data, dict) else {}

        clients_repo = ClientsRepository(session)
        client = clients_repo.get(org_id=org_id, client_id=client_id)
        if not client:
            raise ValueError("Client not found for design system generation.")

        product = session.scalars(
            select(Product).where(
                Product.org_id == org_id,
                Product.client_id == client_id,
                Product.id == product_id,
            )
        ).first()
        if not product:
            raise ValueError("Product not found for design system generation.")

        canon_story: str | None = None
        if isinstance(canon, dict):
            brand = canon.get("brand")
            if isinstance(brand, dict):
                story_value = brand.get("story")
                if isinstance(story_value, str) and story_value.strip():
                    canon_story = story_value.strip()

        brand_story = canon_story or payload_data.get("brand_story") or ""
        if not isinstance(brand_story, str) or not brand_story.strip():
            raise ValueError("Missing brand_story for design system generation.")

        goals = _coerce_string_list(payload_data.get("goals"))
        competitor_urls = _coerce_string_list(payload_data.get("competitor_urls"))
        funnel_notes = payload_data.get("funnel_notes") if isinstance(payload_data.get("funnel_notes"), str) else None

        step_summaries: dict[str, str] = {}
        if isinstance(precanon_research, dict):
            raw = precanon_research.get("step_summaries") or precanon_research.get("stepSummaries")
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
                        step_summaries[key.strip()] = value.strip()

        gen_ctx = DesignSystemGenerationContext(
            org_id=org_id,
            client_id=client_id,
            product_id=str(product.id),
            client_name=str(client.name),
            client_industry=str(client.industry) if client.industry else None,
            brand_story=brand_story.strip(),
            product_name=str(product.title),
            product_description=str(product.description) if product.description else None,
            product_category=str(product.product_type) if product.product_type else None,
            primary_benefits=list(product.primary_benefits or []),
            feature_bullets=list(product.feature_bullets or []),
            guarantee_text=str(product.guarantee_text) if product.guarantee_text else None,
            disclaimers=list(product.disclaimers or []),
            goals=goals,
            funnel_notes=funnel_notes,
            competitor_urls=competitor_urls,
            precanon_step_summaries=step_summaries,
        )

        tokens = generate_design_system_tokens(ctx=gen_ctx)
        if not isinstance(tokens, dict):
            raise RuntimeError("Design system generation returned non-object tokens.")

        brand_tokens = tokens.get("brand")
        if not isinstance(brand_tokens, dict):
            raise RuntimeError("Generated design system tokens missing brand object.")
        brand_tokens["name"] = str(client.name)

        logo_public_id = _resolve_existing_logo_public_id(session=session, org_id=org_id, client_id=client_id)
        if not logo_public_id:
            try:
                asset = create_funnel_image_asset(
                    session=session,
                    org_id=org_id,
                    client_id=client_id,
                    prompt=_build_logo_prompt(
                        client_name=str(client.name),
                        industry=str(client.industry) if client.industry else None,
                        product_name=str(product.title),
                        story=brand_story.strip(),
                    ),
                    # Gemini image API only supports a fixed set of aspect ratios; 21:9 gives a wide wordmark-friendly canvas.
                    aspect_ratio="21:9",
                    usage_context={
                        "kind": "brand_logo",
                        "source": "onboarding",
                        "client_id": client_id,
                        "product_id": str(product.id),
                        "onboarding_payload_id": onboarding_payload_id,
                    },
                    tags=["brand_logo", "design_system"],
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Failed to generate default brand logo for design system via the Gemini image API. "
                    f"Error: {exc}"
                ) from exc
            asset.alt = f"{client.name} logo"
            session.commit()
            logo_public_id = str(asset.public_id)

        brand_tokens["logoAssetPublicId"] = logo_public_id
        logo_alt = brand_tokens.get("logoAlt")
        if not isinstance(logo_alt, str) or not logo_alt.strip():
            brand_tokens["logoAlt"] = str(client.name)

        ds_name = (
            f"Onboarding design system ({product.title}) "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        ds_repo = DesignSystemsRepository(session)
        design_system = ds_repo.create(
            org_id=org_id,
            client_id=client_id,
            name=ds_name,
            tokens=tokens,
        )

        clients_repo.update(org_id=org_id, client_id=client_id, design_system_id=str(design_system.id))

        return {
            "design_system_id": str(design_system.id),
            "client_id": client_id,
            "logoAssetPublicId": logo_public_id,
        }


@activity.defn
def persist_client_onboarding_artifacts_activity(params: Dict[str, Any]) -> Dict[str, bool]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    product_id = params.get("product_id")
    canon = params.get("canon")
    metric_schema = params.get("metric_schema")
    _ = params.get("research_artifacts")
    temporal_workflow_id = params.get("temporal_workflow_id")
    temporal_run_id = params.get("temporal_run_id")

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        if canon:
            artifacts_repo.insert(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                artifact_type=ArtifactTypeEnum.client_canon,
                data=canon,
            )
        if metric_schema:
            artifacts_repo.insert(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                artifact_type=ArtifactTypeEnum.metric_schema,
                data=metric_schema,
            )

        if temporal_workflow_id and temporal_run_id:
            wf_repo = WorkflowsRepository(session)
            run = wf_repo.get_by_temporal_ids(
                org_id=org_id,
                temporal_workflow_id=temporal_workflow_id,
                temporal_run_id=temporal_run_id,
            )
            if run:
                wf_repo.set_status(
                    org_id=org_id,
                    workflow_run_id=str(run.id),
                    status=WorkflowStatusEnum.completed,
                    finished_at=datetime.now(timezone.utc),
                )

    return {
        "canon_persisted": bool(canon),
        "metric_schema_persisted": bool(metric_schema),
    }
