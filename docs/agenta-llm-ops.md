# Agenta LLM Ops Integration

MOS now supports Agenta as the prompt management layer while keeping Langfuse as the observability layer.

## Scope

- Agenta manages prompt templates and versions.
- Langfuse remains the tracing and runtime observability system.
- No silent fallback is used when Agenta is enabled.

## Runtime Behavior

- If `AGENTA_ENABLED=false`:
  - Prompt templates are loaded from local files as before.
- If `AGENTA_ENABLED=true`:
  - Agenta SDK is initialized at API and Temporal worker startup.
  - Prompt templates are fetched from Agenta using `AGENTA_PROMPT_REGISTRY`.
  - Missing config, fetch failures, or invalid prompt values raise explicit errors.

## Prompt Keys Currently Managed

- `prompts/precanon_research/01_competitor_research.md`
- `prompts/precanon_research/01.5_purple_ocean_analyst.md`
- `prompts/precanon_research/03_deep_research_prompt.md`
- `prompts/precanon_research/04_run_deep_research.md`
- `prompts/precanon_research/06_avatar_brief.md`
- `prompts/precanon_research/07_offer_brief.md`
- `prompts/precanon_research/08_necessary_beliefs_prompt1.md`
- `prompts/precanon_research/09_i_believe_statements.md`
- `prompts/creative_analysis/ad_breakdown.md`
- `prompts/swipe/swipe_to_image_ad.md`

## Required Environment Variables

- `AGENTA_ENABLED=true`
- `AGENTA_API_KEY=<api-key>`
- `AGENTA_HOST=https://cloud.agenta.ai`
- `AGENTA_PROMPT_REGISTRY=<json object>`

`AGENTA_PROMPT_REGISTRY` is a JSON map:

```json
{
  "prompts/creative_analysis/ad_breakdown.md": {
    "app_slug": "ad-breakdown",
    "environment_slug": "production",
    "parameter_path": "template"
  }
}
```

Each entry supports:

- `app_slug` (required)
- `parameter_path` (required, dot path into the fetched config object)
- `variant_slug` (optional)
- `variant_version` (optional)
- `environment_slug` (optional)
- `environment_version` (optional)
