from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from app.llm import LLMGenerationParams


@dataclass
class ResearchBaseContext:
    org_id: str
    client_id: str
    product_id: str
    onboarding_payload_id: str
    idea_workspace_id: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    parent_workflow_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    parent_folder_id: Optional[str] = None
    idea_folder_id: Optional[str] = None
    idea_folder_url: Optional[str] = None
    idea_folder_name: Optional[str] = None
    allow_drive_stub: bool = False
    allow_claude_stub: bool = False


@dataclass
class PromptBuildRequest:
    step_key: str
    variables: Mapping[str, str]
    prompt_override: Optional[str] = None
    summary_block_tag: str = "SUMMARY"
    content_block_tag: str = "CONTENT"
    step4_prompt_block_tag: str = "STEP4_PROMPT"


@dataclass
class PromptBuildResult:
    prompt_text: str
    prompt_sha256: str


@dataclass
class StepGenerationRequest:
    step_key: str
    prompt_text: str
    prompt_sha256: str
    llm_params: LLMGenerationParams
    title: Optional[str] = None
    org_id: Optional[str] = None
    client_id: Optional[str] = None
    onboarding_payload_id: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    parent_workflow_id: Optional[str] = None
    parent_run_id: Optional[str] = None


@dataclass
class DeepResearchJobRef:
    job_id: str
    response_id: Optional[str]
    status: Optional[str]


@dataclass
class LlmGenerationResult:
    raw_output: str
    job: Optional[DeepResearchJobRef] = None


@dataclass
class PersistArtifactRequest:
    step_key: str
    title: str
    summary: Optional[str]
    content: str
    prompt_sha256: str
    org_id: str
    client_id: str
    product_id: str
    campaign_id: Optional[str]
    idea_workspace_id: Optional[str]
    workflow_id: Optional[str]
    workflow_run_id: Optional[str]
    parent_workflow_id: Optional[str]
    parent_run_id: Optional[str]
    parent_folder_id: Optional[str]
    idea_folder_id: Optional[str]
    idea_folder_url: Optional[str]
    idea_folder_name: Optional[str]
    allow_drive_stub: bool = False
    allow_claude_stub: bool = False


@dataclass
class PersistArtifactResult:
    doc_id: str
    doc_url: str
    idea_folder_id: Optional[str]
    idea_folder_url: Optional[str]
    claude_file_id: Optional[str]
    created_at_iso: str


@dataclass
class IdeaFolderRequest:
    parent_folder_id: Optional[str]
    idea_folder_name: Optional[str]


@dataclass
class IdeaFolderResult:
    idea_folder_id: Optional[str]
    idea_folder_url: Optional[str]


@dataclass
class ParsedStepOutput:
    summary: str
    content: str
    handoff: Optional[Dict[str, Any]]
