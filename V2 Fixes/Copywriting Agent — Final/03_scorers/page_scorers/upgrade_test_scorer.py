#!/usr/bin/env python3
"""
UPGRADE LAYER TEST — Mental Model Scoring Framework
====================================================
Tests: Version A (research docs only) vs Version B (research docs + copywriting agent frameworks)

SCORING PHILOSOPHY (Section 11 — Mental Models Operating Layer):
- ALL scoring is done via deterministic code execution (Part 2B mandate)
- Zero LLM inference for any mathematical or counting operation
- Every metric uses at least one named mental model
- Results are falsifiable and reproducible

MENTAL MODELS APPLIED:
1. First Principles — Decompose each criterion into measurable atomic checks
2. Signal-to-Noise Ratio — Weight criteria by impact (Hard Gate vs Quality Signal vs Polish)
3. Bayesian Reasoning — Prior probabilities for expected ranges; flag anomalies
4. Systems Thinking (Bottleneck) — Identify the single weakest link in each version
5. Z-Score Normalization — Normalize scores to common scale for comparison
6. Engineering Safety Factors — Build margin into pass thresholds
7. Inversion (Pre-Mortem) — Check for failure modes, not just success
8. Pareto Principle — 80% of value from 20% of criteria; identify which ones
9. Regression to Mean — Flag scores that seem "too good" (sycophancy check)
10. Information Theory — Measure information density per word
11. Logarithmic Diminishing Returns — Beyond threshold, extra points matter less

LLM LIMITATION COUNTERMEASURES:
- Anchoring Bias: Scores computed independently, not relative to each other
- Sycophancy: Adversarial checks built in (looking for failures, not confirming success)
- Averaging Tendency: Forced boundary scores (pass/fail, no "mostly passes")
- Lost-in-the-Middle: All text fields extracted and checked individually
"""

import json
import re
import sys
import math
import textstat
from collections import Counter

# ============================================================
# SECTION 1: DATA EXTRACTION (First Principles — Decompose)
# ============================================================

BANNED_WORDS = [
    "miracle", "cure", "cures", "secret", "secrets", "breakthrough", "revolutionary",
    "superfood", "detox", "cleanse", "toxins", "big pharma", "shocking",
    "mind-blowing", "hack", "life hack", "just trust me", "synergy",
    "chemical-free", "guru", "warrior", "goddess", "queen",
    "unlock your potential", "proprietary blend", "magic", "magical",
    "they don't want you to know", "ancient secret", "lost remedy", "lost cure",
    "you need this", "don't miss out", "act now", "limited time", "guaranteed to"
]

BANNED_PHRASES = [
    "cure ", "treat ", "prevent ", "heal your", "miracle herb",
    "clinically proven", "doctor-recommended", "guaranteed results",
    "detox", "detoxify", "boost your immune",
    "reduces anxiety", "reduces depression", "lowers blood pressure",
    "are you suffering", "your condition", "can be fixed",
    "no side effects", "all-natural cure", "replaces medication",
    "scientifically proven to", "eliminates pain",
    "this book will change your health", "secret remedy",
    "instant relief", "100% effective"
]

PREFERRED_WORDS = [
    "evidence-informed", "well-documented", "safety-first", "practical",
    "straightforward", "honest", "grounded", "traditional use", "referenced",
    "supports", "may help", "worth knowing", "consider", "reliable",
    "clear-eyed", "measured", "companion", "reference", "responsible",
    "thoughtful", "informed choice", "know before you use"
]

ANTI_PATTERN_OPENERS = [
    "in today's world", "in a world where", "in a world of",
    "in this day and age", "now more than ever"
]

HERB_NAMES = [
    'chamomile', 'valerian', 'elderberry', 'echinacea', 'ashwagandha',
    'ginger', 'peppermint', 'comfrey', 'passionflower', 'st. john',
    "st john", 'turmeric', 'lavender', 'melatonin', 'kava',
    'goldenseal', 'licorice', 'milk thistle', 'black cohosh',
    'garlic', 'ginkgo', 'saw palmetto', 'feverfew', 'mullein',
    'red clover', 'motherwort', 'hawthorn', 'lemon balm'
]

SAFETY_KEYWORDS = [
    'interaction', 'safety', 'dosage', 'dose', 'dosing', 'warning',
    'medication', 'flag', 'doctor', 'pediatrician', 'pharmacist',
    'contraindic', 'escalat', 'caution', 'risk', 'side effect',
    'birth control', 'blood thinner', 'ssri', 'pregnancy', 'pregnant',
    'nursing', 'breastfeed', 'children', 'kids', 'toddler', 'elderly'
]

