#!/usr/bin/env python3
"""
VOC Extractor Scoring Engine
==============================
Takes observation sheet data from Agent 2 and computes mathematically
derived VOC item scores + corpus-level health metrics.

Mental Models Applied:
- First Principles: every weight justified causally
- Bayesian Reasoning: confidence intervals per item
- Signal-to-Noise Ratio: signal density scoring
- Systems Thinking (Bottleneck): weakest dimension cap
- Information Theory: dimension entropy
- Behavioral Economics: buyer stage + aspiration gap
- Engineering Safety Factors: compliance hard gate
- Logarithmic Diminishing Returns: word count modifier
- Product Lifecycle Theory: market maturation index
- Momentum (Physics): velocity calculation
- Z-Score Normalization: cross-product comparability

Usage:
    python score_voc.py --input voc_observations.json --output voc_scores.json
"""

import json
import math
import statistics
import argparse
import sys
from collections import Counter
from typing import Dict, List, Tuple, Optional


def score_voc_item(obs: Dict) -> Dict:
    """
    Score a single VOC item from its observation sheet.
    """

    # ============================================================
    # COMPONENT 1: SPECIFICITY (0-1)
    # Most important — specific = usable in copy.
    # Generic observations are background noise.
    # ============================================================
    specificity_observables = [
        obs.get('specific_number') == 'Y',
        obs.get('specific_product_brand') == 'Y',
        obs.get('specific_event_moment') == 'Y',
        obs.get('specific_body_symptom') == 'Y',
        obs.get('before_after_comparison') == 'Y'
    ]
    specificity = sum(specificity_observables) / len(specificity_observables)

    # ============================================================
    # COMPONENT 2: EMOTIONAL INTENSITY (0-1)
    # With word count modifier — longer intense excerpts
    # provide more context for copy.
    # ============================================================
    intensity_observables = [
        obs.get('crisis_language') == 'Y',
        obs.get('profanity_extreme_punctuation') == 'Y',
        obs.get('physical_sensation') == 'Y',
        obs.get('identity_change_desire') == 'Y'
    ]
    raw_intensity = sum(intensity_observables) / len(intensity_observables)
    wc = obs.get('word_count', 0)
    # [Logarithmic Diminishing Returns] A 300-word post is not 2x more valuable than 150 words
    length_modifier = min(1.0, math.log(max(1, wc)) / math.log(300))
    intensity = raw_intensity * 0.75 + length_modifier * 0.25

    # ============================================================
    # COMPONENT 3: ANGLE POTENTIAL (0-1)
    # Adjusted with signal density (SNR at item level).
    # High signal density = the quote practically writes the ad.
    # ============================================================
    angle_observables = [
        obs.get('clear_trigger_event') == 'Y',
        obs.get('named_enemy') == 'Y',
        obs.get('shiftable_belief') == 'Y',
        obs.get('expectation_vs_reality') == 'Y',
        obs.get('headline_ready') == 'Y'
    ]
    raw_angle_potential = sum(angle_observables) / len(angle_observables)

    signal_density_map = {
        'OVER_75_PCT': 1.0,
        '50_TO_75_PCT': 0.7,
        '25_TO_50_PCT': 0.4,
        'UNDER_25_PCT': 0.15
    }
    signal_density = signal_density_map.get(obs.get('usable_content_pct', 'UNDER_25_PCT'), 0.15)

    angle_potential = raw_angle_potential * 0.7 + signal_density * 0.3

    # ============================================================
    # COMPONENT 4: SOURCE CREDIBILITY (0-1)
    # Trustworthy source = defensible claims.
    # ============================================================
    credibility_observables = [
        obs.get('personal_context') == 'Y',
        obs.get('long_narrative') == 'Y',
        obs.get('engagement_received') == 'Y',
        obs.get('real_person_signals') == 'Y',
        obs.get('moderated_community') == 'Y'
    ]
    credibility = sum(credibility_observables) / len(credibility_observables)

    # ============================================================
    # COMPONENT 5: DIMENSION RICHNESS (0-1)
    # Bonus for items that fill more of the 8 extraction dimensions.
    # Richer items give Agent 3 more to work with.
    # ============================================================
    dimensions = ['trigger_event', 'pain_problem', 'desired_outcome',
                  'failed_prior_solution', 'enemy_blame', 'identity_role',
                  'fear_risk', 'emotional_valence']
    filled = sum(1 for d in dimensions
                 if obs.get(d) and obs.get(d) not in ['NONE', 'None', '', None])
    dimension_bonus = filled / len(dimensions)

    # ============================================================
    # === RAW COMPOSITE ===
    # ============================================================
    raw_composite = (
        specificity      * 0.22 +
        intensity        * 0.18 +
        angle_potential   * 0.25 +
        credibility      * 0.15 +
        dimension_bonus  * 0.13 +
        signal_density   * 0.07
    )

    # ============================================================
    # FRESHNESS DECAY
    # Durable psychology (fears, identity) decays slowly.
    # Market-specific info (prices, competitors) decays fast.
    # ============================================================
    is_durable = obs.get('durable_psychology') == 'Y'
    is_market = obs.get('market_specific') == 'Y'

    if is_durable and not is_market:
        decay_rates = {
            'LAST_3MO': 1.0, 'LAST_6MO': 1.0, 'LAST_12MO': 0.95,
            'LAST_24MO': 0.90, 'OLDER': 0.85, 'UNKNOWN': 0.90
        }
    elif is_market and not is_durable:
        decay_rates = {
            'LAST_3MO': 1.0, 'LAST_6MO': 0.90, 'LAST_12MO': 0.75,
            'LAST_24MO': 0.55, 'OLDER': 0.35, 'UNKNOWN': 0.60
        }
    else:
        decay_rates = {
            'LAST_3MO': 1.0, 'LAST_6MO': 0.95, 'LAST_12MO': 0.85,
            'LAST_24MO': 0.70, 'OLDER': 0.55, 'UNKNOWN': 0.75
        }

    freshness_modifier = decay_rates.get(obs.get('date_bracket', 'UNKNOWN'), 0.75)

    # ============================================================
    # ADJUSTED SCORE
    # ============================================================
    adjusted_score = round(raw_composite * freshness_modifier * 100, 1)

    # ============================================================
    # BOTTLENECK DETECTION (Systems Thinking)
    # Cap composite at 1.5x the weakest component.
    # You're only as strong as your weakest link — can't use an
    # incredible quote if the source is garbage.
    # ============================================================
    component_scores = {
        'specificity': specificity,
        'intensity': intensity,
        'angle_potential': angle_potential,
        'credibility': credibility
    }
    min_component_val = min(component_scores.values())
    min_component_name = min(component_scores, key=component_scores.get)

    bottleneck_flag = None
    bottleneck_cap_applied = False
    if min_component_val < 0.2:
        bottleneck_flag = f"BOTTLENECK: {min_component_name} ({round(min_component_val, 2)})"

    bottleneck_cap = min_component_val * 1.5 * 100
    if adjusted_score > bottleneck_cap and min_component_val < 0.3:
        adjusted_score = round(bottleneck_cap, 1)
        bottleneck_cap_applied = True

    # ============================================================
    # ZERO-EVIDENCE GATE (Engineering Safety Factor)
    # A VOC item with no usable features is noise, not signal.
    # No specificity + no intensity + no angle potential = floor.
    # ============================================================
    zero_evidence_gate = False
    if specificity == 0 and raw_intensity == 0 and raw_angle_potential == 0:
        adjusted_score = min(5.0, adjusted_score)
        zero_evidence_gate = True

    # ============================================================
    # CONFIDENCE INTERVAL (Bayesian)
    # Width based on source credibility + dimension completeness.
    # ============================================================
    evidence_strength = credibility * 0.6 + dimension_bonus * 0.4
    uncertainty_width = (1 - evidence_strength) * 20
    confidence_low = max(0, round(adjusted_score - uncertainty_width, 1))
    confidence_high = min(100, round(adjusted_score + uncertainty_width, 1))

    # ============================================================
    # ASPIRATION GAP (derived from observables, not LLM judgment)
    # ============================================================
    crisis_indicators = sum([
        obs.get('crisis_language') == 'Y',
        obs.get('specific_number') == 'Y',
        obs.get('before_after_comparison') == 'Y',
        obs.get('identity_change_desire') == 'Y',
        obs.get('solution_sophistication') == 'EXHAUSTED'
    ])
    aspiration_gap = min(5, crisis_indicators + 1)

    return {
        'voc_id': obs.get('voc_id', 'Unknown'),
        'adjusted_score': adjusted_score,
        'confidence_range': (confidence_low, confidence_high),
        'aspiration_gap': aspiration_gap,
        'freshness_modifier': freshness_modifier,
        'bottleneck_flag': bottleneck_flag,
        'bottleneck_cap_applied': bottleneck_cap_applied,
        'zero_evidence_gate': zero_evidence_gate,
        'components': {
            'specificity': round(specificity * 100, 1),
            'intensity': round(intensity * 100, 1),
            'angle_potential': round(angle_potential * 100, 1),
            'credibility': round(credibility * 100, 1),
            'dimension_bonus': round(dimension_bonus * 100, 1),
            'signal_density': round(signal_density * 100, 1)
        },
        'raw_composite': round(raw_composite * 100, 1),
        'classifications': {
            'buyer_stage': obs.get('buyer_stage', 'UNKNOWN'),
            'solution_sophistication': obs.get('solution_sophistication', 'UNKNOWN'),
            'compliance_risk': obs.get('compliance_risk', 'UNKNOWN'),
            'date_bracket': obs.get('date_bracket', 'UNKNOWN')
        }
    }


