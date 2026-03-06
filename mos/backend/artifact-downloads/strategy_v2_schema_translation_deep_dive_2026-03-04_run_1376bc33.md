# Strategy V2 Schema Translation Deep Dive

- Run ID: `1376bc33-9e3c-47a4-9701-061e2e32668e`
- Copy loop report log ID: `ddd173c5-f09e-4033-a999-03293202a632`
- Timestamp (UTC): `2026-03-04T21:05:00.296068+00:00`

## High-level
- Headline QA status: `PASS`
- Final run error: `TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; errors=hero.primary_cta_url: Extra inputs are not permitted; hero.trust_badges: Extra inputs are not permitted; problem.title: Field required; problem.paragraphs: Field required; problem.emphasis_line: Field required; problem.headline: Extra inputs are not permitted; problem.body: Extra inputs are not permitted; mechanism.comparison.columns.pup: Field required; ... +51 more. Remediation: return template_payload that exactly matches the required template contract.`
- Page attempts: `3`

## Page attempt 1
- failure_message: `Sales template payload JSON parse failed. Details: Failed to parse required JSON object from text content. Remediation: inspect upstream step output.`
- failure_reason_codes: `None`
- presell_quality_pass: `True`
- presell_quality_metrics: words=1309, sections=6, ctas=1
- sales_quality_pass: `False`
- sales_quality_metrics: words=86, sections=1, ctas=0
- sales_quality_failures:
  - `SALES_PAGE_WARM_WORD_FLOOR`: total_words=86, required>=1800
  - `SALES_PAGE_WARM_SECTION_COUNT`: section_count=1, required>=10
  - `SALES_PROOF_DEPTH`: proof_words=0, required>=220
  - `SALES_GUARANTEE_DEPTH`: guarantee_words=0, required>=80
- sales_template_payload_json_len: `13`
- sales_template_payload_json_parse: `FAILED` (JSONDecodeError: Expecting value: line 1 column 1 (char 0))
```text
not regulated
```

