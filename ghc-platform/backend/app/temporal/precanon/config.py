from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .models import StepDefinition

# Base directories
APP_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIR = APP_ROOT / "prompts" / "precanon_research"

# Constants for parsing model output blocks
SUMMARY_BLOCK_TAG = "SUMMARY"
CONTENT_BLOCK_TAG = "CONTENT"
STEP4_PROMPT_BLOCK_TAG = "STEP4_PROMPT"

# Ads context step key (not a document-producing step)
ADS_CONTEXT_STEP_KEY = "02"

# Ordered list of research steps that produce artifacts
RESEARCH_STEP_KEYS: List[str] = ["01", "03", "04", "06", "07", "08", "09"]

# Step configuration for prompt files and payload bounds
STEP_DEFINITIONS: Dict[str, StepDefinition] = {
    "01": StepDefinition(
        key="01",
        prompt_filename="01_competitor_research.md",
        title="Competitor research",
        summary_max_chars=1200,
    ),
    "03": StepDefinition(
        key="03",
        prompt_filename="03_deep_research_prompt.md",
        title="Deep research prompt",
        summary_max_chars=1200,
        handoff_field="step4_prompt",
        handoff_max_chars=20000,
    ),
    "04": StepDefinition(
        key="04",
        prompt_filename="04_run_deep_research.md",
        title="Deep research execution",
        summary_max_chars=1500,
    ),
    "06": StepDefinition(
        key="06",
        prompt_filename="06_avatar_brief.md",
        title="Avatar brief",
        summary_max_chars=1200,
    ),
    "07": StepDefinition(
        key="07",
        prompt_filename="07_offer_brief.md",
        title="Offer brief",
        summary_max_chars=1200,
    ),
    "08": StepDefinition(
        key="08",
        prompt_filename="08_necessary_beliefs_prompt1.md",
        title="Necessary beliefs (prompt 1)",
        summary_max_chars=1200,
    ),
    "09": StepDefinition(
        key="09",
        prompt_filename="09_i_believe_statements.md",
        title='"I believe" statements',
        summary_max_chars=1200,
    ),
}

STEP_DEFINITIONS_ORDERED: List[StepDefinition] = [STEP_DEFINITIONS[key] for key in RESEARCH_STEP_KEYS]
