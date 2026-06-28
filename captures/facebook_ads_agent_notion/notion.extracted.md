# How to Build an AI Facebook Ads Manager Agent with Claude Code

Brought to you by…

Graphed.com - Deploy AI agents for marketing

![image](attachment:5bed2beb-8c7a-42b0-9525-1a1f3d28a33d:graphed-header.png)

Deploy GTM agents that run your marketing based on your live business data.

We handle data pipeline, data warehouse, and agent infrastructure.

Connect your data pipeline to Claude Code, Codex with our MCP - graphed.com/mcp

Self service or hire our team to forward deploy engineers.

Learn more at the link - https://www.graphed.com/

---

Last Friday I deployed an AI agent to run a startup's Facebook ads account. Day 1 the cost per phone number lead was $17. By day 4 it was $3.

Over the weekend the agent generated 30 new pieces of creative, uploaded them to Facebook as paused drafts, watched the live performance data, killed the losers, scaled the winners, and rewrote the next batch based on what was actually converting. No one touched it.

This is what GTM engineering actually looks like — agents in the wild, doing the job a media buyer would charge $8k/month for, except they work 24/7 and learn faster.

It runs on Nano Banana 2 + Facebook Marketing API + Claude Code + a data pipeline into a warehouse + an agent runtime. Here's the exact build.

---

#### What you need before starting

- Claude Code installed (npm install -g @anthropic-ai/claude-code)

- A Facebook Ads account with API access (Marketing API token with ads_management + ads_read)

- Nano Banana 2 access (current best image model for ad creative)

- A target CPA (cost per action) — the dollar amount you're trying to beat per phone number lead, signup, or purchase

- A hosted stack for the pipeline + warehouse + Hermes Agent runtime — covered in section 7 (Graphed is the easy path, Airbyte + ClickHouse + self-hosted Hermes is the open-source path)

- ~2 hours to wire it up the first time

That's it. After this it manages itself.

---

### 1. Generate On-Brand Ad Creative with Nano Banana 2

The creative is the lever. You can have the smartest bidding agent in the world and it doesn't matter if the ads look like stock photos. Nano Banana 2 is the current best image model for ad creative — handles brand consistency, product placement, and human faces better than anything else right now.

Here's the prompt:

> "Build a Claude Code skill that generates Facebook ad creative using Nano Banana 2. Inputs: brand reference images (3-5 hero shots), the product name, the offer, and a desired vibe ('UGC selfie', 'studio product shot', 'lifestyle outdoor', etc.). For each batch run, generate 10 distinct images that all stay on-brand but vary the angle, setting, and composition. Save each image with a metadata JSON file containing the prompt, the vibe tag, and a unique creative_id. Output everything to a ./creatives/[YYYY-MM-DD]/ folder."

You hand it your brand guide once and from then on every batch comes out looking like it was shot for your brand. The vibe tags matter — when performance data comes back, you want to know whether "UGC selfie" or "studio product shot" is the format that's actually converting, not just which individual image won.

Ten images per batch is the sweet spot. Enough variation to test, not so many you're burning credits on slop.

---

### 2. Set Up the Testing + Winners Campaign Structure

The single biggest mistake people make running paid ads is dumping fresh creative straight into their main campaign and letting it eat budget while it figures itself out. You don't let unproven ads spend real money. You make them earn it first.

The structure is two campaigns running side by side:

- Testing campaign — gets 20% of total ad budget. Every new piece of creative lands here first, at a small daily spend per ad. This is where you discover winners cheaply.

- Winners campaign — gets 80% of total ad budget. Only ads that have already proven themselves in Testing get duplicated into here and scaled up.

Here's the prompt:

> "Set up two Facebook ad campaigns in the ad account: (1) 'Testing — Phone Leads' with daily budget X, optimization goal 'phone_number_submitted', single ad set with broad targeting. (2) 'Winners — Phone Leads' with daily budget 4X, same optimization, same ad set structure. Save the campaign IDs to the env file as FB_TESTING_CAMPAIGN_ID and FB_WINNERS_CAMPAIGN_ID. Total budget split should be 20% testing, 80% winners by daily spend."

The 80/20 split is the whole game. Cheap dollars find winners. Real money rides winners. You're never spending big on something the data hasn't already validated.

This is also what makes the agent's job tractable. It only needs to make two kinds of decisions — graduate or kill in Testing, scale or pause in Winners. Not "what should I do with this random ad."

---

### 3. Upload Ads to Facebook via the Marketing API

Manual ad uploads are where most people quit. Building 30 ads in Ads Manager UI takes hours. The API turns each upload into ~3 seconds.

Here's the prompt:

