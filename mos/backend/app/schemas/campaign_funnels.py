from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignFunnelPageSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    template_id: str = Field(
        ...,
        validation_alias="templateId",
        serialization_alias="templateId",
    )
    name: str
    slug: str
    next_page_slug: str | None = Field(
        default=None,
        validation_alias="nextPageSlug",
        serialization_alias="nextPageSlug",
    )

    @field_validator("template_id", "name", "slug")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("templateId, name, and slug must be non-empty strings.")
        return value.strip()

    @field_validator("next_page_slug")
    @classmethod
    def _validate_next_page_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("nextPageSlug must be a non-empty string when provided.")
        return cleaned


class CampaignFunnelGenerationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    experiment_ids: List[str] = Field(
        ...,
        validation_alias="experimentIds",
        serialization_alias="experimentIds",
    )
    variant_ids_by_experiment: Dict[str, List[str]] = Field(
        default_factory=dict,
        validation_alias="variantIdsByExperiment",
        serialization_alias="variantIdsByExperiment",
    )
    pages: List[CampaignFunnelPageSpec] | None = None
    async_media_enrichment: bool = Field(
        default=True,
        validation_alias="asyncMediaEnrichment",
        serialization_alias="asyncMediaEnrichment",
    )
    variant_activity_concurrency: int | None = Field(
        default=None,
        validation_alias="variantActivityConcurrency",
        serialization_alias="variantActivityConcurrency",
    )
    generateTestimonials: bool = False

    @field_validator("pages")
    @classmethod
    def _validate_pages(cls, value: List[CampaignFunnelPageSpec] | None) -> List[CampaignFunnelPageSpec] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("pages must include at least one page when provided.")
        seen_slugs: set[str] = set()
        for page in value:
            if page.slug in seen_slugs:
                raise ValueError(f"pages contains duplicate slug '{page.slug}'.")
            seen_slugs.add(page.slug)
        next_slugs = {page.next_page_slug for page in value if page.next_page_slug}
        missing_next_slugs = sorted(next_slugs.difference(seen_slugs))
        if missing_next_slugs:
            raise ValueError(
                "pages contains nextPageSlug values that do not match a page slug: "
                + ", ".join(missing_next_slugs)
            )
        return value

    @field_validator("experiment_ids")
    @classmethod
    def _validate_experiment_ids(cls, value: List[str]) -> List[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("experimentIds must include at least one angle.")
        cleaned: list[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("experimentIds must contain non-empty strings.")
            cleaned.append(entry.strip())
        seen: set[str] = set()
        deduped: list[str] = []
        for entry in cleaned:
            if entry in seen:
                continue
            seen.add(entry)
            deduped.append(entry)
        return deduped

    @field_validator("variant_ids_by_experiment")
    @classmethod
    def _validate_variant_ids_by_experiment(cls, value: Dict[str, List[str]]) -> Dict[str, List[str]]:
        if not isinstance(value, dict):
            raise ValueError("variantIdsByExperiment must be a mapping of experiment id to variant ids.")
        cleaned: dict[str, list[str]] = {}
        for raw_experiment_id, raw_variant_ids in value.items():
            if not isinstance(raw_experiment_id, str) or not raw_experiment_id.strip():
                raise ValueError("variantIdsByExperiment keys must be non-empty experiment ids.")
            experiment_id = raw_experiment_id.strip()
            if not isinstance(raw_variant_ids, list) or not raw_variant_ids:
                raise ValueError(
                    f"variantIdsByExperiment[{experiment_id}] must include at least one variant id."
                )
            normalized_variant_ids: list[str] = []
            for variant_id in raw_variant_ids:
                if not isinstance(variant_id, str) or not variant_id.strip():
                    raise ValueError(
                        f"variantIdsByExperiment[{experiment_id}] must contain non-empty variant ids."
                    )
                normalized_variant_ids.append(variant_id.strip())
            deduped_variant_ids: list[str] = []
            seen_variant_ids: set[str] = set()
            for variant_id in normalized_variant_ids:
                if variant_id in seen_variant_ids:
                    continue
                seen_variant_ids.add(variant_id)
                deduped_variant_ids.append(variant_id)
            cleaned[experiment_id] = deduped_variant_ids
        return cleaned

    @field_validator("variant_activity_concurrency")
    @classmethod
    def _validate_variant_activity_concurrency(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1:
            raise ValueError("variantActivityConcurrency must be >= 1.")
        return value
