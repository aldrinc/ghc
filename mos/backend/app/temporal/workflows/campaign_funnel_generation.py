from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.campaign_intent_activities import create_funnels_from_experiments_activity
    from app.temporal.activities.experiment_activities import (
        fetch_experiment_specs_activity,
        create_asset_briefs_for_experiments_activity,
    )


DEFAULT_FUNNEL_PAGES = [
    {"template_id": "pre-sales-listicle", "name": "Pre-Sales", "slug": "pre-sales"},
    {"template_id": "sales-pdp", "name": "Sales", "slug": "sales"},
]


def _normalize_variant_selection(
    *,
    selected_experiment_ids: List[str],
    variant_ids_by_experiment: Optional[Dict[str, List[str]]],
) -> Dict[str, set[str]]:
    selected_set = set(selected_experiment_ids)
    selection_map: Dict[str, set[str]] = {}
    if not variant_ids_by_experiment:
        return selection_map

    for experiment_id, variant_ids in variant_ids_by_experiment.items():
        if experiment_id not in selected_set:
            raise RuntimeError(
                f"variant_ids_by_experiment includes experiment {experiment_id!r} "
                "which is not in selected experiment_ids."
            )
        if not isinstance(variant_ids, list) or not variant_ids:
            raise RuntimeError(
                f"variant_ids_by_experiment[{experiment_id!r}] must include at least one variant id."
            )
        normalized: set[str] = set()
        for variant_id in variant_ids:
            if not isinstance(variant_id, str) or not variant_id.strip():
                raise RuntimeError(
                    f"variant_ids_by_experiment[{experiment_id!r}] must contain non-empty variant ids."
                )
            normalized.add(variant_id.strip())
        if not normalized:
            raise RuntimeError(
                f"variant_ids_by_experiment[{experiment_id!r}] must include at least one variant id."
            )
        selection_map[experiment_id] = normalized

    return selection_map


def _filter_experiment_specs(
    *,
    selected_experiment_ids: List[str],
    experiment_specs: List[Dict[str, Any]],
    variant_ids_by_experiment: Optional[Dict[str, List[str]]],
) -> List[Dict[str, Any]]:
    if not experiment_specs:
        raise RuntimeError("No experiment specs available for funnel generation.")

    by_id: Dict[str, Dict[str, Any]] = {}
    for spec in experiment_specs:
        if not isinstance(spec, dict):
            raise RuntimeError("Experiment specs must be objects.")
        experiment_id = spec.get("id")
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise RuntimeError("Experiment spec missing id.")
        by_id[experiment_id] = spec

    selection_map = _normalize_variant_selection(
        selected_experiment_ids=selected_experiment_ids,
        variant_ids_by_experiment=variant_ids_by_experiment,
    )

    filtered_specs: List[Dict[str, Any]] = []
    for experiment_id in selected_experiment_ids:
        spec = by_id.get(experiment_id)
        if not spec:
            raise RuntimeError(f"Selected experiment id not found in experiment specs: {experiment_id}")
        variants = spec.get("variants")
        if not isinstance(variants, list) or not variants:
            raise RuntimeError(f"Experiment {experiment_id} has no variants.")

        parsed_variants: List[Dict[str, Any]] = []
        available_variant_ids: set[str] = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise RuntimeError(f"Variant spec for experiment {experiment_id} must be an object.")
            variant_id = variant.get("id")
            if not isinstance(variant_id, str) or not variant_id.strip():
                raise RuntimeError(f"Variant missing id for experiment {experiment_id}.")
            available_variant_ids.add(variant_id)
            parsed_variants.append(variant)

        selected_variant_ids = selection_map.get(experiment_id)
        if selected_variant_ids is None:
            kept_variants = parsed_variants
        else:
            missing_variant_ids = sorted(selected_variant_ids.difference(available_variant_ids))
            if missing_variant_ids:
                raise RuntimeError(
                    "Selected variants were not found for experiment "
                    f"{experiment_id}: {', '.join(missing_variant_ids)}"
                )
            kept_variants = [
                variant for variant in parsed_variants if str(variant.get("id")) in selected_variant_ids
            ]
            if not kept_variants:
                raise RuntimeError(
                    f"No variants selected for experiment {experiment_id}. Select at least one variant."
                )

        filtered_specs.append(
            {
                **spec,
                "variants": kept_variants,
            }
        )

    return filtered_specs


