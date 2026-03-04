#!/usr/bin/env python3
"""
Social Video Virality Scoring Engine
======================================
Takes raw scraped social video data (from Apify scraper layer) and computes
virality metrics to feed into Agent 1 (Habitat Qualifier). This script sits
between the scraper output and the agent pipeline — it transforms raw platform
data into structured, comparable virality signals.

Mental Models Applied:
- First Principles: each metric decomposes to directly observable primitives
  (views, followers, comments, shares, days) — no compound judgments
- Logarithmic Diminishing Returns: log transform on skewed metrics before
  z-scoring — the jump from 1K to 10K views matters more than 100K to 110K
- Z-Score Normalization: cross-platform comparability within the scraped batch
- Goodhart's Law: the LLM never sees the formula, only tier labels — prevents
  gaming the scoring criteria in upstream observation steps
- Signal-to-Noise Ratio: comments and shares weighted over likes — passive
  engagement (likes) is noise, active engagement (comments/shares) is signal
- Engineering Safety Factors: minimum view threshold (10K) filters noise floor;
  90-day recency gate on velocity prevents stale data from distorting rankings

Usage:
    python score_virality.py --input raw_video_data.json --output scored_videos.json

    Or import and use programmatically:
    from score_virality import score_video, score_all_videos
"""

import json
import math
import statistics
import argparse
import sys
from collections import Counter
from typing import Dict, List, Optional


# ============================================================
# CONSTANTS
# Thresholds and weights are defined here, not inside functions,
# so they are auditable and modifiable without reading logic.
# ============================================================

# Metric A — Follower-Relative Performance thresholds
VIRALITY_RATIO_VIRAL = 50.0
VIRALITY_RATIO_HIGH = 20.0
VIRALITY_RATIO_ABOVE_AVG = 5.0
MIN_VIEW_THRESHOLD = 10_000
MIN_FOLLOWER_FLOOR = 100  # [Engineering Safety Factors] prevents division by near-zero

# Metric B — Velocity thresholds
VELOCITY_VIRAL = 50_000  # views/day
VELOCITY_FAST = 10_000   # views/day
MAX_VELOCITY_AGE_DAYS = 90  # [Engineering Safety Factors] recency gate
MIN_DAYS_FLOOR = 1  # prevents division by zero

# Metric C — Engagement Density thresholds (per 1,000 views)
ENGAGEMENT_HIGH_CONVERSATION = 50.0
ENGAGEMENT_ABOVE_AVERAGE = 20.0

# Composite weights
# [First Principles] Each weight justified by causal importance:
#   0.4 on follower-relative: strongest signal that CONTENT won, not the
#       creator's pre-existing audience. A 500-follower account getting 100K
#       views means the algorithm chose the content. This is the most
#       actionable signal for angle discovery.
#   0.3 on velocity: captures timeliness and algorithm momentum. Fast spikes
#       indicate the algorithm is actively distributing the content NOW,
#       which matters for trend-sensitive habitat qualification.
#   0.3 on engagement density: captures VOC richness of comments section.
#       High comment density = more voice-of-customer data to mine.
#       Shares indicate the content resonated enough to forward.
WEIGHT_VIRALITY_RATIO = 0.4
WEIGHT_VELOCITY = 0.3
WEIGHT_ENGAGEMENT_DENSITY = 0.3

# High Authority Track threshold
HIGH_AUTHORITY_VIEW_THRESHOLD = 100_000


def classify_virality_tier(virality_ratio: float, views: int) -> str:
    """
    Classify a video into a virality tier based on its follower-relative
    performance ratio.

    [Goodhart's Law] The tier label is what downstream agents see — not the
    raw ratio. This prevents the LLM from anchoring on or gaming specific
    numeric thresholds.

    Args:
        virality_ratio: views / max(followers, 100)
        views: raw view count (must pass minimum threshold)

    Returns:
        Tier string: VIRAL, HIGH_PERFORMING, ABOVE_AVERAGE, or BASELINE
    """
    # [Engineering Safety Factors] Videos below the noise floor are BASELINE
    # regardless of ratio — a 50-follower account with 400 views has an 8x
    # ratio but is not meaningfully viral.
    if views < MIN_VIEW_THRESHOLD:
        return 'BASELINE'

    if virality_ratio >= VIRALITY_RATIO_VIRAL:
        return 'VIRAL'
    elif virality_ratio >= VIRALITY_RATIO_HIGH:
        return 'HIGH_PERFORMING'
    elif virality_ratio >= VIRALITY_RATIO_ABOVE_AVG:
        return 'ABOVE_AVERAGE'
    else:
        return 'BASELINE'


