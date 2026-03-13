from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import FunnelDomainStatusEnum
from app.db.models import Asset, Campaign, ClientUserPreference, Funnel, FunnelDomain
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.db.repositories.paid_ads_qa import PaidAdsQaRepository
from app.schemas.paid_ads_qa import (
    PaidAdsDnsRecordResponse,
    PaidAdsMetaDomainVerificationProvisionRequest,
    PaidAdsMetaDomainVerificationProvisionResponse,
    PaidAdsMetaTrackingRepairResponse,
    PaidAdsPlatformProfileResponse,
    PaidAdsPlatformProfileUpsertRequest,
    PaidAdsQaFindingResponse,
    PaidAdsQaRunRequest,
    PaidAdsQaRunResponse,
    PaidAdsRulesetResponse,
    PaidAdsRulesetSummaryResponse,
)
from app.services.meta_review import (
    asset_funnel_id_from_briefs,
    collect_asset_funnel_ids,
    load_campaign_asset_brief_map,
    select_assets_for_generation,
)
from app.services import namecheap_dns as namecheap_dns_service
from app.services.paid_ads_qa import (
    MetaProfileRefreshError,
    RULESET_VERSION,
    activate_mos_meta_funnel_tracking_profile,
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
from app.services.storefront_domains import normalize_absolute_origin, resolve_shop_hosted_origin


router = APIRouter(tags=["paid-ads-qa"])
_META_DOMAIN_VERIFICATION_METADATA_KEY = "metaDomainVerification"


def _get_client_or_404(*, session: Session, org_id: str, client_id: str):
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _get_funnel_or_404(*, session: Session, org_id: str, funnel_id: str) -> Funnel:
    funnel = session.scalar(
        select(Funnel).where(
            Funnel.org_id == org_id,
            Funnel.id == funnel_id,
        )
    )
    if not funnel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")
    return funnel


def _get_funnel_campaign_or_404(*, session: Session, org_id: str, funnel: Funnel) -> Campaign:
    if not funnel.campaign_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This operation requires a funnel that is attached to a campaign.",
        )
    campaign = session.scalar(
        select(Campaign).where(
            Campaign.org_id == org_id,
            Campaign.id == funnel.campaign_id,
        )
    )
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found for funnel")
    if str(campaign.client_id) != str(funnel.client_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Funnel client does not match the parent campaign client.",
        )
    return campaign


def _require_supported_ruleset(ruleset_version: str) -> str:
    try:
        get_ruleset(ruleset_version)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ruleset_version


def _filter_creative_specs_to_generation(*, creative_specs: list[Any], asset_ids: set[str]) -> list[Any]:
    return [spec for spec in creative_specs if getattr(spec, "asset_id", None) and str(spec.asset_id) in asset_ids]


def _campaign_uses_meta_channel(channels: list[str] | None) -> bool:
    for channel in channels or []:
        normalized = clean_optional_text(channel)
        if normalized and normalized.lower() in {"facebook", "instagram", "meta"}:
            return True
    return False


