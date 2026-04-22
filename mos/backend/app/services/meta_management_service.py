from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.db.models import Campaign, MetaPublishRun
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.services.meta_account_configs import (
    MetaWorkspaceConfigError,
    ResolvedMetaWorkspaceConfig,
    meta_ads_client_for_connection,
    resolve_ad_account_id_for_context,
    resolve_workspace_config_for_client_or_config,
)
from app.services.meta_management_benchmarks import (
    MetaManagementBenchmarkError,
    build_management_benchmark_payload,
)
from app.services.meta_media_buying import (
    MetaCutRuleConfig,
    MetaEventMappings,
    MetaInsightsConfig,
    MetaManagementBenchmarkMode,
    MetaManagementBenchmarkStatus,
    MetaManagementPlan,
    MetaMediaBuyingPlanError,
    build_management_plan,
)


class MetaManagementExecutionError(RuntimeError):
    def __init__(self, *, status_code: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class MetaManagementExecutionResult:
    campaign: Campaign | None
    plan: MetaManagementPlan
    resolved: ResolvedMetaWorkspaceConfig
    ad_account_id: str


@dataclass(frozen=True)
class MetaManagementMonitoringRunResult:
    status: str
    reason: str | None = None
    meta_campaign_id: str | None = None
    action_count: int = 0
    row_count: int = 0
    benchmark_available: bool = False
    benchmark_reason_code: str | None = None
    artifact_ids: dict[str, str] | None = None


def resolve_publish_run_management_meta_campaign_id(run: MetaPublishRun) -> str | None:
    metadata = run.metadata_json if isinstance(run.metadata_json, dict) else {}
    management = metadata.get("management")
    if isinstance(management, dict):
        override = management.get("metaCampaignId")
        if isinstance(override, str) and override.strip():
            return override.strip()

    meta_campaign_id = str(run.meta_campaign_id or "").strip()
    return meta_campaign_id or None


def resolve_management_benchmark_mode(
    *,
    benchmark_mode: MetaManagementBenchmarkMode | None,
    evaluate_benchmarks: bool | None,
) -> MetaManagementBenchmarkMode:
    if benchmark_mode is not None:
        if evaluate_benchmarks is not None:
            legacy_mode: MetaManagementBenchmarkMode = (
                "best_effort" if evaluate_benchmarks else "disabled"
            )
            if benchmark_mode != legacy_mode:
                raise MetaManagementExecutionError(
                    status_code=400,
                    detail=(
                        "benchmarkMode conflicts with evaluateBenchmarks. "
                        "Send only one benchmark control field."
                    ),
                )
        return benchmark_mode

    if evaluate_benchmarks is None:
        return "disabled"
    return "best_effort" if evaluate_benchmarks else "disabled"


def _append_warning(plan: MetaManagementPlan, warning: str) -> list[str]:
    if warning in plan.warnings:
        return list(plan.warnings)
    return [*plan.warnings, warning]


def _apply_benchmark_status(
    *,
    plan: MetaManagementPlan,
    benchmark_mode: MetaManagementBenchmarkMode,
    available: bool,
    reason_code: str | None = None,
    reason: str | None = None,
    management_scope: str = "meta_only",
    warning_code: str | None = None,
) -> MetaManagementPlan:
    warnings = _append_warning(plan, warning_code) if warning_code else list(plan.warnings)
    return plan.model_copy(
        update={
            "managementScope": management_scope,
            "benchmarkStatus": MetaManagementBenchmarkStatus(
                requestedMode=benchmark_mode,
                available=available,
                reasonCode=reason_code,
                reason=reason,
            ),
            "warnings": warnings,
        }
    )


def execute_meta_management_plan(
    *,
    session: Session,
    org_id: str,
    user_id: str | None,
    client_id: str | None,
    meta_config_id: str | None,
    meta_campaign_id: str,
    mode: str,
    date_preset: str,
    include_raw: bool,
    benchmark_mode: MetaManagementBenchmarkMode,
    cut_rules: MetaCutRuleConfig,
    event_mappings: MetaEventMappings,
) -> MetaManagementExecutionResult:
    _ = user_id
    try:
        resolved = resolve_workspace_config_for_client_or_config(
            session=session,
            org_id=org_id,
            client_id=client_id,
            config_id=meta_config_id,
        )
        ad_account_id = resolve_ad_account_id_for_context(resolved=resolved)
    except MetaWorkspaceConfigError as exc:
        message = str(exc)
        if message == "clientId or metaConfigId is required.":
            raise MetaManagementExecutionError(status_code=400, detail=message) from exc
        if message == "Meta workspace config not found.":
            raise MetaManagementExecutionError(status_code=404, detail=message) from exc
        raise MetaManagementExecutionError(status_code=409, detail=message) from exc

    try:
        plan = build_management_plan(
            client=meta_ads_client_for_connection(resolved.connection),
            ad_account_id=ad_account_id,
            campaign_id=meta_campaign_id,
            mode=mode,
            insights=MetaInsightsConfig(datePreset=date_preset),
            cut_rules=cut_rules,
            event_mappings=event_mappings,
            include_raw=include_raw,
        )
    except MetaMediaBuyingPlanError as exc:
        detail: Any = {"message": str(exc)}
        if exc.error_payload is not None:
            detail["meta"] = exc.error_payload
        raise MetaManagementExecutionError(
            status_code=exc.status_code or 502,
            detail=detail,
        ) from exc

    repo = MetaAdsRepository(session)
    local_meta_campaign = repo.get_campaign_by_meta_id(
        org_id=org_id,
        ad_account_id=ad_account_id,
        meta_campaign_id=meta_campaign_id,
    )

    campaign: Campaign | None = None
    if local_meta_campaign and local_meta_campaign.campaign_id:
        campaign = CampaignsRepository(session).get(
            org_id=org_id,
            campaign_id=str(local_meta_campaign.campaign_id),
        )
    elif mode == "apply":
        raise MetaManagementExecutionError(
            status_code=409,
            detail=(
                "A locally tracked published campaign is required before "
                "management apply mode can run."
            ),
        )

    if benchmark_mode == "disabled":
        plan = _apply_benchmark_status(
            plan=plan,
            benchmark_mode=benchmark_mode,
            available=False,
            reason_code="disabled_by_request",
            reason="Benchmark evaluation was not requested.",
        )
        return MetaManagementExecutionResult(
            campaign=campaign,
            plan=plan,
            resolved=resolved,
            ad_account_id=ad_account_id,
        )

    if campaign is None:
        detail = (
            "A locally tracked published campaign is required before benchmark evaluation can run."
        )
        if benchmark_mode == "required":
            raise MetaManagementExecutionError(status_code=409, detail=detail)
        plan = _apply_benchmark_status(
            plan=plan,
            benchmark_mode=benchmark_mode,
            available=False,
            reason_code="local_campaign_required",
            reason=detail,
            warning_code="benchmark_unavailable.local_campaign_required",
        )
        return MetaManagementExecutionResult(
            campaign=campaign,
            plan=plan,
            resolved=resolved,
            ad_account_id=ad_account_id,
        )

    try:
        benchmark_context, funnel_snapshot, benchmark_evaluations = (
            build_management_benchmark_payload(
                session=session,
                org_id=org_id,
                campaign=campaign,
                meta_campaign_id=meta_campaign_id,
                date_preset=date_preset,
                ad_rows=plan.rows,
            )
        )
    except MetaManagementBenchmarkError as exc:
        if benchmark_mode == "required":
            raise MetaManagementExecutionError(status_code=409, detail=str(exc)) from exc
        plan = _apply_benchmark_status(
            plan=plan,
            benchmark_mode=benchmark_mode,
            available=False,
            reason_code=exc.code,
            reason=str(exc),
            warning_code=f"benchmark_unavailable.{exc.code}",
        )
        return MetaManagementExecutionResult(
            campaign=campaign,
            plan=plan,
            resolved=resolved,
            ad_account_id=ad_account_id,
        )

    plan = plan.model_copy(
        update={
            "managementScope": "meta_plus_funnel",
            "benchmarkStatus": MetaManagementBenchmarkStatus(
                requestedMode=benchmark_mode,
                available=True,
                reasonCode=None,
                reason=None,
            ),
            "benchmarkContext": benchmark_context,
            "funnelSnapshot": funnel_snapshot,
            "benchmarkEvaluations": benchmark_evaluations,
        }
    )
    return MetaManagementExecutionResult(
        campaign=campaign,
        plan=plan,
        resolved=resolved,
        ad_account_id=ad_account_id,
    )


def persist_meta_management_artifacts(
    *,
    session: Session,
    org_id: str,
    user_id: str | None,
    campaign: Campaign,
    plan: MetaManagementPlan,
) -> dict[str, str]:
    artifacts_repo = ArtifactsRepository(session)
    metrics_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id) if campaign.product_id else None,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.meta_management_metrics_snapshot,
        data={
            "generatedAt": plan.generatedAt,
            "window": plan.window,
            "campaign": plan.campaign,
            "adsets": plan.adsets,
            "objectState": plan.objectState.model_dump(mode="json"),
            "rows": [row.model_dump(mode="json") for row in plan.rows],
            "observedActionTypes": plan.observedActionTypes,
            "managementScope": plan.managementScope,
            "benchmarkStatus": plan.benchmarkStatus.model_dump(mode="json"),
            "benchmarkContext": (
                plan.benchmarkContext.model_dump(mode="json") if plan.benchmarkContext else None
            ),
            "funnelSnapshot": (
                plan.funnelSnapshot.model_dump(mode="json") if plan.funnelSnapshot else None
            ),
            "benchmarkEvaluations": [
                evaluation.model_dump(mode="json") for evaluation in plan.benchmarkEvaluations
            ],
            "customMetricDefinitions": [
                definition.model_dump(mode="json") for definition in plan.customMetricDefinitions
            ],
            "customMetricSummary": [
                metric.model_dump(mode="json") for metric in plan.customMetricSummary
            ],
            "customMetricRows": [
                row.model_dump(mode="json") for row in plan.customMetricRows
            ],
        },
        created_by_user=user_id,
    )
    recommendations_artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=str(campaign.client_id),
        product_id=str(campaign.product_id) if campaign.product_id else None,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.meta_management_recommended_actions,
        data={
            "generatedAt": plan.generatedAt,
            "mode": plan.mode,
            "managementScope": plan.managementScope,
            "benchmarkStatus": plan.benchmarkStatus.model_dump(mode="json"),
            "actions": [action.model_dump(mode="json") for action in plan.actions],
            "warnings": plan.warnings,
            "benchmarkEvaluations": [
                evaluation.model_dump(mode="json") for evaluation in plan.benchmarkEvaluations
            ],
            "customMetricSummary": [
                metric.model_dump(mode="json") for metric in plan.customMetricSummary
            ],
        },
        created_by_user=user_id,
    )
    artifact_ids = {
        "metricsSnapshotArtifactId": str(metrics_artifact.id),
        "recommendedActionsArtifactId": str(recommendations_artifact.id),
    }
    if plan.mode == "apply":
        approval_artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=str(campaign.client_id),
            product_id=str(campaign.product_id) if campaign.product_id else None,
            campaign_id=str(campaign.id),
            artifact_type=ArtifactTypeEnum.meta_management_approval_decision,
            data={
                "generatedAt": plan.generatedAt,
                "approved": True,
                "approvedByUserId": user_id,
                "approvedActionKinds": [action.kind for action in plan.actions],
            },
            created_by_user=user_id,
        )
        artifact_ids["approvalDecisionArtifactId"] = str(approval_artifact.id)
        for applied_action in plan.appliedActions:
            artifacts_repo.insert(
                org_id=org_id,
                client_id=str(campaign.client_id),
                product_id=str(campaign.product_id) if campaign.product_id else None,
                campaign_id=str(campaign.id),
                artifact_type=ArtifactTypeEnum.meta_management_applied_action,
                data=applied_action.model_dump(mode="json"),
                created_by_user=user_id,
            )
    return artifact_ids