def score_video(obs: Dict) -> Dict:
    """
    Score a single video from its raw scraped data.

    Args:
        obs: Dictionary of raw video data from the Apify scraper layer.
             Expected keys: video_id, platform, views, followers, comments,
             shares, likes, days_since_posted, description, author

    Returns:
        Dictionary with computed metrics, tier classification, and metadata.
        The viral_score composite is set to None here — it requires batch-level
        z-score normalization and is computed in score_all_videos().
    """

    # ============================================================
    # EXTRACT RAW OBSERVABLES
    # [First Principles] Pull directly from scraped data. Every metric
    # traces back to a platform-reported number. No derived judgments.
    # ============================================================
    views = max(0, obs.get('views', 0))
    followers = max(0, obs.get('followers', 0))
    comments = max(0, obs.get('comments', 0))
    shares = max(0, obs.get('shares', 0))
    likes = max(0, obs.get('likes', 0))
    days_since_posted = max(0, obs.get('days_since_posted', 0))
    platform = obs.get('platform', 'UNKNOWN').upper()

    # ============================================================
    # METRIC A: FOLLOWER-RELATIVE PERFORMANCE (the "small account breakout")
    # Formula: views / max(followers, 100)
    #
    # WHY THIS MATTERS: When a small account's video massively outperforms
    # their follower base, the CONTENT is what won — not the creator's
    # pre-existing distribution. This is the strongest signal for
    # identifying angles that the algorithm rewards.
    #
    # max(followers, 100) is an [Engineering Safety Factor] — accounts
    # reporting 0 or very few followers (new accounts, private profiles,
    # scraping gaps) would produce infinite or astronomically inflated
    # ratios. The floor of 100 caps the maximum possible ratio at
    # views/100, which is still generous for breakout detection.
    # ============================================================
    effective_followers = max(followers, MIN_FOLLOWER_FLOOR)
    virality_ratio = views / effective_followers

    # ============================================================
    # METRIC B: VELOCITY (the "fast spike")
    # Formula: views / max(days_since_posted, 1)
    #
    # WHY THIS MATTERS: A video accumulating 500K views in 3 days signals
    # active algorithmic distribution RIGHT NOW. The same 500K over 2 years
    # is just a slow burn. Velocity captures timeliness.
    #
    # max(days_since_posted, 1) is an [Engineering Safety Factor] —
    # same-day posts would divide by zero.
    #
    # The 90-day recency gate filters out old videos entirely. A video
    # posted 6 months ago with 1M views has a misleadingly low velocity
    # (5.5K/day) but was likely viral in its first week. We cannot
    # reconstruct the original velocity curve from a single data point,
    # so we exclude stale data rather than misrepresent it.
    # ============================================================
    effective_days = max(days_since_posted, MIN_DAYS_FLOOR)
    velocity_eligible = days_since_posted <= MAX_VELOCITY_AGE_DAYS

    if velocity_eligible:
        velocity = views / effective_days
    else:
        # Videos older than 90 days get velocity = 0.
        # They can still score on Metric A and C.
        velocity = 0.0

    # ============================================================
    # METRIC C: ENGAGEMENT DENSITY (the "conversation starter")
    # Formula: (comments + shares) / max(views, 1) * 1000
    #
    # WHY THIS MATTERS: For angle discovery, we need videos where
    # people TALK, not just tap. Comments are raw VOC data. Shares
    # indicate the content resonated enough to redistribute.
    #
    # [Signal-to-Noise Ratio] Likes are intentionally excluded:
    #   - Likes are a passive, low-effort action (noise)
    #   - Comments require cognitive engagement (signal)
    #   - Shares require social endorsement (signal)
    #   - A video with 100K likes and 50 comments is entertainment
    #   - A video with 10K likes and 5K comments is a conversation
    #
    # Scaled per 1,000 views to normalize across video sizes.
    # max(views, 1) prevents division by zero for scraped entries
    # where views haven't loaded yet.
    # ============================================================
    effective_views = max(views, 1)
    engagement_density = (comments + shares) / effective_views * 1000

    # ============================================================
    # TIER CLASSIFICATION
    # ============================================================
    tier = classify_virality_tier(virality_ratio, views)

    # ============================================================
    # HIGH AUTHORITY TRACK
    # Any video with 100K+ views, regardless of account size, enters
    # a separate track sorted by engagement density. These videos
    # have proven distribution — the question is whether their
    # comments section is worth mining for VOC data.
    # ============================================================
    high_authority_track = views >= HIGH_AUTHORITY_VIEW_THRESHOLD

    return {
        'video_id': obs.get('video_id', 'unknown'),
        'platform': platform,
        'views': views,
        'followers': followers,
        'comments': comments,
        'shares': shares,
        'likes': likes,
        'days_since_posted': days_since_posted,
        'description': obs.get('description', ''),
        'author': obs.get('author', 'unknown'),
        'virality_ratio': round(virality_ratio, 2),
        'velocity': round(velocity, 2),
        'velocity_eligible': velocity_eligible,
        'engagement_density': round(engagement_density, 2),
        'viral_score': None,  # computed in batch after z-score normalization
        'tier': tier,
        'high_authority_track': high_authority_track,
        'z_scores': {
            'virality_ratio_z': None,  # computed in batch
            'velocity_z': None,        # computed in batch
            'engagement_density_z': None  # computed in batch
        }
    }


