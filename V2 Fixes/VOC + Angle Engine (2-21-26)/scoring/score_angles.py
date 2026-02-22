#!/usr/bin/env python3
"""
Purple Ocean Angle Scoring Engine
===================================
Takes observation sheet data from Agent 3 and computes the final
Purple Ocean scores for angle candidates.

Mental Models Applied:
- First Principles: every weight justified causally
- Bayesian Reasoning: confidence intervals based on evidence quality
- Signal-to-Noise Ratio: support/contradiction ratio
- Systems Thinking (Bottleneck): min distinctiveness across saturated angles
- Information Theory: distinctiveness = information content
- Behavioral Economics: loss aversion in pain intensity
- Engineering Safety Factors: plausibility hard gate
- Logarithmic Diminishing Returns: demand signal volume
- Product Lifecycle Theory: angle lifecycle stage prediction
- Momentum (Physics): velocity in market timing
- Z-Score Normalization: cross-product comparability

Usage:
    python score_angles.py --input angle_observations.json --saturated 4 --output angle_scores.json
"""

import json
import math
import statistics
import argparse
import sys
from typing import Dict, List, Tuple, Optional


def score_angle(obs: Dict, saturated_count: int) -> Dict:
    """
    Score a single angle candidate from its observation sheet.

    Args:
        obs: Dictionary of observations from Agent 3
        saturated_count: Number of saturated angles being compared against
    """

    cluster_size = max(1, obs.get('distinct_voc_items', 1))

    # ============================================================
    # COMPONENT 1: DEMAND SIGNAL (0-1)
    # First principle: demand must be EVIDENCED, not assumed.
    # Log scale — diminishing returns on volume.
    # ============================================================
    voc_count = obs.get('distinct_voc_items', 0)
    author_count = obs.get('distinct_authors', 0)

    volume_signal = min(1.0, math.log(max(1, voc_count)) / math.log(200))

    author_diversity = min(1.0, author_count / max(1, voc_count))

    spike_density = min(1.0, obs.get('intensity_spike_count', 0) / max(1, voc_count) * 5)
    giant_density = min(1.0, obs.get('sleeping_giant_count', 0) / max(1, voc_count) * 10)
    high_aspiration = 1.0 if obs.get('aspiration_gap_4plus') == 'Y' else 0.0
    avg_quality = min(1.0, obs.get('avg_adjusted_score', 0) / 80)

    demand_signal = (
        volume_signal    * 0.25 +
        author_diversity * 0.15 +
        spike_density    * 0.15 +
        giant_density    * 0.15 +
        high_aspiration  * 0.10 +
        avg_quality      * 0.20
    )

    # ============================================================
    # COMPONENT 2: PAIN INTENSITY (0-1)
    # Behavioral economics: loss aversion — pain-driven purchases
    # are 2-3x more motivated than aspiration-driven.
    # Measured as DENSITY within cluster (not raw count).
    # ============================================================
    crisis_density = min(1.0, obs.get('crisis_language_count', 0) / cluster_size)
    financial_density = min(1.0, obs.get('dollar_time_loss_count', 0) / cluster_size)
    physical_density = min(1.0, obs.get('physical_symptom_count', 0) / cluster_size)
    emotion_density = min(1.0, obs.get('rage_shame_anxiety_count', 0) / cluster_size)
    exhaustion_density = min(1.0, obs.get('exhausted_sophistication_count', 0) / cluster_size)

    pain_intensity = (
        crisis_density     * 0.25 +
        financial_density  * 0.20 +
        physical_density   * 0.15 +
        emotion_density    * 0.25 +
        exhaustion_density * 0.15
    )

    # ============================================================
    # COMPONENT 3: DISTINCTIVENESS (0-1)
    # Information theory: identical messages carry zero info.
    # Systems thinking (bottleneck): use MINIMUM distinctiveness
    # across all saturated angles — worst case determines score.
    # ============================================================
    distinctiveness_scores = []
    for sa_idx in range(saturated_count):
        dims_different = sum([
            obs.get(f'sa{sa_idx}_different_who') == 'Y',
            obs.get(f'sa{sa_idx}_different_trigger') == 'Y',
            obs.get(f'sa{sa_idx}_different_enemy') == 'Y',
            obs.get(f'sa{sa_idx}_different_belief') == 'Y',
            obs.get(f'sa{sa_idx}_different_mechanism') == 'Y'
        ])
        distinctiveness_scores.append(dims_different / 5)

    if distinctiveness_scores:
        min_dist = min(distinctiveness_scores)
        avg_dist = sum(distinctiveness_scores) / len(distinctiveness_scores)
        distinctiveness = min_dist * 0.6 + avg_dist * 0.4
    else:
        distinctiveness = 0.5

    # ============================================================
    # COMPONENT 4: PLAUSIBILITY (0-1) + HARD GATE
    # Engineering safety: an angle the product can't deliver = fraud.
    # Binary checks. Hard floor at 0.5.
    # ============================================================
    plausibility_checks = [
        obs.get('product_addresses_pain') == 'Y',
        obs.get('product_feature_maps_to_mechanism') == 'Y',
        obs.get('outcome_achievable') == 'Y',
        obs.get('mechanism_factually_supportable') == 'Y'
    ]
    plausibility = sum(plausibility_checks) / len(plausibility_checks)
    plausibility_gate = plausibility >= 0.5

    # ============================================================
    # COMPONENT 5: EVIDENCE QUALITY (0-1)
    # Bayesian: confidence proportional to evidence quality.
    # SNR: support / (support + contradiction).
    # ============================================================
    supporting = obs.get('supporting_voc_count', 0)
    high_quality = obs.get('items_above_60', 0)
    contradicting = obs.get('contradiction_count', 0)

    snr = supporting / (supporting + contradicting) if (supporting + contradicting) > 0 else 0
    quality_density = high_quality / supporting if supporting > 0 else 0

    triangulation_score = {
        'SINGLE': 0.3,
        'DUAL': 0.65,
        'MULTI': 1.0
    }.get(obs.get('triangulation_status', 'SINGLE'), 0.3)

    evidence_quality = (
        snr                 * 0.35 +
        quality_density     * 0.30 +
        triangulation_score * 0.35
    )

    # Source diversity modifier [Information Theory + Simpson's Paradox]
    # Single-source angles may not generalize; multi-source angles are more robust
    source_types = obs.get('source_habitat_types', 1)
    dominant_pct = obs.get('dominant_source_pct', 100) / 100  # convert to 0-1

    if source_types >= 3:
        diversity_modifier = 1.1  # bonus for multi-source
    elif source_types == 2:
        diversity_modifier = 1.0  # neutral
    elif dominant_pct > 0.8:
        diversity_modifier = 0.8  # penalty for extreme single-source dominance
    else:
        diversity_modifier = 0.9  # mild penalty for single source

    evidence_quality = min(1.0, evidence_quality * diversity_modifier)

    # ============================================================
    # COMPONENT 6: COMPLIANCE SAFETY (0-1)
    # Risk management: brilliant angle + banned ad account = negative EV.
    # ============================================================
    total_compliance = (obs.get('green_count', 0) + obs.get('yellow_count', 0) +
                       obs.get('red_count', 0))
    if total_compliance > 0:
        green_ratio = obs.get('green_count', 0) / total_compliance
        red_ratio = obs.get('red_count', 0) / total_compliance
    else:
        green_ratio = 0
        red_ratio = 0

    expressible = 1.0 if obs.get('expressible_without_red') == 'Y' else 0.0
    no_disease = 1.0 if obs.get('requires_disease_naming') != 'Y' else 0.0

    compliance_safety = (
        green_ratio  * 0.25 +
        (1 - red_ratio) * 0.25 +
        expressible  * 0.30 +
        no_disease   * 0.20
    )

    # ============================================================
    # COMPONENT 7: MARKET TIMING (0-1)
    # Momentum + lifecycle + dependency resilience.
    # ============================================================
    velocity_score = {
        'ACCELERATING': 1.0,
        'STEADY': 0.6,
        'DECELERATING': 0.25
    }.get(obs.get('velocity_status', 'STEADY'), 0.6)

    stages_present = sum(1 for stage in ['UNAWARE', 'PROBLEM_AWARE', 'SOLUTION_AWARE',
                                          'PRODUCT_AWARE', 'MOST_AWARE']
                        if obs.get(f'stage_{stage}_count', 0) > 0)
    stage_breadth = stages_present / 5

    chronicity_score = {
        'ACUTE': 0.4, 'CHRONIC': 0.9, 'BOTH': 1.0
    }.get(obs.get('pain_chronicity', 'CHRONIC'), 0.6)

    seasonality_score = {
        'ONGOING': 1.0, 'EVENT_DRIVEN': 0.6, 'SEASONAL': 0.4
    }.get(obs.get('trigger_seasonality', 'ONGOING'), 0.6)

    # Lifecycle stage prediction (Product Lifecycle Theory)
    comp_usage = obs.get('competitor_count_using_angle', '0')
    recent_entry = obs.get('recent_competitor_entry') == 'Y'
    vel = obs.get('velocity_status', 'STEADY')

    if comp_usage == '0' and vel == 'ACCELERATING':
        lifecycle = 'INTRODUCTION_HIGH_POTENTIAL'
        lifecycle_score_val = 0.85
    elif comp_usage == '0' and vel != 'ACCELERATING':
        lifecycle = 'INTRODUCTION_UNCERTAIN'
        lifecycle_score_val = 0.50
    elif comp_usage == '1-2' and vel == 'ACCELERATING':
        lifecycle = 'EARLY_GROWTH'
        lifecycle_score_val = 1.0
    elif comp_usage == '1-2':
        lifecycle = 'EARLY_GROWTH_STEADY'
        lifecycle_score_val = 0.75
    elif comp_usage == '3-5' and not recent_entry:
        lifecycle = 'MATURE_STABLE'
        lifecycle_score_val = 0.45
    elif comp_usage == '3-5' and recent_entry:
        lifecycle = 'GROWTH_CROWDING'
        lifecycle_score_val = 0.60
    elif comp_usage == '6+':
        lifecycle = 'SATURATED'
        lifecycle_score_val = 0.15
    else:
        lifecycle = 'UNKNOWN'
        lifecycle_score_val = 0.50

    # Dependency resilience
    structural = 1.0 if obs.get('pain_structural') == 'Y' else 0.4
    no_news_dep = 0.0 if obs.get('news_cycle_dependent') == 'Y' else 1.0
    no_comp_dep = 0.0 if obs.get('competitor_behavior_dependent') == 'Y' else 1.0
    dependency_resilience = structural * 0.50 + no_news_dep * 0.25 + no_comp_dep * 0.25

    market_timing = (
        velocity_score      * 0.20 +
        stage_breadth       * 0.10 +
        chronicity_score    * 0.15 +
        seasonality_score   * 0.10 +
        lifecycle_score_val * 0.25 +
        dependency_resilience * 0.20
    )

    # ============================================================
    # COMPONENT 8: CREATIVE EXECUTABILITY (0-1)
    # Practical test: can this become an ad?
    # ============================================================
    exec_features = [
        obs.get('single_visual_expressible') == 'Y',
        obs.get('hook_under_12_words') == 'Y',
        obs.get('natural_villain_present') == 'Y',
        obs.get('language_registry_headline_exists') == 'Y'
    ]
    executability = sum(exec_features) / len(exec_features)

    # ============================================================
    # COMPONENT 9: ADDRESSABLE SCOPE (0-1)
    # Market size proxy — narrow segments may not justify spend.
    # ============================================================
    scope_map = {'NARROW': 0.3, 'MODERATE': 0.6, 'BROAD': 1.0}
    universality_map = {'SUBGROUP': 0.3, 'MODERATE': 0.6, 'UNIVERSAL': 1.0}

    addressable_scope = (
        scope_map.get(obs.get('segment_breadth', 'MODERATE'), 0.6) * 0.40 +
        universality_map.get(obs.get('pain_universality', 'MODERATE'), 0.6) * 0.35 +
        stage_breadth * 0.25
    )

    # ============================================================
    # === PURPLE OCEAN COMPOSITE ===
    # ============================================================
    raw_composite = (
        distinctiveness   * 0.20 +
        evidence_quality  * 0.18 +
        demand_signal     * 0.15 +
        pain_intensity    * 0.13 +
        compliance_safety * 0.07 +
        market_timing     * 0.07 +
        executability     * 0.06 +
        addressable_scope * 0.06 +
        plausibility      * 0.05
    )

    # Apply plausibility gate
    gate_applied = False
    if not plausibility_gate:
        final_score = min(30.0, raw_composite * 100)
        gate_applied = True
    else:
        final_score = round(raw_composite * 100, 1)

    # ============================================================
    # EVIDENCE FLOOR GATE (Engineering Safety Factor)
    # An angle with fewer than 5 supporting VOC items does not have
    # sufficient evidence to be tested. Below the stated minimum.
    # ============================================================
    evidence_floor_gate = False
    if supporting < 5:
        final_score = min(20.0, final_score)
        evidence_floor_gate = True
        gate_applied = True

    # ============================================================
    # CONFIDENCE INTERVAL (Bayesian + Variance-Aware)
    # Width driven by: (1) evidence quality AND (2) component score variance.
    # High variance across components = unstable signal = wider interval.
    # ============================================================
    component_values = [
        distinctiveness, evidence_quality, demand_signal, pain_intensity,
        compliance_safety, market_timing, executability, addressable_scope, plausibility
    ]
    if len(component_values) > 1:
        component_variance = statistics.variance(component_values)
    else:
        component_variance = 0

    # Base width from evidence quality, expanded by component variance
    evidence_width = (1 - evidence_quality) * 20
    variance_width = min(10, component_variance * 50)  # cap variance contribution
    uncertainty_width = evidence_width + variance_width
    confidence_low = max(0, round(final_score - uncertainty_width, 1))
    confidence_high = min(100, round(final_score + uncertainty_width, 1))

    return {
        'angle_name': obs.get('angle_name', 'Unknown'),
        'angle_id': obs.get('angle_id', 'Unknown'),
        'final_score': final_score,
        'confidence_range': (confidence_low, confidence_high),
        'plausibility_gate_applied': gate_applied,
        'evidence_floor_gate': evidence_floor_gate,
        'lifecycle_stage': lifecycle,
        'components': {
            'distinctiveness': round(distinctiveness * 100, 1),
            'evidence_quality': round(evidence_quality * 100, 1),
            'demand_signal': round(demand_signal * 100, 1),
            'pain_intensity': round(pain_intensity * 100, 1),
            'compliance_safety': round(compliance_safety * 100, 1),
            'market_timing': round(market_timing * 100, 1),
            'executability': round(executability * 100, 1),
            'addressable_scope': round(addressable_scope * 100, 1),
            'plausibility': round(plausibility * 100, 1)
        },
        'raw_composite': round(raw_composite * 100, 1)
    }


