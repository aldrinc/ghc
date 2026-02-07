import sys
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.auth.dependencies import AuthContext, get_current_user
from app.db.base import engine
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum, AssetSourceEnum, WorkflowKindEnum
from app.db.models import (
    ActivityLog,
    Artifact,
    Asset,
    Campaign,
    Client,
    CompanySwipeAsset,
    ClientSwipeAsset,
    Experiment,
    Org,
    WorkflowRun,
)
from app.main import app
from app.routers import campaigns as campaigns_router
from app.routers import clients as clients_router
from app.routers import workflows as workflows_router


TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    alembic_cfg = Config(str(ROOT_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    command.upgrade(alembic_cfg, "head")


class FakeTemporalHandle:
    def __init__(self, workflow_id: str, sink: list[tuple[str, tuple]]):
        self.id = workflow_id
        self.first_execution_run_id = f"{workflow_id}-run"
        self._sink = sink

    async def signal(self, name: str, *args) -> None:
        self._sink.append((name, args))


class FakeTemporalClient:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.signals: list[tuple[str, tuple]] = []

    async def start_workflow(self, *args, **kwargs) -> FakeTemporalHandle:
        workflow_id = kwargs.get("id") or "test-workflow"
        handle = FakeTemporalHandle(workflow_id, self.signals)
        self.started.append(workflow_id)
        return handle

    def get_workflow_handle(self, workflow_id: str, **_kwargs) -> FakeTemporalHandle:
        return FakeTemporalHandle(workflow_id, self.signals)


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        future=True,
    )
    session = TestingSessionLocal()

    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    org = Org(id=TEST_ORG_ID, name="Test Org")
    session.add(org)
    session.commit()
    session.refresh(org)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def auth_context() -> AuthContext:
    return AuthContext(user_id="test-user", org_id=str(TEST_ORG_ID))


@pytest.fixture()
def override_dependencies(db_session, auth_context):
    def get_session_override():
        try:
            yield db_session
        finally:
            pass

    def get_user_override():
        return auth_context

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_user_override
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def fake_temporal(monkeypatch):
    client = FakeTemporalClient()

    async def _get_temporal_client():
        return client

    monkeypatch.setattr(clients_router, "get_temporal_client", _get_temporal_client)
    monkeypatch.setattr(campaigns_router, "get_temporal_client", _get_temporal_client)
    monkeypatch.setattr(workflows_router, "get_temporal_client", _get_temporal_client)
    return client


@pytest.fixture()
def api_client(override_dependencies):
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def seed_data(db_session):
    client = Client(org_id=TEST_ORG_ID, name="Seed Client", industry="SaaS")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    campaign = Campaign(org_id=TEST_ORG_ID, client_id=client.id, name="Seed Campaign")
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    artifact = Artifact(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        campaign_id=campaign.id,
        type=ArtifactTypeEnum.client_canon,
        data={"note": "test canon"},
    )
    db_session.add(artifact)
    db_session.commit()
    db_session.refresh(artifact)

    experiment = Experiment(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        campaign_id=campaign.id,
        name="Seed Experiment",
        experiment_spec_artifact_id=artifact.id,
    )
    db_session.add(experiment)
    db_session.commit()
    db_session.refresh(experiment)

    asset = Asset(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        campaign_id=campaign.id,
        experiment_id=experiment.id,
        source_type=AssetSourceEnum.generated,
        channel_id="meta",
        format="video",
        content={"body": "seed content"},
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    company_swipe = CompanySwipeAsset(org_id=TEST_ORG_ID, title="Swipe Title")
    db_session.add(company_swipe)
    db_session.commit()
    db_session.refresh(company_swipe)

    client_swipe = ClientSwipeAsset(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        company_swipe_id=company_swipe.id,
        custom_title="Custom Swipe",
    )
    db_session.add(client_swipe)
    db_session.commit()
    db_session.refresh(client_swipe)

    workflow_run = WorkflowRun(
        org_id=TEST_ORG_ID,
        client_id=client.id,
        campaign_id=campaign.id,
        temporal_workflow_id="seed-workflow",
        temporal_run_id="seed-run",
        kind=WorkflowKindEnum.client_onboarding,
    )
    db_session.add(workflow_run)
    db_session.commit()
    db_session.refresh(workflow_run)

    log = ActivityLog(workflow_run_id=workflow_run.id, step="seed-step", status="completed")
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    return {
        "client": client,
        "campaign": campaign,
        "artifact": artifact,
        "asset": asset,
        "experiment": experiment,
        "company_swipe": company_swipe,
        "client_swipe": client_swipe,
        "workflow_run": workflow_run,
        "log": log,
    }