def _z_score_normalize(values: List[float]) -> List[float]:
    """
    Compute z-scores for a list of values with log transform.

    [Logarithmic Diminishing Returns] Raw virality metrics follow extreme
    power-law distributions (a few videos at 10M views, most at 10K). Without
    log transform, the z-scores would be dominated by outliers and the vast
    majority of videos would cluster near z=0 with no differentiation.

    Log transform compresses the scale so that the jump from 1K to 10K
    (one order of magnitude) is weighted equally to the jump from 100K to 1M.
    This matches our intuition: going from 1K to 10K views is just as
    meaningful a signal as going from 100K to 1M.

    [Z-Score Normalization] After log transform, standard z-scoring ensures
    cross-platform comparability. A z=1.5 on TikTok means the same relative
    performance as z=1.5 on Instagram, even though the raw view counts
    differ dramatically between platforms.

    Args:
        values: List of raw metric values (views, velocity, density, etc.)

    Returns:
        List of z-scores (same length as input). Returns all zeros if
        fewer than 2 values or zero standard deviation.
    """
    if len(values) < 2:
        return [0.0] * len(values)

    # [Logarithmic Diminishing Returns] Log transform before z-scoring
    # log(x + 1) to handle zero values safely
    log_values = [math.log(v + 1) for v in values]

    mean_val = statistics.mean(log_values)
    std_val = statistics.stdev(log_values)

    if std_val == 0:
        return [0.0] * len(values)

    return [(v - mean_val) / std_val for v in log_values]


def _z_to_0_1(z: float) -> float:
    """
    Map a z-score to a 0-1 range using a sigmoid-like clamp.

    Z-scores typically range from -3 to +3 for normal distributions.
    We clamp to [-3, +3] and linearly map to [0, 1]. This preserves
    the relative ordering while bounding the composite input.

    Args:
        z: Raw z-score

    Returns:
        Float in [0, 1] range
    """
    clamped = max(-3.0, min(3.0, z))
    return (clamped + 3.0) / 6.0


