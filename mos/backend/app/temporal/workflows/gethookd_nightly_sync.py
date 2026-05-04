"""
GetHookd Nightly Sync Workflow.

This workflow runs nightly to sync GetHookd Explore ads for each workspace
that has valid credentials and at least one enabled feed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.gethookd_sync_activities import (
        GetHookdSyncActivityInput,
        gethookd_sync_workspace_activity,
    )

logger = logging.getLogger(__name__)


@dataclass
class GetHookdNightlySyncInput:
    """Input for the nightly sync workflow."""

    org_id: str
    client_id: str


@dataclass
class GetHookdNightlySyncOutput:
    """Output from the nightly sync workflow."""

    status: str
    feeds_attempted: int
    feeds_succeeded: int
    assets_new: int
    assets_updated: int
    assets_marked_stale: int
    assets_failed: int
    credits_used: float
    error_summary: Optional[str] = None


@workflow.defn
class GetHookdNightlySyncWorkflow:
    """Nightly workflow to sync GetHookd ads for a workspace."""

    @workflow.run
    async def run(self, input: GetHookdNightlySyncInput) -> GetHookdNightlySyncOutput:
        """
        Run the nightly sync for a specific workspace.

        This workflow:
        1. Loads the workspace GetHookd credential
        2. Loads enabled sync feeds
        3. For each feed, calls the sync activity
        4. Returns aggregated results
        """
        logger.info(
            "gethookd_nightly_sync.started",
            extra={
                "org_id": input.org_id,
                "client_id": input.client_id,
            },
        )

        try:
            # Call the activity to do the actual sync work
            result = await workflow.execute_activity(
                gethookd_sync_workspace_activity,
                GetHookdSyncActivityInput(
                    org_id=input.org_id,
                    client_id=input.client_id,
                ),
                start_to_close_timeout=3600,  # 1 hour timeout
                retry_policy=RetryPolicy(
                    maximum_attempts=1,  # No retry for the whole workflow
                ),
            )

            logger.info(
                "gethookd_nightly_sync.completed",
                extra={
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "result": result,
                },
            )

            return result

        except Exception as exc:
            logger.exception(
                "gethookd_nightly_sync.failed",
                extra={
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "error": str(exc),
                },
            )
            return GetHookdNightlySyncOutput(
                status="failed",
                feeds_attempted=0,
                feeds_succeeded=0,
                assets_new=0,
                assets_updated=0,
                assets_marked_stale=0,
                assets_failed=0,
                credits_used=0,
                error_summary=str(exc)[:1000],
            )
