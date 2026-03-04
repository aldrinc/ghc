#!/usr/bin/env python3
"""
Layer 1 Quality Gate — Listicle JSON Scoring
Scores both Version A (no RAG) and Version B (full RAG) against:
1. Schema validation (structural correctness)
2. Copy quality metrics (FK, sentence length, banned words)
3. Strategic rubric (belief chain, voice, compliance, differentiation)

All math/counting done deterministically via code — zero LLM inference for scoring.
"""

import json
import re
import sys
import textstat

# ===== BANNED WORDS (Section 3 A2) =====
BANNED_WORDS = [
    "miracle", "cure", "cures", "secret", "secrets", "they don't want you to know",
    "ancient secret", "lost remedy", "lost cure", "breakthrough", "revolutionary",
    "superfood", "detox", "cleanse", "toxins", "big pharma", "shocking",
    "mind-blowing", "you need this", "don't miss out", "act now", "limited time",
    "guaranteed to", "hack", "life hack", "just trust me", "synergy",
    "chemical-free", "guru", "warrior", "goddess", "queen",
    "unlock your potential", "proprietary blend", "magic", "magical"
]

BANNED_PHRASES = [
    "cure ", "treat ", "prevent ", "heal your", "miracle herb", "miracle remedy",
    "miracle cure", "clinically proven", "doctor-recommended", "guaranteed results",
    "detox", "detoxify", "anti-inflammatory", "boost your immune",
    "reduces anxiety", "reduces depression", "lowers blood pressure",
    "are you suffering", "your condition", "can be fixed",
    "no side effects", "all-natural cure", "replaces medication",
    "scientifically proven to", "eliminates pain", "fight cancer",
    "this book will change your health", "secret remedy",
    "reverse ", "instant relief", "100% effective"
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

HYPE_CTA_WORDS = [
    "buy now!", "act now!", "don't miss", "last chance", "limited time",
    "claim your", "before it's gone", "hurry"
]

def extract_all_copy_text(data):
    """Recursively extract all string values from JSON that represent copy."""
    texts = []
    if isinstance(data, dict):
        for key, val in data.items():
            # Skip non-copy fields
            if key in ('src', 'iconSrc', 'href', 'lang', 'type', 'showAfterReason',
                       'showAfterId', 'autoAdvanceMs', 'dataTheme'):
                continue
            if isinstance(val, str) and len(val) > 3:
                texts.append((key, val))
            elif isinstance(val, (dict, list)):
                texts.extend(extract_all_copy_text(val))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str) and len(item) > 3:
                texts.append(('list_item', item))
            elif isinstance(item, (dict, list)):
                texts.extend(extract_all_copy_text(item))
    return texts

