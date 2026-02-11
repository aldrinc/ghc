from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreativeProductionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asset_brief_ids: list[str] = Field(
        ...,
        validation_alias="assetBriefIds",
        serialization_alias="assetBriefIds",
    )

    @field_validator("asset_brief_ids")
    @classmethod
    def _validate_asset_brief_ids(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("assetBriefIds must be a non-empty list.")
        cleaned: list[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("assetBriefIds must contain non-empty strings.")
            cleaned.append(entry.strip())
        # Keep order stable but remove duplicates.
        seen: set[str] = set()
        deduped: list[str] = []
        for entry in cleaned:
            if entry in seen:
                continue
            seen.add(entry)
            deduped.append(entry)
        if not deduped:
            raise ValueError("assetBriefIds must include at least one id.")
        return deduped

