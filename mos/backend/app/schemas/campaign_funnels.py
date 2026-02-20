from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    async_media_enrichment: bool = Field(
        default=True,
        validation_alias="asyncMediaEnrichment",
        serialization_alias="asyncMediaEnrichment",
    )
    generateTestimonials: bool = False

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
