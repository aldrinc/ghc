from __future__ import annotations

import logging
from dataclasses import dataclass

from temporalio import activity

from app.db.deps import get_session
from app.services.meta_management_service import (
    MetaManagementExecutionError,
    run_meta_management_monitoring_snapshot,
)

logger = logging.getLogger(__name__)


@dataclass
class MetaManagementMonitorActivityInput:
    org_id: str
    campaign_id: str
    date_preset: str = "last_3d"


@dataclass
class MetaManagementMonitorActivityOutput:
    status: str
    reason: str | None = None
    meta_campaign_id: str | None = None
    action_count: int = 0
    row_count: int = 0
    benchmark_available: bool = False
    benchmark_reason_code: str | None = None
    artifact_ids: dict[str, str] | None = None


@activity.defn
async def run_meta_management_monitor_activity(
    input: MetaManagementMonitorActivityInput,
) -> MetaManagementMonitorActivityOutput:
    session = next(get_session())
    try:
        result = run_meta_management_monitoring_snapshot(
            session=session,
            org_id=input.org_id,
            campaign_id=input.campaign_id,
            date_preset=input.date_preset,
        )
        return MetaManagementMonitorActivityOutput(
            status=result.status,
            reason=result.reason,
            meta_campaign_id=result.meta_campaign_id,
            action_count=result.action_count,
            row_count=result.row_count,
            benchmark_available=result.benchmark_available,
            benchmark_reason_code=result.benchmark_reason_code,
            artifact_ids=result.artifact_ids,
        )
    except MetaManagementExecutionError as exc:
        logger.exception(
            "meta_management_monitor.execution_failed",
            extra={
                "org_id": input.org_id,
                "campaign_id": input.campaign_id,
                "detail": exc.detail,
                "status_code": exc.status_code,
            },
        )
        return MetaManagementMonitorActivityOutput(
            status="failed",
            reason=str(exc.detail),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "meta_management_monitor.unexpected_failure",
            extra={
                "org_id": input.org_id,
                "campaign_id": input.campaign_id,
            },
        )
        return MetaManagementMonitorActivityOutput(
            status="failed",
            reason=str(exc),
        )
    finally:
        session.close()
