from enum import Enum


class UserRoleEnum(str, Enum):
    partner = "partner"
    strategy = "strategy"
    creative = "creative"
    performance = "performance"
    ops = "ops"
    data = "data"
    experiment = "experiment"
    admin = "admin"


class ClientStatusEnum(str, Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class CampaignStatusEnum(str, Enum):
    draft = "draft"
    planning = "planning"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"


class ArtifactTypeEnum(str, Enum):
    client_canon = "client_canon"
    metric_schema = "metric_schema"
    strategy_sheet = "strategy_sheet"
    experiment_spec = "experiment_spec"
    asset_brief = "asset_brief"
    qa_report = "qa_report"
    experiment_report = "experiment_report"
    playbook = "playbook"


class WorkflowKindEnum(str, Enum):
    client_onboarding = "client_onboarding"
    campaign_planning = "campaign_planning"
    creative_production = "creative_production"
    experiment_cycle = "experiment_cycle"
    playbook_update = "playbook_update"
    test_campaign = "test_campaign"


class WorkflowStatusEnum(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AssetStatusEnum(str, Enum):
    draft = "draft"
    qa_passed = "qa_passed"
    approved = "approved"
    rejected = "rejected"


class AssetSourceEnum(str, Enum):
    generated = "generated"
    historical = "historical"
    competitor_example = "competitor_example"
