from __future__ import annotations

from typing import Any, Dict

from temporalio import activity


@activity.defn
def update_playbook_from_reports_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "updated"}
