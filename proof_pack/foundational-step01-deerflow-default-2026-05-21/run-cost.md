# DeerFlow DSV4 Pro Step 01 Run Cost

## Usage

- Input tokens: 673,970
- Output tokens: 18,463
- Total tokens: 692,433
- Cache-read input tokens: 620,544
- Cache-miss input tokens: 53,426
- Serper searches: 40
- Jina fetches: 4

## DeepSeek Cost

Pricing used: DeepSeek V4 Pro promotional pricing through 2026-05-31:

- cache-hit input: $0.003625 / 1M tokens
- cache-miss input: $0.435 / 1M tokens
- output: $0.87 / 1M tokens

Formula:

```text
(620,544 / 1,000,000 * 0.003625)
+ (53,426 / 1,000,000 * 0.435)
+ (18,463 / 1,000,000 * 0.87)
= $0.041552592
```

DeepSeek cost: **$0.0416**.

Worst case if every input token were cache-miss: **$0.3092**.

After the promotional window, the same usage at list pricing would be **$0.1662** with cache and **$1.2370** if every input token were cache-miss.

## Search / Fetch Cost

Serper Starter pricing is $1.00 / 1K queries. With 40 searches:

```text
40 / 1000 * 1.00 = $0.04
```

Jina Reader had 4 fetches. The run log does not include Jina token balance deltas. Jina says basic Reader usage is free and API-key usage can charge tokens for higher limits, so cash cost is treated as **$0.00** for this measured estimate unless the key account later shows token overages.

## Total

Best measured estimate:

```text
DeepSeek $0.0416 + Serper $0.0400 + Jina $0.0000 = $0.0816
```

Conservative DeepSeek no-cache bound:

```text
DeepSeek $0.3092 + Serper $0.0400 + Jina $0.0000 = $0.3492
```

Post-promo list-pricing comparison:

```text
With cache: DeepSeek $0.1662 + Serper $0.0400 + Jina $0.0000 = $0.2062
No-cache bound: DeepSeek $1.2370 + Serper $0.0400 + Jina $0.0000 = $1.2770
```

## Sources

- DeepSeek official pricing: https://api-docs.deepseek.com/quick_start/pricing
- Serper official pricing: https://serper.dev/
- Jina Reader pricing/rate limits: https://jina.ai/en-US/reader/
- Captured source manifest: sources/pricing/source_manifest.json
