#!/usr/bin/env python3
"""
HEADLINE QA LOOP — LLM-Powered Auto-Fix Pipeline
=================================================
Scores headlines with headline_scorer_v2.py (deterministic),
identifies failures, and uses an LLM to rewrite and fix.

Architecture:
  Input headline -> Score (v2, deterministic) -> Check tier
    -> If tier >= min_tier: PASS, return
    -> If tier < min_tier: LLM reads failures + fix_hints -> rewrites -> rescore
    -> Repeat up to 3 total iterations
    -> Best-scoring version across all iterations wins
    -> Only output if final best >= A tier (80%)

Usage:
  python3 headline_qa_loop.py "Your headline here" --page-type listicle
  python3 headline_qa_loop.py --batch headlines.txt --page-type listicle
  python3 headline_qa_loop.py "headline" --max-iterations 2 --min-tier S
  python3 headline_qa_loop.py "headline" --output-json
  python3 headline_qa_loop.py "headline" --dry-run  # score only, no LLM
"""

import sys
import os
import json
import argparse
import time

# Add eval directory to path for importing scorer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import headline_scorer_v2 as scorer


# ============================================================
# SECTION 1: CONSTANTS
# ============================================================

BRAND_CONTEXT = """
BRAND: The Honest Herbalist Handbook -- a safety-focused herbal reference for
health-conscious women and parents.

VOICE: The calm, protective guide. Anti-hype, evidence-grounded, safety-first.
Think: experienced friend with a deep reference library.

BANNED WORDS (never use these): miracle, cure, cures, secret, secrets,
breakthrough, revolutionary, superfood, detox, cleanse, shocking, mind-blowing,
hack, guru, warrior, goddess, queen, mama, magic, magical, game-changer,
life-changing, Big Pharma, chemical-free, all-natural, guaranteed to,
they don't want you to know, ancient secret, lost remedy, lost cure

7 LAWS OF HEADLINE ENGINEERING:
1. Open Loop: Create unresolved cognitive tension via incomplete ideas or contradictions
2. Pain Naming: Name the wound before offering the bandage
3. Unique Mechanism: Promise a result they haven't heard said this way before
4. Specificity: Concrete numbers, unusual numbers, descriptors, and timeframes
5. Simplicity: Short words, short phrases, single pass comprehension
6. Credibility: Reference sources, real events, or measurable outcomes
7. Time Compression: Shorter timeframes create stronger desire (for info access, NOT health outcomes)

3 REQUIRED HEADLINE COMPONENTS:
1. Pattern Interrupt: Stops the scroll with something unexpected
2. Relevance Signal: Makes the reader feel "this is for me"
3. Implicit Promise: Tells the reader what continuing gives them
"""

TIER_ORDER = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1, "DISQUALIFIED": 0}

WORD_COUNT_RANGES = {
    "listicle": "8-14",
    "advertorial": "10-18",
    "sales_page": "8-20",
}
LLM_CALL_TIMEOUT_SECONDS = float(os.getenv("STRATEGY_V2_HEADLINE_QA_CALL_TIMEOUT_SECONDS", "45"))
LLM_CALL_MAX_RETRIES = max(0, int(os.getenv("STRATEGY_V2_HEADLINE_QA_CALL_MAX_RETRIES", "0")))