def _selected_shop_storefront_domain(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    user_external_id: str,
) -> str | None:
    preference = session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == user_external_id,
        )
    )
    selected = clean_optional_text(
        getattr(preference, "selected_shop_storefront_domain", None) if preference is not None else None
    )
    return resolve_shop_hosted_origin(selected)


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_optional_text(value) if isinstance(value, str) else None
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _profile_metadata_dict(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = profile.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _meta_domain_verification_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = _profile_metadata_dict(profile)
    raw = metadata.get(_META_DOMAIN_VERIFICATION_METADATA_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _merge_string_list(existing_values: Any, values_to_add: list[str]) -> list[str]:
    merged = _normalize_string_list(existing_values)
    seen = set(merged)
    for value in values_to_add:
        cleaned = clean_optional_text(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        merged.append(cleaned)
    return merged


def _normalize_hostname_candidate(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return None
    candidate = cleaned
    if "://" in candidate:
        parsed = urlparse(candidate)
        hostname = clean_optional_text(parsed.hostname)
        return hostname.lower() if hostname else None
    return candidate.lower().rstrip(".")


def _resolve_funnel_verified_domain(
    *,
    session: Session,
    auth: AuthContext,
    funnel: Funnel,
    profile: dict[str, Any],
    requested_verified_domain: str | None,
) -> str:
    requested = _normalize_hostname_candidate(requested_verified_domain)
    if requested:
        return requested

    funnel_domain = session.scalar(
        select(FunnelDomain).where(
            FunnelDomain.org_id == auth.org_id,
            FunnelDomain.funnel_id == str(funnel.id),
            FunnelDomain.status.in_([FunnelDomainStatusEnum.active, FunnelDomainStatusEnum.verified]),
        )
    )
    if funnel_domain is not None:
        hostname = _normalize_hostname_candidate(getattr(funnel_domain, "hostname", None))
        if hostname:
            return hostname

    existing_profile_domain = _normalize_hostname_candidate(profile.get("verifiedDomain"))
    if existing_profile_domain:
        return existing_profile_domain

    selected_storefront_origin = _selected_shop_storefront_domain(
        session=session,
        org_id=auth.org_id,
        client_id=str(funnel.client_id),
        user_external_id=auth.user_id,
    )
    selected_storefront_host = _normalize_hostname_candidate(selected_storefront_origin)
    if selected_storefront_host:
        return selected_storefront_host

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Meta domain verification requires a verified domain target. "
            "Set the client's selected storefront domain or enter a verified domain explicitly."
        ),
    )


def _resolve_review_base_url(
    *,
    session: Session,
    auth: AuthContext,
    client_id: str,
    requested_review_base_url: str | None,
) -> str | None:
    expected_review_base_url = _selected_shop_storefront_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    provided_review_base_url = normalize_absolute_origin(requested_review_base_url)
    if requested_review_base_url and provided_review_base_url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reviewBaseUrl must be an absolute http(s) URL.",
        )

    if expected_review_base_url and provided_review_base_url and provided_review_base_url != expected_review_base_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Meta QA reviewBaseUrl must match the selected storefront host for this client.",
                "reviewBaseUrl": provided_review_base_url,
                "expectedReviewBaseUrl": expected_review_base_url,
                "storefrontHostname": urlparse(expected_review_base_url).hostname,
            },
        )

    return provided_review_base_url or expected_review_base_url


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
    _require_supported_ruleset(payload.rulesetVersion)
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


@router.post(
    "/funnels/{funnel_id}/paid-ads-qa/meta-domain-verification/provision",
    response_model=PaidAdsMetaDomainVerificationProvisionResponse,
)
def provision_meta_domain_verification_dns(
    funnel_id: str,
    payload: PaidAdsMetaDomainVerificationProvisionRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnel = _get_funnel_or_404(session=session, org_id=auth.org_id, funnel_id=funnel_id)
    campaign = _get_funnel_campaign_or_404(session=session, org_id=auth.org_id, funnel=funnel)
    if not _campaign_uses_meta_channel(campaign.channels):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta domain verification requires the funnel's campaign to target a Meta channel.",
        )

    repo = PaidAdsQaRepository(session)
    profile_record = repo.get_platform_profile(org_id=auth.org_id, client_id=str(funnel.client_id), platform="meta")
    profile_dict = _profile_dict(profile_record, platform="meta", client_id=str(funnel.client_id))
    verified_domain = _resolve_funnel_verified_domain(
        session=session,
        auth=auth,
        funnel=funnel,
        profile=profile_dict,
        requested_verified_domain=payload.verifiedDomain,
    )

    try:
        dns_record = namecheap_dns_service.upsert_txt_record(
            hostname=verified_domain,
            value=payload.txtValue,
            ttl=300,
        )
    except namecheap_dns_service.NamecheapDnsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    metadata = _profile_metadata_dict(profile_dict)
    existing_meta_domain_verification = _meta_domain_verification_metadata(profile_dict)
    metadata[_META_DOMAIN_VERIFICATION_METADATA_KEY] = {
        **existing_meta_domain_verification,
        "status": "dns_record_written",
        "provider": dns_record["provider"],
        "recordType": dns_record["recordType"],
        "host": dns_record["host"],
        "domain": dns_record["domain"],
        "fqdn": dns_record["fqdn"],
        "value": dns_record["value"],
        "ttl": dns_record["ttl"],
        "metaConfirmationRequired": True,
        "funnelIds": _merge_string_list(existing_meta_domain_verification.get("funnelIds"), [str(funnel.id)]),
        "provisionedAt": existing_meta_domain_verification.get("provisionedAt") or datetime.now(timezone.utc).isoformat(),
        "lastSyncedAt": datetime.now(timezone.utc).isoformat(),
        "source": "paid_ads_qa_meta_domain_verification",
    }
    profile_dict["rulesetVersion"] = RULESET_VERSION
    profile_dict["verifiedDomain"] = verified_domain
    if normalize_tracking_provider(profile_dict.get("verifiedDomainStatus")) != "verified":
        profile_dict["verifiedDomainStatus"] = "pending"
    profile_dict["metadata"] = metadata

    saved_profile = repo.upsert_platform_profile(
        org_id=auth.org_id,
        client_id=str(funnel.client_id),
        **_profile_input_from_dict(profile_dict, platform="meta"),
    )
    return PaidAdsMetaDomainVerificationProvisionResponse(
        funnelId=str(funnel.id),
        campaignId=str(campaign.id),
        clientId=str(funnel.client_id),
        verifiedDomain=str(saved_profile.verified_domain),
        verifiedDomainStatus=saved_profile.verified_domain_status,
        dnsRecord=PaidAdsDnsRecordResponse(
            provider=dns_record["provider"],
            recordType=dns_record["recordType"],
            host=dns_record["host"],
            domain=dns_record["domain"],
            fqdn=dns_record["fqdn"],
            value=dns_record["value"],
            ttl=int(dns_record["ttl"]),
            status=dns_record["status"],
        ),
        profile=PaidAdsPlatformProfileResponse(**_to_profile_payload(saved_profile)),
    )


