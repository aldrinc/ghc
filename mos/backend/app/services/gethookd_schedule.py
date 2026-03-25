from __future__ import annotations

from temporalio.client import Schedule, ScheduleActionStartWorkflow, ScheduleSpec

from app.config import settings
from app.temporal.client import get_temporal_client
from app.temporal.workflows.gethookd_nightly_sync import (
    GetHookdNightlySyncInput,
    GetHookdNightlySyncWorkflow,
)


def build_gethookd_schedule_id(*, org_id: str, client_id: str) -> str:
    return f"gethookd-nightly-sync-{org_id}-{client_id}"


async def reconcile_client_gethookd_schedule(
    *, org_id: str, client_id: str, has_credentials: bool, enabled_feed_count: int
) -> str | None:
    client = await get_temporal_client()
    schedule_id = build_gethookd_schedule_id(org_id=org_id, client_id=client_id)
    handle = client.get_schedule_handle(schedule_id)
    should_exist = has_credentials and enabled_feed_count > 0

    if not should_exist:
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
            GetHookdNightlySyncWorkflow.run,
            GetHookdNightlySyncInput(org_id=org_id, client_id=client_id),
            id=f"{schedule_id}-workflow",
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        ),
        spec=ScheduleSpec(
            cron_expressions=[
                str(getattr(settings, "GETHOOKD_SYNC_SCHEDULE_CRON", "0 3 * * *")).strip()
                or "0 3 * * *"
            ]
        ),
    )
    await client.create_schedule(schedule_id, schedule)
    return schedule_id