# Page-type-specific calibration context for the LLM.
# Extracted from WORKFLOW.md Section 4 (Headline-to-Page-Type Calibration)
# and Section 2 (Page-Type Templates).
PAGE_TYPE_CONTEXT = {
    "listicle": """
PAGE TYPE PURPOSE: Presell Listicle
- GOAL: Hook with specific frustration in editorial frame. No product, no sales language.
  The reader is in content-consumption mode. The headline must read like a magazine/blog
  headline, NOT an ad. Conversion event is click-through, not purchase.
- STRUCTURE: Number + curiosity/specificity. The number in the headline should match
  the list items on the page.
- TONE: Editorial, content-native. Must pass the "would a magazine print this?" test.
- PRIMARY LAWS: Law 1 (Open Loop), Law 4 (Specificity), Law 5 (Simplicity)
- BEST ARCHETYPES: Curiosity Gap, Problem Callout, Safety Warning
- WHAT TO AVOID: No price, bonuses, guarantee language, or product name. Do not reveal
  the full mechanism -- the listicle teases; the next page explains. Do not write
  anything that reads as a sales pitch. Think wellness blog headline.
- BELIEF STATE: Reader arrives from a Meta/TikTok ad with curiosity triggered, no belief
  prerequisites. The headline must hook in 3 seconds or they bounce.
- EXAMPLE STYLE: "7 Herbs in Your Kitchen Cabinet With Documented Drug Interactions"
""",
    "advertorial": """
PAGE TYPE PURPOSE: Presell Advertorial
- GOAL: Hook with news/discovery angle in editorial frame. Must read like a wellness
  article. The reader should believe they are reading journalism or a personal discovery
  story, not an ad. Conversion event is click-through to sales page.
- STRUCTURE: News/discovery angle. Third-person journalistic or first-person discovery.
- TONE: Editorial / journalistic. Must pass the "would a magazine print this?" test.
  Even more editorial than a listicle -- this is longform content framing.
- PRIMARY LAWS: Law 1 (Open Loop), Law 3 (Unique Mechanism), Law 6 (Credibility)
- BEST ARCHETYPES: Contrarian Claim, Expert Insight, Story/Anecdote
- WHAT TO AVOID: Do NOT name the product in the headline (product intro happens after
  mechanism reveal, typically not before word 600). No sales language, no price, no
  benefit stacks. Breaking editorial frame early = reader categorizes as ad and bounces.
- BELIEF STATE: Reader arrives from an ad. The advertorial must establish B1-B4
  (herbs help but aren't magic; natural isn't safe; ecosystem is broken; she needs a
  system). The headline seeds B1 + B2.
- EXAMPLE STYLE: "New Safety Review Reveals What Most Herbal Guides Get Wrong About
  Drug Interactions"
""",
    "sales_page": """
PAGE TYPE PURPOSE: Long-Form Sales Page
- GOAL: Make the biggest promise or transformation claim. The headline sets the claim
  ceiling for the entire page -- nothing below it can exceed what the headline promises.
  Conversion event is purchase ($49).
- STRUCTURE: Biggest promise or transformation. Can use pre-head + headline + sub-head
  stack (3-part). The headline alone must work standalone even without pre-head/sub-head.
- TONE: Direct, specific, promise-forward. More assertive than presell headlines but
  still within brand voice (anti-hype). Overtly persuasive.
- PRIMARY LAWS: Law 3 (Unique Mechanism), Law 4 (Specificity), Law 6 (Credibility),
  Law 7 (Time Compression)
- BEST ARCHETYPES: Direct Benefit, Social Proof Lead, Expert Insight, Safety Warning
- WHAT TO AVOID: Do not stack multiple claims in one headline. One clear idea.
  If reader arrives from presell, headline must reference what they just learned.
  If from direct traffic, lead with the product's core differentiator.
- BELIEF STATE: Reader is Solution Aware (from presell) or Problem Aware (direct).
  The headline must establish B5 seed ("this is the system").
- EXAMPLE STYLE: "The Only Herbal Reference That Tells You When NOT to Use an Herb --
  and Why"
""",
}


# ============================================================
# SECTION 2: LLM FIX PROMPT BUILDER
# ============================================================

