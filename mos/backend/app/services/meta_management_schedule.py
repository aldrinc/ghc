from __future__ import annotations

from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec

from app.config import settings
from app.temporal.client import get_temporal_client
from app.temporal.workflows.meta_management_monitor import (
    MetaManagementMonitorInput,
    MetaManagementMonitorWorkflow,
)


def build_meta_management_schedule_id(*, org_id: str, campaign_id: str) -> str:
    return f"meta-management-monitor-{org_id}-{campaign_id}"


async def reconcile_campaign_meta_management_schedule(
    *,
    org_id: str,
    campaign_id: str,
    enabled: bool,
) -> str | None:
    client = await get_temporal_client()
    schedule_id = build_meta_management_schedule_id(org_id=org_id, campaign_id=campaign_id)
    handle = client.get_schedule_handle(schedule_id)

    if not enabled:
        try:
            await handle.delete()
        except Exception:
            pass
        return None

    try:
        await handle.describe()
        await handle.delete()
    except Exception:
        pass

    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            MetaManagementMonitorWorkflow.run,
            MetaManagementMonitorInput(org_id=org_id, campaign_id=campaign_id),
            id=f"{schedule_id}-workflow",
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        ),
        spec=ScheduleSpec(
            cron_expressions=[
                str(getattr(settings, "META_MANAGEMENT_SCHEDULE_CRON", "0 */6 * * *")).strip()
                or "0 */6 * * *"
            ]
        ),
    )
    await client.create_schedule(schedule_id, schedule)
    return schedule_id
