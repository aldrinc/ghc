from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from temporalio import activity

from app.db.enums import ArtifactTypeEnum, WorkflowStatusEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.client_canon import ClientCanon
from app.schemas.metric_schema import MetricSchema, MetricDefinition, EventDefinition
from app.db.base import session_scope
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository


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