def build_fix_prompt(headline, scorer_json, page_type, iteration):
    """Build the LLM prompt for fixing a headline."""

    passing_tests = []
    failing_tests = []

    for test in scorer_json["tests"]:
        if test["passed"]:
            passing_tests.append(
                f"  PASS {test['id']}: {test['name']} -- {test['detail']}"
            )
        else:
            failing_tests.append(
                f"  FAIL {test['id']}: {test['name']} -- {test['detail']}\n"
                f"    Fix hint: {test['fix_hint']}"
            )

    word_range = WORD_COUNT_RANGES.get(page_type, "8-20")
    page_context = PAGE_TYPE_CONTEXT.get(page_type, "")

    prompt = f"""{BRAND_CONTEXT}

HEADLINE TO IMPROVE:
"{headline}"

PAGE TYPE: {page_type or "default"}
TARGET WORD COUNT: {word_range} words
{page_context}
CURRENT SCORE: {scorer_json['composite']['total']}/{scorer_json['composite']['max']} ({scorer_json['composite']['pct']}%) -- Tier {scorer_json['tier']}

ITERATION: {iteration} of 3

PASSING TESTS (PRESERVE these -- do not break what works):
{chr(10).join(passing_tests)}

FAILING TESTS (FIX these):
{chr(10).join(failing_tests)}

RULES:
1. PRESERVE what works. Do not break passing tests to fix failing ones.
2. The headline must follow at least 3 of the 7 Laws listed above.
3. The headline must contain all 3 components: Pattern Interrupt, Relevance Signal, Implicit Promise.
4. Keep reading level at grade 8 or below (use short, common words).
5. One clear idea per headline. No compound structures.
6. Keep within the target word count range.
7. CRITICAL: Follow the page-type calibration rules above. The headline purpose, tone,
   structure, and archetype guidance are specific to this page type.

OUTPUT: Return ONLY the improved headline text. Nothing else. No quotes, no explanation."""

    return prompt


# ============================================================
# SECTION 3: LLM CALL FUNCTION
# ============================================================

def call_llm(prompt, api_key, model="claude-sonnet-4-20250514", messages=None):
    """Call the Anthropic API to get a rewritten headline + request diagnostics."""
    try:
        import anthropic
    except ImportError:
        print("  ERROR: 'anthropic' package not installed. Run: pip install anthropic")
        sys.exit(1)

    client = anthropic.Anthropic(
        api_key=api_key,
        timeout=LLM_CALL_TIMEOUT_SECONDS,
        max_retries=LLM_CALL_MAX_RETRIES,
    )

    def _extract_request_id_from_headers(headers):
        if headers is None:
            return None
        for key in ("request-id", "x-request-id", "anthropic-request-id"):
            value = headers.get(key) if hasattr(headers, "get") else None
            if not value:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    try:
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
        raw_response = client.messages.with_raw_response.create(
            model=model,
            max_tokens=200,
            messages=messages,
            timeout=LLM_CALL_TIMEOUT_SECONDS,
        )
        response = raw_response.parse()
        text = response.content[0].text.strip()
        # Strip quotes if the LLM wrapped the headline
        text = text.strip('"').strip("'").strip('\u201c').strip('\u201d')
        request_id = getattr(raw_response, "request_id", None)
        if not request_id:
            http_response = getattr(raw_response, "http_response", None)
            request_id = _extract_request_id_from_headers(
                getattr(http_response, "headers", None)
            )
        if not request_id:
            request_id = getattr(response, "_request_id", None) or getattr(response, "request_id", None)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
        output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None
        stop_reason = getattr(response, "stop_reason", None)
        print(
            "  INFO: LLM call completed: "
            f"request_id={request_id or 'missing'} input_tokens={input_tokens} output_tokens={output_tokens} "
            f"stop_reason={stop_reason}"
        )
        return {
            "text": text,
            "request_id": request_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "stop_reason": stop_reason,
        }
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        error_response = getattr(e, "response", None) or getattr(e, "http_response", None)
        request_id = _extract_request_id_from_headers(getattr(error_response, "headers", None))
        extra_parts = []
        if status_code:
            extra_parts.append(f"status={status_code}")
        if request_id:
            extra_parts.append(f"request_id={request_id}")
        suffix = f" ({', '.join(extra_parts)})" if extra_parts else ""
        print(f"  WARNING: LLM call failed: {e}{suffix}")
        return None


# ============================================================
# SECTION 4: ITERATION RECORD
# ============================================================

