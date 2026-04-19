from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Client, MetaAdAccountConnection, MetaWorkspaceAdConfig
from app.db.repositories.meta_account_configs import MetaAccountConfigsRepository
from app.services.integration_secrets import IntegrationSecretError, decrypt_secret_json, encrypt_secret_json
from app.services.meta_ads import MetaAdsClient
from app.services.paid_ads_qa import clean_optional_text


class MetaWorkspaceConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedMetaWorkspaceConfig:
    connection: MetaAdAccountConnection
    workspace_config: MetaWorkspaceAdConfig


def normalize_meta_tracking_ids(
    *,
    pixel_id: str | None,
    data_set_id: str | None,
) -> tuple[str | None, str | None]:
    normalized_pixel_id = clean_optional_text(pixel_id)
    normalized_data_set_id = clean_optional_text(data_set_id)
    if normalized_pixel_id and not normalized_data_set_id:
        normalized_data_set_id = normalized_pixel_id
    elif normalized_data_set_id and not normalized_pixel_id:
        normalized_pixel_id = normalized_data_set_id
    return normalized_pixel_id, normalized_data_set_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _connection_access_token(connection: MetaAdAccountConnection) -> str:
    credentials = decrypt_secret_json(connection.credentials_encrypted)
    access_token = clean_optional_text(credentials.get("accessToken")) if isinstance(credentials, dict) else None
    if not access_token:
        raise MetaWorkspaceConfigError(
            f"Meta connection '{connection.name}' is missing an access token. Update the connection credentials."
        )
    return access_token


def meta_ads_client_for_connection(connection: MetaAdAccountConnection) -> MetaAdsClient:
    return MetaAdsClient(
        access_token=_connection_access_token(connection),
        api_version=connection.graph_api_version,
        base_url=connection.graph_api_base_url,
    )


def resolve_ad_account_id_for_context(
    *,
    resolved: ResolvedMetaWorkspaceConfig,
    explicit_ad_account_id: str | None = None,
) -> str:
    context_ad_account_id = clean_optional_text(resolved.connection.ad_account_id)
    requested_ad_account_id = clean_optional_text(explicit_ad_account_id)
    if requested_ad_account_id and context_ad_account_id and requested_ad_account_id != context_ad_account_id:
        raise MetaWorkspaceConfigError(
            "Requested adAccountId does not match the selected Meta workspace config."
        )
    resolved_ad_account_id = requested_ad_account_id or context_ad_account_id
    if not resolved_ad_account_id:
        raise MetaWorkspaceConfigError("adAccountId is required.")
    return resolved_ad_account_id


def merge_meta_profile(
    *,
    connection: MetaAdAccountConnection,
    workspace_config: MetaWorkspaceAdConfig,
) -> dict[str, Any]:
    pixel_id, data_set_id = normalize_meta_tracking_ids(
        pixel_id=workspace_config.pixel_id,
        data_set_id=workspace_config.data_set_id,
    )
    metadata = dict(workspace_config.metadata_json) if isinstance(workspace_config.metadata_json, dict) else {}
    connection_metadata = (
        dict(connection.metadata_json) if isinstance(connection.metadata_json, dict) else {}
    )
    if connection_metadata:
        metadata.setdefault("metaConnection", connection_metadata)
    return {
        "configId": str(workspace_config.id),
        "connectionId": str(connection.id),
        "connectionName": connection.name,
        "clientId": str(workspace_config.client_id),
        "platform": "meta",
        "rulesetVersion": metadata.get("rulesetVersion") or "paid_ads_policy_ruleset_v2",
        "businessManagerId": connection.business_manager_id,
        "businessManagerName": connection.business_manager_name,
        "pageId": workspace_config.page_id,
        "pageName": workspace_config.page_name,
        "adAccountId": connection.ad_account_id,
        "adAccountName": connection.ad_account_name,
        "paymentMethodType": clean_optional_text(connection_metadata.get("paymentMethodType"))
        if isinstance(connection_metadata, dict)
        else None,
        "paymentMethodStatus": clean_optional_text(connection_metadata.get("paymentMethodStatus"))
        if isinstance(connection_metadata, dict)
        else None,
        "pixelId": pixel_id,
        "dataSetId": data_set_id,
        "dataSetShopifyPartnerInstalled": connection_metadata.get("dataSetShopifyPartnerInstalled")
        if isinstance(connection_metadata, dict)
        else None,
        "dataSetDataSharingLevel": clean_optional_text(connection_metadata.get("dataSetDataSharingLevel"))
        if isinstance(connection_metadata, dict)
        else None,
        "dataSetAssignedToAdAccount": connection_metadata.get("dataSetAssignedToAdAccount")
        if isinstance(connection_metadata, dict)
        else None,
        "verifiedDomain": workspace_config.verified_domain,
        "verifiedDomainStatus": workspace_config.verified_domain_status,
        "attributionClickWindow": workspace_config.attribution_click_window,
        "attributionViewWindow": workspace_config.attribution_view_window,
        "viewThroughEnabled": workspace_config.view_through_enabled,
        "trackingProvider": workspace_config.tracking_provider,
        "trackingUrlParameters": workspace_config.tracking_url_parameters,
        "metadata": metadata,
        "createdAt": workspace_config.created_at.isoformat(),
        "updatedAt": workspace_config.updated_at.isoformat(),
    }