def detect_overlaps(angles: List[Dict]) -> List[Dict]:
    """
    Detect intra-candidate overlaps — pairs that are too similar.
    """
    overlaps = []
    for i, a in enumerate(angles):
        for j, b in enumerate(angles):
            if j <= i:
                continue
            shared = sum([
                a.get('who') == b.get('who'),
                a.get('trigger') == b.get('trigger'),
                a.get('enemy') == b.get('enemy'),
                a.get('belief_shift') == b.get('belief_shift'),
                a.get('mechanism') == b.get('mechanism')
            ])
            if shared >= 4:
                overlaps.append({
                    'angle_a': a.get('angle_name', f'A{i}'),
                    'angle_b': b.get('angle_name', f'A{j}'),
                    'shared_dimensions': shared,
                    'recommendation': 'MERGE -- differ on fewer than 2 dimensions'
                })
    return overlaps


def score_all_angles(angles: List[Dict], saturated_count: int) -> Dict:
    """
    Score all angle candidates and compute z-scores.
    """
    scored = [score_angle(a, saturated_count) for a in angles]

    # Z-Score Normalization
    scores = [a['final_score'] for a in scored]
    if len(scores) > 1:
        mean_score = statistics.mean(scores)
        std_score = statistics.stdev(scores)
        if std_score > 0:
            for a in scored:
                a['z_score'] = round((a['final_score'] - mean_score) / std_score, 2)
        else:
            for a in scored:
                a['z_score'] = 0.0
    else:
        mean_score = scores[0] if scores else 0
        std_score = 0
        for a in scored:
            a['z_score'] = 0.0

    scored.sort(key=lambda x: x['final_score'], reverse=True)

    for i, a in enumerate(scored):
        a['rank'] = i + 1

    summary = {
        'total_angles': len(scored),
        'mean_score': round(mean_score, 1),
        'std_score': round(std_score, 1) if std_score else 0,
        'gates_applied': sum(1 for a in scored if a['plausibility_gate_applied']),
        'lifecycle_distribution': {},
        'top_3': [{'name': a['angle_name'], 'score': a['final_score'],
                   'confidence': a['confidence_range']} for a in scored[:3]]
    }

    for a in scored:
        l = a['lifecycle_stage']
        summary['lifecycle_distribution'][l] = summary['lifecycle_distribution'].get(l, 0) + 1

    return {
        'angles': scored,
        'summary': summary,
        'z_score_interpretation': {
            'exceptional': 'z > 1.5 -- top tier, test immediately',
            'strong': 'z > 0.5 -- strong candidate, include in first test batch',
            'average': '0 to 0.5 -- viable but not differentiated',
            'below_average': 'z < 0 -- deprioritize unless strategic reason to test',
            'gated': 'Score capped at 30 -- plausibility concerns, do not test without product changes'
        }
    }


