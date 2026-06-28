# Tenor Quiz Funnel PostHog Analysis

Prepared: 2026-05-15 17:32 CDT  
Campaign: `120246144705220293`  
Quiz URL: `https://shoptenorco.com/8b89a76d/testosterone-support/quiz/`  
Sales page URL: `https://shoptenorco.com/8b89a76d/testosterone-support/sales-page/`

## Executive Summary

The current failure point is not checkout tracking. The paid cohort is not producing Add to Cart / checkout intent.

Clean paid users are reaching the quiz and some are reaching the sales page, but the sales page is producing `0` Add to Cart / checkout clicks in the analyzed clean paid cohort. PostHog does show Add to Cart events from validation/direct/non-clean traffic, so the Add to Cart event itself can fire. The active paid funnel issue appears upstream of checkout: users are either leaving the sales page quickly or reading/skimming without clicking the CTA.

The strongest evidence:

- Meta screenshot for May 14-15 shows `82` link clicks, `74` Entered Presales Page, `17` Entered Sales Page, and no checkout-started metric.
- Clean PostHog paid cohort snapshot showed `77` paid quiz-origin sessions, `11` quiz-to-sales clicks, `13` clean sales-page sessions, and `0` Add to Cart / checkout clicks.
- In clean paid sales-page recordings, `12/13` saw the CTA area, `13/13` saw trust/price instrumentation, and `0/13` clicked Add to Cart / checkout.
- `8/13` clean sales-page sessions stayed at roughly `0-10%` scroll depth.
- `5/13` reached at least `50%` scroll depth, and even those readers did not click Add to Cart.

## Scope And Filters

Analysis window:

- Primary funnel aggregate snapshot: May 14, 2026 00:00 CDT through May 15, 2026 approximately 16:10 CDT.
- Recording / quiz-response recovery continued through May 15, 2026 approximately 17:32 CDT.
- May 15 is a partial day.

Data sources:

- PostHog backend API / HogQL only.
- PostHog session recording snapshot API for recovered visible quiz answer text.
- Meta Ads Manager screenshot supplied in the working thread.

Excluded / treated as test data:

- Maple Grove
- Minneapolis
- Chicago
- deploy-validation
- live-smoke / smoke
- codex validation traffic
- `mos_deploy` validation URLs

Important data-quality note:

PostHog quiz events currently do not store human-readable answer text. They store screen/question IDs such as `screen-dd1b504a`, `countertop`, and generic option IDs such as `heyflow_option`. Exact answer text had to be recovered from session recording DOM click targets. Some recordings are not recoverable because rrweb click target IDs are `-1`.

## Meta Snapshot

From the May 14-15 Meta screenshot:

| Metric | Value |
| --- | ---: |
| Amount spent | `$171.45` |
| Impressions | `2,269` |
| Link clicks | `82` |
| CPC | `$2.09` |
| CTR | `3.61%` |
| Entered Presales Page | `74` |
| Cost per Entered Presales Page | `$2.32` |
| Entered Sales Page | `17` |
| Cost per Entered Sales Page | `$10.09` |
| Sales-to-checkout | no value shown |
| Checkouts initiated | no value shown |

Visible ad-level rows from the screenshot:

| Ad label visible in screenshot | Spend | Impressions | Link clicks | CTR | Entered Presales | Entered Sales |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ProblemAware QUIZ curated-12-quiz | `$75.83` | `804` | `31` | `3.86%` | `27` | `6` |
| ProblemAware QUIZ tenor-19-C018-quiz | `$38.02` | `572` | `21` | `3.67%` | `20` | `9` |
| ProblemAware QUIZ curated-03-quiz | `$20.80` | `159` | `7` | `4.40%` | `5` | `1` |
| ProblemAware QUIZ tenor-18-C017-quiz | `$7.79` | `152` | `5` | `3.29%` | `4` | `0` |
| ProblemAware QUIZ curated-21-quiz | `$3.28` | `134` | `3` | `2.24%` | `3` | `0` |
| ProblemAware QUIZ curated-16-quiz | `$2.12` | `59` | `3` | `5.08%` | `2` | `0` |
| ProblemAware QUIZ curated-05-quiz | `$10.23` | `119` | `3` | `2.52%` | `3` | `0` |
| ProblemAware QUIZ tenor-23-C025-quiz | `$2.05` | `31` | `2` | `6.45%` | `0` | `0` |
| ProblemAware QUIZ curated-19-quiz | `$0.49` | `6` | `2` | `33.33%` | `2` | `0` |
| ProblemAware QUIZ tenor-17-C016-quiz | `$3.04` | `50` | `2` | `4.00%` | `2` | `0` |
| ProblemAware QUIZ curated-27-quiz | `$3.75` | `61` | `1` | `1.64%` | `2` | `0` |
| ProblemAware QUIZ curated-01-quiz | `$0.93` | `36` | `1` | `2.78%` | `1` | `0` |
| ProblemAware QUIZ curated-09-quiz | `$0.22` | `12` | `1` | `8.33%` | `3` | `1` |

Meta-side read:

- Top-of-funnel CTR is not the immediate issue. Overall CTR is `3.61%`, above the RMBC-style minimum threshold of `1.5%` and above the `2.5%` good threshold.
- The problem appears after the click: quiz-to-sales and sales-to-Add-to-Cart are weak.

## RMBC Benchmark Context

Benchmarks referenced from the RMBC/MOS analytics guidelines in this repo:

| Stage | Benchmark / Target |
| --- | ---: |
| Paid ad link CTR minimum | `1.5%` |
| Paid ad link CTR good | `2.5%` |
| Presell / quiz-to-sales CTR target | `30%` |
| Sales-page Add to Cart target for ~$97-$126.99 products | `10%` |
| Sales-page purchase CVR minimum | `3%` |
| Sales-page purchase CVR good | `5%` |
| Checkout CVR target | `30%` |

Observed clean paid funnel snapshot:

| Funnel Stage | May 14 | May 15 partial | Total |
| --- | ---: | ---: | ---: |
| Paid quiz-origin sessions | `46` | `31` | `77` |
| First option presented | `30` | `28` | `58` |
| Selected quiz answers | `13` | `10` | `23` |
| Quiz-to-sales clicks | `7` | `4` | `11` |
| Sales page reached | `8` | `5` | `13` |
| Sales CTA viewed | `8` | `4` | `12` |
| Add to Cart / checkout click | `0` | `0` | `0` |
| Checkout initiated | `0` | `0` | `0` |

Derived:

- Quiz-to-sales click rate: `11 / 77 = 14.3%`, below the `30%` target.
- Clean paid sales-page to Add to Cart: `0 / 13 = 0%`, below the `10%` target for this price band.
- Checkout CVR cannot be meaningfully evaluated because there were no clean paid checkout starts.

## Sales Page Section Map

Approximate mobile section-depth mapping used to interpret scroll recordings:

| Scroll depth | Sales page section |
| ---: | --- |
| `0-11%` | Product / offer hero, price, primary CTA area |
| `11-12%` | Proof bar |
| `12-17%` | """Most T-Boosters Fix One Thing. Tenor Supports All Three.""" |
| `17-32%` | Reviews / social proof |
| `32-40%` | Ingredients / disclosed-ingredient section |
| `40-63%` | Comparison / """The Tenor Difference""" |
| `63-72%` | Science advisory / doctors |
| `72-82%` | Results timeline |
| `82-89%` | Launch kit |
| `89-95%` | FAQ |
| `95%+` | Footer |

Approximate desktop mapping:

| Scroll depth | Sales page section |
| ---: | --- |
| `0-10%` | Product / offer hero |
| `10-11%` | Proof bar |
| `11-20%` | 3-system protocol |
| `20-32%` | Reviews |
| `32-39%` | Ingredients |
| `39-67%` | Comparison |
| `67-79%` | Science advisory |
| `79-88%` | Results timeline |
| `88-95%` | Launch kit / FAQ entry |

## Sales Page Recording Analysis

Clean active paid sales-page sessions analyzed: `13`.

Aggregate behavior:

| Metric | Value |
| --- | ---: |
| Sales-page sessions analyzed | `13` |
| Max scroll `<=10%` | `8/13` |
| Max scroll `>=50%` | `5/13` |
| Max scroll `>=75%` | `3/13` |
| Max scroll `>=90%` | `2/13` |
| CTA viewed | `12/13` |
| Price reveal viewed | `13/13` |
| Trust element viewed | `13/13` |
| Offer stack viewed | `10/13` |
| Add to Cart / checkout clicks | `0/13` |

Per-session sales-page details:

| Session | Date / Time CT | Location | Browser / Device | Ad ID | Recording behavior | Max scroll | Key observed sections | Add to Cart / checkout |
| --- | --- | --- | --- | --- | --- | ---: | --- | ---: |
| `019e2798-8d04-7335-8644-20524ccfb2b5` | May 14 12:48 PM | Atlanta, GA | Facebook Mobile / Mobile | `120246144705180293` | Long, active read; 402s recording, 226s active, 94 clicks | `90%` | Hero, offer, trust, price, comparison, launch kit / FAQ depth | `0` |
| `019e27b9-2819-76bb-aa5d-0b77badde998` | May 14 1:22 PM | Florence, AL | Safari / Desktop | `120246144705180293` | Fast deep skim; 57s recording, 45s active | `75%` | Hero, CTA, offer, comparison / science area | `0` |
| `019e2862-dff5-7a7c-831d-19524576f8eb` | May 14 4:28 PM | Arizona | Chrome / Mobile | `120246144705200293` | Above-fold only; 109s recording, 56s active | `10%` | Hero / offer / CTA | `0` |
| `019e295a-68c1-7312-b8c3-15b9bb3f97b6` | May 14 8:59 PM | Orange City, FL | Facebook Mobile / Mobile | `120246144705180293` | Reached mid-page; clicked offer popup `Yes, lock it in`; no ATC | `50%` | Hero, offer, price, trust, ingredients / comparison entry | `0` |
| `019e296b-c729-7446-8e91-28b4fe3fdf50` | May 14 9:18 PM | Virginia Beach, VA | Mobile Safari | `120246144705180293` | Shallow hero-only session | `10%` | Hero / price / trust / CTA | `0` |
| `019e296c-2e48-7a1f-a490-00d972cfdfc2` | May 14 9:19 PM | Georgia | Facebook Mobile / Mobile | `120246144705180293` | Repeated shallow pageviews / refresh-like behavior; high console errors | `10%` | Hero / price / trust / CTA | `0` |
| `019e296f-b078-7192-904f-ec11835509a2` | May 14 9:22 PM | Hartford, CT | Chrome / Mobile | `120246144705180293` | Shallow hero-only session | `10%` | Hero / price / trust / CTA | `0` |
| `019e29a2-efed-75e6-9241-02fba0735f6a` | May 14 10:20 PM | Waterbury, CT | Facebook Mobile / Mobile | `120246144705270293` | Reached mid-page; 724s recording, mostly inactive | `50%` | Hero, offer, price, trust, ingredients / comparison entry | `0` |
| `019e2be4-cf83-78e8-bd61-0ed9f8d591f8` | May 15 8:48 AM | Cambridge, OH | Facebook Mobile / Mobile | `120246144705060293` | Very quick exit; 16s recording | `0%` | Hero / offer visible instrumentation only | `0` |
| `019e2c68-0159-773f-aef3-6dd5ff1deef3` | May 15 11:13 AM | Fallon, NV | Chrome / Mobile | `120246144705200293` | Deep reader; 750s recording, 219s active; returned/reloaded near top | `90%` | Hero through launch kit / FAQ depth | `0` |
| `019e2ca1-4679-7923-979e-f5a5ae644b59` | May 15 12:14 PM | Georgia | Mobile Safari | `120246144705200293` | Shallow hero-only session | `10%` | Hero / price / trust / CTA | `0` |
| `019e2ca6-724c-7381-9933-516f8383936e` | May 15 12:20 PM | New York | Facebook Mobile / Mobile | `120246144705200293` | Very short; price/offer/trust viewed but CTA view not captured | `0%` | Hero / offer area | `0` |
| `019e2d5f-f6cc-7830-a765-04748d3e7c5b` | May 15 3:42 PM | Oxnard, CA | Chrome / Mobile | `120246144705200293` | Shallow sales session after only two recovered quiz answers | `10%` | Hero / price / trust / CTA | `0` |

Sales-page interpretation:

- CTA visibility is not the main issue. The CTA was visible in nearly all clean paid sales sessions.
- The hero / offer area is not converting most visitors into deeper evaluation or Add to Cart.
- Deep readers are also not clicking Add to Cart, which points to offer / price / subscription / belief objections rather than just scroll-depth visibility.
- The Orange City user clicked the popup `Yes, lock it in`, which is a positive offer-engagement signal, but still did not Add to Cart.

## Quiz Responder List

Clean paid quiz responders identified from event data: `10`.

Important:

- `8` responders had PostHog `$session_id`.
- `2` May 15 responders had missing `$session_id` on the quiz events but had stable `sessionId` / `distinct_id` and matching paid Facebook campaign metadata.
- Exact answer labels were recovered only where recording click targets resolved to option DOM nodes.

| Responder | Date / Time CT | Location | Ad ID | Quiz event evidence | Answer-label recovery status |
| --- | --- | --- | --- | --- | --- |
| `019e2798-8d04-7335-8644-20524ccfb2b5` | May 14 12:46 PM | Atlanta, GA | `120246144705180293` | Full quiz path | Recovered |
| `019e27b9-2819-76bb-aa5d-0b77badde998` | May 14 1:21 PM | Florence, AL | `120246144705180293` | Full quiz path | Recovered |
| `019e27c4-bca2-7ef1-ba54-a2f927ad9589` | May 14 1:34 PM | Atlanta, GA | `120246144705260293` | Partial quiz path | Not recoverable; recording click targets `-1` |
| `019e2816-3f18-73e8-89a0-b82ed5d16c11` | May 14 3:03 PM | West Monroe, LA | `120246144705200293` | First 2 questions | Recovered |
| `019e284f-4807-7324-9ee3-1437eeb0ec34` | May 14 4:05 PM | Morgantown, WV | `120246144704940293` | Full quiz path | Recovered |
| `019e2862-dff5-7a7c-831d-19524576f8eb` | May 14 4:27 PM | Arizona | `120246144705200293` | Full quiz path | Recovered |
| `019e2892-66d3-78f6-9307-a6c2a568267d` | May 14 5:19 PM | Tulsa, OK | `120246144705200293` | First 3-4 questions | Recovered partial |
| `019e295a-68c1-7312-b8c3-15b9bb3f97b6` | May 14 8:57 PM | Orange City, FL | `120246144705180293` | Full quiz path | Not recoverable; recording click targets mostly `-1` |
| `fa6a4ce3-f3ed-46ee-b1cd-9aeb21d5ee39` / recording `019e2d10-fdd3-7841-b623-8d8bc8c553e0` | May 15 2:16 PM | Detroit, MI | `120246144705060293` | Full / near-full quiz path | Recovered with minor ambiguity |
| `f9d9a4ec-fb0f-4ce5-9584-12fa159d50cf` / recording `019e2d5f-f6cc-7830-a765-04748d3e7c5b` | May 15 3:42 PM | Oxnard, CA | `120246144705200293` | First question event; recording shows 2 answers | Recovered partial |