class IterationRecord:
    """Stores scoring data for a single QA loop iteration."""

    def __init__(self, iteration, headline, scorer_json, composite):
        self.iteration = iteration
        self.headline = headline
        self.scorer_json = scorer_json
        self.tier = scorer_json["tier"]
        self.pct = scorer_json["composite"]["pct"]
        self.total = scorer_json["composite"]["total"]
        self.max = scorer_json["composite"]["max"]
        self.passing = set(scorer_json["passing_tests"])
        self.failing = set(scorer_json["failing_tests"])
        self.fixed_from_prev = set()
        self.regressed_from_prev = set()
        self.still_failing = set()


# ============================================================
# SECTION 5: CORE QA LOOP
# ============================================================

def run_qa_loop(headline, page_type=None, max_iterations=3, min_tier="A",
                api_key=None, model="claude-sonnet-4-20250514", dry_run=False):
    """
    Run the full QA loop on a single headline.

    Returns a dict with iteration history and final result.
    The best-scoring iteration wins (regression protection).
    """
    iterations = []
    request_ids = []
    conversation_messages = []

    # --- Iteration 0: Score original headline ---
    result = scorer.score_headline(headline, page_type)
    composite = scorer.compute_composite(result)
    json_out = scorer.to_json(result, composite)

    record = IterationRecord(0, headline, json_out, composite)
    iterations.append(record)

    # Check if already passes the minimum tier
    if TIER_ORDER.get(json_out["tier"], 0) >= TIER_ORDER.get(min_tier, 4):
        return build_result(iterations, min_tier, request_ids=request_ids)

    # Dry run: just score, no LLM
    if dry_run:
        return build_result(iterations, min_tier, request_ids=request_ids)

    # Check for API key
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  WARNING: No API key provided. Use --api-key or set ANTHROPIC_API_KEY env var.")
        print("  Running in dry-run mode (score only).")
        return build_result(iterations, min_tier, request_ids=request_ids)

    # --- Iterations 1+: LLM fix cycles ---
    current_headline = headline
    current_json = json_out

    for i in range(1, max_iterations):
        # Build the fix prompt from current failures
        prompt = build_fix_prompt(current_headline, current_json, page_type, i)
        pending_messages = conversation_messages + [{"role": "user", "content": prompt}]

        # Call LLM for rewrite
        llm_response = call_llm(prompt, api_key, model, messages=pending_messages)

        # Validate LLM response
        if not llm_response:
            continue  # Skip this iteration on API failure
        request_id = llm_response.get("request_id")
        if request_id and request_id not in request_ids:
            request_ids.append(request_id)
        rewritten = llm_response.get("text")
        if not rewritten:
            continue
        if len(rewritten.split()) > 50:
            continue  # Too long, not a headline
        if '\n' in rewritten:
            continue  # Contains newlines, not a single headline
        if rewritten == current_headline:
            continue  # No change
        conversation_messages = pending_messages + [{"role": "assistant", "content": rewritten}]

        # Rescore the rewritten headline
        new_result = scorer.score_headline(rewritten, page_type)
        new_composite = scorer.compute_composite(new_result)
        new_json = scorer.to_json(new_result, new_composite)

        new_record = IterationRecord(i, rewritten, new_json, new_composite)

        # Track what changed from previous iteration
        prev_record = iterations[-1]
        new_record.fixed_from_prev = prev_record.failing - new_record.failing
        new_record.regressed_from_prev = prev_record.passing - new_record.passing
        new_record.still_failing = prev_record.failing & new_record.failing

        iterations.append(new_record)

        # Check if the rewritten headline passes the minimum tier
        if TIER_ORDER.get(new_json["tier"], 0) >= TIER_ORDER.get(min_tier, 4):
            break

        # Update for next iteration
        current_headline = rewritten
        current_json = new_json

    return build_result(iterations, min_tier, request_ids=request_ids)


# ============================================================
# SECTION 6: RESULT BUILDER
# ============================================================

