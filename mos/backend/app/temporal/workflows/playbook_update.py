from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.playbook_activities import update_playbook_from_reports_activity


@dataclass
class PlaybookUpdateInput:
    org_id: str
    client_id: Optional[str] = None
    vertical_key: Optional[str] = None


@workflow.defn
class PlaybookUpdateWorkflow:
    def __init__(self) -> None:
        self._run_now = False

    @workflow.signal
    def run_now(self) -> None:
        self._run_now = True

    @workflow.run
    async def run(self, input: PlaybookUpdateInput) -> None:
        await workflow.wait_condition(lambda: self._run_now)
        await workflow.execute_activity(
            update_playbook_from_reports_activity,
            {"org_id": input.org_id, "client_id": input.client_id, "vertical_key": input.vertical_key},
            schedule_to_close_timeout=timedelta(minutes=5),
        )
