from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


class ClientPosthogSettingsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    enabled: bool = False
    project_api_key: str | None = Field(
        default=None,
        validation_alias="projectApiKey",
        serialization_alias="projectApiKey",
    )
    api_host: str | None = Field(
        default=None,
        validation_alias="apiHost",
        serialization_alias="apiHost",
    )
    ui_host: str | None = Field(
        default=None,
        validation_alias="uiHost",
        serialization_alias="uiHost",
    )
    defaults: str | None = None
    person_profiles: Literal["identified_only", "always"] | None = Field(
        default=None,
        validation_alias="personProfiles",
        serialization_alias="personProfiles",
    )
    source_mode: Literal["structured", "snippet"] = Field(
        default="structured",
        validation_alias="sourceMode",
        serialization_alias="sourceMode",
    )
    source_snippet: str | None = Field(
        default=None,
        validation_alias="sourceSnippet",
        serialization_alias="sourceSnippet",
    )

    @field_validator(
        "project_api_key",
        "api_host",
        "ui_host",
        "defaults",
        "source_snippet",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str | None:
        return _clean_optional_text(value)


class ClientPosthogSnippetParseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    snippet: str

    @field_validator("snippet", mode="before")
    @classmethod
    def _normalize_snippet(cls, value: object) -> str:
        cleaned = _clean_optional_text(value)
        if not cleaned:
            raise ValueError("snippet is required.")
        return cleaned


class ClientPosthogSettingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    has_settings: bool = Field(
        default=False,
        validation_alias="hasSettings",
        serialization_alias="hasSettings",
    )
    enabled: bool = False
    project_api_key: str | None = Field(
        default=None,
        validation_alias="projectApiKey",
        serialization_alias="projectApiKey",
    )
    api_host: str | None = Field(
        default=None,
        validation_alias="apiHost",
        serialization_alias="apiHost",
    )
    ui_host: str | None = Field(
        default=None,
        validation_alias="uiHost",
        serialization_alias="uiHost",
    )
    defaults: str | None = None
    person_profiles: Literal["identified_only", "always"] = Field(
        default="identified_only",
        validation_alias="personProfiles",
        serialization_alias="personProfiles",
    )
    source_mode: Literal["structured", "snippet"] = Field(
        default="structured",
        validation_alias="sourceMode",
        serialization_alias="sourceMode",
    )
    source_snippet: str | None = Field(
        default=None,
        validation_alias="sourceSnippet",
        serialization_alias="sourceSnippet",
    )
    resolved_tracking: dict[str, Any] | None = Field(
        default=None,
        validation_alias="resolvedTracking",
        serialization_alias="resolvedTracking",
    )
    created_at: datetime | None = Field(
        default=None,
        validation_alias="createdAt",
        serialization_alias="createdAt",
    )
    updated_at: datetime | None = Field(
        default=None,
        validation_alias="updatedAt",
        serialization_alias="updatedAt",
    )
