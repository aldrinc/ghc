from __future__ import annotations

from html import escape
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ClientComplianceProfile, ClientUserPreference
from app.db.repositories.client_compliance_profiles import ClientComplianceProfilesRepository
from app.db.repositories.clients import ClientsRepository
from app.schemas.compliance import (
    ClientComplianceProfileResponse,
    ClientComplianceProfileUpsertRequest,
    ClientComplianceRequirementsResponse,
    ComplianceShopifyPolicySyncPageResponse,
    ComplianceShopifyPolicySyncRequest,
    ComplianceShopifyPolicySyncResponse,
    CompliancePolicyTemplateResponse,
    ComplianceRulesetResponse,
    ComplianceRulesetSummaryResponse,
)
from app.services.compliance import (
    RULESET_VERSION,
    build_page_requirements,
    get_policy_page_handle,
    get_profile_url_field_for_page_key,
    get_policy_template,
    get_ruleset,
    list_policy_templates,
    list_policy_page_keys,
    list_rulesets,
    normalize_business_models,
    render_policy_template_markdown,
)
from app.services.shopify_connection import upsert_client_shopify_policy_pages


router = APIRouter(tags=["compliance"])


def _ensure_client_exists(*, session: Session, org_id: str, client_id: str) -> None:
    client = ClientsRepository(session).get(org_id=org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_optional_url(*, value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be an absolute URL (http/https).",
        )
    return cleaned


def _profile_to_response(profile: ClientComplianceProfile) -> ClientComplianceProfileResponse:
    return ClientComplianceProfileResponse(
        id=str(profile.id),
        orgId=str(profile.org_id),
        clientId=str(profile.client_id),
        rulesetVersion=profile.ruleset_version,
        businessModels=profile.business_models,
        legalBusinessName=profile.legal_business_name,
        operatingEntityName=profile.operating_entity_name,
        companyAddressText=profile.company_address_text,
        businessLicenseIdentifier=profile.business_license_identifier,
        supportEmail=profile.support_email,
        supportPhone=profile.support_phone,
        supportHoursText=profile.support_hours_text,
        responseTimeCommitment=profile.response_time_commitment,
        privacyPolicyUrl=profile.privacy_policy_url,
        termsOfServiceUrl=profile.terms_of_service_url,
        returnsRefundsPolicyUrl=profile.returns_refunds_policy_url,
        shippingPolicyUrl=profile.shipping_policy_url,
        contactSupportUrl=profile.contact_support_url,
        companyInformationUrl=profile.company_information_url,
        subscriptionTermsAndCancellationUrl=profile.subscription_terms_and_cancellation_url,
        metadata=profile.metadata_json,
        createdAt=profile.created_at.isoformat(),
        updatedAt=profile.updated_at.isoformat(),
    )


def _profile_page_urls(profile: ClientComplianceProfile) -> dict[str, str | None]:
    return {
        "privacy_policy": profile.privacy_policy_url,
        "terms_of_service": profile.terms_of_service_url,
        "returns_refunds_policy": profile.returns_refunds_policy_url,
        "shipping_policy": profile.shipping_policy_url,
        "contact_support": profile.contact_support_url,
        "company_information": profile.company_information_url,
        "subscription_terms_and_cancellation": profile.subscription_terms_and_cancellation_url,
    }


def _get_selected_shop_domain(*, session: Session, org_id: str, client_id: str, user_external_id: str) -> str | None:
    pref = session.scalar(
        select(ClientUserPreference).where(
            ClientUserPreference.org_id == org_id,
            ClientUserPreference.client_id == client_id,
            ClientUserPreference.user_external_id == user_external_id,
        )
    )
    if not pref:
        return None
    selected = getattr(pref, "selected_shop_domain", None)
    if not isinstance(selected, str) or not selected.strip():
        return None
    return selected.strip().lower()


def _profile_placeholder_values(profile: ClientComplianceProfile) -> dict[str, str]:
    values: dict[str, str] = {}
    scalar_fields = {
        "legal_business_name": profile.legal_business_name,
        "operating_entity_name": profile.operating_entity_name,
        "company_address_text": profile.company_address_text,
        "business_license_identifier": profile.business_license_identifier,
        "support_email": profile.support_email,
        "support_phone": profile.support_phone,
        "support_hours_text": profile.support_hours_text,
        "response_time_commitment": profile.response_time_commitment,
    }
    for key, value in scalar_fields.items():
        if isinstance(value, str) and value.strip():
            values[key] = value.strip()

    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    for key, raw_value in metadata.items():
        if not isinstance(key, str):
            continue
        placeholder_key = key.strip()
        if not placeholder_key:
            continue
        if raw_value is None:
            continue
        if isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if not cleaned:
                continue
            values[placeholder_key] = cleaned
            continue
        if isinstance(raw_value, (int, float, bool)):
            values[placeholder_key] = str(raw_value)
    return values


def _select_page_keys_for_sync(
    *,
    requested_page_keys: list[str],
    include_strongly_recommended: bool,
    requirements: dict,
) -> list[str]:
    known_page_keys = set(list_policy_page_keys())
    classification_by_page_key = {
        page["pageKey"]: page["classification"]
        for page in requirements["pages"]
    }

    if requested_page_keys:
        selected: list[str] = []
        seen: set[str] = set()
        invalid: list[str] = []
        not_applicable: list[str] = []
        for raw in requested_page_keys:
            page_key = raw.strip()
            if page_key in seen:
                continue
            seen.add(page_key)
            if page_key not in known_page_keys:
                invalid.append(page_key)
                continue
            if classification_by_page_key.get(page_key) == "not_applicable":
                not_applicable.append(page_key)
                continue
            selected.append(page_key)

        if invalid:
            invalid_str = ", ".join(sorted(invalid))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown pageKeys requested for sync: {invalid_str}",
            )
        if not_applicable:
            invalid_str = ", ".join(sorted(not_applicable))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requested pageKeys are not applicable for this client profile: {invalid_str}",
            )
        if not selected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No applicable pageKeys were provided for sync.",
            )
        return selected

    selected_by_ruleset: list[str] = []
    for page in requirements["pages"]:
        classification = page["classification"]
        if classification == "required":
            selected_by_ruleset.append(page["pageKey"])
            continue
        if classification == "strongly_recommended" and include_strongly_recommended:
            selected_by_ruleset.append(page["pageKey"])
    if not selected_by_ruleset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No required or strongly recommended compliance pages are applicable for this profile.",
        )
    return selected_by_ruleset