> "Build a Claude Code skill that uploads ad creatives to the Testing campaign as paused drafts via the Marketing API. For each image in the creatives folder: (1) upload the image to the ad account's image library, (2) create an ad creative object with the image, the link, the page ID, and copy generated by Claude based on the vibe tag, (3) create an Ad inside the Testing campaign's ad set, in PAUSED status. Use the FB_ACCESS_TOKEN, FB_AD_ACCOUNT_ID, FB_PAGE_ID, and FB_TESTING_CAMPAIGN_ID from the env file. Stop and log if any call returns an error — don't retry silently. Output a CSV of every ad created with its creative_id and FB ad ID."

Everything new starts in Testing. The Winners campaign only ever receives ads that have already been proven — never raw new creative.

PAUSED status is the safety rail. The agent creates everything as drafts so the optimizer agent (in step 5) decides what gets turned on after the morning review. You never want a runaway loop spending money before performance data is in.

The copy gets generated alongside the upload — the vibe tag drives the tone (UGC = casual, studio shot = benefit-led headline). Don't reuse the same headline across 30 ads or Facebook collapses them into one auction.

---

### 4. Pipe Live Facebook Ads Data Into a Warehouse

This is the part that makes the whole loop possible. You can't optimize what you can't measure, and the FB Ads UI is too slow and too aggregated to be useful for an agent. You need ad-level data, refreshed hourly, in a warehouse the agent can query.

Here's the prompt:

> "Set up a Fivetran sync from Facebook Ads to our ClickHouse warehouse (or Postgres if no warehouse yet). Sync these objects hourly: ads, ad creatives, ad insights at the ad level (spend, impressions, clicks, CTR, conversions, cost per result), and the custom event 'phone_number_submitted'. Make sure the schema preserves the creative_id from the metadata JSON so we can join FB ad performance back to the Nano Banana batch and vibe tag. Validate the first sync — confirm we see yesterday's spend matching what's in Ads Manager."

The creative_id join is the part most people skip and then regret. Without it you know "ad #4029182 has a $3 CPL" but not "the UGC-selfie batch from last Tuesday has a $3 CPL." The agent needs the second view, not the first, to decide what to make more of.

Hourly sync is the right cadence. Real-time is overkill (FB itself only updates attribution windows hourly), daily is too slow when you're spending real money.

---

### 5. Have the Agent Manage Both Campaigns

Now the loop closes. The agent queries the warehouse, sees what's working in Testing, kills the dead ones, promotes proven creative into Winners, and scales the winners that keep performing.

Here's the prompt:

> "Build a Claude Code skill that runs the daily ad optimization across the Testing and Winners campaigns. Set TARGET_CPA as the cost per phone number lead we're aiming for (e.g., $5). Steps: (1) Query the warehouse for every ad active in the last 24 hours in both campaigns — return spend, conversions, cost per phone_number_submitted (CPA), and the vibe tag. (2) In TESTING: for any ad with spend > $20 and zero conversions, pause it via the FB API — that's the kill rule, no leads at meaningful spend = dead. (3) In TESTING: for any ad with CPA at or below TARGET_CPA AND at least one conversion, duplicate the ad into the Winners campaign at a higher daily budget. Mark the original as 'graduated' so we don't double-promote. (4) In WINNERS: for any ad with CPA below 0.5x TARGET_CPA, scale its ad set budget by 20%. For any ad with CPA above 2x TARGET_CPA, pause it. (5) Aggregate performance by vibe tag across both campaigns — return the top 2 vibes by CPA. (6) Write a creative brief that asks the Nano Banana skill (step 1) to generate the next Testing batch using the winning vibes. Log every action taken to a daily report."

This is the brain. It's reading actual conversion data — not vanity metrics like CTR — and making spend decisions based on cost per action. Cost per action is the only number that matters here. Everything else (CTR, CPM, frequency) is a leading indicator at best, a distraction at worst.

The kill rule for Testing is simple: zero conversions after meaningful spend = dead. No CPA math needed when there are no conversions to divide by. That's the signal that creative just didn't work, kill it and move on.

Promotion to Winners only happens when an ad hits your target CPA in Testing. That's the bar. Beat the target on cheap dollars, you earn real money.

---

### 6. Wire the Whole Thing into a Recurring Task

The first five steps are the pipeline. This is what makes it run while you sleep.

Here's the prompt:

> "Set up a Hermes Agent recurring task that runs the full FB ads optimization loop once a day at 6am. Each run: (a) execute the optimization skill from step 5 — kill zero-conversion ads in Testing, promote target-CPA ads from Testing to Winners, scale or pause ads in Winners, identify winning vibes, (b) generate a new batch of 10 creatives via Nano Banana 2 using the winning vibe tags, (c) upload them as paused drafts to the Testing campaign, (d) post a Slack summary to #ad-ops with yesterday's spend, CPA, promotions, kills, scaled winners, and the top creative. Cap total daily new ad spend increases at 30% of yesterday's total — never let the agent double the budget overnight."