@dataclass
class CampaignFunnelGenerationInput:
    org_id: str
    client_id: str
    product_id: str
    campaign_id: str
    experiment_ids: List[str]
    variant_ids_by_experiment: Optional[Dict[str, List[str]]] = None
    funnel_name_prefix: Optional[str] = None
    generate_testimonials: bool = False


@workflow.defn
class CampaignFunnelGenerationWorkflow:
    @workflow.run
    async def run(self, input: CampaignFunnelGenerationInput) -> Dict[str, Any]:
        if not input.experiment_ids:
            raise RuntimeError("experiment_ids are required to generate funnels.")

        specs_result = await workflow.execute_activity(
            fetch_experiment_specs_activity,
            {
                "org_id": input.org_id,
                "campaign_id": input.campaign_id,
                "experiment_ids": input.experiment_ids,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
        )
        raw_experiment_specs = specs_result.get("experiment_specs") if isinstance(specs_result, dict) else []
        experiment_specs = _filter_experiment_specs(
            selected_experiment_ids=input.experiment_ids,
            experiment_specs=raw_experiment_specs,
            variant_ids_by_experiment=input.variant_ids_by_experiment,
        )

        # This activity generates N funnels (each with multiple pages, images, and optionally testimonials).
        # The runtime scales with the number of variants, so size the timeout accordingly.
        funnel_count = 0
        for exp in experiment_specs:
            if not isinstance(exp, dict):
                continue
            variants = exp.get("variants") or []
            if isinstance(variants, list):
                funnel_count += len(variants)
        if funnel_count < 1:
            raise RuntimeError("No experiment variants available for funnel generation.")

        per_variant_timeout = max(timedelta(minutes=45), timedelta(minutes=15))
        funnel_items: list[dict[str, Any]] = []
        non_fatal_errors: list[dict[str, Any]] = []
        for experiment in experiment_specs:
            variants = experiment.get("variants") or []
            for variant in variants:
                per_variant_spec = {**experiment, "variants": [variant]}
                batch_result = await workflow.execute_activity(
                    create_funnels_from_experiments_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": input.campaign_id,
                        "experiment_specs": [per_variant_spec],
                        "pages": DEFAULT_FUNNEL_PAGES,
                        "funnel_name_prefix": input.funnel_name_prefix or "Funnel",
                        "idea_workspace_id": workflow.info().workflow_id,
                        "actor_user_id": "workflow",
                        "generate_ai_drafts": True,
                        "generate_testimonials": bool(input.generate_testimonials),
                        "temporal_workflow_id": workflow.info().workflow_id,
                        "temporal_run_id": workflow.info().run_id,
                    },
                    schedule_to_close_timeout=per_variant_timeout,
                )
                if not isinstance(batch_result, dict):
                    raise RuntimeError("Funnel generation activity returned an invalid result payload.")
                result_items = batch_result.get("funnels") or []
                if isinstance(result_items, list):
                    for item in result_items:
                        if isinstance(item, dict):
                            funnel_items.append(item)
                result_non_fatal_errors = batch_result.get("non_fatal_errors") or []
                if isinstance(result_non_fatal_errors, list):
                    for entry in result_non_fatal_errors:
                        if isinstance(entry, dict):
                            non_fatal_errors.append(entry)

        funnel_batch = {
            "funnels": funnel_items,
            "non_fatal_errors": non_fatal_errors,
        }

        funnel_map: Dict[str, str] = {}
        if isinstance(funnel_batch, dict):
            batch_items = funnel_batch.get("funnels") or []
            if isinstance(batch_items, list):
                for item in batch_items:
                    if not isinstance(item, dict):
                        continue
                    funnel_payload = item.get("funnel")
                    if not isinstance(funnel_payload, dict):
                        continue
                    funnel_id = funnel_payload.get("funnel_id")
                    experiment_id = item.get("experiment_id")
                    variant_id = item.get("variant_id")
                    if funnel_id and experiment_id and variant_id:
                        funnel_map[f"{experiment_id}:{variant_id}"] = funnel_id

        briefs_result = await workflow.execute_activity(
            create_asset_briefs_for_experiments_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "experiment_specs": experiment_specs,
                "idea_workspace_id": workflow.info().workflow_id,
                "funnel_map": funnel_map,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
        )

        return {
            "campaign_id": input.campaign_id,
            "funnels": funnel_batch,
            "asset_briefs": briefs_result,
        }
