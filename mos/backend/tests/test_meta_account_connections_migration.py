from __future__ import annotations

import json
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from uuid import uuid4

from sqlalchemy.dialects import postgresql


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0059_meta_account_connections_and_configs.py"
)
_MIGRATION_SPEC = importlib.util.spec_from_file_location(
    "migration_0059_meta_account_connections_and_configs",
    _MIGRATION_PATH,
)
assert _MIGRATION_SPEC is not None and _MIGRATION_SPEC.loader is not None
_MIGRATION = importlib.util.module_from_spec(_MIGRATION_SPEC)
_MIGRATION_SPEC.loader.exec_module(_MIGRATION)


def test_typed_metadata_insert_uses_jsonb_bind() -> None:
    statement = _MIGRATION._typed_metadata_insert(
        "INSERT INTO meta_ad_account_connections (metadata) VALUES (:metadata)"
    )

    metadata_bind = statement._bindparams["metadata"]
    assert isinstance(metadata_bind.type, postgresql.JSONB)


def test_backfill_meta_workspace_configs_uses_typed_metadata_binds(monkeypatch) -> None:
    profile_metadata = {
        "metaGraphValidation": {"apiVersion": "v24.0"},
        "mosMetaTracking": {"status": "active", "mode": "public_funnel_runtime"},
    }
    profile = {
        "id": uuid4(),
        "org_id": uuid4(),
        "client_id": uuid4(),
        "business_manager_id": "bm_1",
        "business_manager_name": "Business Manager",
        "page_id": "page_1",
        "page_name": "Page Name",
        "ad_account_id": "act_1",
        "ad_account_name": "Account Name",
        "pixel_id": "pixel_1",
        "data_set_id": "dataset_1",
        "verified_domain": "shop.example.com",
        "verified_domain_status": "verified",
        "attribution_click_window": "7d_click",
        "attribution_view_window": "1d_view",
        "view_through_enabled": True,
        "tracking_provider": "meta",
        "tracking_url_parameters": "utm_source=meta",
        "metadata": profile_metadata,
        "created_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
    }
    executed: list[tuple[object, dict | None]] = []

    class _MappingsResult:
        def mappings(self):
            return [profile]

    class _FakeBind:
        def execute(self, statement, params=None):
            executed.append((statement, params))
            if params is None:
                return _MappingsResult()
            return None

    monkeypatch.setattr(_MIGRATION.op, "get_bind", lambda: _FakeBind())

    _MIGRATION._backfill_meta_workspace_configs()

    inserts = [(statement, params) for statement, params in executed if params is not None]
    assert len(inserts) == 2
    for statement, params in inserts:
        assert params is not None
        metadata_bind = statement._bindparams["metadata"]
        assert isinstance(metadata_bind.type, postgresql.JSONB)
        metadata_payload = params["metadata"]
        if isinstance(metadata_payload, str):
            metadata_payload = json.loads(metadata_payload)
        assert metadata_payload == profile_metadata
