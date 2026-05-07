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


class CampaignDeliveryModeEnum(str, Enum):
    internal_funnel = "internal_funnel"
    external_urls = "external_urls"


class CampaignDeliveryValidationStatusEnum(str, Enum):
    not_applicable = "not_applicable"
    not_validated = "not_validated"
    valid = "valid"
    invalid = "invalid"


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
    skill_foundational_input = "skill_foundational_input"
    skill_angle_library = "skill_angle_library"
    skill_angle_selection = "skill_angle_selection"
    skill_knowledge_base = "skill_knowledge_base"
    skill_signal_report = "skill_signal_report"
    skill_cso = "skill_cso"
    skill_offer_document = "skill_offer_document"
    skill_headline_pool = "skill_headline_pool"
    skill_headline_selection = "skill_headline_selection"
    skill_presell_page = "skill_presell_page"
    skill_sales_page = "skill_sales_page"
    skill_brand_profile = "skill_brand_profile"
    skill_runtime_bundle = "skill_runtime_bundle"
    campaign_loaded_angles = "campaign_loaded_angles"
    campaign_loaded_offer = "campaign_loaded_offer"
    campaign_loaded_copy = "campaign_loaded_copy"
    campaign_loaded_copy_context = "campaign_loaded_copy_context"
    campaign_creative_context = "campaign_creative_context"
    asset_brief = "asset_brief"
    ad_copy_pack = "ad_copy_pack"
    creative_generation_plan = "creative_generation_plan"
    qa_report = "qa_report"
    experiment_report = "experiment_report"
    playbook = "playbook"
    funnel_runtime_bundle = "funnel_runtime_bundle"
    site_runtime_bundle = "site_runtime_bundle"
    strategy_v2_step_payload = "strategy_v2_step_payload"
    strategy_v2_stage0 = "strategy_v2_stage0"
    strategy_v2_stage1 = "strategy_v2_stage1"
    strategy_v2_stage2 = "strategy_v2_stage2"
    strategy_v2_stage3 = "strategy_v2_stage3"
    strategy_v2_awareness_angle_matrix = "strategy_v2_awareness_angle_matrix"
    strategy_v2_offer = "strategy_v2_offer"
    strategy_v2_copy = "strategy_v2_copy"
    strategy_v2_copy_context = "strategy_v2_copy_context"
    strategy_v2_launch_context = "strategy_v2_launch_context"
    meta_launch_plan = "meta_launch_plan"
    meta_management_metrics_snapshot = "meta_management_metrics_snapshot"
    meta_management_recommended_actions = "meta_management_recommended_actions"
    meta_management_report_markdown = "meta_management_report_markdown"
    meta_management_approval_decision = "meta_management_approval_decision"
    meta_management_applied_action = "meta_management_applied_action"


class WorkflowKindEnum(str, Enum):
    client_onboarding = "client_onboarding"
    campaign_intent = "campaign_intent"
    campaign_funnel_generation = "campaign_funnel_generation"
    strategy_v2_angle_launch = "strategy_v2_angle_launch"
    strategy_v2_angle_iteration = "strategy_v2_angle_iteration"
    campaign_planning = "campaign_planning"
    creative_production = "creative_production"
    swipe_image_ad = "swipe_image_ad"
    experiment_cycle = "experiment_cycle"
    playbook_update = "playbook_update"
    test_campaign = "test_campaign"
    strategy_v2 = "strategy_v2"


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


class GeminiContextFileStatusEnum(str, Enum):
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
    ad_click = "ad_click"
    page_view = "page_view"
    cta_click = "cta_click"
    funnel_enter = "Entered Funnel"
    funnel_exit = "funnel_exit"
    presell_page_view = "presell_page_view"
    pre_sales_page_view = "pre_sales_page_view"
    sales_page_view = "sales_page_view"
    offer_page_view = "offer_page_view"
    checkout_page_view = "checkout_page_view"
    thank_you_page_view = "thank_you_page_view"
    custom_page_view = "custom_page_view"
    qualified_session = "qualified_session"
    scroll_depth = "scroll_depth"
    section_view = "section_view"
    proof_view = "proof_view"
    cta_view = "cta_view"
    offer_stack_view = "offer_stack_view"
    value_stack_view = "value_stack_view"
    price_reveal_view = "price_reveal_view"
    selector_interaction = "selector_interaction"
    subscription_selected = "subscription_selected"
    guarantee_view = "guarantee_view"
    trust_element_view = "trust_element_view"
    product_detail_interaction = "product_detail_interaction"
    pre_sales_to_sales_click = "pre_sales_to_sales_click"
    sales_to_checkout_click = "sales_to_checkout_click"
    checkout_click = "checkout_click"
    checkout_redirect_started = "checkout_redirect_started"
    checkout_pagehide = "checkout_pagehide"
    checkout_visibility_hidden = "checkout_visibility_hidden"
    custom_page_click = "custom_page_click"
    checkout_started = "checkout_started"
    order_completed = "order_completed"
    purchase = "purchase"
    refund = "refund"
    chargeback = "chargeback"
    support_ticket = "support_ticket"
    tracking_chain_check = "tracking_chain_check"
    web_vital_recorded = "web_vital_recorded"
    quiz_lead_viewed = "quiz_lead_viewed"
    quiz_question_viewed = "quiz_question_viewed"
    quiz_option_presented = "quiz_option_presented"
    quiz_option_selected = "quiz_option_selected"
    quiz_option_deselected = "quiz_option_deselected"
    quiz_question_submitted = "quiz_question_submitted"
    quiz_completed = "quiz_completed"
    quiz_result_viewed = "quiz_result_viewed"
    quiz_mechanism_viewed = "quiz_mechanism_viewed"
    quiz_proof_viewed = "quiz_proof_viewed"
    quiz_recommendation_viewed = "quiz_recommendation_viewed"
    quiz_cta_viewed = "quiz_cta_viewed"


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


class FunnelExperienceKindEnum(str, Enum):
    funnel = "funnel"
    site = "site"


class SiteTypeEnum(str, Enum):
    ecommerce = "ecommerce"


class SiteFamilyEnum(str, Enum):
    medusa_b2b_starter = "medusa-b2b-starter"
    medusa_b2c_starter = "medusa-b2c-starter"


class CommerceProviderEnum(str, Enum):
    medusa = "medusa"
    shopify = "shopify"


class SitePageTypeEnum(str, Enum):
    home = "home"
    store = "store"
    collection = "collection"
    category = "category"
    product_detail = "product_detail"
    cart = "cart"
    checkout = "checkout"
    account_dashboard = "account_dashboard"
    account_profile = "account_profile"
    account_addresses = "account_addresses"
    account_orders = "account_orders"
    account_order_detail = "account_order_detail"
    order_confirmed = "order_confirmed"
    order_transfer = "order_transfer"
    order_transfer_accept = "order_transfer_accept"
    order_transfer_decline = "order_transfer_decline"
    account = "account"
    quote = "quote"
    approval = "approval"


class SiteThemeBindingModeEnum(str, Enum):
    """Site theme binding mode determining how the site resolves its design system tokens.

    - standalone: Site intentionally has no bound design system. Returns null tokens.
    - workspace_default: Site intentionally uses the workspace default design system.
    - design_system: Site intentionally uses a specific selected design system.
    """

    standalone = "standalone"
    workspace_default = "workspace_default"
    design_system = "design_system"