def resolve_workspace_config(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    config_id: str | None = None,
) -> ResolvedMetaWorkspaceConfig:
    repo = MetaAccountConfigsRepository(session)
    if config_id:
        workspace_config = repo.get_workspace_config(org_id=org_id, client_id=client_id, config_id=config_id)
        if workspace_config is None or workspace_config.status == "archived":
            raise MetaWorkspaceConfigError("Meta workspace config not found.")
    else:
        workspace_config = repo.get_default_workspace_config(org_id=org_id, client_id=client_id)
        if workspace_config is None:
            raise MetaWorkspaceConfigError(
                "No active Meta ad config is selected for this workspace. Attach or select one first."
            )
    connection = repo.get_connection(org_id=org_id, connection_id=str(workspace_config.meta_connection_id))
    if connection is None or connection.status == "archived":
        raise MetaWorkspaceConfigError("The selected Meta ad connection no longer exists.")
    return ResolvedMetaWorkspaceConfig(connection=connection, workspace_config=workspace_config)


def resolve_workspace_config_for_client_or_config(
    *,
    session: Session,
    org_id: str,
    client_id: str | None = None,
    config_id: str | None = None,
) -> ResolvedMetaWorkspaceConfig:
    resolved_client_id = clean_optional_text(client_id)
    resolved_config_id = clean_optional_text(config_id)
    if not resolved_client_id and not resolved_config_id:
        raise MetaWorkspaceConfigError("clientId or metaConfigId is required.")

    repo = MetaAccountConfigsRepository(session)
    if resolved_config_id and not resolved_client_id:
        workspace_config = repo.get_workspace_config_by_id(org_id=org_id, config_id=resolved_config_id)
        if workspace_config is None:
            raise MetaWorkspaceConfigError("Meta workspace config not found.")
        resolved_client_id = str(workspace_config.client_id)

    assert resolved_client_id is not None
    return resolve_workspace_config(
        session=session,
        org_id=org_id,
        client_id=resolved_client_id,
        config_id=resolved_config_id,
    )


def update_connection_credentials(
    *,
    repo: MetaAccountConfigsRepository,
    connection: MetaAdAccountConnection,
    access_token: str,
    token_expires_at: datetime | None = None,
) -> MetaAdAccountConnection:
    return repo.update_connection(
        connection,
        credentials_encrypted=encrypt_secret_json({"accessToken": access_token}),
        credentials_last_updated_at=_utcnow(),
        token_expires_at=token_expires_at,
    )


def touch_workspace_default(
    *,
    repo: MetaAccountConfigsRepository,
    workspace_config: MetaWorkspaceAdConfig,
    is_default: bool,
) -> MetaWorkspaceAdConfig:
    if is_default:
        repo.clear_default_workspace_config(
            org_id=str(workspace_config.org_id),
            client_id=str(workspace_config.client_id),
        )
    return repo.update_workspace_config(workspace_config, is_default=is_default)


def connection_usage_rows(
    *,
    session: Session,
    org_id: str,
    connection_id: str,
) -> list[tuple[MetaWorkspaceAdConfig, Client]]:
    rows = (
        session.query(MetaWorkspaceAdConfig, Client)
        .join(Client, Client.id == MetaWorkspaceAdConfig.client_id)
        .filter(
            MetaWorkspaceAdConfig.org_id == org_id,
            MetaWorkspaceAdConfig.meta_connection_id == connection_id,
            MetaWorkspaceAdConfig.status != "archived",
        )
        .order_by(Client.name.asc(), MetaWorkspaceAdConfig.name.asc())
        .all()
    )
    return [(config, client) for config, client in rows]
