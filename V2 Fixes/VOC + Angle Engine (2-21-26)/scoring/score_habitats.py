#!/usr/bin/env python3
"""
Habitat Scanner Scoring Engine
===============================
Takes observation sheet data from Agent 1 and computes mathematically
derived habitat scores using first-principles formulas.

Mental Models Applied:
- First Principles: every weight justified causally
- Logarithmic Diminishing Returns: volume scoring
- Bayesian Reasoning: confidence intervals
- Signal-to-Noise Ratio: habitat relevance filtering
- Systems Thinking (Bottleneck): mining feasibility gate
- Behavioral Economics: buyer density estimation
- Product Lifecycle Theory: habitat lifecycle stage
- Momentum (Physics): trend direction
- Z-Score Normalization: cross-product comparability
- Engineering Safety Factors: mining risk hard gate

Usage:
    python score_habitats.py --input habitat_observations.json --output habitat_scores.json

    Or import and use programmatically:
    from score_habitats import score_habitat, score_all_habitats
"""

import json
import math
import statistics
import argparse
import sys
from typing import Dict, List, Tuple, Optional


def _coerce_yes_no(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"Y", "N"}:
            return normalized
    if isinstance(value, bool):
        return "Y" if value else "N"
    return "N"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def apply_video_modifiers(base_components: Dict[str, float], video_obs: Dict) -> Tuple[Dict[str, float], Dict]:
    """
    Apply deterministic video-habitat modifiers to base component values.
    """
    updated = dict(base_components)
    modifier_deltas: Dict[str, float] = {}
    has_video_fields = any(
        key in video_obs
        for key in (
            "viral_videos_found",
            "comment_sections_active",
            "contains_purchase_intent",
            "creator_diversity",
            "video_count_scraped",
            "median_view_count",
            "viral_video_count",
        )
    )
    if not has_video_fields:
        return updated, {"applied": False, "modifiers": {}}

    if _coerce_yes_no(video_obs.get("viral_videos_found")) == "Y":
        updated["emotional_depth"] = _clamp01(updated["emotional_depth"] + 0.08)
        modifier_deltas["emotional_depth"] = 0.08
    if _coerce_yes_no(video_obs.get("comment_sections_active")) == "Y":
        updated["language_quality"] = _clamp01(updated["language_quality"] + 0.10)
        modifier_deltas["language_quality"] = 0.10
    if _coerce_yes_no(video_obs.get("contains_purchase_intent")) == "Y":
        updated["buyer_density"] = _clamp01(updated["buyer_density"] + 0.08)
        modifier_deltas["buyer_density"] = 0.08

    creator_diversity = str(video_obs.get("creator_diversity", "")).strip().upper()
    if creator_diversity == "SINGLE":
        updated["signal_to_noise"] = _clamp01(updated["signal_to_noise"] - 0.10)
        modifier_deltas["signal_to_noise"] = modifier_deltas.get("signal_to_noise", 0.0) - 0.10
    elif creator_diversity == "MANY":
        updated["signal_to_noise"] = _clamp01(updated["signal_to_noise"] + 0.07)
        modifier_deltas["signal_to_noise"] = modifier_deltas.get("signal_to_noise", 0.0) + 0.07

    return updated, {"applied": bool(modifier_deltas), "modifiers": modifier_deltas}