def build_result(iterations, min_tier, request_ids=None):
    """
    Build the final result dict from iteration history.

    Regression protection: the BEST iteration (highest pct) wins,
    not necessarily the last one.
    """
    # Find best iteration (highest score)
    best = max(iterations, key=lambda r: r.pct)
    final = iterations[-1]

    # Determine pass/fail status
    status = "PASS" if TIER_ORDER.get(best.tier, 0) >= TIER_ORDER.get(min_tier, 4) else "FAIL"

    return {
        "original_headline": iterations[0].headline,
        "final_headline": final.headline,
        "best_headline": best.headline,
        "best_iteration": best.iteration,
        "status": status,
        "final_tier": final.tier,
        "final_pct": final.pct,
        "best_tier": best.tier,
        "best_pct": best.pct,
        "iterations": iterations,
        "min_tier": min_tier,
        "total_iterations": len(iterations),
        "request_ids": request_ids or [],
    }


# ============================================================
# SECTION 7: HUMAN-READABLE REPORT
# ============================================================

def print_qa_report(qa_result):
    """Print human-readable QA loop report to stdout."""
    print(f"\n  {'='*71}")
    print(f"    HEADLINE QA LOOP")
    print(f"  {'='*71}")

    for record in qa_result["iterations"]:
        tier_num = TIER_ORDER.get(record.tier, 0)
        min_num = TIER_ORDER.get(qa_result["min_tier"], 4)
        tier_mark = " PASS" if tier_num >= min_num else ""

        if record.iteration == 0:
            print(f"\n    Iteration 0 (original): "
                  f"{record.total}/{record.max} ({record.pct:.1f}%) "
                  f"-- Tier {record.tier}")
            print(f"      \"{record.headline}\"")
            if record.failing:
                print(f"      Failing: {', '.join(sorted(record.failing))}")
        else:
            print(f"\n    Iteration {record.iteration}: "
                  f"{record.total}/{record.max} ({record.pct:.1f}%) "
                  f"-- Tier {record.tier}{tier_mark}")
            print(f"      \"{record.headline}\"")
            parts = []
            if record.fixed_from_prev:
                parts.append(f"Fixed: {', '.join(sorted(record.fixed_from_prev))}")
            if record.still_failing:
                parts.append(f"Still failing: {', '.join(sorted(record.still_failing))}")
            if record.regressed_from_prev:
                parts.append(f"Regressions: {', '.join(sorted(record.regressed_from_prev))}")
            if parts:
                print(f"      {' | '.join(parts)}")

    # Final verdict
    print(f"\n    {'-'*67}")
    status_mark = "PASS" if qa_result["status"] == "PASS" else "FAIL"
    print(f"    RESULT: {qa_result['status']} [{status_mark}]")
    print(f"    Best: Iteration {qa_result['best_iteration']} "
          f"-- Tier {qa_result['best_tier']} ({qa_result['best_pct']:.1f}%)")
    print(f"    Best headline: \"{qa_result['best_headline']}\"")
    print(f"  {'='*71}")


# ============================================================
# SECTION 8: JSON OUTPUT
# ============================================================

def to_json(qa_result):
    """Convert QA result to machine-readable JSON dict."""
    return {
        "original_headline": qa_result["original_headline"],
        "final_headline": qa_result["final_headline"],
        "best_headline": qa_result["best_headline"],
        "status": qa_result["status"],
        "best_tier": qa_result["best_tier"],
        "best_pct": qa_result["best_pct"],
        "total_iterations": qa_result["total_iterations"],
        "iterations": [
            {
                "iteration": r.iteration,
                "headline": r.headline,
                "score": {
                    "total": r.total,
                    "max": r.max,
                    "pct": r.pct,
                },
                "tier": r.tier,
                "failing_tests": sorted(list(r.failing)),
                "passing_tests": sorted(list(r.passing)),
                "fixed": sorted(list(r.fixed_from_prev)) if r.iteration > 0 else [],
                "regressions": sorted(list(r.regressed_from_prev)) if r.iteration > 0 else [],
            }
            for r in qa_result["iterations"]
        ],
        "metadata": {
            "min_tier": qa_result["min_tier"],
            "scorer_version": "2.0",
            "request_ids": qa_result.get("request_ids", []),
        },
    }


# ============================================================
# SECTION 9: BATCH MODE
# ============================================================