def run_meta_management_monitoring_snapshot(
    *,
    session: Session,
    org_id: str,
    campaign_id: str,
    date_preset: str = "last_3d",
) -> MetaManagementMonitoringRunResult:
    campaigns_repo = CampaignsRepository(session)
    campaign = campaigns_repo.get(org_id=org_id, campaign_id=campaign_id)
    if campaign is None:
        return MetaManagementMonitoringRunResult(
            status="skipped",
            reason="campaign_not_found",
        )

    repo = MetaAdsRepository(session)
    publish_run = repo.get_latest_published_run(org_id=org_id, campaign_id=str(campaign.id))
    if publish_run is None:
        return MetaManagementMonitoringRunResult(
            status="skipped",
            reason="published_meta_campaign_not_found",
        )

    meta_campaign_id = resolve_publish_run_management_meta_campaign_id(publish_run)
    if not meta_campaign_id:
        return MetaManagementMonitoringRunResult(
            status="skipped",
            reason="published_meta_campaign_not_found",
        )

    result = execute_meta_management_plan(
        session=session,
        org_id=org_id,
        user_id=None,
        client_id=str(campaign.client_id),
        meta_config_id=(
            str(publish_run.meta_workspace_config_id)
            if publish_run.meta_workspace_config_id
            else None
        ),
        meta_campaign_id=meta_campaign_id,
        mode="plan_only",
        date_preset=date_preset,
        include_raw=False,
        benchmark_mode="best_effort",
        cut_rules=MetaCutRuleConfig(),
        event_mappings=MetaEventMappings(),
    )
    artifact_ids = persist_meta_management_artifacts(
        session=session,
        org_id=org_id,
        user_id=None,
        campaign=campaign,
        plan=result.plan,
    )
    return MetaManagementMonitoringRunResult(
        status="applied",
        meta_campaign_id=meta_campaign_id,
        action_count=len(result.plan.actions),
        row_count=len(result.plan.rows),
        benchmark_available=result.plan.benchmarkStatus.available,
        benchmark_reason_code=result.plan.benchmarkStatus.reasonCode,
        artifact_ids=artifact_ids,
    )