def compute_corpus_health(items: List[Dict], scored_items: List[Dict]) -> Dict:
    """
    Compute corpus-level health metrics.
    """
    total = len(scored_items)
    if total == 0:
        return {'error': 'Empty corpus'}

    # Sentiment distribution
    valence_counts = Counter(i.get('emotional_valence', 'NEUTRAL') for i in items)
    max_valence_pct = max(valence_counts.values()) / total if valence_counts else 0

    # Buyer stage distribution
    stage_counts = Counter(s.get('classifications', {}).get('buyer_stage', 'UNKNOWN')
                          for s in scored_items)
    stages_present = sum(1 for s in ['UNAWARE', 'PROBLEM_AWARE', 'SOLUTION_AWARE',
                                      'PRODUCT_AWARE', 'MOST_AWARE']
                        if stage_counts.get(s, 0) > 0)

    # Solution sophistication distribution
    soph_counts = Counter(s.get('classifications', {}).get('solution_sophistication', 'UNKNOWN')
                         for s in scored_items)

    # Market Maturation Index (Product Lifecycle Theory)
    novice_pct = soph_counts.get('NOVICE', 0) / total
    experienced_pct = soph_counts.get('EXPERIENCED', 0) / total
    exhausted_pct = soph_counts.get('EXHAUSTED', 0) / total
    maturation_index = novice_pct * 1.0 + experienced_pct * 2.0 + exhausted_pct * 3.0

    if maturation_index < 1.5:
        market_stage = 'EARLY_MARKET'
    elif maturation_index < 2.2:
        market_stage = 'GROWTH_MARKET'
    else:
        market_stage = 'MATURE_MARKET'

    # Compliance distribution
    compliance_counts = Counter(s.get('classifications', {}).get('compliance_risk', 'UNKNOWN')
                               for s in scored_items)

    # Compliance hard gate (Engineering Safety Factor)
    high_scoring = [s for s in scored_items if s['adjusted_score'] >= 60]
    if high_scoring:
        red_in_top = sum(1 for s in high_scoring
                        if s.get('classifications', {}).get('compliance_risk') == 'RED')
        red_ratio_in_top = red_in_top / len(high_scoring)
    else:
        red_ratio_in_top = 0

    if red_ratio_in_top > 0.60:
        compliance_gate = 'CRITICAL_WARNING'
    elif red_ratio_in_top > 0.35:
        compliance_gate = 'ELEVATED_RISK'
    else:
        compliance_gate = 'MANAGEABLE'

    # Dimension Entropy (Information Theory)
    dimension_names = ['trigger_event', 'pain_problem', 'desired_outcome',
                       'failed_prior_solution', 'enemy_blame', 'identity_role',
                       'fear_risk', 'emotional_valence']

    dimension_fill_rates = {}
    for dim in dimension_names:
        filled = sum(1 for i in items
                    if i.get(dim) and i.get(dim) not in ['NONE', 'None', '', None])
        dimension_fill_rates[dim] = filled / total

    fill_values = list(dimension_fill_rates.values())
    total_fill = sum(fill_values)
    if total_fill > 0:
        probabilities = [r / total_fill for r in fill_values if r > 0]
        entropy = -sum(p * math.log2(p) for p in probabilities)
        max_entropy = math.log2(len(dimension_names))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
    else:
        normalized_entropy = 0

    # Score statistics
    scores = [s['adjusted_score'] for s in scored_items]

    # Bottleneck rate
    bottleneck_count = sum(1 for s in scored_items if s['bottleneck_cap_applied'])

    health = {
        'total_items': total,
        'target_met_200': total >= 200,
        'score_stats': {
            'mean': round(statistics.mean(scores), 1),
            'median': round(statistics.median(scores), 1),
            'std': round(statistics.stdev(scores), 1) if len(scores) > 1 else 0,
            'max': round(max(scores), 1),
            'min': round(min(scores), 1),
            'high_score_pct': round(sum(1 for s in scores if s >= 60) / total * 100, 1)
        },
        'sentiment_distribution': dict(valence_counts),
        'sentiment_skewed': max_valence_pct > 0.70,
        'max_sentiment_pct': round(max_valence_pct * 100, 1),
        'buyer_stages': dict(stage_counts),
        'stages_present': stages_present,
        'stages_target_met': stages_present >= 3,
        'sophistication_distribution': dict(soph_counts),
        'market_maturation_index': round(maturation_index, 2),
        'market_stage': market_stage,
        'compliance_distribution': dict(compliance_counts),
        'compliance_gate': compliance_gate,
        'red_ratio_in_top_items': round(red_ratio_in_top, 2),
        'dimension_fill_rates': {k: round(v, 2) for k, v in dimension_fill_rates.items()},
        'dimension_entropy': round(normalized_entropy, 3),
        'entropy_healthy': normalized_entropy >= 0.75,
        'bottleneck_rate': round(bottleneck_count / total * 100, 1),
        'aspiration_gap_distribution': dict(Counter(s['aspiration_gap'] for s in scored_items))
    }

    # Generate warnings
    warnings = []
    if not health['target_met_200']:
        warnings.append(f"LOW CORPUS VOLUME: {total} items (target: 200+)")
    if health['sentiment_skewed']:
        warnings.append(f"SENTIMENT SKEW: max valence at {health['max_sentiment_pct']}% (target: <70%)")
    if not health['stages_target_met']:
        warnings.append(f"STAGE GAP: only {stages_present}/5 buyer stages represented")
    if not health['entropy_healthy']:
        low_dims = [d for d, r in dimension_fill_rates.items() if r < 0.25]
        warnings.append(f"LOW DIMENSION ENTROPY ({round(normalized_entropy, 2)}). Underfilled: {low_dims}")
    if compliance_gate == 'CRITICAL_WARNING':
        warnings.append(f"COMPLIANCE CRITICAL: {round(red_ratio_in_top * 100)}% of top items are RED risk")
    elif compliance_gate == 'ELEVATED_RISK':
        warnings.append(f"COMPLIANCE ELEVATED: {round(red_ratio_in_top * 100)}% of top items are RED risk")

    health['warnings'] = warnings

    return health