def run_batch(headlines, page_type=None, max_iterations=3, min_tier="A",
              api_key=None, model="claude-sonnet-4-20250514", dry_run=False):
    """Run QA loop on multiple headlines. Returns list of result dicts."""
    all_results = []

    for i, hl in enumerate(headlines):
        hl = hl.strip()
        if not hl:
            continue
        print(f"\n  -- Headline {i+1}/{len(headlines)} --")
        result = run_qa_loop(hl, page_type, max_iterations, min_tier,
                             api_key, model, dry_run)
        print_qa_report(result)
        all_results.append(result)

        # Brief pause between API calls to avoid rate limiting
        if not dry_run and i < len(headlines) - 1:
            time.sleep(1)

    # --- Batch summary ---
    passing = [r for r in all_results if r["status"] == "PASS"]
    failing = [r for r in all_results if r["status"] == "FAIL"]

    print(f"\n  {'='*71}")
    print(f"    BATCH SUMMARY")
    print(f"  {'='*71}")
    print(f"    Total headlines:          {len(all_results)}")
    print(f"    Passed ({min_tier}+ tier):        {len(passing)}")
    print(f"    Failed:                   {len(failing)}")

    if passing:
        print(f"\n    PASSING HEADLINES:")
        for r in passing:
            print(f"      [{r['best_tier']}] \"{r['best_headline']}\"")

    if failing:
        print(f"\n    FAILED HEADLINES (did not reach {min_tier} tier):")
        for r in failing:
            print(f"      [{r['best_tier']}] \"{r['best_headline']}\" "
                  f"({r['best_pct']:.1f}%)")

    # Run HookBank analysis on passing headlines if >= 5
    if len(passing) >= 5:
        print(f"\n    Running HookBank analysis on {len(passing)} passing headlines...")
        passing_headlines = [r["best_headline"] for r in passing]
        scorer.print_batch_report(passing_headlines, page_type)

    print(f"  {'='*71}")

    return all_results


# ============================================================
# SECTION 10: CLI INTERFACE
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Headline QA Loop -- LLM-Powered Auto-Fix Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 headline_qa_loop.py "Your headline here" --page-type listicle
  python3 headline_qa_loop.py --batch headlines.txt --page-type listicle
  python3 headline_qa_loop.py "headline" --max-iterations 2 --min-tier S
  python3 headline_qa_loop.py "headline" --output-json
  python3 headline_qa_loop.py "headline" --dry-run
        """
    )
    parser.add_argument("headline", nargs="?",
                        help="Headline text to process")
    parser.add_argument("--page-type",
                        choices=["listicle", "advertorial", "sales_page"],
                        default=None,
                        help="Page type for scoring")
    parser.add_argument("--batch", metavar="FILE",
                        help="Process multiple headlines from a file (one per line)")
    parser.add_argument("--max-iterations", type=int, default=3,
                        help="Max iterations including original (default: 3)")
    parser.add_argument("--min-tier",
                        choices=["S", "A", "B", "C"],
                        default="A",
                        help="Minimum tier to pass (default: A)")
    parser.add_argument("--api-key", default=None,
                        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    parser.add_argument("--model", default="claude-sonnet-4-20250514",
                        help="Model to use for LLM fixes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Score only, no LLM calls")
    parser.add_argument("--output-json", action="store_true",
                        help="Output machine-readable JSON")

    args = parser.parse_args()

    # --- Batch mode ---
    if args.batch:
        try:
            with open(args.batch, 'r') as f:
                headlines = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"  ERROR: File not found: {args.batch}")
            sys.exit(1)

        if not headlines:
            print("  ERROR: No headlines found in file.")
            sys.exit(1)

        results = run_batch(headlines, args.page_type, args.max_iterations,
                            args.min_tier, args.api_key, args.model,
                            args.dry_run)

        if args.output_json:
            json_results = [to_json(r) for r in results]
            print(json.dumps(json_results, indent=2))

    # --- Single headline mode ---
    elif args.headline:
        result = run_qa_loop(args.headline, args.page_type, args.max_iterations,
                             args.min_tier, args.api_key, args.model,
                             args.dry_run)

        if args.output_json:
            print(json.dumps(to_json(result), indent=2))
        else:
            print_qa_report(result)

    # --- No input ---
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