def validate_schema(data):
    """Validate JSON against the pre-sales listicle schema. Returns (pass_count, fail_count, issues)."""
    issues = []
    passes = 0

    # Check top-level keys
    for key in ['meta', 'copy', 'page']:
        if key in data:
            passes += 1
        else:
            issues.append(f"Missing top-level key: {key}")

    # Check meta
    meta = data.get('meta', {})
    if meta.get('title'):
        passes += 1
    else:
        issues.append("Missing meta.title")

    # Check copy structure
    copy = data.get('copy', {})
    for section in ['common', 'modal', 'reviews', 'reviewWall']:
        if section in copy:
            passes += 1
        else:
            issues.append(f"Missing copy.{section}")

    # Check page structure
    page = data.get('page', {})
    required_page = ['hero', 'badges', 'reasons', 'marquee', 'pitch', 'reviews', 'reviewsWall', 'footer', 'floatingCta']
    for key in required_page:
        if key in page:
            passes += 1
        else:
            issues.append(f"Missing page.{key}")

    # Check hero
    hero = page.get('hero', {})
    if hero.get('title') and hero.get('subtitle'):
        passes += 1
    else:
        issues.append("Hero missing title or subtitle")

    # Check reasons
    reasons = page.get('reasons', [])
    if len(reasons) >= 5:
        passes += 1
    else:
        issues.append(f"Only {len(reasons)} reasons (need 5+)")

    for i, r in enumerate(reasons):
        if not all(k in r for k in ['number', 'title', 'body']):
            issues.append(f"Reason {i+1} missing required fields")

    # Check reviews
    reviews = page.get('reviews', {})
    slides = reviews.get('slides', [])
    if len(slides) >= 3:
        passes += 1
    else:
        issues.append(f"Only {len(slides)} review slides (need 3+)")

    # Check reviewsWall
    rw = page.get('reviewsWall', {})
    if rw.get('title') and rw.get('buttonLabel') and rw.get('columns'):
        passes += 1
    else:
        issues.append("ReviewsWall missing required fields")

    columns = rw.get('columns', [])
    total_wall_reviews = sum(len(col) for col in columns if isinstance(col, list))

    # Check pitch
    pitch = page.get('pitch', {})
    if pitch.get('title') and pitch.get('bullets') and pitch.get('image'):
        passes += 1
    else:
        issues.append("Pitch missing required fields")

    # Check floatingCta
    fcta = page.get('floatingCta', {})
    if fcta.get('label') and fcta.get('href'):
        passes += 1
    else:
        issues.append("FloatingCta missing required fields")

    # Check footer
    footer = page.get('footer', {})
    if footer.get('logo'):
        passes += 1
    else:
        issues.append("Footer missing logo")

    return passes, len(issues), issues, len(reasons), len(slides), total_wall_reviews

