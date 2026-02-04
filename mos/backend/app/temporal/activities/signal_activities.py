from __future__ import annotations

from typing import Any, Dict

from temporalio import activity


@activity.defn
def ensure_experiment_configured_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"configured": True, "experiment_ids": params.get("experiment_ids", [])}


@activity.defn
def fetch_experiment_results_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"all_experiments_ready": True, "results": []}


@activity.defn
def build_experiment_report_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"report": {"summary": "Placeholder experiment report"}}
