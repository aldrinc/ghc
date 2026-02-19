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


class AdChannelEnum(str, Enum):
    META_ADS_LIBRARY = "META_ADS_LIBRARY"
    TIKTOK_CREATIVE_CENTER = "TIKTOK_CREATIVE_CENTER"
    GOOGLE_ADS_TRANSPARENCY = "GOOGLE_ADS_TRANSPARENCY"


class BrandRoleEnum(str, Enum):
    client = "client"
    peer = "peer"


class ProductBrandRelationshipTypeEnum(str, Enum):
    competitor = "competitor"


class ProductBrandRelationshipSourceEnum(str, Enum):
    onboarding_seed = "onboarding_seed"
    competitor_discovery = "competitor_discovery"
    ads_ingestion = "ads_ingestion"
    manual_admin = "manual_admin"


class BrandChannelVerificationStatusEnum(str, Enum):
    unverified = "unverified"
    verified = "verified"
    mismatch = "mismatch"


class AdIngestStatusEnum(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AdStatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"
    unknown = "unknown"


class MediaAssetTypeEnum(str, Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    TEXT = "TEXT"
    HTML = "HTML"
    SCREENSHOT = "SCREENSHOT"
    OTHER = "OTHER"


class MediaMirrorStatusEnum(str, Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    partial = "partial"


class ArtifactTypeEnum(str, Enum):
    client_canon = "client_canon"
    metric_schema = "metric_schema"
    strategy_sheet = "strategy_sheet"
    experiment_spec = "experiment_spec"
    asset_brief = "asset_brief"
    qa_report = "qa_report"
    experiment_report = "experiment_report"
    playbook = "playbook"
    funnel_runtime_bundle = "funnel_runtime_bundle"


class WorkflowKindEnum(str, Enum):
    client_onboarding = "client_onboarding"
    campaign_intent = "campaign_intent"
    campaign_funnel_generation = "campaign_funnel_generation"
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


class ResearchJobStatusEnum(str, Enum):
    created = "created"
    queued = "queued"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    incomplete = "incomplete"
    errored = "errored"


class AssetStatusEnum(str, Enum):
    draft = "draft"
    qa_passed = "qa_passed"
    approved = "approved"
    rejected = "rejected"


class AssetSourceEnum(str, Enum):
    generated = "generated"
    historical = "historical"
    competitor_example = "competitor_example"
    upload = "upload"
    ai = "ai"


class ClaudeContextFileStatusEnum(str, Enum):
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class FunnelStatusEnum(str, Enum):
    draft = "draft"
    published = "published"
    disabled = "disabled"
    archived = "archived"


class FunnelPageVersionStatusEnum(str, Enum):
    draft = "draft"
    approved = "approved"


class FunnelPageVersionSourceEnum(str, Enum):
    human = "human"
    ai = "ai"
    duplicate = "duplicate"


class FunnelPageReviewStatusEnum(str, Enum):
    draft = "draft"
    review = "review"
    approved = "approved"


class FunnelPublicationLinkKindEnum(str, Enum):
    cta = "cta"
    back = "back"
    default = "default"
    auto = "auto"


class FunnelDomainStatusEnum(str, Enum):
    pending = "pending"
    verified = "verified"
    active = "active"
    disabled = "disabled"


class FunnelAssetKindEnum(str, Enum):
    image = "image"


class FunnelAssetSourceEnum(str, Enum):
    upload = "upload"
    ai = "ai"


class FunnelAssetStatusEnum(str, Enum):
    pending = "pending"
    ready = "ready"
    failed = "failed"


class FunnelEventTypeEnum(str, Enum):
    page_view = "page_view"
    cta_click = "cta_click"
    funnel_enter = "funnel_enter"
    funnel_exit = "funnel_exit"
    order_completed = "order_completed"


class AgentRunStatusEnum(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentToolCallStatusEnum(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