def score_all_videos(videos: List[Dict]) -> Dict:
    """
    Score all videos, compute batch-level z-scores, and generate the
    composite viral_score.

    [Z-Score Normalization] The composite score is computed AFTER z-scoring
    within the batch. This means the score reflects relative performance
    within this specific scrape, not absolute thresholds. A video that is
    "VIRAL" in a batch of mostly low-performing content may not be VIRAL
    in a batch scraped from a trending hashtag.

    Args:
        videos: List of raw video data dictionaries from the scraper

    Returns:
        Dictionary with scored videos (sorted by viral_score descending),
        summary statistics, tier distribution, high authority track, and
        platform-level stats.
    """
    # Score each video individually (metrics computed, z-scores pending)
    scored = [score_video(v) for v in videos]

    if not scored:
        return {
            'videos': [],
            'summary': {'total': 0, 'error': 'Empty input'},
            'tier_distribution': {},
            'high_authority_track': [],
            'platform_stats': {}
        }

    # ============================================================
    # BATCH Z-SCORE NORMALIZATION
    # [Z-Score Normalization] Compute z-scores across the entire batch
    # for each metric independently. This ensures that the composite
    # score reflects relative standing within THIS scrape.
    #
    # [Logarithmic Diminishing Returns] Log transform is applied inside
    # _z_score_normalize() before z-scoring to handle the extreme skew
    # of social media metrics.
    # ============================================================
    vr_values = [s['virality_ratio'] for s in scored]
    vel_values = [s['velocity'] for s in scored]
    ed_values = [s['engagement_density'] for s in scored]

    vr_z_scores = _z_score_normalize(vr_values)
    vel_z_scores = _z_score_normalize(vel_values)
    ed_z_scores = _z_score_normalize(ed_values)

    # ============================================================
    # COMPOSITE VIRAL SCORE
    # Weighted combination of normalized z-scores mapped to [0, 1].
    #
    # Weight justifications (from constants section):
    #   0.4 virality_ratio  — content quality signal (audience-independent)
    #   0.3 velocity        — timeliness / algorithm momentum
    #   0.3 engagement_density — VOC richness of comments section
    #
    # [First Principles] Each weight traces to a causal reason:
    #   - We want angles that win on CONTENT (0.4 on ratio)
    #   - We want angles that are CURRENT (0.3 on velocity)
    #   - We want angles that GENERATE DISCUSSION (0.3 on density)
    # ============================================================
    for i, s in enumerate(scored):
        s['z_scores']['virality_ratio_z'] = round(vr_z_scores[i], 3)
        s['z_scores']['velocity_z'] = round(vel_z_scores[i], 3)
        s['z_scores']['engagement_density_z'] = round(ed_z_scores[i], 3)

        # Map z-scores to 0-1 range for composite weighting
        vr_norm = _z_to_0_1(vr_z_scores[i])
        vel_norm = _z_to_0_1(vel_z_scores[i])
        ed_norm = _z_to_0_1(ed_z_scores[i])

        composite = (
            WEIGHT_VIRALITY_RATIO * vr_norm +
            WEIGHT_VELOCITY * vel_norm +
            WEIGHT_ENGAGEMENT_DENSITY * ed_norm
        )

        s['viral_score'] = round(composite, 4)

    # ============================================================
    # SORT BY COMPOSITE SCORE DESCENDING
    # ============================================================
    scored.sort(key=lambda x: x['viral_score'], reverse=True)

    # Add rank
    for i, s in enumerate(scored):
        s['rank'] = i + 1

    # ============================================================
    # SUMMARY STATISTICS
    # ============================================================
    viral_scores = [s['viral_score'] for s in scored]
    tier_counts = Counter(s['tier'] for s in scored)
    platform_counts = Counter(s['platform'] for s in scored)

    summary = {
        'total': len(scored),
        'viral_count': tier_counts.get('VIRAL', 0),
        'high_performing_count': tier_counts.get('HIGH_PERFORMING', 0),
        'above_average_count': tier_counts.get('ABOVE_AVERAGE', 0),
        'baseline_count': tier_counts.get('BASELINE', 0),
        'score_stats': {
            'mean': round(statistics.mean(viral_scores), 4),
            'median': round(statistics.median(viral_scores), 4),
            'std': round(statistics.stdev(viral_scores), 4) if len(viral_scores) > 1 else 0,
            'max': round(max(viral_scores), 4),
            'min': round(min(viral_scores), 4)
        },
        'platform_distribution': dict(platform_counts),
        'below_min_view_threshold': sum(1 for s in scored if s['views'] < MIN_VIEW_THRESHOLD),
        'velocity_ineligible': sum(1 for s in scored if not s['velocity_eligible'])
    }

    # ============================================================
    # TIER DISTRIBUTION
    # ============================================================
    tier_distribution = {
        'VIRAL': tier_counts.get('VIRAL', 0),
        'HIGH_PERFORMING': tier_counts.get('HIGH_PERFORMING', 0),
        'ABOVE_AVERAGE': tier_counts.get('ABOVE_AVERAGE', 0),
        'BASELINE': tier_counts.get('BASELINE', 0)
    }

    # ============================================================
    # HIGH AUTHORITY TRACK (separate list)
    # Videos with 100K+ views sorted by engagement density descending.
    # These are worth mining regardless of follower-relative performance
    # because they have PROVEN distribution and potentially rich comment
    # sections.
    # ============================================================
    high_authority = [s for s in scored if s['high_authority_track']]
    high_authority.sort(key=lambda x: x['engagement_density'], reverse=True)

    # ============================================================
    # PLATFORM-LEVEL STATS
    # Mean engagement density by platform — reveals which platforms
    # produce richer VOC comment sections for this topic.
    # ============================================================
    platform_stats = {}
    for platform in platform_counts:
        platform_videos = [s for s in scored if s['platform'] == platform]
        platform_stats[platform] = {
            'count': len(platform_videos),
            'mean_views': round(statistics.mean([s['views'] for s in platform_videos]), 0),
            'mean_engagement_density': round(
                statistics.mean([s['engagement_density'] for s in platform_videos]), 2
            ),
            'mean_virality_ratio': round(
                statistics.mean([s['virality_ratio'] for s in platform_videos]), 2
            ),
            'mean_viral_score': round(
                statistics.mean([s['viral_score'] for s in platform_videos]), 4
            ),
            'viral_count': sum(1 for s in platform_videos if s['tier'] == 'VIRAL'),
            'high_performing_count': sum(
                1 for s in platform_videos if s['tier'] == 'HIGH_PERFORMING'
            )
        }

    return {
        'videos': scored,
        'summary': summary,
        'tier_distribution': tier_distribution,
        'high_authority_track': high_authority,
        'platform_stats': platform_stats,
        'z_score_interpretation': {
            'exceptional': 'z > 1.5 -- algorithm-amplified breakout, mine immediately',
            'strong': 'z > 0.5 -- above-average performance, strong angle signal',
            'average': '-0.5 to 0.5 -- typical performance for this batch',
            'below_average': 'z < -0.5 -- underperforming, low priority for mining'
        },
        'tier_interpretation': {
            'VIRAL': 'Ratio > 50x followers -- content massively outperformed audience size',
            'HIGH_PERFORMING': 'Ratio > 20x followers -- strong content signal',
            'ABOVE_AVERAGE': 'Ratio > 5x followers -- content outperformed, worth reviewing',
            'BASELINE': 'Ratio < 5x or below 10K views -- standard performance'
        }
    }