## Recovered Quiz Responses

### Atlanta, GA - Full Quiz

Session: `019e2798-8d04-7335-8644-20524ccfb2b5`  
Ad ID: `120246144705180293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `50+ Years Old` |
| Biggest concern | `Sex drive and performance` |
| Stress symptoms | `Yes` |
| 3pm energy | `Noticeably lower - Afternoon slump hits hard` |
| When changes started | `Over a year ago` |
| Expected results | `Higher energy that lasts all day`; `Increased muscle mass and strength`; `Better sex drive and performance`; `Improved mental clarity and focus`; `All of the above` |
| Body composition | `Soft with some muscle` |
| Sleep | `5-6 hours` |
| Family history | `No` |
| Processed foods | `Occasionally - Mostly whole foods` |

Sales-page behavior:

- Reached sales page.
- Recorded deep sales-page read to about `90%` scroll.
- Saw CTA, offer stack, price, trust modules.
- No Add to Cart / checkout click.

### Florence, AL - Full Quiz

Session: `019e27b9-2819-76bb-aa5d-0b77badde998`  
Ad ID: `120246144705180293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `30 - 39 Years Old` |
| Biggest concern | `Mental focus and clarity` |
| Stress symptoms | `No` |
| 3pm energy | `Slightly tired - Still functional but slower` |
| When changes started | `In the past year` |
| Expected results | `Improved mental clarity and focus` |
| Body composition | `Soft with some muscle` |
| Sleep | `5-6 hours` |
| Family history | `Not Sure` |
| Processed foods | `Occasionally - Mostly whole foods` |

Sales-page behavior:

- Reached sales page.
- Fast skim to about `75%` scroll.
- No Add to Cart / checkout click.

### Atlanta, GA - Partial Quiz, Unrecoverable Answer Labels

Session: `019e27c4-bca2-7ef1-ba54-a2f927ad9589`  
Ad ID: `120246144705260293`

Event data confirms answers were submitted for these question IDs:

| Question ID | Question |
| --- | --- |
| `screen-dd1b504a` | How old are you? |
| `countertop` | Biggest concern |
| `screen-0ef6bf3d` | Stress symptoms |
| `screen-f63af73b` | 3pm energy |
| `screen-4c33fd5a` | When changes started |
| `screen-bbb0a0c9` | Expected results |

Answer labels could not be recovered because the recording click targets were `-1` rather than option DOM node IDs.

### West Monroe, LA - Partial Quiz

Session: `019e2816-3f18-73e8-89a0-b82ed5d16c11`  
Ad ID: `120246144705200293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `50+ Years Old` |
| Biggest concern | `Energy levels` |

This user stopped after the first two recovered answers.

### Morgantown, WV - Full Quiz

Session: `019e284f-4807-7324-9ee3-1437eeb0ec34`  
Ad ID: `120246144704940293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `50+ Years Old` |
| Biggest concern | `Energy levels` |
| Stress symptoms | `No` |
| 3pm energy | `Completely drained - Need caffeine or a nap` |
| When changes started | `Over a year ago` |
| Expected results | `All of the above` |
| Body composition | `Average build` |
| Sleep | `5-6 hours` |
| Family history | `No` |
| Processed foods | `Rarely - I avoid processed foods` |

This user completed the quiz path in events but did not produce clean paid Add to Cart / checkout behavior.

### Arizona - Full Quiz

Session: `019e2862-dff5-7a7c-831d-19524576f8eb`  
Ad ID: `120246144705200293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `50+ Years Old` |
| Biggest concern | `Sex drive and performance` |
| Stress symptoms | `Yes` |
| 3pm energy | `Completely drained - Need caffeine or a nap` |
| When changes started | `Over a year ago` |
| Expected results | `All of the above` |
| Body composition | `Soft with some muscle` |
| Sleep | `Less than 5 hours` |
| Family history | `Yes` |
| Processed foods | `Occasionally - Mostly whole foods` |

Sales-page behavior:

- Reached sales page.
- Stayed shallow at about `10%` scroll.
- No Add to Cart / checkout click.

### Tulsa, OK - Partial Quiz

Session: `019e2892-66d3-78f6-9307-a6c2a568267d`  
Ad ID: `120246144705200293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `50+ Years Old` |
| Biggest concern | `Sex drive and performance` |
| Stress symptoms | `No` |
| 3pm energy | `Slightly tired - Still functional but slower` |

This user stopped after the early quiz questions.

### Orange City, FL - Full Quiz, Unrecoverable Answer Labels

Session: `019e295a-68c1-7312-b8c3-15b9bb3f97b6`  
Ad ID: `120246144705180293`

Event data confirms a full quiz path, including these question IDs:

| Question ID | Question |
| --- | --- |
| `screen-dd1b504a` | How old are you? |
| `countertop` | Biggest concern |
| `screen-0ef6bf3d` | Stress symptoms |
| `screen-f63af73b` | 3pm energy |
| `screen-4c33fd5a` | When changes started |
| `screen-bbb0a0c9` | Expected results |
| `screen-af9b72b0` | Body composition |
| `screen-29a3bfed` | Sleep |
| `screen-97dda69d` | Family history |
| `screen-7bfa168d` | Processed foods |

Answer labels could not be recovered because most recording click targets were `-1`.

Sales-page behavior:

- Reached the sales page.
- Reached about `50%` scroll.
- Clicked the offer popup button `Yes, lock it in`.
- Did not click Add to Cart / checkout.

### Detroit, MI - Full / Near-Full Quiz

MOS session ID: `fa6a4ce3-f3ed-46ee-b1cd-9aeb21d5ee39`  
Recording ID: `019e2d10-fdd3-7841-b623-8d8bc8c553e0`  
Ad ID: `120246144705060293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `50+ Years Old` |
| Biggest concern | `Sex drive and performance` |
| 3pm energy | `Noticeably lower - Afternoon slump hits hard` |
| When changes started | `In the past year` |
| Expected results | `Increased muscle mass and strength`; `Better sex drive and performance`; `All of the above` |
| Body composition | `Soft with some muscle` |
| Sleep | `5-6 hours` |
| Family history | Recording showed `No` and `Not Sure`; treat final as `Not Sure` |
| Processed foods | `Daily - Most meals include processed foods` |

Caveat:

- The recording decoder saw `No` and `Not Sure` close together on the late-question sequence.
- Because the event payload did not include answer text, and May 15 quiz events were missing `$session_id`, the safest interpretation is final family-history answer `Not Sure`.

### Oxnard, CA - Partial Quiz

MOS session ID: `f9d9a4ec-fb0f-4ce5-9584-12fa159d50cf`  
Recording ID: `019e2d5f-f6cc-7830-a765-04748d3e7c5b`  
Ad ID: `120246144705200293`

| Question | Recovered answer |
| --- | --- |
| How old are you? | `50+ Years Old` |
| Biggest concern | `Energy levels` |

Sales-page behavior:

- Reached the sales page after only two recovered quiz answers.
- Stayed shallow at about `10%` scroll.
- No Add to Cart / checkout click.

## Recovered Answer Distribution

Recovered-answer denominator varies by question because some users abandoned early and two sessions had unrecoverable answer labels.

## Quiz Summary Aggregate Table

This table is the fastest read of the quiz response pattern. Counts are based only on answer labels that were recoverable from backend recordings. Two paid responders had quiz events but unrecoverable answer labels because PostHog recording click targets were `-1`.

| Quiz area | Most common answer | Count / denominator | Runner-up / other meaningful answers | Read |
| --- | --- | ---: | --- | --- |
| Age | `50+ Years Old` | `7 / 8` | `30 - 39 Years Old`: `1 / 8` | The recovered respondent pool skews heavily older. |
| Biggest concern | `Sex drive and performance` | `4 / 8` | `Energy levels`: `3 / 8`; `Mental focus and clarity`: `1 / 8` | Main stated demand is sex drive/performance, with energy close behind. |
| Stress symptoms | `No` | `3 / 5` | `Yes`: `2 / 5`; Detroit not counted due ambiguity | Not a clean stress-dominant sample from recovered labels. |
| 3pm energy | Three-way split | `2 / 6` each | `Completely drained`, `Noticeably lower`, and `Slightly tired` each appeared twice | Energy fatigue is present, but severity varies. |
| When changes started | `Over a year ago` | `3 / 5` | `In the past year`: `2 / 5` | Most recovered full responders report a persistent issue, not a brand-new problem. |
| Expected results | `All of the above` | `4 selections` | `Increased muscle mass and strength`: `2`; `Better sex drive and performance`: `2`; `Improved mental clarity and focus`: `2`; `Higher energy`: `1` | Multi-select behavior shows broad outcome demand rather than one narrow job-to-be-done. |
| Body composition | `Soft with some muscle` | `4 / 5` | `Average build`: `1 / 5` | Recovered full responders mostly self-identify as not lean/optimized. |
| Sleep | `5-6 hours` | `4 / 5` | `Less than 5 hours`: `1 / 5` | Sleep quality/duration is a common weakness in the recovered full responders. |
| Family history | Tie: `No` and `Not Sure` | `2 / 5` each | `Yes`: `1 / 5` | No single dominant family-history signal. |
| Processed foods | `Occasionally - Mostly whole foods` | `3 / 5` | `Daily`: `1 / 5`; `Rarely`: `1 / 5` | Diet signal is mixed; not all respondents self-report poor diet. |

## Respondent Demographic Aggregate

This table includes all `10` clean paid quiz responders identified from event data, including the two sessions where exact answer labels were not recoverable.

| Demographic / traffic dimension | Aggregate |
| --- | --- |
| Identified paid quiz responders | `10` |
| Date split | May 14: `8 / 10`; May 15 partial: `2 / 10` |
| Geography | Georgia: `2`; Alabama: `1`; Louisiana: `1`; West Virginia: `1`; Arizona: `1`; Oklahoma: `1`; Florida: `1`; Michigan: `1`; California: `1` |
| City-level concentration | Atlanta, GA had `2` responders; all other identified city/state pairs had `1` each |
| Device class | Mobile: `8 / 10`; Tablet: `1 / 10`; Desktop: `1 / 10` |
| Browser / app surface | Facebook in-app / Facebook Mobile: about `5 / 10`; Chrome Mobile: about `4 / 10`; Safari Desktop: `1 / 10` |
| Most common quiz age demographic | `50+ Years Old`: `7 / 8` recovered age answers |
| Most common ad ID among quiz responders | `120246144705200293`: `4 / 10`; next `120246144705180293`: `3 / 10` |
| Other ad IDs represented | `120246144705260293`: `1`; `120246144704940293`: `1`; `120246144705060293`: `1` |
| Completion pattern | Full / near-full quiz event path: `6 / 10`; early partial path: `4 / 10` |
| Answer-label recovery | Recovered full or partial answer labels: `8 / 10`; unrecoverable labels: `2 / 10` |

Summary read:

- The demographic pattern is mostly mobile, Facebook-sourced, and older.
- The strongest recovered quiz demographic is `50+ Years Old`.
- The top pain signal is sex drive/performance, with energy close behind.
- The recovered responder profile looks directionally aligned with the testosterone-support offer; the larger issue remains converting that intent into Add to Cart.

| Question | Distribution from recovered answer labels |
| --- | --- |
| Age | `50+ Years Old`: 7; `30 - 39 Years Old`: 1 |
| Biggest concern | `Sex drive and performance`: 4; `Energy levels`: 3; `Mental focus and clarity`: 1 |
| Stress symptoms | `Yes`: 2; `No`: 3; Detroit ambiguous / not counted |
| 3pm energy | `Completely drained`: 2; `Noticeably lower`: 2; `Slightly tired`: 2 |
| When changes started | `Over a year ago`: 3; `In the past year`: 2 |
| Expected results | `All of the above`: 4; `Increased muscle mass and strength`: 2; `Better sex drive and performance`: 2; `Improved mental clarity and focus`: 2; `Higher energy that lasts all day`: 1 |
| Body composition | `Soft with some muscle`: 4; `Average build`: 1 |
| Sleep | `5-6 hours`: 4; `Less than 5 hours`: 1 |
| Family history | `No`: 2; `Not Sure`: 2; `Yes`: 1 |
| Processed foods | `Occasionally - Mostly whole foods`: 3; `Rarely - I avoid processed foods`: 1; `Daily - Most meals include processed foods`: 1 |

Audience read:

- The recovered audience is directionally relevant: mostly older men, energy / sex-drive concerns, sleep issues, and multi-month/year decline.
- This does not look like a completely misqualified audience from the recovered answer sample.
- The conversion failure is more likely in commitment-building, quiz-to-sales transition, offer framing, price/subscription confidence, or sales-page buying motivation.

## Analytics / Tracking Issues Found

### 1. Quiz answer text is not captured in events

Current quiz events store:

- `questionId`
- `optionId`
- `screenId`-like values
- generic `heyflow_option`

They do not reliably store:

- `question_text`
- `option_text`
- final multi-select answer array

Impact:

- Dashboards cannot show """what users answered""" without session recording recovery.
- Recording recovery is slow, rate-limited, and not always possible.

Recommended fix:

Capture these properties on quiz answer events:

- `question_id`
- `question_text`
- `question_index`
- `option_id`
- `option_text`
- `answer_text`
- `selected_options`
- `is_multi_select`
- `quiz_id`
- `quiz_version`
- `campaign_id`
- `ad_id`
- `adset_id`
- `posthog_session_id`
- `mos_session_id`

### 2. May 15 quiz events sometimes miss `$session_id`

Observed:

- Detroit and Oxnard quiz events had stable `sessionId` / `distinct_id` / campaign metadata but missing PostHog `$session_id`.

Impact:

- Session-level funnels can undercount quiz responders or disconnect quiz responses from recordings.

Recommended fix:

- Ensure all frontend events carry both PostHog `$session_id` and MOS `sessionId`.
- Normalize dashboard joins to use a fallback key only for reporting, but keep canonical session IDs intact at capture time.

### 3. Some recordings have unusable click targets

Observed:

- Atlanta partial session and Orange City full quiz path had rrweb click targets of `-1`.

Impact:

- Exact answer labels cannot be reconstructed from recordings even though quiz events confirm submitted question IDs.

Recommended fix:

- Do not rely on recordings for answer analytics.
- Store answer text at event-capture time.

### 4. Alias / duplicate events need dashboard handling

Observed event pairs include:

- `QuizQuestionSubmitted` and `quiz_question_submitted`
- `QuizOptionSelected` and `quiz_option_selected`
- `AddToCart` and `add_to_cart`
- `Entered Sales Page`, `EnteredSales`, `sales_page_view`

Impact:

- Counts can double unless dashboard logic deduplicates by canonical event role or event ID.

Recommended dashboard approach:

- Use canonical event role where available.
- Deduplicate by `mos_event_id` / `eventId` when available.
- Maintain a canonical event taxonomy for funnel dashboards.

## Interpretation

## Ad Hook to Quiz Page Congruence - Top Spend Ads

Window: Meta ad insights for `May 14-15, 2026`; PostHog clean paid sessions from `May 14 00:00 CDT` through `May 16 00:00 CDT`. Clean filter excludes Maple Grove, Minneapolis, and Chicago.

Completion definitions:

- `Answered any`: session has at least one quiz answer/submit event.
- `Full completion`: same session has quiz submit events reaching late/final quiz screens.
- `Completion signal`: broader signal including recommendation/completion events where quiz events appear split across sessions. Use directionally because the current instrumentation can split quiz activity and recommendation events.

| Ad ID | Ad / concept | Spend | Link clicks | Clean landed sessions | Answered any | Full completion | Completion signal | Congruence read |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `120246144705200293` | `curated-12-quiz` / Concept 5 offer-proof-guarantee | `$83.74` | `41` | `34` | `5` / `14.7%` | `1` / `2.9%` | `3` / `8.8%` | Weakest high-spend bridge |
| `120246144705180293` | `tenor-19-C018-quiz` / Concept 5 offer-proof-guarantee | `$43.85` | `24` | `25` | `4` / `16.0%` | `4` / `16.0%` | `9` / `36.0%` | Stronger visual bridge |
| `120246144705060293` | `curated-03-quiz` / Concept 5 offer-proof-guarantee | `$20.93` | `7` | `5` | `1` / `20.0%` | `1` / `20.0%` | `1` / `20.0%` | Good conceptual match, low sample |
| `120246144704940293` | `curated-05-quiz` / Concept 4 daily-decline-system-problem | `$15.36` | `4` | `4` | `1` / `25.0%` | `1` / `25.0%` | `1` / `25.0%` | Good symptom match, low sample |

### Quiz page promise

The quiz page opens with:

- Headline: `Find Out What's Really Happening With Your Testosterone`
- Subhead: `This 2-minute assessment analyzes your symptoms, lifestyle, and risk factor in order to find a solution.`
- Proof/testimonial: a skeptical customer says the quiz helped him get his T levels back and made him and his wife happy.
- First question: `How old are you?`
- Offer strip: `50% Off + $70 of Free Gifts + 90 Day Guarantee`