def score_habitat(obs: Dict) -> Dict:
    """
    Score a single habitat from its observation sheet.

    Args:
        obs: Dictionary of binary/categorical observations from Agent 1

    Returns:
        Dictionary with final score, component scores, confidence range,
        gate status, and metadata
    """

    # ============================================================
    # COMPONENT 1: VOLUME (0-1)
    # Logarithmic diminishing returns — the marginal value of
    # the 500th datapoint is near zero if the first 50 covered
    # the same themes. Volume is a floor check, not quality signal.
    # ============================================================
    # Volume: true logarithmic scale (not step function)
    # [Logarithmic Diminishing Returns] The jump from 10→100 matters far more than 1000→2000
    # Convert tier observations to approximate thread count, then apply log
    if obs.get('threads_1000_plus') == 'Y':
        approx_threads = 1000
    elif obs.get('threads_200_plus') == 'Y':
        approx_threads = 200
    elif obs.get('threads_50_plus') == 'Y':
        approx_threads = 50
    else:
        approx_threads = 10  # below minimum tier
    volume_points = min(1.0, math.log(max(1, approx_threads)) / math.log(1000))

    # ============================================================
    # COMPONENT 2: RECENCY (0-1)
    # Temporal relevance — weighted toward recent, exponential decay.
    # Recent data = current market state. Old data = historical context.
    # ============================================================
    recency_points = sum([
        0.5 if obs.get('posts_last_3mo') == 'Y' else 0,
        0.3 if obs.get('posts_last_6mo') == 'Y' else 0,
        0.2 if obs.get('posts_last_12mo') == 'Y' else 0
    ])
    recency_modifier = {
        'MAJORITY_RECENT': 1.0,
        'BALANCED': 0.8,
        'MAJORITY_OLD': 0.5
    }.get(obs.get('recency_ratio', 'BALANCED'), 0.5)
    recency_score = recency_points * recency_modifier

    # ============================================================
    # COMPONENT 3: SPECIFICITY (0-1)
    # On-topic precision — direct signals worth more than adjacent.
    # Penalty for adjacent-only habitats (they waste extraction time).
    # ============================================================
    specificity_score = sum([
        0.35 if obs.get('exact_category') == 'Y' else 0,
        0.30 if obs.get('purchasing_comparing') == 'Y' else 0,
        0.25 if obs.get('personal_usage') == 'Y' else 0,
        -0.15 if obs.get('adjacent_only') == 'Y' else 0
    ])
    specificity_score = max(0, min(1, specificity_score))

    # ============================================================
    # COMPONENT 4: EMOTIONAL DEPTH (0-1)
    # Core mining value — emotional depth IS the raw material
    # for angle construction. Highest weight in composite.
    # ============================================================
    depth_features = [
        obs.get('first_person_narratives') == 'Y',
        obs.get('trigger_events') == 'Y',
        obs.get('fear_frustration_shame') == 'Y',
        obs.get('specific_dollar_or_time') == 'Y',
        obs.get('long_detailed_posts') == 'Y'
    ]
    depth_score = sum(depth_features) / len(depth_features)

    # ============================================================
    # COMPONENT 5: BUYER DENSITY (0-1)
    # Behavioral economics — intent signals predict conversion.
    # A habitat full of lurkers ≠ a habitat full of buyers.
    # ============================================================
    intent_map = {'MOST': 1.0, 'SOME': 0.65, 'FEW': 0.3, 'NONE': 0.05}
    buyer_density = (
        intent_map.get(obs.get('purchase_intent_density', 'NONE'), 0.05) * 0.50 +
        (1.0 if obs.get('discusses_spending') == 'Y' else 0.0) * 0.25 +
        (1.0 if obs.get('recommendation_threads') == 'Y' else 0.0) * 0.25
    )

    # ============================================================
    # COMPONENT 6: LANGUAGE QUALITY (0-1)
    # From language depth samples — predicts VOC richness.
    # Scored per sample post, then averaged.
    # ============================================================
    samples = obs.get('language_samples', [])
    if samples:
        sample_scores = []
        for sample in samples:
            features = sum([
                sample.get('has_trigger_event') == 'Y',
                sample.get('has_failed_solution') == 'Y',
                sample.get('has_identity_language') == 'Y',
                sample.get('has_specific_outcome') == 'Y'
            ])
            feature_score = features / 4
            # Word count bonus (longer = richer, diminishing returns)
            wc = sample.get('word_count', 0)
            length_bonus = min(1.0, wc / 200)
            post_quality = feature_score * 0.7 + length_bonus * 0.3
            sample_scores.append(post_quality)
        language_quality = sum(sample_scores) / len(sample_scores)
    else:
        language_quality = 0.0

    # ============================================================
    # COMPONENT 7: SIGNAL-TO-NOISE RATIO (0-1)
    # From electrical engineering — signal / (signal + noise).
    # A subreddit with 95% off-topic posts wastes extraction time.
    # ============================================================
    snr_map = {
        'OVER_50_PCT': 1.0,
        '25_TO_50_PCT': 0.7,
        '10_TO_25_PCT': 0.4,
        'UNDER_10_PCT': 0.15
    }
    noise_penalty = 0.2 if obs.get('dominated_by_offtopic') == 'Y' else 0.0
    habitat_snr = snr_map.get(obs.get('relevance_pct', 'UNDER_10_PCT'), 0.15) - noise_penalty
    habitat_snr = max(0, habitat_snr)

    # ============================================================
    # COMPONENT 8: COMPETITOR WHITESPACE (0-1)
    # Information theory — mining the same source as competitors
    # yields diminishing unique insights. Whitespace = edge.
    # ============================================================
    saturation_penalty = {
        '0': 0.0,
        '1-3': 0.1,
        '4-7': 0.3,
        '8+': 0.5
    }.get(obs.get('competitor_brand_count', '0'), 0.0)
    if obs.get('competitor_ads_present') == 'Y':
        saturation_penalty += 0.2
    competitor_whitespace = 1.0 - min(1.0, saturation_penalty)

    # ============================================================
    # COMPONENT 9: MARKET TIMING (0-1)
    # Momentum (physics) + Product lifecycle theory.
    # Combines trend direction with habitat lifecycle stage.
    # ============================================================
    trend_score = {
        'HIGHER': 1.0,
        'SAME': 0.6,
        'LOWER': 0.3,
        'CANNOT_DETERMINE': 0.5
    }.get(obs.get('trend_direction', 'CANNOT_DETERMINE'), 0.5)

    # Habitat lifecycle (product lifecycle theory)
    age = obs.get('habitat_age', 'CANNOT_DETERMINE')
    member_trend = obs.get('membership_trend', 'CANNOT_DETERMINE')
    post_trend = obs.get('post_frequency_trend', 'CANNOT_DETERMINE')

    if age in ['UNDER_1YR', '1_TO_3YR'] and member_trend == 'GROWING':
        lifecycle_score = 1.0
        lifecycle_stage = 'GROWTH'
    elif member_trend == 'GROWING' and post_trend == 'INCREASING':
        lifecycle_score = 1.0
        lifecycle_stage = 'GROWTH'
    elif member_trend == 'STABLE' and post_trend in ['SAME', 'INCREASING']:
        lifecycle_score = 0.75
        lifecycle_stage = 'MATURE_ACTIVE'
    elif member_trend == 'DECLINING' or post_trend == 'DECREASING':
        lifecycle_score = 0.4
        lifecycle_stage = 'DECLINING'
    elif member_trend == 'CANNOT_DETERMINE' and post_trend == 'CANNOT_DETERMINE':
        lifecycle_score = 0.5
        lifecycle_stage = 'UNKNOWN'
    else:
        lifecycle_score = 0.65
        lifecycle_stage = 'MATURE_STABLE'

    market_timing = trend_score * 0.50 + lifecycle_score * 0.50

    # ============================================================
    # COMPONENT 10: MINING FEASIBILITY (0-1)
    # Engineering safety factors — a promising habitat you can't
    # actually mine is worthless. Hard gate at 0.5.
    # ============================================================
    publicly_accessible_ok = _coerce_yes_no(obs.get('publicly_accessible')) == 'Y'
    text_based_content_ok = _coerce_yes_no(obs.get('text_based_content')) == 'Y'
    target_language_ok = _coerce_yes_no(obs.get('target_language')) == 'Y'
    no_rate_limiting_ok = _coerce_yes_no(obs.get('no_rate_limiting')) == 'Y'

    # Language can only be judged when extractable text exists.
    effective_target_language_ok = target_language_ok if text_based_content_ok else True
    feasibility_checks = [
        publicly_accessible_ok,
        text_based_content_ok,
        effective_target_language_ok,
        no_rate_limiting_ok,
    ]
    mining_feasibility = sum(feasibility_checks) / len(feasibility_checks)

    base_components = {
        'volume': volume_points,
        'recency': recency_score,
        'specificity': specificity_score,
        'emotional_depth': depth_score,
        'buyer_density': buyer_density,
        'language_quality': language_quality,
        'signal_to_noise': habitat_snr,
        'competitor_whitespace': competitor_whitespace,
        'market_timing': market_timing,
        'mining_feasibility': mining_feasibility,
    }
    components, video_modifier_diagnostics = apply_video_modifiers(base_components, obs)

    # ============================================================
    # === COMPOSITE HABITAT SCORE ===
    # Weights justified by causal importance to angle discovery:
    # Emotional depth + language quality = highest (they ARE the raw material)
    # Specificity + buyer density = second (commercial relevance)
    # Everything else = supporting signals
    # ============================================================
    composite = (
        components['volume']               * 0.05 +
        components['recency']              * 0.10 +
        components['specificity']          * 0.14 +
        components['emotional_depth']      * 0.18 +
        components['buyer_density']        * 0.13 +
        components['language_quality']     * 0.14 +
        components['signal_to_noise']      * 0.07 +
        components['competitor_whitespace'] * 0.07 +
        components['market_timing']        * 0.06 +
        components['mining_feasibility']   * 0.06
    )

    habitat_final_score = round(composite * 100, 1)

    # ============================================================
    # MINING RISK HARD GATE (Engineering Safety Factor)
    # If any mining-risk requirement fails, cap score at 25 regardless
    # of other components. This mirrors a circuit breaker: inaccessible
    # habitats cannot be prioritized.
    # ============================================================
    mining_gate_failures: List[str] = []
    if not publicly_accessible_ok:
        mining_gate_failures.append('publicly_accessible')
    if not text_based_content_ok:
        mining_gate_failures.append('text_based_content')
    if text_based_content_ok and not target_language_ok:
        mining_gate_failures.append('target_language')
    if not no_rate_limiting_ok:
        mining_gate_failures.append('no_rate_limiting')
    mining_gate_applied = False
    if mining_gate_failures:
        habitat_final_score = min(25.0, habitat_final_score)
        mining_gate_applied = True

    # ============================================================
    # CONFIDENCE INTERVAL (Bayesian Reasoning)
    # Width inversely proportional to how many observables were
    # definitively answered. More unknowns = wider range.
    # ============================================================
    observable_keys = [
        'threads_50_plus', 'threads_200_plus', 'threads_1000_plus',
        'posts_last_3mo', 'posts_last_6mo', 'posts_last_12mo', 'recency_ratio',
        'exact_category', 'purchasing_comparing', 'personal_usage', 'adjacent_only',
        'first_person_narratives', 'trigger_events', 'fear_frustration_shame',
        'specific_dollar_or_time', 'long_detailed_posts',
        'relevance_pct', 'dominated_by_offtopic',
        'competitor_brands_mentioned', 'competitor_brand_count', 'competitor_ads_present',
        'trend_direction', 'membership_trend', 'post_frequency_trend',
        'publicly_accessible', 'text_based_content', 'target_language', 'no_rate_limiting',
        'purchase_intent_density', 'discusses_spending', 'recommendation_threads'
    ]
    definitive = sum(1 for k in observable_keys
                     if obs.get(k) not in [None, '', 'CANNOT_DETERMINE', 'UNKNOWN'])
    evidence_completeness = definitive / len(observable_keys) if observable_keys else 0

    uncertainty_width = (1 - evidence_completeness) * 20
    confidence_low = max(0, round(habitat_final_score - uncertainty_width, 1))
    confidence_high = min(100, round(habitat_final_score + uncertainty_width, 1))

    return {
        'habitat_name': obs.get('habitat_name', 'Unknown'),
        'habitat_type': obs.get('habitat_type', 'Unknown'),
        'url': obs.get('url_pattern', ''),
        'final_score': habitat_final_score,
        'confidence_range': (confidence_low, confidence_high),
        'mining_gate_applied': mining_gate_applied,
        'mining_gate_failures': mining_gate_failures,
        'lifecycle_stage': lifecycle_stage,
        'reusability': obs.get('reusability', 'UNKNOWN'),
        'components': {
            'volume': round(components['volume'] * 100, 1),
            'recency': round(components['recency'] * 100, 1),
            'specificity': round(components['specificity'] * 100, 1),
            'emotional_depth': round(components['emotional_depth'] * 100, 1),
            'buyer_density': round(components['buyer_density'] * 100, 1),
            'language_quality': round(components['language_quality'] * 100, 1),
            'signal_to_noise': round(components['signal_to_noise'] * 100, 1),
            'competitor_whitespace': round(components['competitor_whitespace'] * 100, 1),
            'market_timing': round(components['market_timing'] * 100, 1),
            'mining_feasibility': round(components['mining_feasibility'] * 100, 1)
        },
        'evidence_completeness': round(evidence_completeness, 2),
        'video_modifiers_applied': video_modifier_diagnostics,
    }