def _markdown_to_shopify_html(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]
    output: list[str] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        text = " ".join(part.strip() for part in paragraph_lines if part.strip())
        if text:
            output.append(f"<p>{escape(text)}</p>")
        paragraph_lines.clear()

    def flush_list() -> None:
        if not list_items:
            return
        output.append("<ul>")
        output.extend(list_items)
        output.append("</ul>")
        list_items.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue

        if line.startswith("# "):
            flush_paragraph()
            flush_list()
            output.append(f"<h1>{escape(line[2:].strip())}</h1>")
            continue

        if line.startswith("## "):
            flush_paragraph()
            flush_list()
            output.append(f"<h2>{escape(line[3:].strip())}</h2>")
            continue

        if line.startswith("- "):
            flush_paragraph()
            list_items.append(f"<li>{escape(line[2:].strip())}</li>")
            continue

        flush_list()
        paragraph_lines.append(line)

    flush_paragraph()
    flush_list()

    rendered = "\n".join(output).strip()
    if not rendered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rendered policy content is empty and cannot be synced.",
        )
    return rendered


@router.get("/compliance/rulesets", response_model=list[ComplianceRulesetSummaryResponse])
def list_compliance_rulesets(
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    return list_rulesets()


@router.get("/compliance/rulesets/{ruleset_version}", response_model=ComplianceRulesetResponse)
def get_compliance_ruleset(
    ruleset_version: str,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    try:
        return get_ruleset(version=ruleset_version)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/compliance/policy-templates", response_model=list[CompliancePolicyTemplateResponse])
def list_compliance_policy_templates(
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    return list_policy_templates()


@router.get("/compliance/policy-templates/{page_key}", response_model=CompliancePolicyTemplateResponse)
def get_compliance_policy_template(
    page_key: str,
    auth: AuthContext = Depends(get_current_user),
):
    _ = auth
    try:
        return get_policy_template(page_key=page_key)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/clients/{client_id}/compliance/profile", response_model=ClientComplianceProfileResponse)
def get_client_compliance_profile(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _ensure_client_exists(session=session, org_id=auth.org_id, client_id=client_id)
    repo = ClientComplianceProfilesRepository(session)
    profile = repo.get(org_id=auth.org_id, client_id=client_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance profile not found for this client.",
        )
    return _profile_to_response(profile)


@router.put("/clients/{client_id}/compliance/profile", response_model=ClientComplianceProfileResponse)
def upsert_client_compliance_profile(
    client_id: str,
    payload: ClientComplianceProfileUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _ensure_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    if payload.rulesetVersion != RULESET_VERSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported rulesetVersion '{payload.rulesetVersion}'. "
                f"Expected '{RULESET_VERSION}'."
            ),
        )

    try:
        business_models = normalize_business_models(payload.businessModels)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    metadata = payload.metadata or {}
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="metadata must be an object.")

    repo = ClientComplianceProfilesRepository(session)
    profile = repo.upsert(
        org_id=auth.org_id,
        client_id=client_id,
        ruleset_version=payload.rulesetVersion,
        business_models=business_models,
        legal_business_name=_clean_optional_text(payload.legalBusinessName),
        operating_entity_name=_clean_optional_text(payload.operatingEntityName),
        company_address_text=_clean_optional_text(payload.companyAddressText),
        business_license_identifier=_clean_optional_text(payload.businessLicenseIdentifier),
        support_email=_clean_optional_text(payload.supportEmail),
        support_phone=_clean_optional_text(payload.supportPhone),
        support_hours_text=_clean_optional_text(payload.supportHoursText),
        response_time_commitment=_clean_optional_text(payload.responseTimeCommitment),
        privacy_policy_url=_clean_optional_url(value=payload.privacyPolicyUrl, field_name="privacyPolicyUrl"),
        terms_of_service_url=_clean_optional_url(value=payload.termsOfServiceUrl, field_name="termsOfServiceUrl"),
        returns_refunds_policy_url=_clean_optional_url(
            value=payload.returnsRefundsPolicyUrl,
            field_name="returnsRefundsPolicyUrl",
        ),
        shipping_policy_url=_clean_optional_url(value=payload.shippingPolicyUrl, field_name="shippingPolicyUrl"),
        contact_support_url=_clean_optional_url(value=payload.contactSupportUrl, field_name="contactSupportUrl"),
        company_information_url=_clean_optional_url(
            value=payload.companyInformationUrl,
            field_name="companyInformationUrl",
        ),
        subscription_terms_and_cancellation_url=_clean_optional_url(
            value=payload.subscriptionTermsAndCancellationUrl,
            field_name="subscriptionTermsAndCancellationUrl",
        ),
        metadata_json=metadata,
    )
    return _profile_to_response(profile)


@router.get(
    "/clients/{client_id}/compliance/requirements",
    response_model=ClientComplianceRequirementsResponse,
)
def get_client_compliance_requirements(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _ensure_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    repo = ClientComplianceProfilesRepository(session)
    profile = repo.get(org_id=auth.org_id, client_id=client_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance profile not found for this client.",
        )

    requirements = build_page_requirements(
        ruleset_version=profile.ruleset_version,
        business_models=profile.business_models,
        page_urls=_profile_page_urls(profile),
    )
    return ClientComplianceRequirementsResponse(**requirements)


@router.post(
    "/clients/{client_id}/compliance/shopify/policy-pages/sync",
    response_model=ComplianceShopifyPolicySyncResponse,
)
def sync_client_compliance_policy_pages_to_shopify(
    client_id: str,
    payload: ComplianceShopifyPolicySyncRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _ensure_client_exists(session=session, org_id=auth.org_id, client_id=client_id)

    repo = ClientComplianceProfilesRepository(session)
    profile = repo.get(org_id=auth.org_id, client_id=client_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance profile not found for this client.",
        )

    requirements = build_page_requirements(
        ruleset_version=profile.ruleset_version,
        business_models=profile.business_models,
        page_urls=_profile_page_urls(profile),
    )
    page_keys_to_sync = _select_page_keys_for_sync(
        requested_page_keys=payload.pageKeys,
        include_strongly_recommended=payload.includeStronglyRecommended,
        requirements=requirements,
    )

    placeholders = _profile_placeholder_values(profile)
    sync_pages_payload: list[dict[str, str]] = []
    for page_key in page_keys_to_sync:
        template = get_policy_template(page_key=page_key)
        try:
            rendered_markdown = render_policy_template_markdown(
                page_key=page_key,
                placeholder_values=placeholders,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        sync_pages_payload.append(
            {
                "pageKey": page_key,
                "title": template["title"],
                "handle": get_policy_page_handle(page_key=page_key),
                "bodyHtml": _markdown_to_shopify_html(rendered_markdown),
            }
        )

    selected_shop_domain = payload.shopDomain or _get_selected_shop_domain(
        session=session,
        org_id=auth.org_id,
        client_id=client_id,
        user_external_id=auth.user_id,
    )
    sync_payload = upsert_client_shopify_policy_pages(
        client_id=client_id,
        pages=sync_pages_payload,
        shop_domain=selected_shop_domain,
    )

    synced_pages = sync_payload["pages"]
    returned_page_keys = {item["pageKey"] for item in synced_pages}
    expected_page_keys = set(page_keys_to_sync)
    if returned_page_keys != expected_page_keys:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Shopify policy-page sync returned an unexpected page set. "
                f"expected={sorted(expected_page_keys)} got={sorted(returned_page_keys)}"
            ),
        )

    updated_profile_urls: dict[str, str] = {}
    response_pages: list[ComplianceShopifyPolicySyncPageResponse] = []
    for page in synced_pages:
        page_key = page["pageKey"]
        profile_url_field = get_profile_url_field_for_page_key(page_key=page_key)
        setattr(profile, profile_url_field, page["url"])
        updated_profile_urls[profile_url_field] = page["url"]
        response_pages.append(
            ComplianceShopifyPolicySyncPageResponse(
                pageKey=page_key,
                title=page["title"],
                handle=page["handle"],
                pageId=page["pageId"],
                url=page["url"],
                operation=page["operation"],
                profileUrlField=profile_url_field,
            )
        )

    profile.updated_at = func.now()
    session.add(profile)
    session.commit()

    return ComplianceShopifyPolicySyncResponse(
        rulesetVersion=profile.ruleset_version,
        shopDomain=sync_payload["shopDomain"],
        pages=response_pages,
        updatedProfileUrls=updated_profile_urls,
    )
