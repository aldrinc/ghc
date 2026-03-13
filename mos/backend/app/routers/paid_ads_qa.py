from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Asset, Campaign
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.schemas.paid_ads_qa import (
    PaidAdsPlatformProfileResponse,
    PaidAdsPlatformProfileUpsertRequest,
    PaidAdsQaFindingResponse,
    PaidAdsQaRunRequest,
    PaidAdsQaRunResponse,
    PaidAdsRulesetResponse,
    PaidAdsRulesetSummaryResponse,
)
from app.services.meta_review import select_assets_for_generation
from app.services.paid_ads_qa import (
    MetaProfileRefreshError,
    RULESET_VERSION,
    clean_optional_text,
    derive_run_status,
    evaluate_meta_campaign,
    evaluate_platform_profile,
    get_ruleset,
    list_rulesets,
    normalize_platform,
    normalize_tracking_provider,
    refresh_meta_platform_profile_from_graph,
    render_report_markdown,
    summarize_findings,
    write_report_file,
)


router = APIRouter(tags=["paid-ads-qa"])


def _get_client_or_404(*, session: Session, org_id: str, client_id: str):
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _filter_creative_specs_to_generation(*, creative_specs: list[Any], asset_ids: set[str]) -> list[Any]:
    return [spec for spec in creative_specs if getattr(spec, "asset_id", None) and str(spec.asset_id) in asset_ids]


def _to_profile_payload(profile: Any) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "orgId": str(profile.org_id),
        "clientId": str(profile.client_id),
        "platform": profile.platform,
        "rulesetVersion": profile.ruleset_version,
        "businessManagerId": profile.business_manager_id,
        "businessManagerName": profile.business_manager_name,
        "pageId": profile.page_id,
        "pageName": profile.page_name,
        "adAccountId": profile.ad_account_id,
        "adAccountName": profile.ad_account_name,
        "paymentMethodType": profile.payment_method_type,
        "paymentMethodStatus": profile.payment_method_status,
        "pixelId": profile.pixel_id,
        "dataSetId": profile.data_set_id,
        "dataSetShopifyPartnerInstalled": profile.data_set_shopify_partner_installed,
        "dataSetDataSharingLevel": profile.data_set_data_sharing_level,
        "dataSetAssignedToAdAccount": profile.data_set_assigned_to_ad_account,
        "verifiedDomain": profile.verified_domain,
        "verifiedDomainStatus": profile.verified_domain_status,
        "attributionClickWindow": profile.attribution_click_window,
        "attributionViewWindow": profile.attribution_view_window,
        "viewThroughEnabled": profile.view_through_enabled,
        "trackingProvider": profile.tracking_provider,
        "trackingUrlParameters": profile.tracking_url_parameters,
        "metadata": profile.metadata_json if isinstance(profile.metadata_json, dict) else {},
        "createdAt": profile.created_at.isoformat(),
        "updatedAt": profile.updated_at.isoformat(),
    }


def _profile_input_from_payload(payload: PaidAdsPlatformProfileUpsertRequest, *, platform: str) -> dict[str, Any]:
    return {
        "platform": platform,
        "ruleset_version": payload.rulesetVersion,
        "business_manager_id": clean_optional_text(payload.businessManagerId),
        "business_manager_name": clean_optional_text(payload.businessManagerName),
        "page_id": clean_optional_text(payload.pageId),
        "page_name": clean_optional_text(payload.pageName),
        "ad_account_id": clean_optional_text(payload.adAccountId),
        "ad_account_name": clean_optional_text(payload.adAccountName),
        "payment_method_type": normalize_tracking_provider(payload.paymentMethodType),
        "payment_method_status": clean_optional_text(payload.paymentMethodStatus),
        "pixel_id": clean_optional_text(payload.pixelId),
        "data_set_id": clean_optional_text(payload.dataSetId),
        "data_set_shopify_partner_installed": payload.dataSetShopifyPartnerInstalled,
        "data_set_data_sharing_level": normalize_tracking_provider(payload.dataSetDataSharingLevel),
        "data_set_assigned_to_ad_account": payload.dataSetAssignedToAdAccount,
        "verified_domain": clean_optional_text(payload.verifiedDomain),
        "verified_domain_status": normalize_tracking_provider(payload.verifiedDomainStatus),
        "attribution_click_window": normalize_tracking_provider(payload.attributionClickWindow),
        "attribution_view_window": normalize_tracking_provider(payload.attributionViewWindow),
        "view_through_enabled": payload.viewThroughEnabled,
        "tracking_provider": normalize_tracking_provider(payload.trackingProvider),
        "tracking_url_parameters": clean_optional_text(payload.trackingUrlParameters),
        "metadata_json": payload.metadata or {},
    }