def score_all_habitats(habitats: List[Dict]) -> Dict:
    """
    Score all habitats and compute z-scores for cross-product comparability.

    Args:
        habitats: List of observation sheet dictionaries

    Returns:
        Dictionary with scored habitats (sorted by score), z-scores,
        summary statistics, and the ranked mining plan
    """
    scored = [score_habitat(h) for h in habitats]

    # Component-level Z-Score Normalization
    # [Z-Score] Normalize each component across all habitats before comparing
    # This ensures components with different natural ranges contribute equally
    component_names = ['volume', 'recency', 'specificity', 'emotional_depth',
                       'buyer_density', 'language_quality', 'signal_to_noise',
                       'competitor_whitespace', 'market_timing', 'mining_feasibility']

    if len(scored) > 1:
        for comp in component_names:
            comp_values = [h['components'][comp] for h in scored]
            comp_mean = statistics.mean(comp_values)
            comp_std = statistics.stdev(comp_values) if len(comp_values) > 1 else 1
            if comp_std > 0:
                for h in scored:
                    h['components'][f'{comp}_z'] = round(
                        (h['components'][comp] - comp_mean) / comp_std, 2)
            else:
                for h in scored:
                    h['components'][f'{comp}_z'] = 0.0

    # Z-Score Normalization (Statistics)
    raw_scores = [h['final_score'] for h in scored]
    if len(raw_scores) > 1:
        mean_score = statistics.mean(raw_scores)
        std_score = statistics.stdev(raw_scores)
        if std_score > 0:
            for h in scored:
                h['z_score'] = round((h['final_score'] - mean_score) / std_score, 2)
        else:
            for h in scored:
                h['z_score'] = 0.0
    else:
        mean_score = raw_scores[0] if raw_scores else 0
        std_score = 0
        for h in scored:
            h['z_score'] = 0.0

    # Sort by final score descending
    scored.sort(key=lambda x: x['final_score'], reverse=True)

    # Add rank
    for i, h in enumerate(scored):
        h['rank'] = i + 1

    # Summary statistics
    summary = {
        'total_habitats': len(scored),
        'mean_score': round(mean_score, 1),
        'std_score': round(std_score, 1),
        'median_score': round(statistics.median(raw_scores), 1) if raw_scores else 0,
        'max_score': round(max(raw_scores), 1) if raw_scores else 0,
        'min_score': round(min(raw_scores), 1) if raw_scores else 0,
        'gates_applied': sum(1 for h in scored if h['mining_gate_applied']),
        'type_distribution': {},
        'lifecycle_distribution': {}
    }

    for h in scored:
        t = h['habitat_type']
        summary['type_distribution'][t] = summary['type_distribution'].get(t, 0) + 1
        l = h['lifecycle_stage']
        summary['lifecycle_distribution'][l] = summary['lifecycle_distribution'].get(l, 0) + 1

    # Habitat Type Entropy (Information Theory)
    # Detects monoculture — if all habitats are the same type, diversity is zero
    type_counts = list(summary['type_distribution'].values())
    total_types = sum(type_counts)
    if total_types > 0 and len(type_counts) > 1:
        type_probs = [c / total_types for c in type_counts if c > 0]
        type_entropy = -sum(p * math.log2(p) for p in type_probs)
        max_type_entropy = math.log2(len(type_counts))
        normalized_type_entropy = type_entropy / max_type_entropy if max_type_entropy > 0 else 0
    else:
        normalized_type_entropy = 0.0

    summary['habitat_type_entropy'] = round(normalized_type_entropy, 3)
    summary['habitat_type_entropy_healthy'] = normalized_type_entropy >= 0.6

    if not summary['habitat_type_entropy_healthy']:
        dominant_type = max(summary['type_distribution'], key=summary['type_distribution'].get)
        dominant_pct = round(summary['type_distribution'][dominant_type] / total_types * 100, 1)
        summary['monoculture_warning'] = (
            f"HABITAT_MONOCULTURE: {dominant_type} represents {dominant_pct}% of qualified habitats. "
            f"Insufficient type diversity (entropy: {summary['habitat_type_entropy']}). "
            f"VOC corpus may over-represent {dominant_type}-specific communication patterns."
        )

    return {
        'habitats': scored,
        'summary': summary,
        'z_score_interpretation': {
            'exceptional': 'z > 1.5',
            'strong': 'z > 0.5',
            'average': '0 to 0.5',
            'below_average': 'z < 0'
        }
    }


