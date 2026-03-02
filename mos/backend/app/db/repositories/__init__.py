from app.db.repositories.clients import ClientsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.experiments import ExperimentsRepository
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.swipes import CompanySwipesRepository, ClientSwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.db.repositories.ads import AdsRepository
from app.db.repositories.deep_research_jobs import DeepResearchJobsRepository
from app.db.repositories.jobs import JobsRepository
from app.db.repositories.teardowns import TeardownsRepository
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository
from app.db.repositories.client_compliance_profiles import ClientComplianceProfilesRepository
from app.db.repositories.meta_ads import MetaAdsRepository
from app.db.repositories.research_artifacts import ResearchArtifactsRepository
from app.db.repositories.org_deploy_domains import OrgDeployDomainsRepository
from app.db.repositories.shopify_theme_template_drafts import (
    ShopifyThemeTemplateDraftsRepository,
)

__all__ = [
    "ClientsRepository",
    "CampaignsRepository",
    "ArtifactsRepository",
    "ExperimentsRepository",
    "AssetsRepository",
    "CompanySwipesRepository",
    "ClientSwipesRepository",
    "WorkflowsRepository",
    "AdsRepository",
    "DeepResearchJobsRepository",
    "TeardownsRepository",
    "ClaudeContextFilesRepository",
    "ClientComplianceProfilesRepository",
    "MetaAdsRepository",
    "ResearchArtifactsRepository",
    "OrgDeployDomainsRepository",
    "ShopifyThemeTemplateDraftsRepository",
]