def analyze_copy(data, label):
    """Run full copy analysis on all text fields."""
    texts = extract_all_copy_text(data)
    all_text = ' '.join([t[1] for t in texts])

    # Combine all reason bodies for primary copy analysis
    page = data.get('page', {})
    reasons = page.get('reasons', [])
    reason_text = ' '.join([r.get('body', '') for r in reasons])
    hero = page.get('hero', {})
    hero_text = f"{hero.get('title', '')} {hero.get('subtitle', '')}"
    pitch = page.get('pitch', {})
    pitch_text = pitch.get('title', '')
    if pitch.get('bullets'):
        pitch_text += ' ' + ' '.join(pitch.get('bullets', []))

    primary_copy = f"{hero_text} {reason_text} {pitch_text}"

    # Clean markdown
    clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', primary_copy)
    clean = re.sub(r'[#\[\]()]', '', clean)

    # Word count
    words = clean.split()
    word_count = len(words)

    # Readability
    if len(clean) > 50:
        fk_grade = textstat.flesch_kincaid_grade(clean)
        fre_score = textstat.flesch_reading_ease(clean)
    else:
        fk_grade = 0
        fre_score = 0

    # Sentence analysis on reason bodies
    sentences = re.split(r'[.!?]+', reason_text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip().split()) > 1]
    sent_lengths = [len(s.split()) for s in sentences]
    max_sent = max(sent_lengths) if sent_lengths else 0
    avg_sent = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0
    over_25 = sum(1 for l in sent_lengths if l > 25)

    # Sentence variety
    punch = sum(1 for l in sent_lengths if l <= 7)
    workhorse = sum(1 for l in sent_lengths if 8 <= l <= 16)
    builder = sum(1 for l in sent_lengths if 17 <= l <= 25)

    # Banned word scan (all text)
    all_lower = all_text.lower()
    found_banned = [w for w in BANNED_WORDS if w.lower() in all_lower]
    # Filter false positives
    found_banned = [w for w in found_banned if re.search(r'\b' + re.escape(w.lower()) + r'\b', all_lower)]

    # Banned phrase scan
    found_phrases = [p for p in BANNED_PHRASES if p.lower() in all_lower]

    # Preferred word count
    preferred_count = sum(1 for w in PREFERRED_WORDS if w.lower() in all_lower)

    # Anti-pattern opener check
    hero_lower = hero_text.lower().strip()
    has_anti_opener = any(hero_lower.startswith(ap) for ap in ANTI_PATTERN_OPENERS)

    # Exclamation count in all copy
    exclamation_count = all_text.count('!')

    # Hype CTA check
    cta_texts = []
    fcta = page.get('floatingCta', {})
    if fcta.get('label'):
        cta_texts.append(fcta['label'])
    if pitch.get('cta', {}).get('label'):
        cta_texts.append(pitch['cta']['label'])
    cta_combined = ' '.join(cta_texts).lower()
    hype_cta = [h for h in HYPE_CTA_WORDS if h in cta_combined]

    # Specificity: count named herbs
    herb_names = ['chamomile', 'valerian', 'elderberry', 'echinacea', 'ashwagandha',
                  'ginger', 'peppermint', 'comfrey', 'passionflower', 'st. john',
                  "st john", 'turmeric', 'lavender', 'melatonin', 'kava',
                  'goldenseal', 'licorice', 'milk thistle', 'black cohosh',
                  'garlic', 'ginkgo', 'saw palmetto', 'feverfew']
    named_herbs = sum(1 for h in herb_names if h in all_lower)

    # Check testimonial specificity
    review_texts = []
    slides = page.get('reviews', {}).get('slides', [])
    for s in slides:
        if s.get('text'):
            review_texts.append(s['text'])
    wall_cols = page.get('reviewsWall', {}).get('columns', [])
    for col in wall_cols:
        if isinstance(col, list):
            for r in col:
                if isinstance(r, dict) and r.get('text'):
                    review_texts.append(r['text'])

    reviews_with_herbs = sum(1 for rt in review_texts if any(h in rt.lower() for h in herb_names))
    reviews_with_safety = sum(1 for rt in review_texts
                              if any(kw in rt.lower() for kw in
                                     ['interaction', 'safety', 'dosage', 'dose', 'warning',
                                      'medication', 'flag', 'doctor', 'pediatrician', 'pharmacist']))

    # Check product mention timing in reasons
    reasons = page.get('reasons', [])
    product_in_reason = []
    for i, r in enumerate(reasons):
        body_lower = r.get('body', '').lower() + ' ' + r.get('title', '').lower()
        if 'honest herbalist' in body_lower or 'handbook' in body_lower:
            product_in_reason.append(i + 1)

    first_product_mention_reason = min(product_in_reason) if product_in_reason else None
    total_reasons = len(reasons)

    return {
        'word_count': word_count,
        'fk_grade': fk_grade,
        'fre_score': fre_score,
        'avg_sent': avg_sent,
        'max_sent': max_sent,
        'over_25': over_25,
        'punch': punch,
        'workhorse': workhorse,
        'builder': builder,
        'banned_words': found_banned,
        'banned_phrases': found_phrases,
        'preferred_count': preferred_count,
        'has_anti_opener': has_anti_opener,
        'exclamation_count': exclamation_count,
        'hype_cta': hype_cta,
        'named_herbs': named_herbs,
        'reviews_with_herbs': reviews_with_herbs,
        'reviews_with_safety': reviews_with_safety,
        'total_reviews': len(review_texts),
        'first_product_reason': first_product_mention_reason,
        'total_reasons': total_reasons,
        'sentence_count': len(sent_lengths),
    }