def print_purple_ocean_scorecard(results: Dict):
    """Pretty-print the Purple Ocean scorecard."""
    print("\n" + "=" * 100)
    print("PURPLE OCEAN ANGLE SCORECARD")
    print("=" * 100)

    summary = results['summary']
    print(f"\nTotal Angles: {summary['total_angles']} | "
          f"Mean: {summary['mean_score']} | Std: {summary['std_score']}")
    print(f"Plausibility Gates Applied: {summary['gates_applied']}")
    print(f"Lifecycle Distribution: {summary['lifecycle_distribution']}")

    print("\n" + "-" * 100)
    print(f"{'Rank':<5} {'Score':<8} {'Z':<7} {'Conf Range':<16} {'Gate':<6} "
          f"{'Lifecycle':<22} {'Angle Name'}")
    print("-" * 100)

    for a in results['angles']:
        gate = "GATED" if a['plausibility_gate_applied'] else "OK"
        conf = f"({a['confidence_range'][0]}-{a['confidence_range'][1]})"
        lc = a['lifecycle_stage'][:20]
        print(f"{a['rank']:<5} {a['final_score']:<8} {a['z_score']:<7} {conf:<16} "
              f"{gate:<6} {lc:<22} {a['angle_name']}")

    print("\n" + "-" * 100)
    print("COMPONENT BREAKDOWN (Top 5)")
    print("-" * 100)

    for a in results['angles'][:5]:
        print(f"\n  #{a['rank']} {a['angle_name']} "
              f"(Score: {a['final_score']}, Z: {a['z_score']}, "
              f"Lifecycle: {a['lifecycle_stage']})")
        for comp, val in a['components'].items():
            bar_filled = int(val / 5)
            bar_empty = 20 - bar_filled
            bar = "#" * bar_filled + "." * bar_empty
            print(f"    {comp:<25} [{bar}] {val}")

    print("\n" + "=" * 100)
    print("Z-SCORE INTERPRETATION")
    print("=" * 100)
    for label, desc in results['z_score_interpretation'].items():
        print(f"  {label:<20} {desc}")


