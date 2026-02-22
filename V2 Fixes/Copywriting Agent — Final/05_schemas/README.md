# 05_schemas — Input/Output Contracts

## What This Contains
JSON schemas that define the data contracts for all system inputs and outputs.

### headline_input.json
Input schema for headline generation. Required fields:
- page_type (listicle, advertorial, sales_page, meta_ad, tiktok, etc.)
- awareness_level (unaware, problem_aware, solution_aware, product_aware, most_aware)
- key_benefit, target_audience_segment, mechanism_hint
- beliefs_to_target (B1-B8)
- archetype_preference, emotional_register, quantity

### headline_output.json
Output schema for generated headlines. Per-headline:
- text, archetype, belief_targeted, emotional_register
- laws_demonstrated (7 Laws of Headline Engineering)
- anatomy (pattern_interrupt, relevance_signal, implicit_promise)
- score object (4 dimensions with sub-tests)
- promise_contract (loop_question, specific_promise, delivery_test, minimum_delivery)

### presales_listicle.schema.json
Template schema for presale listicle pages. Defines:
- HeroConfig, Badge, Reason, Pitch, ReviewSlide, Reviews, ReviewWall
- Module structure: hero, reasons, reviews, marquee, pitch, review_wall, footer

### sales_pdp.schema.json
Template schema for sales page PDP (Product Display Page). Defines:
- Hero (header, gallery, purchase flow), Videos, Marquee, Story, Comparison
- ReviewSlider, Guarantee, FAQ, ReviewWall, Footer, Modals