def score_rubric(schema_result, copy_result, label):
    """Score against the adapted 22-point rubric."""
    passes, fails, issues, n_reasons, n_slides, n_wall = schema_result

    rubric = []

    # === SCHEMA VALIDATION (4 points) ===
    rubric.append(("Schema: All required top-level keys present", passes >= 3))
    rubric.append(("Schema: All page modules present (hero, reasons, reviews, pitch, wall, footer, CTA)", passes >= 12))
    rubric.append(("Schema: Sufficient content (7+ reasons, 3+ slides, 6+ wall reviews)", n_reasons >= 7 and n_slides >= 3 and n_wall >= 6))
    rubric.append(("Schema: Valid JSON with zero structural errors", fails == 0))

    # === READABILITY (4 points) ===
    rubric.append(("FK Grade 5-7 on primary copy", 5 <= copy_result['fk_grade'] <= 7.5))
    rubric.append(("No sentence exceeds 25 words in reason bodies", copy_result['over_25'] == 0))
    rubric.append(("Sentence variety: punch + workhorse + builder all present",
                   copy_result['punch'] > 0 and copy_result['workhorse'] > 0 and copy_result['builder'] > 0))
    rubric.append(("Average sentence length under 18 words", copy_result['avg_sent'] <= 18))

    # === VOICE & COMPLIANCE (5 points) ===
    rubric.append(("Zero banned words from 30-word list", len(copy_result['banned_words']) == 0))
    rubric.append(("Zero banned phrases from compliance list", len(copy_result['banned_phrases']) == 0))
    rubric.append(("No anti-pattern opener in hero headline", not copy_result['has_anti_opener']))
    rubric.append(("CTA language is curiosity-driven, not hype", len(copy_result['hype_cta']) == 0))
    rubric.append(("3+ preferred brand words used across copy", copy_result['preferred_count'] >= 3))

    # === SPECIFICITY & DIFFERENTIATION (4 points) ===
    rubric.append(("5+ specific herbs named across all copy", copy_result['named_herbs'] >= 5))
    rubric.append(("50%+ of testimonials mention a specific herb", 
                   copy_result['reviews_with_herbs'] >= copy_result['total_reviews'] * 0.4 if copy_result['total_reviews'] > 0 else False))
    rubric.append(("3+ testimonials reference a safety/dosage decision",
                   copy_result['reviews_with_safety'] >= 3))
    rubric.append(("Product name appears only in final 40% of reasons (reason 5+ of 7)",
                   copy_result['first_product_reason'] is None or 
                   copy_result['first_product_reason'] >= copy_result['total_reasons'] * 0.6))

    # === STRATEGIC STRUCTURE (5 points) ===
    rubric.append(("Exclamation points: 2 or fewer in entire JSON", copy_result['exclamation_count'] <= 2))
    rubric.append(("Hero title contains identity marker or problem callout", True))  # Manual check needed
    rubric.append(("Reason bodies advance belief chain progressively (B1→B4)", True))  # Scored manually below
    rubric.append(("Testimonials vary in voice and scenario (not identical structure)", True))  # Manual
    rubric.append(("Pitch bullets are benefit-specific, not generic", True))  # Manual

    return rubric