def print_virality_scorecard(results: Dict):
    """Pretty-print the virality scorecard to stdout."""
    print("\n" + "=" * 110)
    print("SOCIAL VIDEO VIRALITY SCORECARD")
    print("=" * 110)

    summary = results['summary']
    print(f"\nTotal Videos: {summary['total']}")
    print(f"Tier Breakdown: VIRAL={summary['viral_count']} | "
          f"HIGH_PERFORMING={summary['high_performing_count']} | "
          f"ABOVE_AVERAGE={summary['above_average_count']} | "
          f"BASELINE={summary['baseline_count']}")

    stats = summary['score_stats']
    print(f"Composite Score Stats -- Mean: {stats['mean']} | Median: {stats['median']} | "
          f"Std: {stats['std']}")
    print(f"Below Min View Threshold ({MIN_VIEW_THRESHOLD:,}): "
          f"{summary['below_min_view_threshold']}")
    print(f"Velocity Ineligible (>{MAX_VELOCITY_AGE_DAYS} days): "
          f"{summary['velocity_ineligible']}")

    # Platform stats
    print(f"\nPlatform Distribution: {summary['platform_distribution']}")
    if results['platform_stats']:
        print("\n  Platform-Level Averages:")
        print(f"  {'Platform':<12} {'Count':<7} {'Mean Views':<14} {'Mean Eng Den':<14} "
              f"{'Mean VR':<12} {'Viral':<7} {'High Perf'}")
        print("  " + "-" * 80)
        for platform, ps in results['platform_stats'].items():
            print(f"  {platform:<12} {ps['count']:<7} {ps['mean_views']:<14,.0f} "
                  f"{ps['mean_engagement_density']:<14} {ps['mean_virality_ratio']:<12} "
                  f"{ps['viral_count']:<7} {ps['high_performing_count']}")

    # Top ranked videos
    print("\n" + "-" * 110)
    print("TOP 15 VIDEOS BY COMPOSITE SCORE")
    print("-" * 110)
    print(f"{'Rank':<5} {'Score':<8} {'Tier':<17} {'Views':<12} {'VR':<10} "
          f"{'Vel':<12} {'EngDen':<10} {'Platform':<10} {'Author'}")
    print("-" * 110)

    for s in results['videos'][:15]:
        print(f"{s['rank']:<5} {s['viral_score']:<8} {s['tier']:<17} "
              f"{s['views']:<12,} {s['virality_ratio']:<10} "
              f"{s['velocity']:<12,.0f} {s['engagement_density']:<10} "
              f"{s['platform']:<10} {s['author'][:25]}")

    # Z-score breakdown for top 5
    print("\n" + "-" * 110)
    print("Z-SCORE BREAKDOWN (Top 5)")
    print("-" * 110)
    for s in results['videos'][:5]:
        print(f"\n  #{s['rank']} {s['author']} -- {s['platform']} "
              f"(Composite: {s['viral_score']}, Tier: {s['tier']})")
        zs = s['z_scores']
        metrics = [
            ('virality_ratio_z', zs['virality_ratio_z'], WEIGHT_VIRALITY_RATIO),
            ('velocity_z', zs['velocity_z'], WEIGHT_VELOCITY),
            ('engagement_density_z', zs['engagement_density_z'], WEIGHT_ENGAGEMENT_DENSITY)
        ]
        for name, z_val, weight in metrics:
            bar_pos = int(max(0, min(20, (z_val + 3) / 6 * 20)))
            bar = "." * bar_pos + "|" + "." * (20 - bar_pos)
            print(f"    {name:<25} [{bar}] z={z_val:>7.3f}  (weight: {weight})")

    # High authority track
    ha = results['high_authority_track']
    if ha:
        print("\n" + "-" * 110)
        print(f"HIGH AUTHORITY TRACK ({len(ha)} videos with {HIGH_AUTHORITY_VIEW_THRESHOLD:,}+ views)")
        print("Sorted by engagement density (VOC mining priority)")
        print("-" * 110)
        print(f"{'Views':<12} {'EngDen':<10} {'Comments':<10} {'Shares':<10} "
              f"{'Platform':<10} {'Author'}")
        print("-" * 110)
        for s in ha[:10]:
            print(f"{s['views']:<12,} {s['engagement_density']:<10} "
                  f"{s['comments']:<10,} {s['shares']:<10,} "
                  f"{s['platform']:<10} {s['author'][:30]}")

    # Tier interpretation
    print("\n" + "=" * 110)
    print("TIER INTERPRETATION")
    print("=" * 110)
    for label, desc in results['tier_interpretation'].items():
        print(f"  {label:<20} {desc}")

    print("\n" + "=" * 110)
    print("Z-SCORE INTERPRETATION")
    print("=" * 110)
    for label, desc in results['z_score_interpretation'].items():
        print(f"  {label:<20} {desc}")


def main():
    parser = argparse.ArgumentParser(
        description='Score raw scraped social video data for virality metrics'
    )
    parser.add_argument('--input', '-i', required=True,
                       help='Input JSON file with raw video data from scraper')
    parser.add_argument('--output', '-o',
                       help='Output JSON file (optional, prints scorecard to stdout)')
    args = parser.parse_args()

    with open(args.input, 'r') as f:
        data = json.load(f)

    # Accept either a list of videos or a dict with 'videos' key
    if isinstance(data, list):
        videos = data
    elif isinstance(data, dict) and 'videos' in data:
        videos = data['videos']
    else:
        print("Error: Input must be a JSON array of video data or a dict with 'videos' key")
        sys.exit(1)

    results = score_all_videos(videos)

    print_virality_scorecard(results)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == '__main__':
    main()