def _profile_input_from_dict(profile: dict[str, Any], *, platform: str) -> dict[str, Any]:
    return {
        "platform": platform,
        "ruleset_version": str(profile.get("rulesetVersion") or RULESET_VERSION),
        "business_manager_id": clean_optional_text(profile.get("businessManagerId")),
        "business_manager_name": clean_optional_text(profile.get("businessManagerName")),
        "page_id": clean_optional_text(profile.get("pageId")),
        "page_name": clean_optional_text(profile.get("pageName")),
        "ad_account_id": clean_optional_text(profile.get("adAccountId")),
        "ad_account_name": clean_optional_text(profile.get("adAccountName")),
        "payment_method_type": normalize_tracking_provider(profile.get("paymentMethodType")),
        "payment_method_status": clean_optional_text(profile.get("paymentMethodStatus")),
        "pixel_id": clean_optional_text(profile.get("pixelId")),
        "data_set_id": clean_optional_text(profile.get("dataSetId")),
        "data_set_shopify_partner_installed": profile.get("dataSetShopifyPartnerInstalled"),
        "data_set_data_sharing_level": normalize_tracking_provider(profile.get("dataSetDataSharingLevel")),
        "data_set_assigned_to_ad_account": profile.get("dataSetAssignedToAdAccount"),
        "verified_domain": clean_optional_text(profile.get("verifiedDomain")),
        "verified_domain_status": normalize_tracking_provider(profile.get("verifiedDomainStatus")),
        "attribution_click_window": normalize_tracking_provider(profile.get("attributionClickWindow")),
        "attribution_view_window": normalize_tracking_provider(profile.get("attributionViewWindow")),
        "view_through_enabled": profile.get("viewThroughEnabled"),
        "tracking_provider": normalize_tracking_provider(profile.get("trackingProvider")),
        "tracking_url_parameters": clean_optional_text(profile.get("trackingUrlParameters")),
        "metadata_json": profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {},
    }


def _profile_dict(record: Any | None, *, platform: str, client_id: str) -> dict[str, Any]:
    if record is None:
        return {
            "clientId": client_id,
            "platform": platform,
            "rulesetVersion": RULESET_VERSION,
            "metadata": {},
        }
    return _to_profile_payload(record)


def _refresh_meta_profile(
    *,
    repo: PaidAdsQaRepository,
    org_id: str,
    client_id: str,
    record: Any | None,
) -> Any:
    profile_dict = _profile_dict(record, platform="meta", client_id=client_id)
    try:
        refreshed = refresh_meta_platform_profile_from_graph(profile=profile_dict, ruleset_version=RULESET_VERSION)
    except MetaProfileRefreshError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return repo.upsert_platform_profile(
        org_id=org_id,
        client_id=client_id,
        **_profile_input_from_dict(refreshed, platform="meta"),
    )


def _finding_response(record: Any) -> PaidAdsQaFindingResponse:
    return PaidAdsQaFindingResponse(
        id=str(record.id),
        ruleId=record.rule_id,
        ruleType=record.rule_type,
        platform=record.platform,
        severity=record.severity,
        status=record.status,
        title=record.title,
        message=record.message,
        artifactType=record.artifact_type,
        artifactRef=record.artifact_ref,
        fixGuidance=record.fix_guidance_json or [],
        evidence=record.evidence_json or {},
        needsVerification=record.needs_verification,
        sourceId=record.source_id,
        sourceTitle=record.source_title,
        sourceUrl=record.source_url,
        policyAnchorQuote=record.policy_anchor_quote,
        createdAt=record.created_at.isoformat(),
    )