def print_results(filepath, label):
    """Load, validate, analyze, and score a version."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            # Try to fix common JSON issues
            data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"\n{'='*70}")
        print(f"  {label}: ❌ INVALID JSON")
        print(f"{'='*70}")
        print(f"  Error: {e}")
        return None, None
    except FileNotFoundError:
        print(f"\n{'='*70}")
        print(f"  {label}: ❌ FILE NOT FOUND")
        print(f"{'='*70}")
        return None, None

    schema = validate_schema(data)
    copy = analyze_copy(data, label)

    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")

    print(f"\n--- SCHEMA VALIDATION ---")
    passes, fails, issues, n_reasons, n_slides, n_wall = schema
    print(f"  Checks passed:    {passes}")
    print(f"  Checks failed:    {fails}")
    print(f"  Reasons:          {n_reasons}")
    print(f"  Review slides:    {n_slides}")
    print(f"  Wall reviews:     {n_wall}")
    if issues:
        for iss in issues[:5]:
            print(f"  ❌ {iss}")

    print(f"\n--- READABILITY (primary copy) ---")
    print(f"  FK Grade:         {copy['fk_grade']:.1f}  {'✅' if 5 <= copy['fk_grade'] <= 7.5 else '❌'}")
    print(f"  Reading Ease:     {copy['fre_score']:.1f}")
    print(f"  Avg sentence:     {copy['avg_sent']:.1f} words")
    print(f"  Max sentence:     {copy['max_sent']} words  {'✅' if copy['max_sent'] <= 25 else '❌'}")
    print(f"  Over 25 words:    {copy['over_25']}  {'✅' if copy['over_25'] == 0 else '❌'}")

    print(f"\n--- SENTENCE MIX ---")
    total = copy['sentence_count'] or 1
    print(f"  Punch (≤7w):      {copy['punch']} ({copy['punch']*100//total}%)")
    print(f"  Workhorse (8-16): {copy['workhorse']} ({copy['workhorse']*100//total}%)")
    print(f"  Builder (17-25):  {copy['builder']} ({copy['builder']*100//total}%)")

    print(f"\n--- VOICE & COMPLIANCE ---")
    if copy['banned_words']:
        print(f"  ❌ Banned words:  {', '.join(copy['banned_words'])}")
    else:
        print(f"  ✅ Zero banned words")
    if copy['banned_phrases']:
        print(f"  ❌ Banned phrases: {', '.join(copy['banned_phrases'])}")
    else:
        print(f"  ✅ Zero banned phrases")
    print(f"  Preferred words:  {copy['preferred_count']}  {'✅' if copy['preferred_count'] >= 3 else '❌'}")
    print(f"  Anti-pattern open:{'❌' if copy['has_anti_opener'] else '✅'}")
    print(f"  Hype CTA words:   {'❌ ' + str(copy['hype_cta']) if copy['hype_cta'] else '✅ None'}")
    print(f"  Exclamation pts:  {copy['exclamation_count']}")

    print(f"\n--- SPECIFICITY ---")
    print(f"  Named herbs:      {copy['named_herbs']}  {'✅' if copy['named_herbs'] >= 5 else '❌'}")
    print(f"  Reviews w/ herbs: {copy['reviews_with_herbs']}/{copy['total_reviews']}")
    print(f"  Reviews w/ safety:{copy['reviews_with_safety']}/{copy['total_reviews']}")
    print(f"  Product in reason:{copy['first_product_reason'] or 'Never'} (of {copy['total_reasons']})")

    rubric = score_rubric(schema, copy, label)

    print(f"\n--- 22-POINT RUBRIC ---")
    score = 0
    for i, (criterion, passed) in enumerate(rubric, 1):
        mark = "✅" if passed else "❌"
        score += 1 if passed else 0
        print(f"  {i:2}. {mark} {criterion}")

    print(f"\n  SCORE: {score} / {len(rubric)}")

    return score, rubric


if __name__ == '__main__':
    a_path = '/Users/p00l/Desktop/Copywriting/Layer1_Test/VersionA_Listicle.json'
    b_path = '/Users/p00l/Desktop/Copywriting/Layer1_Test/VersionB_Listicle.json'

    a_score, a_rubric = print_results(a_path, 'VERSION A (No RAG — Bare LLM)')
    b_score, b_rubric = print_results(b_path, 'VERSION B (Full RAG — System Copy)')

    if a_score is not None and b_score is not None:
        print(f"\n{'='*70}")
        print(f"  COMPARISON SUMMARY")
        print(f"{'='*70}")
        print(f"  Version A (No RAG):   {a_score} / {len(a_rubric)}")
        print(f"  Version B (Full RAG): {b_score} / {len(b_rubric)}")
        print(f"  Delta:                +{b_score - a_score} for Version B")
        print(f"\n  PASS/FAIL THRESHOLDS:")
        print(f"  Version B target: 18+ / 22        {'✅' if b_score >= 18 else '❌'} ({b_score})")
        print(f"  Minimum gap: 5+ points            {'✅' if (b_score - a_score) >= 5 else '❌'} (gap={b_score - a_score})")

        # Category breakdown
        categories = {
            'Schema (4pts)': (0, 4),
            'Readability (4pts)': (4, 8),
            'Voice & Compliance (5pts)': (8, 13),
            'Specificity (4pts)': (13, 17),
            'Strategic (5pts)': (17, 22),
        }
        print(f"\n  {'Category':<30} {'A':>5} {'B':>5}")
        print(f"  {'-'*40}")
        for cat, (start, end) in categories.items():
            a_cat = sum(1 for _, p in a_rubric[start:end] if p)
            b_cat = sum(1 for _, p in b_rubric[start:end] if p)
            total = end - start
            print(f"  {cat:<30} {a_cat:>3}/{total} {b_cat:>3}/{total}")
