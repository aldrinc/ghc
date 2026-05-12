Do not add fallbacks without explicit authorization, prefer erroring out with a clean, well-described error so that it's clear what the system is doing.
Don't ever change the LLM or AI model without my authorization or try alternatives after a model been set by us.
Never ever ask me to run scripts or code, especially when the work is validation of your work. Run it yourself and review the output to ensure the work you performed is correct and delivers value to me.
Do not ever create any fake data unless explicitly authorized.
Never deploy directly to production, restart production services, or make live server changes without explicit authorization in the current thread.
When deployment is needed, prefer the normal `main` -> GitHub -> CI/CD path first. Only use direct prod access when I explicitly authorize that override.
No standalone/static HTML funnel deploys outside `html-deploy-v1`. Do not use legacy standalone flows, ad hoc route-scoped artifact copies, or manual server-side HTML replacements for production HTML funnel deployment unless I explicitly authorize a break-glass override in the current thread.
Optimize outputs for human review speed. Review is the bottleneck.
For plans, docs, and design writeups: lead with the decision, use short sections, prefer scannable bullets, and use tables only where they materially improve comprehension such as taxonomies, schemas, field maps, and decision matrices.
Do not turn an entire document into tables when only one section needs tabular structure.

Remote dev URL policy:
- This repository's shared Hetzner VM is private-only behind NetBird.
- Never present a public Hetzner IPv4 as the user-facing URL for dev services unless the user explicitly asks for public exposure.
- When you need a shareable dev URL, use `./scripts/resolve-dev-access-url.sh <port>` instead of scraping Vite/Uvicorn network output.
- Prefer URLs in this order: configured private domain for the service, then the VM's `wt0`/NetBird address, then `127.0.0.1` only for commands run inside the VM itself.
- If tooling prints multiple interfaces, ignore public/NAT addresses such as `178.*` or `172.*` for user-facing instructions.

MOS authenticated UI validation:
- MOS preview/editor validation should use the repo-local ignored auth file `/Users/aldrinclement/Documents/programming/marketi/.env.mos-test-auth`.
- Read `MOS_TEST_EMAIL` and `MOS_TEST_PASSWORD` from that file for automated sign-in; do not commit plaintext credentials into tracked files.
- Use `/Users/aldrinclement/Documents/programming/marketi/mos/frontend/scripts/validate-site-preview.mjs` for authenticated preview checks. It persists Playwright auth state under `/Users/aldrinclement/Documents/programming/marketi/.local/playwright-home/`.
- If the cached auth state is stale, refresh it by signing in through `/sign-in` with the MOS test credentials before running preview validation.