@router.post(
    "/funnels/{funnel_id}/paid-ads-qa/meta-tracking/repair",
    response_model=PaidAdsMetaTrackingRepairResponse,
)
def repair_funnel_meta_tracking(
    funnel_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    funnel = _get_funnel_or_404(session=session, org_id=auth.org_id, funnel_id=funnel_id)
    campaign = _get_funnel_campaign_or_404(session=session, org_id=auth.org_id, funnel=funnel)
    if not _campaign_uses_meta_channel(campaign.channels):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta tracking repair requires the funnel's campaign to target a Meta channel.",
        )

    repo = PaidAdsQaRepository(session)
    profile_record = repo.get_platform_profile(org_id=auth.org_id, client_id=str(funnel.client_id), platform="meta")
    profile_dict = _profile_dict(profile_record, platform="meta", client_id=str(funnel.client_id))
    try:
        configured_profile = activate_mos_meta_funnel_tracking_profile(
            profile=profile_dict,
            funnel_ids=[str(funnel.id)],
            ruleset_version=RULESET_VERSION,
        )
    except MetaProfileRefreshError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    saved_profile = repo.upsert_platform_profile(
        org_id=auth.org_id,
        client_id=str(funnel.client_id),
        **_profile_input_from_dict(configured_profile, platform="meta"),
    )
    return PaidAdsMetaTrackingRepairResponse(
        funnelId=str(funnel.id),
        campaignId=str(campaign.id),
        clientId=str(funnel.client_id),
        profile=PaidAdsPlatformProfileResponse(**_to_profile_payload(saved_profile)),
    )


@router.post("/campaigns/{campaign_id}/paid-ads-qa/runs", response_model=PaidAdsQaRunResponse)
def run_campaign_paid_ads_qa(
    campaign_id: str,
    payload: PaidAdsQaRunRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    normalized_platform = normalize_platform(payload.platform)
    _require_supported_ruleset(payload.rulesetVersion)
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
    review_base_url = _resolve_review_base_url(
        session=session,
        auth=auth,
        client_id=str(campaign.client_id),
        requested_review_base_url=clean_optional_text(payload.reviewBaseUrl),
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
    brief_map = load_campaign_asset_brief_map(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=str(campaign.id),
        session=session,
    )
    generation_funnel_ids = collect_asset_funnel_ids(assets=ready_assets, brief_map=brief_map)
    requested_funnel_id = clean_optional_text(payload.funnelId)
    if requested_funnel_id is None and len(generation_funnel_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Meta QA requires an explicit funnel when the selected generation spans multiple funnels.",
                "generationKey": selected_generation_key,
                "availableFunnelIds": sorted(generation_funnel_ids),
            },
        )
    if requested_funnel_id and generation_funnel_ids and requested_funnel_id not in generation_funnel_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "The requested funnel has no generated assets in the selected Meta QA generation.",
                "generationKey": selected_generation_key,
                "requestedFunnelId": requested_funnel_id,
                "availableFunnelIds": sorted(generation_funnel_ids),
            },
        )
    resolved_funnel_id = requested_funnel_id
    if resolved_funnel_id is None and len(generation_funnel_ids) == 1:
        resolved_funnel_id = next(iter(generation_funnel_ids))
    if resolved_funnel_id:
        ready_assets = [
            asset
            for asset in ready_assets
            if asset_funnel_id_from_briefs(asset, brief_map=brief_map) == resolved_funnel_id
        ]
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
        review_base_url=review_base_url,
        ruleset_version=RULESET_VERSION,
    )
    assessment["metadata"]["generationKey"] = selected_generation_key
    assessment["metadata"]["requestedGenerationKey"] = clean_optional_text(payload.generationKey)
    assessment["metadata"]["generationAssetIds"] = sorted(ready_asset_ids)
    assessment["metadata"]["funnelId"] = resolved_funnel_id
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