## Page attempt 2
- failure_message: `TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; errors=hero.purchase_title: Field required; hero.headline: Extra inputs are not permitted; hero.subheadline: Extra inputs are not permitted; hero.primary_cta_url: Extra inputs are not permitted; problem: Field required; mechanism.title: Field required; mechanism.paragraphs: Field required; mechanism.comparison.columns: Input should be a valid dictionary or instance of TemplateFitPackComparisonColumns; ... +69 more. Remediation: return template_payload that exactly matches the required template contract.`
- failure_reason_codes: `['TEMPLATE_PAYLOAD_VALIDATION']`
- presell_quality_pass: `True`
- presell_quality_metrics: words=1310, sections=6, ctas=1
- sales_quality_pass: `True`
- sales_quality_metrics: words=2488, sections=12, ctas=3
- sales_template_payload_json_len: `10313`
- sales_template_payload_json_parse: `SUCCESS`
- missing_top_level_keys: `['cta_close', 'faq', 'problem']`
- extra_top_level_keys: `['cta_primary', 'legal_disclaimer', 'problem_recap', 'product_name', 'product_subtitle', 'schema']`
- TemplateFitPack validation: `FAIL`
- validation_error_count: `77`
- validation_error_types: `{'missing': 32, 'extra_forbidden': 37, 'model_type': 1, 'string_type': 5, 'string_too_long': 2}`
### Validation errors (full)
```text
01. hero.purchase_title: Field required [missing]
02. hero.headline: Extra inputs are not permitted [extra_forbidden]
03. hero.subheadline: Extra inputs are not permitted [extra_forbidden]
04. hero.primary_cta_url: Extra inputs are not permitted [extra_forbidden]
05. problem: Field required [missing]
06. mechanism.title: Field required [missing]
07. mechanism.paragraphs: Field required [missing]
08. mechanism.comparison.columns: Input should be a valid dictionary or instance of TemplateFitPackComparisonColumns [model_type]
09. mechanism.comparison.rows.0.label: Field required [missing]
10. mechanism.comparison.rows.0.pup: Field required [missing]
11. mechanism.comparison.rows.0.disposable: Field required [missing]
12. mechanism.comparison.rows.0.feature: Extra inputs are not permitted [extra_forbidden]
13. mechanism.comparison.rows.0.col1: Extra inputs are not permitted [extra_forbidden]
14. mechanism.comparison.rows.0.col2: Extra inputs are not permitted [extra_forbidden]
15. mechanism.comparison.rows.1.label: Field required [missing]
16. mechanism.comparison.rows.1.pup: Field required [missing]
17. mechanism.comparison.rows.1.disposable: Field required [missing]
18. mechanism.comparison.rows.1.feature: Extra inputs are not permitted [extra_forbidden]
19. mechanism.comparison.rows.1.col1: Extra inputs are not permitted [extra_forbidden]
20. mechanism.comparison.rows.1.col2: Extra inputs are not permitted [extra_forbidden]
21. mechanism.comparison.rows.2.label: Field required [missing]
22. mechanism.comparison.rows.2.pup: Field required [missing]
23. mechanism.comparison.rows.2.disposable: Field required [missing]
24. mechanism.comparison.rows.2.feature: Extra inputs are not permitted [extra_forbidden]
25. mechanism.comparison.rows.2.col1: Extra inputs are not permitted [extra_forbidden]
26. mechanism.comparison.rows.2.col2: Extra inputs are not permitted [extra_forbidden]
27. mechanism.comparison.rows.3.label: Field required [missing]
28. mechanism.comparison.rows.3.pup: Field required [missing]
29. mechanism.comparison.rows.3.disposable: Field required [missing]
30. mechanism.comparison.rows.3.feature: Extra inputs are not permitted [extra_forbidden]
31. mechanism.comparison.rows.3.col1: Extra inputs are not permitted [extra_forbidden]
32. mechanism.comparison.rows.3.col2: Extra inputs are not permitted [extra_forbidden]
33. mechanism.comparison.rows.4.label: Field required [missing]
34. mechanism.comparison.rows.4.pup: Field required [missing]
35. mechanism.comparison.rows.4.disposable: Field required [missing]
36. mechanism.comparison.rows.4.feature: Extra inputs are not permitted [extra_forbidden]
37. mechanism.comparison.rows.4.col1: Extra inputs are not permitted [extra_forbidden]
38. mechanism.comparison.rows.4.col2: Extra inputs are not permitted [extra_forbidden]
39. mechanism.headline: Extra inputs are not permitted [extra_forbidden]
40. mechanism.intro: Extra inputs are not permitted [extra_forbidden]
41. social_proof.badge: Field required [missing]
42. social_proof.title: Field required [missing]
43. social_proof.rating_label: Field required [missing]
44. social_proof.summary: Field required [missing]
45. social_proof.headline: Extra inputs are not permitted [extra_forbidden]
46. social_proof.testimonials: Extra inputs are not permitted [extra_forbidden]
47. whats_inside.benefits.0: Input should be a valid string [string_type]
48. whats_inside.benefits.1: Input should be a valid string [string_type]
49. whats_inside.benefits.2: Input should be a valid string [string_type]
50. whats_inside.benefits.3: Input should be a valid string [string_type]
51. whats_inside.benefits.4: Input should be a valid string [string_type]
52. whats_inside.offer_helper_text: Field required [missing]
53. whats_inside.headline: Extra inputs are not permitted [extra_forbidden]
54. bonus.free_gifts_title: Field required [missing]
55. bonus.free_gifts_body: String should have at most 220 characters [string_too_long]
56. bonus.headline: Extra inputs are not permitted [extra_forbidden]
57. bonus.items: Extra inputs are not permitted [extra_forbidden]
58. bonus.total_value: Extra inputs are not permitted [extra_forbidden]
59. bonus.your_price: Extra inputs are not permitted [extra_forbidden]
60. guarantee.title: Field required [missing]
61. guarantee.paragraphs: Field required [missing]
62. guarantee.why_title: Field required [missing]
63. guarantee.why_body: Field required [missing]
64. guarantee.closing_line: Field required [missing]
65. guarantee.headline: Extra inputs are not permitted [extra_forbidden]
66. guarantee.body: Extra inputs are not permitted [extra_forbidden]
67. guarantee.duration_days: Extra inputs are not permitted [extra_forbidden]
68. guarantee.type: Extra inputs are not permitted [extra_forbidden]
69. faq: Field required [missing]
70. cta_close: Field required [missing]
71. urgency_message: String should have at most 220 characters [string_too_long]
72. schema: Extra inputs are not permitted [extra_forbidden]
73. product_name: Extra inputs are not permitted [extra_forbidden]
74. product_subtitle: Extra inputs are not permitted [extra_forbidden]
75. problem_recap: Extra inputs are not permitted [extra_forbidden]
76. cta_primary: Extra inputs are not permitted [extra_forbidden]
77. legal_disclaimer: Extra inputs are not permitted [extra_forbidden]
```