def score_all_voc(items: List[Dict]) -> Dict:
    """
    Score all VOC items and compute corpus-level metrics.
    """
    scored = [score_voc_item(item) for item in items]

    # Z-Score Normalization
    scores = [s['adjusted_score'] for s in scored]
    if len(scores) > 1:
        mean_score = statistics.mean(scores)
        std_score = statistics.stdev(scores)
        if std_score > 0:
            for s in scored:
                s['z_score'] = round((s['adjusted_score'] - mean_score) / std_score, 2)
        else:
            for s in scored:
                s['z_score'] = 0.0
    else:
        for s in scored:
            s['z_score'] = 0.0

    # Regression to the Mean — Shrinkage
    # [Regression to Mean] Extreme scores from thin evidence are likely noise.
    # Pull extreme z-scores toward 0 proportional to evidence thinness.
    if len(scores) > 1:
        mean_score_val = statistics.mean(scores)
        for s in scored:
            # Evidence strength proxy: credibility component (0-100 scale)
            evidence_strength = s['components'].get('credibility', 50) / 100
            # Shrinkage factor: strong evidence → keep score; weak → pull toward mean
            shrinkage_factor = 0.5 + (evidence_strength * 0.5)  # range: 0.5 to 1.0
            shrunk_score = mean_score_val + (s['adjusted_score'] - mean_score_val) * shrinkage_factor
            s['shrunk_score'] = round(shrunk_score, 1)
            s['shrinkage_applied'] = round(1.0 - shrinkage_factor, 2)

    # Sort by adjusted score descending
    scored.sort(key=lambda x: x['adjusted_score'], reverse=True)

    # Corpus health
    health = compute_corpus_health(items, scored)

    return {
        'items': scored,
        'corpus_health': health,
        'z_score_interpretation': {
            'exceptional': 'z > 1.5',
            'strong': 'z > 0.5',
            'average': '0 to 0.5',
            'below_average': 'z < 0'
        }
    }