def _run_response(run: Any, findings: list[Any]) -> PaidAdsQaRunResponse:
    return PaidAdsQaRunResponse(
        id=str(run.id),
        orgId=str(run.org_id),
        clientId=str(run.client_id),
        campaignId=str(run.campaign_id) if run.campaign_id else None,
        platform=run.platform,
        subjectType=run.subject_type,
        subjectId=run.subject_id,
        rulesetVersion=run.ruleset_version,
        status=run.status,
        blockerCount=run.blocker_count,
        highCount=run.high_count,
        mediumCount=run.medium_count,
        lowCount=run.low_count,
        needsManualReviewCount=run.needs_manual_review_count,
        checkedRuleIds=run.checked_rule_ids or [],
        reportFilePath=run.report_file_path,
        reportMarkdown=run.report_markdown,
        metadata=run.metadata_json or {},
        findings=[_finding_response(record) for record in findings],
        createdAt=run.created_at.isoformat(),
        completedAt=run.completed_at.isoformat() if run.completed_at else None,
    )


@router.get("/paid-ads-qa/rulesets", response_model=list[PaidAdsRulesetSummaryResponse])
def list_paid_ads_rulesets(auth: AuthContext = Depends(get_current_user)):
    _ = auth
    return list_rulesets()


@router.get("/paid-ads-qa/rulesets/{ruleset_version}", response_model=PaidAdsRulesetResponse)
def get_paid_ads_ruleset(ruleset_version: str, auth: AuthContext = Depends(get_current_user)):
    _ = auth
    try:
        return get_ruleset(ruleset_version)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/clients/{client_id}/paid-ads-qa/platforms/{platform}/profile",
    response_model=PaidAdsPlatformProfileResponse,
)
def get_paid_ads_platform_profile(
    client_id: str,
    platform: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    normalized_platform = normalize_platform(platform)
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = PaidAdsQaRepository(session)
    profile = repo.get_platform_profile(org_id=auth.org_id, client_id=client_id, platform=normalized_platform)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paid ads platform profile not found")
    return PaidAdsPlatformProfileResponse(**_to_profile_payload(profile))


@router.put(
    "/clients/{client_id}/paid-ads-qa/platforms/{platform}/profile",
    response_model=PaidAdsPlatformProfileResponse,
)
def upsert_paid_ads_platform_profile(
    client_id: str,
    platform: str,
    payload: PaidAdsPlatformProfileUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    normalized_platform = normalize_platform(platform)
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    if payload.rulesetVersion != RULESET_VERSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported rulesetVersion '{payload.rulesetVersion}'. Expected '{RULESET_VERSION}'.",
        )
    repo = PaidAdsQaRepository(session)
    profile = repo.upsert_platform_profile(
        org_id=auth.org_id,
        client_id=client_id,
        **_profile_input_from_payload(payload, platform=normalized_platform),
    )
    return PaidAdsPlatformProfileResponse(**_to_profile_payload(profile))


@router.post(
    "/clients/{client_id}/paid-ads-qa/platforms/{platform}/assessment",
    response_model=PaidAdsQaRunResponse,
)
def assess_paid_ads_platform_profile(
    client_id: str,
    platform: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    normalized_platform = normalize_platform(platform)
    _get_client_or_404(session=session, org_id=auth.org_id, client_id=client_id)
    repo = PaidAdsQaRepository(session)
    profile = repo.get_platform_profile(org_id=auth.org_id, client_id=client_id, platform=normalized_platform)
    if normalized_platform == "meta":
        profile = _refresh_meta_profile(repo=repo, org_id=auth.org_id, client_id=client_id, record=profile)
    assessment = evaluate_platform_profile(
        platform=normalized_platform,
        profile=_profile_dict(profile, platform=normalized_platform, client_id=client_id),
        ruleset_version=RULESET_VERSION,
    )
    summary = summarize_findings(assessment["findings"])
    status_value = derive_run_status(assessment["findings"])
    run_uuid = uuid4()
    run_id = str(run_uuid)
    report_markdown = render_report_markdown(
        subject_type="platform_profile",
        subject_id=f"{client_id}:{normalized_platform}",
        platform=normalized_platform,
        ruleset_version=RULESET_VERSION,
        status=status_value,
        checked_rule_ids=assessment["checkedRuleIds"],
        findings=assessment["findings"],
        metadata=assessment["metadata"],
    )
    report_file_path = write_report_file(
        run_id=run_id,
        subject_type="platform_profile",
        subject_id=f"{client_id}:{normalized_platform}",
        platform=normalized_platform,
        report_markdown=report_markdown,
    )
    run = repo.create_run(
        id=run_uuid,
        org_id=auth.org_id,
        client_id=client_id,
        campaign_id=None,
        platform=normalized_platform,
        subject_type="platform_profile",
        subject_id=f"{client_id}:{normalized_platform}",
        ruleset_version=RULESET_VERSION,
        status=status_value,
        blocker_count=summary["blockerCount"],
        high_count=summary["highCount"],
        medium_count=summary["mediumCount"],
        low_count=summary["lowCount"],
        needs_manual_review_count=summary["needsManualReviewCount"],
        checked_rule_ids=assessment["checkedRuleIds"],
        report_markdown=report_markdown,
        report_file_path=report_file_path,
        metadata_json=assessment["metadata"],
        completed_at=datetime.now(timezone.utc),
    )
    finding_records = repo.create_findings(
        findings=[
            {
                "org_id": auth.org_id,
                "qa_run_id": str(run.id),
                "rule_id": finding["ruleId"],
                "rule_type": finding["ruleType"],
                "platform": finding["platform"],
                "severity": finding["severity"],
                "status": finding["status"],
                "artifact_type": finding["artifactType"],
                "artifact_ref": finding["artifactRef"],
                "title": finding["title"],
                "message": finding["message"],
                "fix_guidance_json": finding["fixGuidance"],
                "evidence_json": finding["evidence"],
                "needs_verification": finding["needsVerification"],
                "source_id": finding["sourceId"],
                "source_title": finding["sourceTitle"],
                "source_url": finding["sourceUrl"],
                "policy_anchor_quote": finding["policyAnchorQuote"],
            }
            for finding in assessment["findings"]
        ]
    )
    return _run_response(run, finding_records)


@router.post("/campaigns/{campaign_id}/paid-ads-qa/runs", response_model=PaidAdsQaRunResponse)
def run_campaign_paid_ads_qa(
    campaign_id: str,
    payload: PaidAdsQaRunRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    normalized_platform = normalize_platform(payload.platform)
    if payload.rulesetVersion != RULESET_VERSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported rulesetVersion '{payload.rulesetVersion}'. Expected '{RULESET_VERSION}'.",
        )
    campaign = session.scalar(
        select(Campaign).where(
            Campaign.org_id == auth.org_id,
            Campaign.id == campaign_id,
        )
    )
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if normalized_platform != "meta":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign-level paid ads QA is currently implemented for Meta only. Use platform profile assessment for TikTok readiness.",
        )

    repo = PaidAdsQaRepository(session)
    profile = repo.get_platform_profile(org_id=auth.org_id, client_id=str(campaign.client_id), platform="meta")
    profile = _refresh_meta_profile(
        repo=repo,
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        record=profile,
    )
    meta_repo = MetaAdsRepository(session)
    adset_specs = meta_repo.list_adset_specs(org_id=auth.org_id, campaign_id=str(campaign.id))
    campaign_ready_assets = session.scalars(
        select(Asset).where(
            Asset.org_id == auth.org_id,
            Asset.campaign_id == str(campaign.id),
            Asset.file_status == "ready",
        )
    ).all()
    selected_generation_key, ready_assets = select_assets_for_generation(
        campaign_ready_assets,
        generation_key=clean_optional_text(payload.generationKey),
    )
    ready_asset_ids = {str(asset.id) for asset in ready_assets}
    creative_specs = _filter_creative_specs_to_generation(
        creative_specs=meta_repo.list_creative_specs(org_id=auth.org_id, campaign_id=str(campaign.id)),
        asset_ids=ready_asset_ids,
    )
    assessment = evaluate_meta_campaign(
        campaign=campaign,
        creative_specs=creative_specs,
        adset_specs=adset_specs,
        ready_assets=ready_assets,
        platform_profile=_profile_dict(profile, platform="meta", client_id=str(campaign.client_id)),
        review_base_url=clean_optional_text(payload.reviewBaseUrl),
        ruleset_version=RULESET_VERSION,
    )
    assessment["metadata"]["generationKey"] = selected_generation_key
    assessment["metadata"]["requestedGenerationKey"] = clean_optional_text(payload.generationKey)
    assessment["metadata"]["generationAssetIds"] = sorted(ready_asset_ids)
    summary = summarize_findings(assessment["findings"])
    status_value = derive_run_status(assessment["findings"])
    run_uuid = uuid4()
    run_id = str(run_uuid)
    report_markdown = render_report_markdown(
        subject_type="campaign",
        subject_id=str(campaign.id),
        platform="meta",
        ruleset_version=RULESET_VERSION,
        status=status_value,
        checked_rule_ids=assessment["checkedRuleIds"],
        findings=assessment["findings"],
        metadata=assessment["metadata"],
    )
    report_file_path = write_report_file(
        run_id=run_id,
        subject_type="campaign",
        subject_id=str(campaign.id),
        platform="meta",
        report_markdown=report_markdown,
    )
    run = repo.create_run(
        id=run_uuid,
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=str(campaign.id),
        platform="meta",
        subject_type="campaign",
        subject_id=str(campaign.id),
        ruleset_version=RULESET_VERSION,
        status=status_value,
        blocker_count=summary["blockerCount"],
        high_count=summary["highCount"],
        medium_count=summary["mediumCount"],
        low_count=summary["lowCount"],
        needs_manual_review_count=summary["needsManualReviewCount"],
        checked_rule_ids=assessment["checkedRuleIds"],
        report_markdown=report_markdown,
        report_file_path=report_file_path,
        metadata_json=assessment["metadata"],
        completed_at=datetime.now(timezone.utc),
    )
    finding_records = repo.create_findings(
        findings=[
            {
                "org_id": auth.org_id,
                "qa_run_id": str(run.id),
                "rule_id": finding["ruleId"],
                "rule_type": finding["ruleType"],
                "platform": finding["platform"],
                "severity": finding["severity"],
                "status": finding["status"],
                "artifact_type": finding["artifactType"],
                "artifact_ref": finding["artifactRef"],
                "title": finding["title"],
                "message": finding["message"],
                "fix_guidance_json": finding["fixGuidance"],
                "evidence_json": finding["evidence"],
                "needs_verification": finding["needsVerification"],
                "source_id": finding["sourceId"],
                "source_title": finding["sourceTitle"],
                "source_url": finding["sourceUrl"],
                "policy_anchor_quote": finding["policyAnchorQuote"],
            }
            for finding in assessment["findings"]
        ]
    )
    return _run_response(run, finding_records)


@router.get("/campaigns/{campaign_id}/paid-ads-qa/runs", response_model=list[PaidAdsQaRunResponse])
def list_campaign_paid_ads_qa_runs(
    campaign_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = session.scalar(
        select(Campaign).where(
            Campaign.org_id == auth.org_id,
            Campaign.id == campaign_id,
        )
    )
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    repo = PaidAdsQaRepository(session)
    runs = repo.list_runs(
        org_id=auth.org_id,
        campaign_id=str(campaign.id),
        subject_type="campaign",
        limit=limit,
    )
    return [_run_response(run, repo.list_findings(qa_run_id=str(run.id))) for run in runs]


@router.get("/campaigns/{campaign_id}/paid-ads-qa/runs/{run_id}", response_model=PaidAdsQaRunResponse)
def get_campaign_paid_ads_qa_run(
    campaign_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = PaidAdsQaRepository(session)
    run = repo.get_run(org_id=auth.org_id, run_id=run_id)
    if not run or str(run.campaign_id or "") != campaign_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paid ads QA run not found")
    findings = repo.list_findings(qa_run_id=str(run.id))
    return _run_response(run, findings)


@router.get("/campaigns/{campaign_id}/paid-ads-qa/runs/{run_id}/report.md")
def get_campaign_paid_ads_qa_report_markdown(
    campaign_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = PaidAdsQaRepository(session)
    run = repo.get_run(org_id=auth.org_id, run_id=run_id)
    if not run or str(run.campaign_id or "") != campaign_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paid ads QA run not found")
    return Response(content=run.report_markdown, media_type="text/markdown; charset=utf-8")