The spend cap is non-negotiable. The whole point of an autonomous loop is that it runs without you watching it, and the failure mode you protect against is the agent going on a tear and 10x'ing spend on something that looked good for two hours and then cratered.

Slack summary keeps you in the loop without putting you in the way. You read it in the morning, override if something looks off, otherwise let it cook.

---

### 7. Where to Host All of This (The Boring Required Part)

None of this works without three pieces of infrastructure running 24/7:

1. A data pipeline that syncs Facebook Ads data hourly into a warehouse

1. A data warehouse the agent can query in plain SQL

1. A Hermes Agent runtime somewhere it can wake up daily and run the loop

You have two paths to get there.

The easy path — just use Graphed. Graphed is a hosted data analytics platform built for exactly this. You connect Facebook Ads via OAuth (15 minutes), the warehouse is managed for you, and the Hermes Agent runtime is part of the product. One signup, one bill, no DevOps. The whole pipeline + warehouse + agent host runs under one roof. This is what we use for client deployments because it removes a week of setup work and gives you an agent that can also pull from HubSpot, Stripe, GA4, Klaviyo, and everything else as you grow. graphed.com

The open-source path — wire it together yourself. If you want to own the stack:

- Pipeline: Airbyte (self-hosted or cloud) — has a Facebook Marketing connector that syncs ads, insights, and conversions to your warehouse.

- Warehouse: ClickHouse (self-hosted on a VPS or ClickHouse Cloud). Postgres works too if you're starting small.

- Hermes Agent: Self-host it on Railway, Fly.io, or any VPS — it's just a long-running process that needs an Anthropic API key, an env file, and a writable directory.

The open-source path is more work but gives you full control. The Graphed path is faster and removes operational overhead. Pick based on whether your edge is "we like managing infrastructure" or "we like shipping."

Either way, the agent code from sections 1-6 is identical. Only the hosting changes.

---

### 8. The Outcome — What Actually Happened

This is the part the screenshots don't tell you. On the live deployment last weekend:

- Day 1: $17 cost per phone number lead. Manual ad ops, 4 ads running.

- Day 2: Agent launched. Generated 10 new ads, uploaded as drafts, turned 5 on.

- Day 3: Two creatives outperformed account average by 3x. Agent paused 4 losers, scaled 2 winners, generated 10 more in the winning vibe.

- Day 4: $3 cost per phone number lead. Same ad spend. 5.6x improvement.

That's a full-time media buyer's quarter compressed into a weekend. And it runs every day from here on out, getting smarter as more data lands in the warehouse.

---

### The Skill File (copy this)

This is the SKILL.md that ties the whole thing together. Drop it into your Hermes Agent's skills folder at /opt/data/skills/agent/hermes-agent-basics/SKILL.md and the agent will load it on boot. It documents every tool, every API, every user preference, and every workflow the agent needs to operate.

Customize the brand guidelines section, the ad account ID, and the pain points to fit your business. Everything else is the skeleton you keep.