def print_voc_scorecard(results: Dict):
    """Pretty-print the VOC scorecard to stdout."""
    print("\n" + "=" * 90)
    print("VOC EXTRACTOR SCORECARD")
    print("=" * 90)

    health = results['corpus_health']
    target_str = "YES" if health['target_met_200'] else "NO"
    print(f"\nTotal Items: {health['total_items']} | Target Met: {target_str}")
    stats = health['score_stats']
    print(f"Score Stats -- Mean: {stats['mean']} | Median: {stats['median']} | "
          f"Std: {stats['std']} | High Score %: {stats['high_score_pct']}%")
    print(f"Market Stage: {health['market_stage']} (Maturation Index: {health['market_maturation_index']})")
    print(f"Compliance Gate: {health['compliance_gate']}")
    entropy_str = "OK" if health['entropy_healthy'] else "LOW"
    print(f"Dimension Entropy: {health['dimension_entropy']} ({entropy_str})")

    if health['warnings']:
        print("\n  WARNINGS:")
        for w in health['warnings']:
            print(f"  - {w}")

    print(f"\nDimension Fill Rates:")
    for dim, rate in health['dimension_fill_rates'].items():
        bar_filled = int(rate * 20)
        bar_empty = 20 - bar_filled
        bar = "#" * bar_filled + "." * bar_empty
        status = "OK" if rate >= 0.25 else "LOW"
        print(f"  {dim:<25} [{bar}] {round(rate * 100)}% {status}")

    print(f"\nBuyer Stages: {health['buyer_stages']}")
    print(f"Sophistication: {health['sophistication_distribution']}")
    print(f"Compliance: {health['compliance_distribution']}")

    print("\n" + "-" * 90)
    print("TOP 10 VOC ITEMS")
    print("-" * 90)
    print(f"{'ID':<8} {'Score':<8} {'Z':<7} {'Conf Range':<15} {'BN':<5} {'AspGap':<8} {'Stage'}")
    print("-" * 90)

    for item in results['items'][:10]:
        bn = "CAP" if item['bottleneck_cap_applied'] else "OK"
        conf = f"({item['confidence_range'][0]}-{item['confidence_range'][1]})"
        stage = item['classifications']['buyer_stage'][:12]
        print(f"{item['voc_id']:<8} {item['adjusted_score']:<8} {item['z_score']:<7} "
              f"{conf:<15} {bn:<5} {item['aspiration_gap']:<8} {stage}")


def main():
    parser = argparse.ArgumentParser(description='Score VOC observation sheets')
    parser.add_argument('--input', '-i', required=True, help='Input JSON file')
    parser.add_argument('--output', '-o', help='Output JSON file')
    args = parser.parse_args()

    with open(args.input, 'r') as f:
        data = json.load(f)

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and 'items' in data:
        items = data['items']
    else:
        print("Error: Input must be a JSON array of VOC observations")
        sys.exit(1)

    results = score_all_voc(items)
    print_voc_scorecard(results)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == '__main__':
    main()