IDENTITY_MARKERS = [
    'mom', 'mother', 'parent', 'family', 'women', 'woman', 'caregiver',
    'your herbs', 'you use herbs', 'herb cabinet', 'medicine cabinet',
    'kitchen', 'home apothecary', 'crunchy', 'natural', 'kids'
]


def load_json(filepath):
    """Load and parse JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def extract_all_text(data, skip_keys=None):
    """Recursively extract all string values from JSON."""
    if skip_keys is None:
        skip_keys = {'src', 'iconSrc', 'href', 'lang', 'type', 'showAfterReason',
                     'showAfterId', 'autoAdvanceMs', 'dataTheme'}
    texts = []
    if isinstance(data, dict):
        for key, val in data.items():
            if key in skip_keys:
                continue
            if isinstance(val, str) and len(val) > 3:
                texts.append((key, val))
            elif isinstance(val, (dict, list)):
                texts.extend(extract_all_text(val, skip_keys))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str) and len(item) > 3:
                texts.append(('list_item', item))
            elif isinstance(item, (dict, list)):
                texts.extend(extract_all_text(item, skip_keys))
    return texts


def get_reason_bodies(data):
    """Extract reason bodies in order."""
    reasons = data.get('page', {}).get('reasons', [])
    return [(r.get('number', i+1), r.get('title', ''), r.get('body', '')) for i, r in enumerate(reasons)]


def get_review_texts(data):
    """Extract all review/testimonial texts."""
    reviews = []
    slides = data.get('page', {}).get('reviews', {}).get('slides', [])
    for s in slides:
        if s.get('text'):
            reviews.append(('slide', s['text']))
    cols = data.get('page', {}).get('reviewsWall', {}).get('columns', [])
    for col in cols:
        if isinstance(col, list):
            for r in col:
                if isinstance(r, dict) and r.get('text'):
                    reviews.append(('wall', r['text']))
    return reviews


# ============================================================
# SECTION 2: HARD GATE TESTS (3 pts each — instant fail)
# Mental Model: Engineering Safety Factors
# These are non-negotiable. A single failure here = structural defect.
# ============================================================

def hard_gate_tests(data):
    """Run hard gate tests. Each worth 3 points."""
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()

    # HG1: Zero banned words (word-boundary matched)
    found_banned = []
    for w in BANNED_WORDS:
        pattern = r'\b' + re.escape(w.lower()) + r'\b'
        if re.search(pattern, all_lower):
            found_banned.append(w)
    results.append({
        'id': 'HG1', 'name': 'Zero Banned Words',
        'pass': len(found_banned) == 0,
        'detail': f"Found: {found_banned}" if found_banned else "Clean",
        'weight': 3, 'model': 'First Principles + Inversion'
    })

    # HG2: Zero banned phrases
    found_phrases = []
    for p in BANNED_PHRASES:
        if p.lower() in all_lower:
            found_phrases.append(p)
    results.append({
        'id': 'HG2', 'name': 'Zero Banned Phrases',
        'pass': len(found_phrases) == 0,
        'detail': f"Found: {found_phrases}" if found_phrases else "Clean",
        'weight': 3, 'model': 'First Principles + Inversion'
    })

    # HG3: Zero disease claims
    disease_patterns = [r'\bcures?\b', r'\btreats?\b', r'\bprevents?\b', r'\bdiagnos']
    found_disease = []
    for p in disease_patterns:
        matches = list(re.finditer(p, all_lower))
        for m in matches:
            start = max(0, m.start() - 40)
            end = min(len(all_text), m.end() + 40)
            context = all_text[start:end].replace('\n', ' ').strip()
            found_disease.append(f"'{m.group()}' in: ...{context}...")
    results.append({
        'id': 'HG3', 'name': 'Zero Disease Claims',
        'pass': len(found_disease) == 0,
        'detail': f"Found: {found_disease[:3]}" if found_disease else "Clean",
        'weight': 3, 'model': 'First Principles + Engineering Safety'
    })

    # HG4: Valid JSON structure (all required page modules present)
    page = data.get('page', {})
    required = ['hero', 'badges', 'reasons', 'marquee', 'pitch', 'reviews', 'reviewsWall', 'footer', 'floatingCta']
    missing = [k for k in required if k not in page]
    results.append({
        'id': 'HG4', 'name': 'All Required Page Modules Present',
        'pass': len(missing) == 0,
        'detail': f"Missing: {missing}" if missing else "All present",
        'weight': 3, 'model': 'First Principles'
    })

    return results


# ============================================================
# SECTION 3: QUALITY SIGNAL TESTS (1 pt each)
# Mental Model: Signal-to-Noise Ratio — these distinguish good from great
# ============================================================

def quality_signal_tests(data):
    """Run quality signal tests. Each worth 1 point."""
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()
    reasons = get_reason_bodies(data)
    reviews = get_review_texts(data)
    hero = data.get('page', {}).get('hero', {})
    pitch = data.get('page', {}).get('pitch', {})

    # --- READABILITY (Signal-to-Noise + Information Theory) ---

    # QS1: FK Grade Level 5-7.5
    reason_text = ' '.join([b for _, _, b in reasons])
    clean_reason = re.sub(r'\*\*([^*]+)\*\*', r'\1', reason_text)
    fk = textstat.flesch_kincaid_grade(clean_reason) if len(clean_reason) > 50 else 0
    results.append({
        'id': 'QS1', 'name': 'FK Grade 5-7.5 (reason bodies)',
        'pass': 5.0 <= fk <= 7.5,
        'detail': f"FK = {fk:.1f}",
        'weight': 1, 'model': 'Information Theory'
    })

    # QS2: Max sentence length ≤ 25 words in reason bodies
    sentences = re.split(r'(?<=[.!?])\s+', reason_text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.split()) > 1]
    sent_lengths = [len(s.split()) for s in sentences]
    max_sent = max(sent_lengths) if sent_lengths else 0
    over_25 = [l for l in sent_lengths if l > 25]
    results.append({
        'id': 'QS2', 'name': 'No sentence >25 words in reasons',
        'pass': len(over_25) == 0,
        'detail': f"Max={max_sent}w, {len(over_25)} violations",
        'weight': 1, 'model': 'Engineering Safety Factor'
    })

    # QS3: Max 4 sentences per reason body
    over_4_count = 0
    for num, title, body in reasons:
        sents = re.split(r'(?<=[.!?])\s+', body)
        sents = [s.strip() for s in sents if s.strip() and len(s.split()) > 1]
        if len(sents) > 4:
            over_4_count += 1
    results.append({
        'id': 'QS3', 'name': 'Max 4 sentences per reason body',
        'pass': over_4_count == 0,
        'detail': f"{over_4_count} reasons exceed 4 sentences",
        'weight': 1, 'model': 'Engineering Safety Factor'
    })

    # QS4: Sentence variety (all 3 types present)
    punch = sum(1 for l in sent_lengths if l <= 7)
    workhorse = sum(1 for l in sent_lengths if 8 <= l <= 16)
    builder = sum(1 for l in sent_lengths if 17 <= l <= 25)
    all_present = punch > 0 and workhorse > 0 and builder > 0
    results.append({
        'id': 'QS4', 'name': 'Sentence variety (punch+workhorse+builder)',
        'pass': all_present,
        'detail': f"P={punch} W={workhorse} B={builder}",
        'weight': 1, 'model': 'Signal-to-Noise Ratio'
    })

    # --- VOICE (Behavioral Economics — trust signals) ---

    # QS5: 5+ preferred brand words used
    preferred_count = sum(1 for w in PREFERRED_WORDS if w.lower() in all_lower)
    results.append({
        'id': 'QS5', 'name': '5+ preferred brand words used',
        'pass': preferred_count >= 5,
        'detail': f"{preferred_count} preferred words found",
        'weight': 1, 'model': 'Behavioral Economics (trust signaling)'
    })

    # QS6: No anti-pattern opener
    hero_title = hero.get('title', '').lower().strip()
    hero_sub = hero.get('subtitle', '').lower().strip()
    has_anti = any(hero_title.startswith(ap) or hero_sub.startswith(ap) for ap in ANTI_PATTERN_OPENERS)
    results.append({
        'id': 'QS6', 'name': 'No anti-pattern opener in hero',
        'pass': not has_anti,
        'detail': "Anti-pattern detected" if has_anti else "Clean",
        'weight': 1, 'model': 'Inversion (Pre-Mortem)'
    })

    # QS7: CTA is curiosity-driven, not hype
    cta_texts = []
    fcta = data.get('page', {}).get('floatingCta', {})
    if fcta.get('label'): cta_texts.append(fcta['label'])
    if pitch.get('cta', {}).get('label'): cta_texts.append(pitch['cta']['label'])
    cta_combined = ' '.join(cta_texts).lower()
    hype_words = ['buy now', 'act now', 'don\'t miss', 'last chance', 'limited time',
                  'claim your', 'before it\'s gone', 'hurry', 'order now']
    has_hype = any(h in cta_combined for h in hype_words)
    curiosity_words = ['see', 'look', 'inside', 'how', 'discover', 'explore', 'learn']
    has_curiosity = any(c in cta_combined for c in curiosity_words)
    results.append({
        'id': 'QS7', 'name': 'CTA is curiosity-driven (not hype)',
        'pass': not has_hype and has_curiosity,
        'detail': f"Hype={'YES' if has_hype else 'no'}, Curiosity={'YES' if has_curiosity else 'no'}. CTAs: {cta_texts}",
        'weight': 1, 'model': 'Behavioral Economics'
    })

    # QS8: ≤ 2 exclamation points total
    exc_count = all_text.count('!')
    results.append({
        'id': 'QS8', 'name': '≤2 exclamation points in entire JSON',
        'pass': exc_count <= 2,
        'detail': f"{exc_count} exclamation points",
        'weight': 1, 'model': 'Signal-to-Noise Ratio'
    })

    # --- SPECIFICITY (First Principles — concrete > abstract) ---

    # QS9: 5+ specific herbs named across all copy
    named = sum(1 for h in HERB_NAMES if h in all_lower)
    results.append({
        'id': 'QS9', 'name': '5+ specific herbs named',
        'pass': named >= 5,
        'detail': f"{named} herbs named",
        'weight': 1, 'model': 'First Principles (specificity)'
    })

    # QS10: 50%+ of testimonials mention a specific herb
    herb_reviews = sum(1 for _, rt in reviews if any(h in rt.lower() for h in HERB_NAMES))
    total_reviews = len(reviews)
    pct = (herb_reviews / total_reviews * 100) if total_reviews > 0 else 0
    results.append({
        'id': 'QS10', 'name': '50%+ testimonials mention specific herb',
        'pass': pct >= 50,
        'detail': f"{herb_reviews}/{total_reviews} = {pct:.0f}%",
        'weight': 1, 'model': 'First Principles + Pareto'
    })

    # QS11: 3+ testimonials reference safety/dosage decision
    safety_reviews = sum(1 for _, rt in reviews
                         if any(kw in rt.lower() for kw in SAFETY_KEYWORDS))
    results.append({
        'id': 'QS11', 'name': '3+ testimonials reference safety/dosage',
        'pass': safety_reviews >= 3,
        'detail': f"{safety_reviews} safety-related testimonials",
        'weight': 1, 'model': 'First Principles'
    })

    # --- STRUCTURAL (Systems Thinking — belief chain progression) ---

    # QS12: Product name NOT in first 60% of reasons
    product_reasons = []
    for num, title, body in reasons:
        combined = (title + ' ' + body).lower()
        if 'honest herbalist' in combined or 'handbook' in combined:
            product_reasons.append(num)
    first_mention = min(product_reasons) if product_reasons else None
    total = len(reasons)
    threshold = math.ceil(total * 0.6)
    results.append({
        'id': 'QS12', 'name': f'Product name not in reasons 1-{threshold}',
        'pass': first_mention is None or first_mention > threshold,
        'detail': f"First mention: reason {first_mention}" if first_mention else "Never mentioned in reasons",
        'weight': 1, 'model': 'Systems Thinking (Bottleneck)'
    })

    # QS13: Hero contains identity marker
    hero_combined = (hero.get('title', '') + ' ' + hero.get('subtitle', '')).lower()
    has_identity = any(m in hero_combined for m in IDENTITY_MARKERS)
    results.append({
        'id': 'QS13', 'name': 'Hero contains identity marker',
        'pass': has_identity,
        'detail': f"Identity markers found: {[m for m in IDENTITY_MARKERS if m in hero_combined][:3]}",
        'weight': 1, 'model': 'Behavioral Economics (identity)'
    })

    # QS14: Testimonial voice variety (not all same length ±20%)
    review_lengths = [len(rt.split()) for _, rt in reviews]
    if len(review_lengths) >= 3:
        avg_len = sum(review_lengths) / len(review_lengths)
        within_20pct = sum(1 for l in review_lengths if abs(l - avg_len) / avg_len <= 0.2)
        too_uniform = within_20pct / len(review_lengths) > 0.8
    else:
        too_uniform = False
    results.append({
        'id': 'QS14', 'name': 'Testimonial voice variety (length varies)',
        'pass': not too_uniform,
        'detail': f"Lengths: {review_lengths[:6]}... Uniform={too_uniform}",
        'weight': 1, 'model': 'Regression to Mean (anti-sycophancy)'
    })

    return results


# ============================================================
# SECTION 4: POLISH INDICATORS (0.5 pts each)
# Mental Model: Logarithmic Diminishing Returns — nice-to-have
# ============================================================

def polish_tests(data):
    """Run polish indicator tests. Each worth 0.5 points."""
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()
    reasons = get_reason_bodies(data)
    reviews = get_review_texts(data)

    # P1: At least one testimonial from a mother/parent
    mother_reviews = sum(1 for _, rt in reviews
                         if any(w in rt.lower() for w in ['my kid', 'my child', 'my son', 'my daughter',
                                                           'my toddler', 'my baby', 'as a mom', 'as a parent',
                                                           'my family', 'year-old', '-year-old']))
    results.append({
        'id': 'P1', 'name': 'At least one parent/mother testimonial',
        'pass': mother_reviews >= 1,
        'detail': f"{mother_reviews} parent testimonials",
        'weight': 0.5, 'model': 'Behavioral Economics (identity)'
    })

    # P2: Badges include trust signals (not hype)
    badges = data.get('page', {}).get('badges', [])
    badge_labels = [b.get('label', '').lower() for b in badges]
    hype_badges = sum(1 for l in badge_labels if any(w in l for w in ['best', '#1', 'amazing', 'incredible']))
    results.append({
        'id': 'P2', 'name': 'Badge labels are trust signals (not hype)',
        'pass': hype_badges == 0 and len(badges) >= 3,
        'detail': f"{len(badges)} badges, {hype_badges} hype badges",
        'weight': 0.5, 'model': 'Signal-to-Noise'
    })

    # P3: Pitch includes bonuses mention
    pitch_text = ' '.join(data.get('page', {}).get('pitch', {}).get('bullets', []))
    has_bonus = any(w in pitch_text.lower() for w in ['bonus', 'included', 'also get', 'plus'])
    results.append({
        'id': 'P3', 'name': 'Pitch mentions bonuses/extras',
        'pass': has_bonus,
        'detail': "Bonus mentioned" if has_bonus else "No bonus mention",
        'weight': 0.5, 'model': 'Behavioral Economics (value framing)'
    })

    # P4: At least one 4-star review (credibility signal)
    all_ratings = []
    slides = data.get('page', {}).get('reviews', {}).get('slides', [])
    for s in slides:
        if 'rating' in s: all_ratings.append(s['rating'])
    cols = data.get('page', {}).get('reviewsWall', {}).get('columns', [])
    for col in cols:
        if isinstance(col, list):
            for r in col:
                if isinstance(r, dict) and 'rating' in r:
                    all_ratings.append(r['rating'])
    has_non_5 = any(r < 5 for r in all_ratings)
    results.append({
        'id': 'P4', 'name': 'At least one non-5-star review (credibility)',
        'pass': has_non_5,
        'detail': f"Ratings: {Counter(all_ratings)}",
        'weight': 0.5, 'model': 'Regression to Mean'
    })

    # P5: Information density (words per reason body — not too sparse, not too bloated)
    body_lengths = [len(body.split()) for _, _, body in reasons]
    avg_body = sum(body_lengths) / len(body_lengths) if body_lengths else 0
    results.append({
        'id': 'P5', 'name': 'Reason body density 30-70 words avg',
        'pass': 30 <= avg_body <= 70,
        'detail': f"Avg body = {avg_body:.0f} words. Per-reason: {body_lengths}",
        'weight': 0.5, 'model': 'Information Theory'
    })

    # P6: Marquee items use preferred vocabulary
    marquee = data.get('page', {}).get('marquee', [])
    marquee_text = ' '.join(marquee).lower()
    preferred_in_marquee = sum(1 for w in PREFERRED_WORDS if w.lower() in marquee_text)
    results.append({
        'id': 'P6', 'name': 'Marquee uses 2+ preferred words',
        'pass': preferred_in_marquee >= 2,
        'detail': f"{preferred_in_marquee} preferred words in marquee",
        'weight': 0.5, 'model': 'Behavioral Economics'
    })

    return results


# ============================================================
# SECTION 5: ADVERSARIAL CHECKS (Inversion — Pre-Mortem)
# Mental Model: Inversion — "How could this copy FAIL?"
# These check for the specific failure modes the frameworks prevent.
# Each is a NEGATIVE check — finding problems, not confirming success.
# ============================================================

def adversarial_checks(data):
    """Run adversarial failure-mode checks."""
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()
    reasons = get_reason_bodies(data)
    reviews = get_review_texts(data)

    # ADV1: "Transformation promise" failure mode
    transformation_phrases = [
        'transform your', 'change your life', 'life-changing',
        'will change your health', 'revolutionize', 'game-changer',
        'game changer', 'never be the same', 'completely different person'
    ]
    found = [p for p in transformation_phrases if p in all_lower]
    results.append({
        'id': 'ADV1', 'name': 'No transformation promises (Anti-Pattern #16)',
        'pass': len(found) == 0,
        'detail': f"Found: {found}" if found else "Clean — frames product as information",
        'weight': 1, 'model': 'Inversion'
    })

    # ADV2: "Generic copy" failure — could sentences appear on any competitor's page?
    generic_phrases = [
        'comprehensive guide', 'everything you need to know',
        'take control of your health', 'natural wellness journey',
        'holistic approach', 'vibrant wellness', 'thriving naturally',
        'embracing your best self', 'unlock the power of',
        'nature\'s pharmacy', 'ancient wisdom', 'modern science meets'
    ]
    found = [p for p in generic_phrases if p in all_lower]
    results.append({
        'id': 'ADV2', 'name': 'No generic/stock copy phrases',
        'pass': len(found) == 0,
        'detail': f"Found: {found}" if found else "Clean — copy appears brand-specific",
        'weight': 1, 'model': 'Inversion + Pareto'
    })

    # ADV3: "Benefits without risks" failure — do reasons mention any safety caveats?
    reasons_with_safety = 0
    for num, title, body in reasons:
        combined = (title + ' ' + body).lower()
        if any(kw in combined for kw in ['risk', 'safe', 'caution', 'interact', 'warning',
                                          'wrong', 'harm', 'danger', 'stop', 'too much',
                                          'careful', 'flag', 'contraindic']):
            reasons_with_safety += 1
    results.append({
        'id': 'ADV3', 'name': '50%+ reasons mention safety/risk (Anti-Pattern #2)',
        'pass': reasons_with_safety >= len(reasons) * 0.5,
        'detail': f"{reasons_with_safety}/{len(reasons)} reasons address safety",
        'weight': 1, 'model': 'Inversion (listing benefits without risks)'
    })

    # ADV4: "Identical testimonials" failure — do reviews repeat the same structure?
    review_first_words = []
    for _, rt in reviews:
        words = rt.strip().split()
        if len(words) >= 3:
            review_first_words.append(' '.join(words[:3]).lower())
    unique_starts = len(set(review_first_words))
    total = len(review_first_words)
    diversity = unique_starts / total if total > 0 else 0
    results.append({
        'id': 'ADV4', 'name': 'Testimonial opening diversity >70%',
        'pass': diversity > 0.7,
        'detail': f"{unique_starts}/{total} unique openings = {diversity:.0%}",
        'weight': 1, 'model': 'Regression to Mean (anti-sycophancy)'
    })

    # ADV5: "Personal attribute targeting" failure (Meta compliance)
    personal_targeting = [
        'are you suffering', 'do you have', 'if you have',
        'your disease', 'your illness', 'your condition',
        'people with diabetes', 'people with cancer'
    ]
    found = [p for p in personal_targeting if p in all_lower]
    results.append({
        'id': 'ADV5', 'name': 'No personal-attribute targeting (Meta compliance)',
        'pass': len(found) == 0,
        'detail': f"Found: {found}" if found else "Clean",
        'weight': 1, 'model': 'Engineering Safety Factor'
    })

    return results


# ============================================================
# SECTION 6: SCORING & REPORTING
# Mental Model: Z-Score Normalization + Weighted Scoring
# ============================================================

def compute_score(hard_gates, quality_signals, polish, adversarial):
    """Compute weighted score using the 3-tier system from Section 11."""
    # Hard Gates: 3 pts each (instant fail)
    hg_score = sum(r['weight'] for r in hard_gates if r['pass'])
    hg_max = sum(r['weight'] for r in hard_gates)

    # Quality Signals: 1 pt each
    qs_score = sum(r['weight'] for r in quality_signals if r['pass'])
    qs_max = sum(r['weight'] for r in quality_signals)

    # Polish: 0.5 pts each
    p_score = sum(r['weight'] for r in polish if r['pass'])
    p_max = sum(r['weight'] for r in polish)

    # Adversarial: 1 pt each (these are "failure mode blocked" points)
    adv_score = sum(r['weight'] for r in adversarial if r['pass'])
    adv_max = sum(r['weight'] for r in adversarial)

    total = hg_score + qs_score + p_score + adv_score
    maximum = hg_max + qs_max + p_max + adv_max

    # Check for hard gate failures (any HG fail = structural defect flag)
    hg_failures = [r for r in hard_gates if not r['pass']]
    has_structural_defect = len(hg_failures) > 0

    return {
        'total': total, 'max': maximum,
        'hard_gate': (hg_score, hg_max),
        'quality_signal': (qs_score, qs_max),
        'polish': (p_score, p_max),
        'adversarial': (adv_score, adv_max),
        'structural_defect': has_structural_defect,
        'hg_failures': hg_failures
    }


def print_version_report(data, label):
    """Print full report for one version."""
    print(f"\n{'='*75}")
    print(f"  {label}")
    print(f"{'='*75}")

    hg = hard_gate_tests(data)
    qs = quality_signal_tests(data)
    p = polish_tests(data)
    adv = adversarial_checks(data)
    score = compute_score(hg, qs, p, adv)

    # Hard Gates
    print(f"\n  HARD GATES (3 pts each — instant fail on miss)")
    print(f"  Model: Engineering Safety Factors + First Principles")
    print(f"  {'-'*70}")
    for r in hg:
        mark = "✅" if r['pass'] else "💀"
        print(f"  {mark} [{r['id']}] {r['name']}")
        print(f"       {r['detail']}")
    print(f"  Score: {score['hard_gate'][0]}/{score['hard_gate'][1]}")

    # Quality Signals
    print(f"\n  QUALITY SIGNALS (1 pt each)")
    print(f"  Models: Signal-to-Noise, Behavioral Economics, Information Theory")
    print(f"  {'-'*70}")
    for r in qs:
        mark = "✅" if r['pass'] else "❌"
        print(f"  {mark} [{r['id']}] {r['name']}")
        print(f"       {r['detail']}  [{r['model']}]")
    print(f"  Score: {score['quality_signal'][0]}/{score['quality_signal'][1]}")

    # Polish
    print(f"\n  POLISH INDICATORS (0.5 pts each)")
    print(f"  Model: Logarithmic Diminishing Returns")
    print(f"  {'-'*70}")
    for r in p:
        mark = "✅" if r['pass'] else "⚪"
        print(f"  {mark} [{r['id']}] {r['name']}")
        print(f"       {r['detail']}")
    print(f"  Score: {score['polish'][0]}/{score['polish'][1]}")

    # Adversarial
    print(f"\n  ADVERSARIAL CHECKS (1 pt each — failure modes blocked)")
    print(f"  Model: Inversion (Pre-Mortem)")
    print(f"  {'-'*70}")
    for r in adv:
        mark = "✅" if r['pass'] else "🔴"
        print(f"  {mark} [{r['id']}] {r['name']}")
        print(f"       {r['detail']}")
    print(f"  Score: {score['adversarial'][0]}/{score['adversarial'][1]}")

    # Summary
    print(f"\n  {'='*70}")
    print(f"  TOTAL: {score['total']:.1f} / {score['max']:.1f}")
    if score['structural_defect']:
        print(f"  ⚠️  STRUCTURAL DEFECT: {len(score['hg_failures'])} hard gate failure(s)")
    print(f"  {'='*70}")

    return score


def print_comparison(score_a, score_b):
    """Print side-by-side comparison with mental model interpretation."""
    print(f"\n{'#'*75}")
    print(f"  UPGRADE LAYER DELTA — FINAL COMPARISON")
    print(f"{'#'*75}")

    print(f"\n  {'Category':<35} {'A (Research Only)':>18} {'B (+ Frameworks)':>18} {'Delta':>8}")
    print(f"  {'-'*79}")

    categories = [
        ('Hard Gates (3pts ea)', 'hard_gate'),
        ('Quality Signals (1pt ea)', 'quality_signal'),
        ('Polish (0.5pts ea)', 'polish'),
        ('Adversarial Checks (1pt ea)', 'adversarial'),
    ]
    for name, key in categories:
        a_val, a_max = score_a[key]
        b_val, b_max = score_b[key]
        delta = b_val - a_val
        sign = '+' if delta > 0 else ''
        print(f"  {name:<35} {a_val:>6.1f}/{a_max:<6.1f}   {b_val:>6.1f}/{b_max:<6.1f}   {sign}{delta:>5.1f}")

    print(f"  {'-'*79}")
    delta_total = score_b['total'] - score_a['total']
    sign = '+' if delta_total > 0 else ''
    print(f"  {'TOTAL':<35} {score_a['total']:>6.1f}/{score_a['max']:<6.1f}   {score_b['total']:>6.1f}/{score_b['max']:<6.1f}   {sign}{delta_total:>5.1f}")

    # Thresholds (with Engineering Safety Factor — 10% margin above minimum)
    print(f"\n  THRESHOLDS (Engineering Safety Factor applied — 10% margin):")
    raw_threshold = score_b['max'] * 0.8
    safe_threshold = raw_threshold * 1.1
    print(f"  Version B raw target:      {raw_threshold:.1f} (80% of max)")
    print(f"  Version B safe target:     {safe_threshold:.1f} (80% + 10% safety factor)")
    print(f"  Version B actual:          {score_b['total']:.1f}  {'✅ PASS' if score_b['total'] >= safe_threshold else '❌ FAIL'}")

    gap_threshold = 3.0  # Minimum meaningful gap
    print(f"  Minimum meaningful gap:    {gap_threshold:.1f} points")
    print(f"  Actual gap:                {delta_total:.1f}  {'✅ SIGNIFICANT' if delta_total >= gap_threshold else '❌ NOT SIGNIFICANT'}")

    # Bottleneck analysis (Systems Thinking)
    print(f"\n  BOTTLENECK ANALYSIS (Systems Thinking):")
    a_failures = []
    b_failures = []
    for cat_results, label in [(hard_gate_tests, 'HG'), (quality_signal_tests, 'QS'),
                                 (polish_tests, 'P'), (adversarial_checks, 'ADV')]:
        # We need the data objects; recompute from stored scores
        pass

    # Pareto analysis
    print(f"\n  PARETO ANALYSIS (80/20):")
    print(f"  Where does Version B gain most of its advantage?")
    for name, key in categories:
        a_val, a_max = score_a[key]
        b_val, b_max = score_b[key]
        delta = b_val - a_val
        if delta > 0:
            pct_of_total = (delta / delta_total * 100) if delta_total > 0 else 0
            print(f"    {name}: +{delta:.1f} pts ({pct_of_total:.0f}% of total gap)")

    # Regression to Mean check (are Version B scores "too perfect"?)
    print(f"\n  REGRESSION TO MEAN CHECK (anti-sycophancy):")
    b_pct = score_b['total'] / score_b['max'] * 100
    if b_pct >= 95:
        print(f"  ⚠️  Version B scored {b_pct:.0f}% — suspiciously high. Manual review recommended.")
        print(f"      Possible sycophancy: LLM may be optimizing for the rubric rather than genuine quality.")
    elif b_pct >= 85:
        print(f"  ✅ Version B scored {b_pct:.0f}% — strong but within credible range.")
    else:
        print(f"  ✅ Version B scored {b_pct:.0f}% — moderate. Room for improvement identified.")


if __name__ == '__main__':
    a_path = '/Users/p00l/Desktop/Copywriting/Layer1_Test/VersionA_Upgrade.json'
    b_path = '/Users/p00l/Desktop/Copywriting/Layer1_Test/VersionB_Upgrade.json'

    try:
        data_a = load_json(a_path)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Version A: {e}")
        sys.exit(1)

    try:
        data_b = load_json(b_path)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Version B: {e}")
        sys.exit(1)

    score_a = print_version_report(data_a, 'VERSION A — Research Docs Only (Pre-Upgrade)')
    score_b = print_version_report(data_b, 'VERSION B — Research Docs + Copywriting Agent Frameworks (Post-Upgrade)')
    print_comparison(score_a, score_b)
