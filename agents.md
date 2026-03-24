Do not add fallbacks without explicit authorization, prefer erroring out with a clean, well-described error so that it's clear what the system is doing.
Don't ever change the LLM or AI model without my authorization or try alternatives after a model been set by us.
Never ever ask me to run scripts or code, especially when the work is validation of your work. Run it yourself and review the output to ensure the work you performed is correct and delivers value to me.
Do not ever create any fake data unless explicitly authorized.
Never deploy directly to production, restart production services, or make live server changes without explicit authorization in the current thread.
When deployment is needed, prefer the normal `main` -> GitHub -> CI/CD path first. Only use direct prod access when I explicitly authorize that override.
Optimize outputs for human review speed. Review is the bottleneck.
For plans, docs, and design writeups: lead with the decision, use short sections, prefer scannable bullets, and use tables only where they materially improve comprehension such as taxonomies, schemas, field maps, and decision matrices.
Do not turn an entire document into tables when only one section needs tabular structure.
