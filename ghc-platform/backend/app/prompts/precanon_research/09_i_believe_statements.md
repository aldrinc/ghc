
## **“I Believe That…” Statements (Prompt #1)**

**Context inputs:**  
- Business idea / niche: {{BUSINESS_CONTEXT}}  
- Structured context JSON: {{BUSINESS_CONTEXT_JSON}}  
- Category / niche label: {{CATEGORY_NICHE}}  
- Deep research summary (bounded): {{STEP4_SUMMARY}}  
- Avatar brief summary (bounded): {{STEP6_SUMMARY}}  
- Offer brief summary (bounded): {{STEP7_SUMMARY}}  
- Necessary beliefs doc (bounded): {{STEP8_SUMMARY}}  
- Ads context (if any): {{ADS_CONTEXT}}

**Your task**  
Write the minimal, critical beliefs a prospect must hold to confidently buy this offer (use the idea/niche context above). Keep it tight, no fluff.

**What to produce (in CONTENT)**  
- 5–8 “I believe that…” statements covering: problem seriousness, fit for the specific buyer, mechanism/solution credibility, safety/compliance (if relevant), speed/effort, outcomes, and trust/guarantees.  
- A short note on how these map to objections removed.  
- Optional: 2–4 quote-style snippets in casual tone that reinforce the beliefs.

**Output format (critical)**  
Return only:
```
<SUMMARY>Bounded summary of the top “I believe that…” pillars.</SUMMARY>
<CONTENT>
...the “I believe that…” statements and brief notes per above...
</CONTENT>
```