```Markdown

---
name: hermes-agent-basics
description: Core workflow and conventions for Hermes Agent interactions
category: agent
---

# Hermes Agent Basics

High-level guide to how Hermes Agent works, including available tools, API patterns, and user preferences.

## Available Tools

| Tool | Purpose |
|------|---------|
| `web_search` | Search the web (max 5 results) |
| `web_extract` | Extract content from URLs (max 5 URLs) |
| `execute_code` | Run Python scripts with tool access |
| `terminal` | Execute shell commands |
| `read_file` | Read files with line numbers |
| `write_file` | Write complete file content |
| `patch` | Targeted find-and-replace edits |
| `search_files` | Search file contents or find files |
| `mcp_graphed_warehouse_*` | Query Facebook Ads data warehouse |
| `deploy_artifact` | Build/deploy static websites |
| `vision_analyze` | Analyze images |
| `delegate_task` | Spawn subagents |
| `skill_view/manage` | Load/create skills |
| `memory` | Persist facts across sessions |
| `create_secret` | Request API keys from user |

## Core APIs Used

### Kie.ai Image Generation
POST https://api.kie.ai/v1/images/generations Headers: Authorization: Bearer <kie_api_secret> Body: { "model": "nano-banana-2", "prompt": "...", "num_images": 1 } Returns: { "data": [{ "url": "quickdraw_url" }] }

- Secret name: `kie_api`
- Model: `nano-banana-2` (Flux-based, good for stylized images)
- Output: Quickdraw URLs (tempfile.aiquickdraw.com)

### Exa.ai Semantic Search
POST https://api.exa.ai/search Headers: Authorization: Bearer <exa_api_secret> Body: { "query": "homeowner landscape design frustrations reddit", "num_results": 50 }

- Used for Reddit pain point research
- Scrapes Reddit, forums for user frustrations

### Facebook Graph API
Base: https://graph.facebook.com/v21.0 Auth: Bearer <fb_access_token>

Endpoints used:

/me - Verify token
/me/adaccounts - List ad accounts
/act_<id>/ads - List ads
/act_<id>/adcreatives - Create ad creatives
/act_<id>/adimages - Upload images (multipart/form-data)
- Ad Account ID: `act_734348472362184`
- Ad Set ID: `120226541729700642`
- Page ID: `631650653373491`

### Graphed Data Warehouse
MCP Server: graphed-warehouse Functions:

mcp_graphed_warehouse_query(sql, parameters)
mcp_graphed_warehouse_explore_schema()
mcp_graphed_warehouse_list_prompts()
mcp_graphed_warehouse_get_prompt(name, arguments)
- Used for Facebook Ads performance analytics

## User Preferences

### Communication Style
- **Be direct and concise** — don't be verbose unless asked
- **Show generated assets first** — user wants to review before committing
- **Test before full commitment** — verify everything works

### Brand Guidelines (Eden Studio SF)
- **Mission**: "Bring nature home"
- **Target Audience**: Pragmatic Aesthetes, 35-45, primarily female, affluent
- **Tone**: Timeless, evocative, inspired, elevated
- **Messaging pillars**: "In weeks, not seasons", "Intelligently designed, expertly installed"
- **IMPORTANT**: Never mention "Eden" explicitly in ad copy or images — treat as confidential brand name

### Pain Points (Ranked by Frequency)
1. Contractor Issues (20%)
2. Decision Paralysis (18%)
3. Cost/Pricing (16%)
4. Time/Timeline (6%)
5. Design Uncertainty (4%)

### Technical Preferences
- Brand style: Hand-drawn line art illustrations
- Dashboard: Dark theme (#0d1117), IBM Plex Sans/Mono, teal/purple/orange chart lines
- Phone conversion ID: `offsite_conversion.custom.2459253791180326`
- Test ads paused first before going live

## Workflow Patterns

### Image Generation Workflow
1. Load `kie-ai-image-generation` skill
2. Generate concepts → show user quickdraw URLs
3. Refine based on feedback
4. Finalize and save to project directory

### Facebook Ad Publishing Workflow
1. Generate images with Kie.ai
2. Upload images to Facebook (may encounter token issues with multipart)
3. Create ad creatives
4. Associate with ad set
5. Track in database.json

### Pain Point Research Workflow
1. Load `reddit-pain-point-research` skill
2. Use Exa.ai to search Reddit for relevant frustrations
3. Analyze and rank by frequency
4. Map to brand messaging pillars

## Pitfalls

1. **Facebook image upload** — multipart/form-data uploads may fail with 401 due to proxy issues with Authorization header replacement
2. **Verbose responses** — user prefers concise; don't over-explain
3. **Brand name leakage** — don't mention "Eden" in public-facing ad copy
4. **Tool call limits** — execute_code has 50 tool calls per script limit
5. **Memory overload** — keep memory entries factual, not procedural (use skills for workflows)

## Memory Triggers

Store these as facts in memory:
- User corrections/preferences
- Environment specifics (paths, credentials)
- API quirks discovered
- Project conventions

Don't store:
- Task progress (use todo tool)
- Session outcomes
- Temporary state

## Skills to Load

Always load relevant skills before starting tasks:
- `kie-ai-image-generation` — for image generation
- `reddit-pain-point-research` — for pain point research
- `fb-ads-performance-dashboard` — for analytics dashboards
- `eden-fb-ads-daily-workflow` — for daily ad workflows
- `graphed-fb-ads-query` — for querying FB Ads data


```

---

### The Full System

Here's what you just built:

1. Creative — Nano Banana 2 generates 10 on-brand ad images per batch, tagged by vibe

1. Structure — Testing campaign (20% of budget) and Winners campaign (80% of budget) running side by side

1. Upload — A Claude Code skill uploads new creative as PAUSED drafts into the Testing campaign via the FB Marketing API

1. Data — A data pipeline syncs FB Ads insights hourly to a warehouse, joined to creative_id

1. Optimizer — The agent kills zero-conversion ads in Testing, promotes target-CPA winners into the Winners campaign, scales the top performers

1. Loop — Hermes Agent runs the whole thing daily at 6am with a spend cap and a Slack report

1. Hosting — Use Graphed for the easy hosted path, or stitch Airbyte + ClickHouse + self-hosted Hermes if you want to own it

1. Outcome — $17 → $3 CPA in four days. No media buyer. No agency. No "let me get back to you Monday."

This is the real GTM engineering. Agents in the wild, doing the job, getting better every day.

Go break it.
