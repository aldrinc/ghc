"""Pydantic schemas for Postiz integration API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class PostizCredentialsRequest(BaseModel):
    """Request to save Postiz credentials for a workspace."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    base_url: str = Field(validation_alias="baseUrl", serialization_alias="baseUrl")
    api_key: str = Field(validation_alias="apiKey", serialization_alias="apiKey")

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        cleaned = str(value or "").strip().rstrip("/")
        if not cleaned:
            raise ValueError("baseUrl is required.")
        if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
            raise ValueError("baseUrl must be a valid HTTP/HTTPS URL.")
        return cleaned

    @field_validator("api_key")
    @classmethod
    def _validate_api_key(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("apiKey is required.")
        return cleaned


class PostizCredentialsResponse(BaseModel):
    """Response for Postiz credentials."""

    model_config = ConfigDict(populate_by_name=True)

    has_credentials: bool = Field(
        validation_alias="hasCredentials", serialization_alias="hasCredentials"
    )
    base_url: str | None = Field(
        default=None,
        validation_alias="baseUrl",
        serialization_alias="baseUrl",
    )
    auth_type: str | None = Field(
        default=None,
        validation_alias="authType",
        serialization_alias="authType",
    )
    last_validated_at: datetime | None = Field(
        default=None,
        validation_alias="lastValidatedAt",
        serialization_alias="lastValidatedAt",
    )
    last_validation_error: str | None = Field(
        default=None,
        validation_alias="lastValidationError",
        serialization_alias="lastValidationError",
    )


class PostizChannelResponse(BaseModel):
    """Response for a Postiz channel."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    postiz_integration_id: str = Field(
        validation_alias="postizIntegrationId", serialization_alias="postizIntegrationId"
    )
    postiz_channel_id: str = Field(
        validation_alias="postizChannelId", serialization_alias="postizChannelId"
    )
    identifier: str
    name: str
    profile: str | None = Field(default=None)
    picture_url: str | None = Field(
        default=None, validation_alias="pictureUrl", serialization_alias="pictureUrl"
    )
    disabled: bool = False
    is_default: bool = Field(
        default=False, validation_alias="isDefault", serialization_alias="isDefault"
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict, validation_alias="metadata", serialization_alias="metadata"
    )
    last_synced_at: datetime | None = Field(
        default=None, validation_alias="lastSyncedAt", serialization_alias="lastSyncedAt"
    )
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class PostizConnectUrlResponse(BaseModel):
    """Response for channel connect URL."""

    model_config = ConfigDict(populate_by_name=True)

    connect_url: str = Field(validation_alias="connectUrl", serialization_alias="connectUrl")
    integration: str


class PostizConnectUrlRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    integration: str

    @field_validator("integration")
    @classmethod
    def _validate_integration(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("integration is required.")
        return cleaned


class PostizBrowserLaunchResponse(BaseModel):
    """Response for a prepared Postiz browser handoff."""

    model_config = ConfigDict(populate_by_name=True)

    launch_url: str = Field(validation_alias="launchUrl", serialization_alias="launchUrl")
    auto_configured_credentials: bool = Field(
        default=False,
        validation_alias="autoConfiguredCredentials",
        serialization_alias="autoConfiguredCredentials",
    )


class PostizBrowserLaunchRequest(BaseModel):
    """Optional frontend context for a prepared Postiz browser handoff."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    email: EmailStr | None = None


class PostizPostingProfileBase(BaseModel):
    """Base schema for Postiz posting profiles."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    is_default: bool = Field(
        default=False, validation_alias="isDefault", serialization_alias="isDefault"
    )
    default_channel_ids: list[str] = Field(
        default_factory=list,
        validation_alias="defaultChannelIds",
        serialization_alias="defaultChannelIds",
    )
    timezone: str | None = Field(
        default=None, validation_alias="timezone", serialization_alias="timezone"
    )
    short_link: bool = Field(
        default=None, validation_alias="shortLink", serialization_alias="shortLink"
    )
    provider_settings_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="providerSettings",
        serialization_alias="providerSettings",
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("name is required.")
        return cleaned


class PostizPostingProfileCreateRequest(PostizPostingProfileBase):
    """Request to create a Postiz posting profile."""

    pass


class PostizPostingProfileUpdateRequest(BaseModel):
    """Request to update a Postiz posting profile."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str | None = None
    is_default: bool | None = Field(
        default=None, validation_alias="isDefault", serialization_alias="isDefault"
    )
    default_channel_ids: list[str] | None = Field(
        default=None,
        validation_alias="defaultChannelIds",
        serialization_alias="defaultChannelIds",
    )
    timezone: str | None = Field(
        default=None, validation_alias="timezone", serialization_alias="timezone"
    )
    short_link: bool | None = Field(
        default=None, validation_alias="shortLink", serialization_alias="shortLink"
    )
    provider_settings_json: dict[str, Any] | None = Field(
        default=None,
        validation_alias="providerSettings",
        serialization_alias="providerSettings",
    )


class PostizPostingProfileResponse(PostizPostingProfileBase):
    """Response for a Postiz posting profile."""

    id: str
    postiz_posting_profile_id: str | None = Field(
        default=None,
        validation_alias="postizPostingProfileId",
        serialization_alias="postizPostingProfileId",
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict, validation_alias="metadata", serialization_alias="metadata"
    )
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")

    timezone: str | None = Field(
        default=None, validation_alias="timezone", serialization_alias="timezone"
    )
    short_link: bool | None = Field(
        default=None, validation_alias="shortLink", serialization_alias="shortLink"
    )


class PostizCreatePostRequest(BaseModel):
    """Request to create a Postiz post."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    content: str
    post_type: str = Field(
        default="now", validation_alias="postType", serialization_alias="postType"
    )
    scheduled_for: datetime | None = Field(
        default=None, validation_alias="scheduledFor", serialization_alias="scheduledFor"
    )
    channel_ids: list[str] = Field(validation_alias="channelIds", serialization_alias="channelIds")
    media_urls: list[str] = Field(
        default_factory=list, validation_alias="mediaUrls", serialization_alias="mediaUrls"
    )
    link_url: str | None = Field(
        default=None, validation_alias="linkUrl", serialization_alias="linkUrl"
    )
    posting_profile_id: str | None = Field(
        default=None, validation_alias="postingProfileId", serialization_alias="postingProfileId"
    )
    provider_settings_by_identifier: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="providerSettingsByIdentifier",
        serialization_alias="providerSettingsByIdentifier",
    )

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("content is required.")
        return cleaned

    @field_validator("channel_ids")
    @classmethod
    def _validate_channel_ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(item or "").strip() for item in value if str(item or "").strip()]
        if not cleaned:
            raise ValueError("channelIds must contain at least one channel id.")
        return cleaned

    @field_validator("post_type")
    @classmethod
    def _validate_post_type(cls, value: str) -> str:
        cleaned = str(value or "").strip().lower()
        if cleaned not in ("now", "schedule", "draft"):
            raise ValueError("postType must be one of: now, schedule, draft.")
        return cleaned

    @field_validator("scheduled_for")
    @classmethod
    def _validate_scheduled_for(cls, value: datetime | None, info) -> datetime | None:
        if info.data.get("post_type") == "schedule" and value is None:
            raise ValueError("scheduledFor is required when postType is schedule.")
        return value


class PostizPostResponse(BaseModel):
    """Response for a Postiz post."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    postiz_post_id: str | None = Field(
        default=None,
        validation_alias="postizPostId",
        serialization_alias="postizPostId",
    )
    postiz_post_ids: list[str] = Field(
        default_factory=list,
        validation_alias="postizPostIds",
        serialization_alias="postizPostIds",
    )
    content: str
    post_type: str = Field(validation_alias="postType", serialization_alias="postType")
    scheduled_for: datetime | None = Field(
        default=None, validation_alias="scheduledFor", serialization_alias="scheduledFor"
    )
    target_channels_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="targetChannels",
        serialization_alias="targetChannels",
    )
    media_urls_json: list[str] = Field(
        default_factory=list, validation_alias="mediaUrls", serialization_alias="mediaUrls"
    )
    link_url: str | None = Field(
        default=None, validation_alias="linkUrl", serialization_alias="linkUrl"
    )
    status: str
    postiz_post_status: str | None = Field(
        default=None, validation_alias="postizPostStatus", serialization_alias="postizPostStatus"
    )
    release_urls_json: list[str] = Field(
        default_factory=list, validation_alias="releaseUrls", serialization_alias="releaseUrls"
    )
    error_payload_json: dict[str, Any] | None = Field(
        default=None, validation_alias="errorPayload", serialization_alias="errorPayload"
    )
    last_synced_at: datetime | None = Field(
        default=None, validation_alias="lastSyncedAt", serialization_alias="lastSyncedAt"
    )
    created_at: datetime = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: datetime = Field(validation_alias="updatedAt", serialization_alias="updatedAt")


class PostizPostListResponse(BaseModel):
    """Response for listing Postiz posts."""

    model_config = ConfigDict(populate_by_name=True)

    posts: list[PostizPostResponse]
    total: int


class PostizSyncResponse(BaseModel):
    """Response for Postiz sync operation."""

    model_config = ConfigDict(populate_by_name=True)

    synced_count: int = Field(validation_alias="syncedCount", serialization_alias="syncedCount")
    errors: list[str] = Field(default_factory=list)