def main():
    parser = argparse.ArgumentParser(description='Score angle observation sheets (Purple Ocean)')
    parser.add_argument('--input', '-i', required=True, help='Input JSON file')
    parser.add_argument('--saturated', '-s', type=int, required=True,
                       help='Number of saturated angles being compared against')
    parser.add_argument('--output', '-o', help='Output JSON file')
    parser.add_argument('--overlaps', help='JSON file with angle primitive data for overlap detection')
    args = parser.parse_args()

    with open(args.input, 'r') as f:
        data = json.load(f)

    if isinstance(data, list):
        angles = data
    elif isinstance(data, dict) and 'angles' in data:
        angles = data['angles']
    else:
        print("Error: Input must be a JSON array of angle observations")
        sys.exit(1)

    results = score_all_angles(angles, args.saturated)

    # Overlap detection if data provided
    if args.overlaps:
        with open(args.overlaps, 'r') as f:
            overlap_data = json.load(f)
        overlaps = detect_overlaps(overlap_data if isinstance(overlap_data, list) else overlap_data.get('angles', []))
        results['overlaps'] = overlaps
        if overlaps:
            print("\n  MERGE CANDIDATES DETECTED:")
            for o in overlaps:
                print(f"  {o['angle_a']} <-> {o['angle_b']} "
                      f"(shared: {o['shared_dimensions']}/5 dims) -- {o['recommendation']}")

    print_purple_ocean_scorecard(results)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == '__main__':
    main()