## Page attempt 3
- failure_message: `TEMPLATE_PAYLOAD_VALIDATION: template_id=sales-pdp; errors=hero.primary_cta_url: Extra inputs are not permitted; hero.trust_badges: Extra inputs are not permitted; problem.title: Field required; problem.paragraphs: Field required; problem.emphasis_line: Field required; problem.headline: Extra inputs are not permitted; problem.body: Extra inputs are not permitted; mechanism.comparison.columns.pup: Field required; ... +51 more. Remediation: return template_payload that exactly matches the required template contract.`
- failure_reason_codes: `['TEMPLATE_PAYLOAD_VALIDATION']`
- presell_quality_pass: `True`
- presell_quality_metrics: words=1260, sections=6, ctas=1
- sales_quality_pass: `True`
- sales_quality_metrics: words=2291, sections=12, ctas=3
- sales_template_payload_json_len: `8767`
- sales_template_payload_json_parse: `SUCCESS`
- missing_top_level_keys: `['cta_close', 'faq']`
- extra_top_level_keys: `['pricing', 'template_id']`
- TemplateFitPack validation: `FAIL`
- validation_error_count: `59`
- validation_error_types: `{'extra_forbidden': 24, 'missing': 33, 'string_too_long': 2}`
### Validation errors (full)
```text
01. hero.primary_cta_url: Extra inputs are not permitted [extra_forbidden]
02. hero.trust_badges: Extra inputs are not permitted [extra_forbidden]
03. problem.title: Field required [missing]
04. problem.paragraphs: Field required [missing]
05. problem.emphasis_line: Field required [missing]
06. problem.headline: Extra inputs are not permitted [extra_forbidden]
07. problem.body: Extra inputs are not permitted [extra_forbidden]
08. mechanism.comparison.columns.pup: Field required [missing]
09. mechanism.comparison.columns.disposable: Field required [missing]
10. mechanism.comparison.columns.left: Extra inputs are not permitted [extra_forbidden]
11. mechanism.comparison.columns.right: Extra inputs are not permitted [extra_forbidden]
12. mechanism.comparison.rows.0.label: Field required [missing]
13. mechanism.comparison.rows.0.pup: Field required [missing]
14. mechanism.comparison.rows.0.disposable: Field required [missing]
15. mechanism.comparison.rows.0.left: Extra inputs are not permitted [extra_forbidden]
16. mechanism.comparison.rows.0.right: Extra inputs are not permitted [extra_forbidden]
17. mechanism.comparison.rows.1.label: Field required [missing]
18. mechanism.comparison.rows.1.pup: Field required [missing]
19. mechanism.comparison.rows.1.disposable: Field required [missing]
20. mechanism.comparison.rows.1.left: Extra inputs are not permitted [extra_forbidden]
21. mechanism.comparison.rows.1.right: Extra inputs are not permitted [extra_forbidden]
22. mechanism.comparison.rows.2.label: Field required [missing]
23. mechanism.comparison.rows.2.pup: Field required [missing]
24. mechanism.comparison.rows.2.disposable: Field required [missing]
25. mechanism.comparison.rows.2.left: Extra inputs are not permitted [extra_forbidden]
26. mechanism.comparison.rows.2.right: Extra inputs are not permitted [extra_forbidden]
27. mechanism.comparison.rows.3.label: Field required [missing]
28. mechanism.comparison.rows.3.pup: Field required [missing]
29. mechanism.comparison.rows.3.disposable: Field required [missing]
30. mechanism.comparison.rows.3.left: Extra inputs are not permitted [extra_forbidden]
31. mechanism.comparison.rows.3.right: Extra inputs are not permitted [extra_forbidden]
32. mechanism.comparison.rows.4.label: Field required [missing]
33. mechanism.comparison.rows.4.pup: Field required [missing]
34. mechanism.comparison.rows.4.disposable: Field required [missing]
35. mechanism.comparison.rows.4.left: Extra inputs are not permitted [extra_forbidden]
36. mechanism.comparison.rows.4.right: Extra inputs are not permitted [extra_forbidden]
37. social_proof.badge: Field required [missing]
38. social_proof.title: Field required [missing]
39. social_proof.rating_label: Field required [missing]
40. social_proof.summary: Field required [missing]
41. social_proof.headline: Extra inputs are not permitted [extra_forbidden]
42. social_proof.testimonials: Extra inputs are not permitted [extra_forbidden]
43. whats_inside.offer_helper_text: Field required [missing]
44. whats_inside.headline: Extra inputs are not permitted [extra_forbidden]
45. bonus.free_gifts_title: Field required [missing]
46. bonus.free_gifts_body: String should have at most 220 characters [string_too_long]
47. bonus.headline: Extra inputs are not permitted [extra_forbidden]
48. guarantee.title: Field required [missing]
49. guarantee.paragraphs: Field required [missing]
50. guarantee.why_title: Field required [missing]
51. guarantee.why_body: Field required [missing]
52. guarantee.closing_line: Field required [missing]
53. guarantee.headline: Extra inputs are not permitted [extra_forbidden]
54. guarantee.body: Extra inputs are not permitted [extra_forbidden]
55. faq: Field required [missing]
56. cta_close: Field required [missing]
57. urgency_message: String should have at most 220 characters [string_too_long]
58. template_id: Extra inputs are not permitted [extra_forbidden]
59. pricing: Extra inputs are not permitted [extra_forbidden]
```