### Top spend diagnosis

`120246144705200293` / `curated-12-quiz` is the main concern.

- The ad copy promises `429,576+ men took this 60-second test`, says something showed up in `bloodwork`, and says the quiz tells users `which of the three hormones is hitting you hardest right now`.
- The creative visual says `Not Feeling Like Yourself Lately?` and promises a guided quiz to identify the next step.
- The quiz page partially matches the visual hook, but it does not echo the strongest copy promises: `429,576+`, `60-second`, `7 questions`, `bloodwork`, or `three hormones`.
- The first page also says `2-minute assessment`, creating a direct time-promise mismatch with the ad's `60-second test`.
- Behavior supports a congruence problem: this ad has the most spend and clicks but only `14.7%` of clean landed sessions answered any quiz question and only `2.9%` reached a full in-session completion.

RMBC read: the ad lead is a social-proof / diagnostic curiosity lead, but the landing page lead is a generic testosterone quiz lead. The ad creates a proof-heavy, lab-like expectation; the page immediately becomes a symptom/lifestyle intake. That is a Brief and Copy mismatch more than a traffic-quality issue.

`120246144705180293` / `tenor-19-C018-quiz` uses essentially the same body copy, but its visual bridge is stronger.

- The visual centers the Daily Drive Essentials bottle, says `Take the Quiz`, `Not Feeling Like Yourself?`, and `Start the Free Quiz`.
- That makes the click feel like a product-backed quiz path rather than a pure diagnostic/bloodwork reveal.
- It produced a much better full-completion pattern: `4 / 25` full completions and `9 / 25` broader completion signals.