def print_scorecard(results: Dict):
    """Pretty-print the habitat scorecard to stdout."""
    print("\n" + "=" * 90)
    print("HABITAT SCANNER SCORECARD")
    print("=" * 90)

    summary = results['summary']
    print(f"\nTotal Habitats: {summary['total_habitats']}")
    print(f"Mean Score: {summary['mean_score']} | Median: {summary['median_score']} | "
          f"Std Dev: {summary['std_score']}")
    print(f"Range: {summary['min_score']} — {summary['max_score']}")
    print(f"Mining Gates Applied: {summary['gates_applied']}")

    print(f"\nType Distribution: {summary['type_distribution']}")
    print(f"Lifecycle Distribution: {summary['lifecycle_distribution']}")

    print("\n" + "-" * 90)
    print(f"{'Rank':<5} {'Score':<8} {'Z':<7} {'Conf Range':<15} {'Gate':<6} "
          f"{'Type':<18} {'Habitat Name'}")
    print("-" * 90)

    for h in results['habitats']:
        gate_str = "GATED" if h['mining_gate_applied'] else "OK"
        conf = f"({h['confidence_range'][0]}-{h['confidence_range'][1]})"
        print(f"{h['rank']:<5} {h['final_score']:<8} {h['z_score']:<7} {conf:<15} "
              f"{gate_str:<6} {h['habitat_type']:<18} {h['habitat_name']}")

    print("\n" + "-" * 90)
    print("COMPONENT BREAKDOWN (Top 5)")
    print("-" * 90)
    for h in results['habitats'][:5]:
        print(f"\n  {h['habitat_name']} (Score: {h['final_score']}, Z: {h['z_score']})")
        for comp, val in h['components'].items():
            bar_filled = int(val / 5)
            bar_empty = 20 - bar_filled
            bar = "#" * bar_filled + "." * bar_empty
            print(f"    {comp:<25} [{bar}] {val}")


def main():
    parser = argparse.ArgumentParser(description='Score habitat observation sheets')
    parser.add_argument('--input', '-i', required=True, help='Input JSON file with observation sheets')
    parser.add_argument('--output', '-o', help='Output JSON file (optional, prints to stdout if omitted)')
    args = parser.parse_args()

    with open(args.input, 'r') as f:
        data = json.load(f)

    # Accept either a list of habitats or a dict with 'habitats' key
    if isinstance(data, list):
        habitats = data
    elif isinstance(data, dict) and 'habitats' in data:
        habitats = data['habitats']
    else:
        print("Error: Input must be a JSON array of habitat observations or a dict with 'habitats' key")
        sys.exit(1)

    results = score_all_habitats(habitats)

    print_scorecard(results)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == '__main__':
    main()
