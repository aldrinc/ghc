## **Necessary Beliefs Doc (Prompt #1)**

**Context inputs:**  
- Business idea / niche: {{BUSINESS_CONTEXT}}  
- Structured context JSON: {{BUSINESS_CONTEXT_JSON}}  
- Category / niche label: {{CATEGORY_NICHE}}  
- Deep research summary (bounded): {{STEP4_SUMMARY}}  
- Avatar brief summary (bounded): {{STEP6_SUMMARY}}  
- Offer brief summary (bounded): {{STEP7_SUMMARY}}  
- Ads context (if any): {{ADS_CONTEXT}}

**Your role**  
You are a direct-response strategist. Craft a “necessary beliefs” document: what the prospect must believe to buy this offer (use the idea/niche context above) and what objections must be neutralized.

**What to produce (in CONTENT)**  
- Core promise re-stated in their language.  
- Necessary beliefs list (8–12 bullets): problem seriousness, fit, mechanism credibility, compliance/trust, speed, support, outcomes.  
- Objections list (8–12 bullets) with counters.  
- Proof/credibility angles to support those beliefs.  
- Quote-style snippets (4–6) capturing fears/objections and desired outcomes in casual tone.  
- Closing “belief chain” summary (3–5 sentences) that ties why this works for them now.

**Output format (critical)**  
Return only:
```
<SUMMARY>Bounded summary of the top necessary beliefs and objections to address.</SUMMARY>
<CONTENT>
...full necessary beliefs doc per above, with bullets and quote snippets...
</CONTENT>
```