RMBC read: this ad is more product/solution-aware than `curated-12`, so the page's immediate testosterone quiz and offer strip feel less abrupt. The visual pre-sells the product/protocol transition that the page eventually makes.

`120246144705060293` / `curated-03-quiz` is directionally congruent but under-sampled.

- The visual hook says `Not feeling like yourself?` and names `energy, drive, focus, recovery` and `root cause`.
- The quiz page matches that symptom/root-cause frame better than it matches the bloodwork-heavy ad body.
- Small sample, but `1 / 5` clean landed sessions reached full completion.

RMBC read: this is the cleanest Research-to-Copy bridge for a problem-aware man who is trying to explain decline, not necessarily buy a bottle immediately.

`120246144704940293` / `curated-05-quiz` is also directionally congruent but low volume.

- The body hook is `Your grandfather had more testosterone at 60 than you have at 35`, then blames modern life and sends users to a `60-second test`.
- The visual says `Unlock Your Energy & Drive Again`, lists `Energy & Focus`, `Daily Stamina`, `Drive & Recovery`, `Guided Protocol`, and `For Men 40+`.
- The quiz page matches testosterone/energy/drive, but it does not continue the `modern life` mechanism from the ad.
- Small sample, but `1 / 4` clean landed sessions reached full completion.

RMBC read: the persona is a premature-decline man who wants an external explanation for why he feels older than he should. The page is acceptable, but a stronger bridge would echo the `modern life` cause before asking age.

