from __future__ import annotations

from typing import Any, Dict, List

from temporalio import activity


@activity.defn
def run_brand_qa_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    assets: List[Dict[str, Any]] = params.get("assets", [])
    return {"results": [{"asset": idx, "passed": True} for idx, _ in enumerate(assets)]}


@activity.defn
def run_compliance_qa_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    assets: List[Dict[str, Any]] = params.get("assets", [])
    return {"results": [{"asset": idx, "passed": True} for idx, _ in enumerate(assets)]}
