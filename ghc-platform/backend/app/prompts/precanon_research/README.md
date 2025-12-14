Pre-canon market research prompt templates
==========================================

This folder stores versioned prompt files for the precanon research workflow:

- 01_competitor_research.md
- 03_deep_research_prompt.md
- 04_run_deep_research.md
- 06_avatar_brief.md
- 07_offer_brief.md
- 08_necessary_beliefs_prompt1.md
- 09_i_believe_statements.md

Prompts should use simple token placeholders (e.g., {{ORG_ID}}, {{CLIENT_ID}}, {{ONBOARDING_PAYLOAD_ID}}, {{BUSINESS_CONTEXT_JSON}}, {{STEP1_SUMMARY}}, {{STEP3_PROMPT}}, {{STEP4_SUMMARY}}, {{STEP6_SUMMARY}}, {{STEP7_SUMMARY}}, {{STEP8_SUMMARY}}, {{ADS_CONTEXT}}).

Model responses must emit tagged blocks:
- <SUMMARY>...</SUMMARY>
- <CONTENT>...</CONTENT>
- Step 3 adds <STEP4_PROMPT>...</STEP4_PROMPT>