### Persona Signals by Winning/Completing Ads

| Ad ID | Persona attracted | Awareness level | Core emotional driver | What the quiz page should immediately confirm |
|---|---|---|---|---|
| `120246144705200293` | Skeptical proof-seeker who wants diagnostic certainty | Problem-aware to solution-aware | `I need to know what's really happening before I trust another supplement` | This is a fast, specific T-signal assessment with credible proof and a clear result |
| `120246144705180293` | Product-curious man open to a supplement protocol | Solution-aware | `I don't feel like myself and want a concrete next step` | The quiz leads to a Daily Drive Essentials protocol fit/recommendation |
| `120246144705060293` | Symptom/root-cause seeker | Problem-aware | `Energy, focus, drive, or recovery changed and I want the reason` | The quiz will identify likely root causes behind those changes |
| `120246144704940293` | Premature-decline / modern-life believer | Problem-aware | `This is not laziness; something in modern life is draining me` | The quiz evaluates age, lifestyle, stress, and daily risk factors |

### Recommendation

The biggest fix is not the ad copy alone. The quiz landing page should mirror the promise of the highest-spend ads before the first question:

1. If keeping the `429,576+ men took this 60-second test` hook, make the quiz hero echo `60-second`, `7 questions`, and the social proof number.
2. If keeping the `bloodwork` / `three hormones` promise, the page needs a clearer diagnostic bridge explaining what the quiz can and cannot identify before asking age.
3. If the page remains `2-minute assessment` plus generic symptom/lifestyle language, then the top-spend ad copy should be softened toward the current page promise and away from the stronger lab/bloodwork reveal.
4. Preserve the `Not feeling like yourself` visual language. The better-performing paths all match that problem-aware symptom frame.
5. Consider routing Concept 5 offer/proof/guarantee ads to a quiz hero variant that starts with proof and diagnostic specificity, while Concept 4 daily-decline ads get a hero variant about modern-life/stress/lifestyle causes.

The ads are generating clicks. The quiz is collecting some relevant user intent. The sales page is not turning that intent into cart behavior.

The strongest problem areas:

1. **Quiz-to-sales conversion is below target.**  
   Clean observed quiz-to-sales is about `14.3%`, versus the `30%` target.

2. **Sales-page Add to Cart is zero in clean paid traffic.**  
   Clean observed sales-page to Add to Cart is `0%`, versus the `10%` target for the expected price band.

3. **Above-the-fold sales-page users are not compelled.**  
   Most clean sales-page visitors saw the hero / price / CTA area and did not continue deeply.

4. **Deep readers still do not click.**  
   The two deepest sessions reached about `90%` scroll depth but still did not Add to Cart.

5. **The offer popup can get engagement, but still does not create cart intent.**  
   Orange City clicked `Yes, lock it in`, then still did not Add to Cart.

## Recommended Next Actions

### Analytics fixes

1. Add explicit quiz answer text capture to PostHog.
2. Fix missing `$session_id` on quiz events.
3. Deduplicate canonical vs alias event names in dashboards.
4. Add a clean paid traffic filter to dashboards:
   - include `utm_source=facebook` or campaign `120246144705220293`
   - exclude deploy/test/codex/smoke traffic
   - exclude Maple Grove, Minneapolis, Chicago
5. Add dashboard panels for:
   - quiz responder count
   - answer distribution by question
   - quiz question drop-off
   - quiz-to-sales click rate
   - sales-page scroll-depth distribution
   - sales CTA view-to-click
   - Add to Cart / checkout click rate

### Funnel / offer diagnostics

1. Review the sales-page hero and first-screen offer. Most paid sales-page users do not scroll past the first offer area.
2. Review subscription / price framing. Deep readers still do not click, which often points to unresolved price or commitment objection.
3. Review quiz-to-sales transition copy. The quiz may not be building enough commitment before asking users to buy.
4. Consider a sales-page CTA click diagnostic event that captures:
   - CTA ID
   - CTA copy
   - product variant
   - selected package / subscription state
   - whether popup was shown
   - whether popup was accepted
5. Treat current checkout-start absence as a downstream symptom until Add to Cart clicks appear in clean paid traffic.

## Bottom Line

The campaign is not blocked by checkout tracking. It is blocked by insufficient buyer action before checkout.

The audience signal from recovered quiz responses is not obviously wrong: users are older, concerned with energy / sex drive, and reporting sleep / decline patterns that match the offer. The key issue is that qualified or semi-qualified users are not clicking Add to Cart after seeing the offer.

The immediate operational need is to fix quiz answer instrumentation so the team can see answer distributions directly in PostHog dashboards. The immediate funnel need is to improve the quiz-to-sales transition and sales-page offer/CTA effectiveness, because clean paid Add to Cart is currently `0`.
