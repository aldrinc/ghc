#!/usr/bin/env python3
"""
UPGRADE LAYER TEST v2 -- Mental Model Scoring Framework
========================================================
Tests: Version A (research docs only) vs Version B (research docs + copywriting agent frameworks)

CHANGES FROM v1:
- Hard Gates reduced to 2 pts each (was 3) -- no single test dominates the delta
- 6 new differentiator tests added (QS15-QS18, ADV6-ADV7)
- FK grade target recalibrated to 5.0-9.0 for safety-angle copy
- Supports 2 trials per version with median reporting
- All scoring remains deterministic Python -- zero LLM inference
"""

import json
import re
import sys
import math
import textstat
from collections import Counter
import statistics

# ============================================================
# SECTION 1: DATA EXTRACTION (First Principles -- Decompose)
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
    'red clover', 'motherwort', 'hawthorn', 'lemon balm',
    'red raspberry', 'pennyroyal'
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
    with open(filepath, 'r') as f:
        return json.load(f)


def extract_all_text(data, skip_keys=None):
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


def extract_brand_voice_text(data):
    """Extract text from brand-voice sections only (NOT testimonials)."""
    page = data.get('page', {})
    brand_sections = ['hero', 'badges', 'reasons', 'marquee', 'pitch', 'floatingCta', 'footer']
    texts = []
    for key in brand_sections:
        section = page.get(key)
        if section:
            texts.extend(extract_all_text(section))
    return ' '.join([t[1] for t in texts])


def get_reason_bodies(data):
    reasons = data.get('page', {}).get('reasons', [])
    return [(r.get('number', i+1), r.get('title', ''), r.get('body', '')) for i, r in enumerate(reasons)]


def get_review_texts(data):
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
# SECTION 2: HARD GATE TESTS (2 pts each -- reduced from 3)
# ============================================================

def hard_gate_tests(data):
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()

    # HG1: Zero banned words
    found_banned = []
    for w in BANNED_WORDS:
        pattern = r'\b' + re.escape(w.lower()) + r'\b'
        if re.search(pattern, all_lower):
            found_banned.append(w)
    results.append({
        'id': 'HG1', 'name': 'Zero Banned Words',
        'pass': len(found_banned) == 0,
        'detail': f"Found: {found_banned}" if found_banned else "Clean",
        'weight': 2, 'model': 'First Principles + Inversion'
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
        'weight': 2, 'model': 'First Principles + Inversion'
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
        'weight': 2, 'model': 'First Principles + Engineering Safety'
    })

    # HG4: All required page modules present
    page = data.get('page', {})
    required = ['hero', 'badges', 'reasons', 'marquee', 'pitch', 'reviews', 'reviewsWall', 'footer', 'floatingCta']
    missing = [k for k in required if k not in page]
    results.append({
        'id': 'HG4', 'name': 'All Required Page Modules Present',
        'pass': len(missing) == 0,
        'detail': f"Missing: {missing}" if missing else "All present",
        'weight': 2, 'model': 'First Principles'
    })

    return results


# ============================================================
# SECTION 3: QUALITY SIGNAL TESTS (1 pt each)
# Now 18 tests (was 14) -- 4 new differentiators added
# ============================================================

def quality_signal_tests(data):
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()
    reasons = get_reason_bodies(data)
    reviews = get_review_texts(data)
    hero = data.get('page', {}).get('hero', {})
    pitch = data.get('page', {}).get('pitch', {})
    brand_text = extract_brand_voice_text(data)

    # --- READABILITY ---

    # QS1: FK Grade 5-9.0 (recalibrated for safety-angle copy)
    reason_text = ' '.join([b for _, _, b in reasons])
    clean_reason = re.sub(r'\*\*([^*]+)\*\*', r'\1', reason_text)
    fk = textstat.flesch_kincaid_grade(clean_reason) if len(clean_reason) > 50 else 0
    results.append({
        'id': 'QS1', 'name': 'FK Grade 5-9.0 (reason bodies)',
        'pass': 5.0 <= fk <= 9.0,
        'detail': f"FK = {fk:.1f}",
        'weight': 1, 'model': 'Information Theory'
    })

    # QS2: Max sentence length <= 25 words in reason bodies
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

    # --- VOICE ---

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
    curiosity_words = ['see', 'look', 'inside', 'how', 'discover', 'explore', 'learn', 'what']
    has_curiosity = any(c in cta_combined for c in curiosity_words)
    results.append({
        'id': 'QS7', 'name': 'CTA is curiosity-driven (not hype)',
        'pass': not has_hype and has_curiosity,
        'detail': f"Hype={'YES' if has_hype else 'no'}, Curiosity={'YES' if has_curiosity else 'no'}. CTAs: {cta_texts}",
        'weight': 1, 'model': 'Behavioral Economics'
    })

    # QS8: <= 2 exclamation points total
    exc_count = all_text.count('!')
    results.append({
        'id': 'QS8', 'name': '<=2 exclamation points in entire JSON',
        'pass': exc_count <= 2,
        'detail': f"{exc_count} exclamation points",
        'weight': 1, 'model': 'Signal-to-Noise Ratio'
    })

    # --- SPECIFICITY ---

    # QS9: 5+ specific herbs named
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

    # QS11: 3+ testimonials reference safety/dosage
    safety_reviews = sum(1 for _, rt in reviews
                         if any(kw in rt.lower() for kw in SAFETY_KEYWORDS))
    results.append({
        'id': 'QS11', 'name': '3+ testimonials reference safety/dosage',
        'pass': safety_reviews >= 3,
        'detail': f"{safety_reviews} safety-related testimonials",
        'weight': 1, 'model': 'First Principles'
    })

    # --- STRUCTURAL ---

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

    # QS14: Testimonial voice variety
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

    # === NEW DIFFERENTIATOR TESTS ===

    # QS15: Contraction rate >= 70% in brand voice (Section 3, Rule A5)
    brand_lower = brand_text.lower()
    expanded_patterns = [
        (r'\byou will\b', "you'll"),
        (r'\bit is\b', "it's"),
        (r'\bwe are\b', "we're"),
        (r'\bthat is\b', "that's"),
        (r'\bdo not\b', "don't"),
        (r'\bdoes not\b', "doesn't"),
        (r'\bwill not\b', "won't"),
        (r'\bcannot\b', "can't"),
        (r'\bthey are\b', "they're"),
        (r'\bwe have\b', "we've"),
        (r'\byou are\b', "you're"),
        (r'\bis not\b', "isn't"),
        (r'\bwas not\b', "wasn't"),
        (r'\bwere not\b', "weren't"),
        (r'\bhas not\b', "hasn't"),
        (r'\bhave not\b', "haven't"),
        (r'\bwould not\b', "wouldn't"),
        (r'\bcould not\b', "couldn't"),
        (r'\bshould not\b', "shouldn't"),
    ]
    expanded_count = 0
    for pattern, _ in expanded_patterns:
        expanded_count += len(re.findall(pattern, brand_lower))
    contracted_count = 0
    for _, contraction in expanded_patterns:
        contracted_count += len(re.findall(re.escape(contraction), brand_lower))
    total_contractable = expanded_count + contracted_count
    contraction_rate = contracted_count / total_contractable if total_contractable > 0 else 1.0
    results.append({
        'id': 'QS15', 'name': 'Contraction rate >= 70% in brand voice',
        'pass': contraction_rate >= 0.70 or total_contractable == 0,
        'detail': f"{contracted_count}/{total_contractable} contracted ({contraction_rate:.0%}). {expanded_count} stiff expansions.",
        'weight': 1, 'model': 'Section 3 Rule A5 (voice calibration)'
    })

    # QS16: Foundation Gate: B1+B2 before B3 in reasons (Subsection A, Section 2.3)
    b1_keywords = ['herbs can', 'herbal', 'traditionally used', 'remedy', 'natural remedies',
                   'herbs have', 'plants that', 'botanical', 'track record', 'traditional use',
                   'well-documented', 'documented for']
    b2_keywords = ['not automatically safe', 'interaction', 'interfere', 'risk', 'caution',
                   'contraindic', 'side effect', 'wrong herb', 'dangerous', 'careful',
                   "natural doesn't mean", "natural isn't", "natural is not",
                   'too much', 'disable', 'amplify', 'spike']
    b3_keywords = ['ecosystem', 'contradictory', 'contradicting', 'conflicting', 'ai-generated',
                   'ai generated', 'misinformation', 'blog posts', 'broken',
                   'information overload', 'facebook group', 'reddit', 'tiktok',
                   'three different answers', 'three contradictory']

    first_b1 = first_b2 = first_b3 = None
    for i, (num, title, body) in enumerate(reasons):
        combined = (title + ' ' + body).lower()
        if first_b1 is None and any(k in combined for k in b1_keywords):
            first_b1 = i
        if first_b2 is None and any(k in combined for k in b2_keywords):
            first_b2 = i
        if first_b3 is None and any(k in combined for k in b3_keywords):
            first_b3 = i

    if first_b3 is None:
        gate_pass = True
        gate_detail = "B3 not found in reasons (gate not applicable)"
    elif first_b1 is None or first_b2 is None:
        gate_pass = False
        gate_detail = f"B1={'missing' if first_b1 is None else f'R{first_b1+1}'}, B2={'missing' if first_b2 is None else f'R{first_b2+1}'}, B3=R{first_b3+1}"
    else:
        gate_pass = (first_b1 <= first_b3) and (first_b2 <= first_b3)
        gate_detail = f"B1=R{first_b1+1}, B2=R{first_b2+1}, B3=R{first_b3+1}. Gate={'PASS' if gate_pass else 'FAIL'}"
    results.append({
        'id': 'QS16', 'name': 'Foundation Gate: B1+B2 before B3 in reasons',
        'pass': gate_pass,
        'detail': gate_detail,
        'weight': 1, 'model': 'Subsection A 2.3 (belief chain sequencing)'
    })

    # QS17: Exclamations only in testimonials (Section 3, Anti-Pattern #4)
    page = data.get('page', {})
    brand_section_keys = ['hero', 'badges', 'reasons', 'marquee', 'pitch', 'floatingCta', 'footer']
    exc_violations = []
    for key in brand_section_keys:
        section = page.get(key)
        if section:
            section_text = ' '.join([t[1] for t in extract_all_text(section)])
            exc_in_section = section_text.count('!')
            if exc_in_section > 0:
                exc_violations.append(f"{key}: {exc_in_section}")
    results.append({
        'id': 'QS17', 'name': 'Exclamations only in testimonials (not brand voice)',
        'pass': len(exc_violations) == 0,
        'detail': f"Violations: {exc_violations}" if exc_violations else "Clean",
        'weight': 1, 'model': 'Section 3 Anti-Pattern #4'
    })

    # QS18: Zero emoji in sales copy (Section 3, Anti-Pattern #18)
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002B50"
        "\U00002764"
        "]+", flags=re.UNICODE
    )
    found_emoji = emoji_pattern.findall(all_text)
    results.append({
        'id': 'QS18', 'name': 'Zero emoji in sales copy',
        'pass': len(found_emoji) == 0,
        'detail': f"Found {len(found_emoji)} emoji: {found_emoji[:5]}" if found_emoji else "Clean",
        'weight': 1, 'model': 'Section 3 Anti-Pattern #18'
    })

    return results


# ============================================================
# SECTION 4: POLISH INDICATORS (0.5 pts each)
# ============================================================

def polish_tests(data):
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()
    reasons = get_reason_bodies(data)
    reviews = get_review_texts(data)

    # P1: Parent testimonial
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

    # P2: Trust badges
    badges = data.get('page', {}).get('badges', [])
    badge_labels = [b.get('label', '').lower() for b in badges]
    hype_badges = sum(1 for l in badge_labels if any(w in l for w in ['best', '#1', 'amazing', 'incredible']))
    results.append({
        'id': 'P2', 'name': 'Badge labels are trust signals (not hype)',
        'pass': hype_badges == 0 and len(badges) >= 3,
        'detail': f"{len(badges)} badges, {hype_badges} hype badges",
        'weight': 0.5, 'model': 'Signal-to-Noise'
    })

    # P3: Bonus mention in pitch
    pitch_text = ' '.join(data.get('page', {}).get('pitch', {}).get('bullets', []))
    has_bonus = any(w in pitch_text.lower() for w in ['bonus', 'included', 'also get', 'plus', 'free'])
    results.append({
        'id': 'P3', 'name': 'Pitch mentions bonuses/extras',
        'pass': has_bonus,
        'detail': "Bonus mentioned" if has_bonus else "No bonus mention",
        'weight': 0.5, 'model': 'Behavioral Economics (value framing)'
    })

    # P4: Non-5-star review
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

    # P5: Body density 30-70 words avg
    body_lengths = [len(body.split()) for _, _, body in reasons]
    avg_body = sum(body_lengths) / len(body_lengths) if body_lengths else 0
    results.append({
        'id': 'P5', 'name': 'Reason body density 30-70 words avg',
        'pass': 30 <= avg_body <= 70,
        'detail': f"Avg body = {avg_body:.0f} words. Per-reason: {body_lengths}",
        'weight': 0.5, 'model': 'Information Theory'
    })

    # P6: Marquee preferred words
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
# SECTION 5: ADVERSARIAL CHECKS (1 pt each)
# Now 7 tests (was 5) -- 2 new differentiators added
# ============================================================

def adversarial_checks(data):
    results = []
    all_text = ' '.join([t[1] for t in extract_all_text(data)])
    all_lower = all_text.lower()
    reasons = get_reason_bodies(data)
    reviews = get_review_texts(data)

    # ADV1: No transformation promises
    transformation_phrases = [
        'transform your', 'change your life', 'life-changing',
        'will change your health', 'revolutionize', 'game-changer',
        'game changer', 'never be the same', 'completely different person'
    ]
    found = [p for p in transformation_phrases if p in all_lower]
    results.append({
        'id': 'ADV1', 'name': 'No transformation promises (Anti-Pattern #16)',
        'pass': len(found) == 0,
        'detail': f"Found: {found}" if found else "Clean",
        'weight': 1, 'model': 'Inversion'
    })

    # ADV2: No generic stock copy
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
        'detail': f"Found: {found}" if found else "Clean",
        'weight': 1, 'model': 'Inversion + Pareto'
    })

    # ADV3: 50%+ reasons mention safety
    reasons_with_safety = 0
    for num, title, body in reasons:
        combined = (title + ' ' + body).lower()
        if any(kw in combined for kw in ['risk', 'safe', 'caution', 'interact', 'warning',
                                          'wrong', 'harm', 'danger', 'stop', 'too much',
                                          'careful', 'flag', 'contraindic']):
            reasons_with_safety += 1
    results.append({
        'id': 'ADV3', 'name': '50%+ reasons mention safety/risk',
        'pass': reasons_with_safety >= len(reasons) * 0.5,
        'detail': f"{reasons_with_safety}/{len(reasons)} reasons address safety",
        'weight': 1, 'model': 'Inversion'
    })

    # ADV4: Testimonial opening diversity
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
        'weight': 1, 'model': 'Regression to Mean'
    })

    # ADV5: No personal-attribute targeting
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

    # === NEW DIFFERENTIATORS ===

    # ADV6: No consecutive builder sentences (Subsection B, Section 3.1)
    reason_text = ' '.join([body for _, _, body in reasons])
    all_sentences = re.split(r'(?<=[.!?])\s+', reason_text)
    all_sentences = [s.strip() for s in all_sentences if s.strip() and len(s.split()) > 1]
    consecutive_builders = 0
    prev_is_builder = False
    for s in all_sentences:
        wc = len(s.split())
        is_builder = 17 <= wc <= 25
        if is_builder and prev_is_builder:
            consecutive_builders += 1
        prev_is_builder = is_builder
    results.append({
        'id': 'ADV6', 'name': 'No consecutive builder sentences (17-25w)',
        'pass': consecutive_builders == 0,
        'detail': f"{consecutive_builders} back-to-back builder violations",
        'weight': 1, 'model': 'Subsection B 3.1 (rhythm variation)'
    })

    # ADV7: Agitation includes externalization beat (Subsection A, Section 3.3)
    reason_text_lower = ' '.join([body for _, _, body in reasons]).lower()
    agitation_markers = ['confus', 'overwhelm', 'frustrat', 'contradict', 'guesswork',
                         'unreliable', 'wrong', 'worry', 'scared', 'uncertain',
                         'broken', 'conflicting']
    has_agitation = any(m in reason_text_lower for m in agitation_markers)

    externalize_markers = [
        'not your fault', "isn't your fault", "it's not that you",
        'ecosystem', 'system is', 'system was', 'information landscape',
        'the real problem is', "that's not a knowledge problem",
        "shouldn't need", "shouldn't have to", "not because you",
        'the problem isn\'t you', "the problem was never",
        'structurally broken', 'information environment',
        'reward clicks', 'affiliate', 'written by no one',
        'reviewed by no one', 'ai-generated', 'ai generated',
        'content farm'
    ]
    has_externalize = any(m in reason_text_lower for m in externalize_markers)

    if not has_agitation:
        ext_pass = True
        ext_detail = "No agitation detected -- externalization not required"
    else:
        ext_pass = has_externalize
        ext_detail = f"Agitation present. Externalization: {'found' if has_externalize else 'MISSING -- reader left in personal blame'}"
    results.append({
        'id': 'ADV7', 'name': 'Agitation includes externalization beat',
        'pass': ext_pass,
        'detail': ext_detail,
        'weight': 1, 'model': 'Subsection A 3.3 (system-blame not reader-blame)'
    })

    return results


# ============================================================
# SECTION 6: SCORING & REPORTING
# ============================================================

def compute_score(hard_gates, quality_signals, polish, adversarial):
    hg_score = sum(r['weight'] for r in hard_gates if r['pass'])
    hg_max = sum(r['weight'] for r in hard_gates)
    qs_score = sum(r['weight'] for r in quality_signals if r['pass'])
    qs_max = sum(r['weight'] for r in quality_signals)
    p_score = sum(r['weight'] for r in polish if r['pass'])
    p_max = sum(r['weight'] for r in polish)
    adv_score = sum(r['weight'] for r in adversarial if r['pass'])
    adv_max = sum(r['weight'] for r in adversarial)

    total = hg_score + qs_score + p_score + adv_score
    maximum = hg_max + qs_max + p_max + adv_max
    hg_failures = [r for r in hard_gates if not r['pass']]

    return {
        'total': total, 'max': maximum,
        'hard_gate': (hg_score, hg_max),
        'quality_signal': (qs_score, qs_max),
        'polish': (p_score, p_max),
        'adversarial': (adv_score, adv_max),
        'structural_defect': len(hg_failures) > 0,
        'hg_failures': hg_failures
    }


def score_file(data):
    """Score a single JSON file. Returns (score_dict, all_results)."""
    hg = hard_gate_tests(data)
    qs = quality_signal_tests(data)
    p = polish_tests(data)
    adv = adversarial_checks(data)
    score = compute_score(hg, qs, p, adv)
    return score, {'hg': hg, 'qs': qs, 'p': p, 'adv': adv}


def print_version_report(data, label):
    print(f"\n{'='*75}")
    print(f"  {label}")
    print(f"{'='*75}")

    score, results = score_file(data)

    # Hard Gates
    print(f"\n  HARD GATES (2 pts each)")
    print(f"  {'-'*70}")
    for r in results['hg']:
        mark = "PASS" if r['pass'] else "FAIL"
        print(f"  [{mark}] {r['id']}: {r['name']}")
        print(f"         {r['detail']}")
    print(f"  Score: {score['hard_gate'][0]}/{score['hard_gate'][1]}")

    # Quality Signals
    print(f"\n  QUALITY SIGNALS (1 pt each)")
    print(f"  {'-'*70}")
    for r in results['qs']:
        mark = "PASS" if r['pass'] else "FAIL"
        print(f"  [{mark}] {r['id']}: {r['name']}")
        print(f"         {r['detail']}  [{r['model']}]")
    print(f"  Score: {score['quality_signal'][0]}/{score['quality_signal'][1]}")

    # Polish
    print(f"\n  POLISH INDICATORS (0.5 pts each)")
    print(f"  {'-'*70}")
    for r in results['p']:
        mark = "PASS" if r['pass'] else "FAIL"
        print(f"  [{mark}] {r['id']}: {r['name']}")
        print(f"         {r['detail']}")
    print(f"  Score: {score['polish'][0]}/{score['polish'][1]}")

    # Adversarial
    print(f"\n  ADVERSARIAL CHECKS (1 pt each)")
    print(f"  {'-'*70}")
    for r in results['adv']:
        mark = "PASS" if r['pass'] else "FAIL"
        print(f"  [{mark}] {r['id']}: {r['name']}")
        print(f"         {r['detail']}")
    print(f"  Score: {score['adversarial'][0]}/{score['adversarial'][1]}")

    print(f"\n  {'='*70}")
    print(f"  TOTAL: {score['total']:.1f} / {score['max']:.1f} ({score['total']/score['max']*100:.1f}%)")
    if score['structural_defect']:
        print(f"  WARNING: {len(score['hg_failures'])} hard gate failure(s)")
    print(f"  {'='*70}")

    return score


def print_multi_trial_comparison(scores_a, scores_b, labels_a, labels_b):
    """Compare multiple trials with median analysis."""
    print(f"\n{'#'*75}")
    print(f"  MULTI-TRIAL COMPARISON")
    print(f"{'#'*75}")

    # Individual trial scores
    print(f"\n  Individual Trial Scores:")
    print(f"  {'-'*50}")
    for label, score in zip(labels_a + labels_b, scores_a + scores_b):
        pct = score['total'] / score['max'] * 100
        print(f"  {label:<20} {score['total']:>5.1f} / {score['max']:.1f} ({pct:.1f}%)")

    # Median computation
    a_totals = [s['total'] for s in scores_a]
    b_totals = [s['total'] for s in scores_b]
    median_a = statistics.median(a_totals)
    median_b = statistics.median(b_totals)
    max_score = scores_a[0]['max']

    print(f"\n  Median Scores:")
    print(f"  {'-'*50}")
    print(f"  Version A (Research Only):    {median_a:.1f} / {max_score:.1f} ({median_a/max_score*100:.1f}%)")
    print(f"  Version B (+ Frameworks):     {median_b:.1f} / {max_score:.1f} ({median_b/max_score*100:.1f}%)")
    delta = median_b - median_a
    print(f"  Delta:                        {'+' if delta > 0 else ''}{delta:.1f} pts")

    # Consistency check
    print(f"\n  Trial Consistency Check:")
    print(f"  {'-'*50}")
    a_spread = max(a_totals) - min(a_totals)
    b_spread = max(b_totals) - min(b_totals)
    consistency_threshold = max_score * 0.15
    a_consistent = a_spread <= consistency_threshold
    b_consistent = b_spread <= consistency_threshold
    print(f"  Version A spread: {a_spread:.1f} pts ({'CONSISTENT' if a_consistent else 'INCONSISTENT -- prompt sensitivity detected'})")
    print(f"  Version B spread: {b_spread:.1f} pts ({'CONSISTENT' if b_consistent else 'INCONSISTENT -- prompt sensitivity detected'})")
    print(f"  Threshold (15% of max): {consistency_threshold:.1f} pts")

    # Category breakdown (using median-scoring trial)
    print(f"\n  Category Comparison (median trials):")
    print(f"  {'-'*75}")
    # Find median trials (closest to median if exact median not in list)
    median_a_idx = min(range(len(a_totals)), key=lambda i: abs(a_totals[i] - median_a))
    median_b_idx = min(range(len(b_totals)), key=lambda i: abs(b_totals[i] - median_b))
    sa = scores_a[median_a_idx]
    sb = scores_b[median_b_idx]

    categories = [
        ('Hard Gates (2pts ea)', 'hard_gate'),
        ('Quality Signals (1pt ea)', 'quality_signal'),
        ('Polish (0.5pts ea)', 'polish'),
        ('Adversarial Checks (1pt ea)', 'adversarial'),
    ]
    print(f"  {'Category':<35} {'A':>12} {'B':>12} {'Delta':>8}")
    print(f"  {'-'*67}")
    for name, key in categories:
        a_val, a_max = sa[key]
        b_val, b_max = sb[key]
        d = b_val - a_val
        sign = '+' if d > 0 else ''
        print(f"  {name:<35} {a_val:>5.1f}/{a_max:<4.1f}  {b_val:>5.1f}/{b_max:<4.1f}  {sign}{d:>5.1f}")
    print(f"  {'-'*67}")
    print(f"  {'TOTAL':<35} {sa['total']:>5.1f}/{sa['max']:<4.1f}  {sb['total']:>5.1f}/{sb['max']:<4.1f}  {'+' if delta > 0 else ''}{delta:>5.1f}")

    # Thresholds
    print(f"\n  Thresholds:")
    print(f"  {'-'*50}")
    raw_thresh = max_score * 0.8
    safe_thresh = raw_thresh * 1.1
    print(f"  Version B target (80%):     {raw_thresh:.1f}")
    print(f"  Version B safe (80%+10%):   {safe_thresh:.1f}")
    print(f"  Version B actual (median):  {median_b:.1f}  {'PASS' if median_b >= safe_thresh else 'FAIL'}")
    gap_thresh = 3.0
    print(f"  Minimum meaningful gap:     {gap_thresh:.1f}")
    print(f"  Actual gap:                 {delta:.1f}  {'SIGNIFICANT' if delta >= gap_thresh else 'NOT SIGNIFICANT'}")

    # Pareto
    if delta > 0:
        print(f"\n  Pareto Analysis:")
        print(f"  {'-'*50}")
        for name, key in categories:
            a_val, _ = sa[key]
            b_val, _ = sb[key]
            d = b_val - a_val
            if d > 0:
                pct = d / delta * 100
                print(f"    {name}: +{d:.1f} pts ({pct:.0f}% of gap)")

    # Regression to mean
    print(f"\n  Regression to Mean Check:")
    print(f"  {'-'*50}")
    b_pct = median_b / max_score * 100
    if b_pct >= 95:
        print(f"  WARNING: Version B scored {b_pct:.0f}% -- suspiciously high")
    elif b_pct >= 85:
        print(f"  OK: Version B scored {b_pct:.0f}% -- strong but credible")
    else:
        print(f"  OK: Version B scored {b_pct:.0f}% -- moderate, room for improvement")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 scorer_v2.py <A1.json> <A2.json> <B1.json> <B2.json>")
        print("   or: python3 scorer_v2.py <A.json> <B.json>")
        sys.exit(1)

    if len(sys.argv) == 3:
        # Single trial mode
        a_path, b_path = sys.argv[1], sys.argv[2]
        data_a = load_json(a_path)
        data_b = load_json(b_path)
        score_a = print_version_report(data_a, f'VERSION A -- {a_path}')
        score_b = print_version_report(data_b, f'VERSION B -- {b_path}')
        print_multi_trial_comparison([score_a], [score_b], ['A'], ['B'])

    elif len(sys.argv) == 5:
        # Dual trial mode
        a1_path, a2_path, b1_path, b2_path = sys.argv[1:5]
        data_a1 = load_json(a1_path)
        data_a2 = load_json(a2_path)
        data_b1 = load_json(b1_path)
        data_b2 = load_json(b2_path)

        score_a1 = print_version_report(data_a1, f'VERSION A -- Trial 1 ({a1_path})')
        score_a2 = print_version_report(data_a2, f'VERSION A -- Trial 2 ({a2_path})')
        score_b1 = print_version_report(data_b1, f'VERSION B -- Trial 1 ({b1_path})')
        score_b2 = print_version_report(data_b2, f'VERSION B -- Trial 2 ({b2_path})')

        print_multi_trial_comparison(
            [score_a1, score_a2], [score_b1, score_b2],
            ['A Trial 1', 'A Trial 2'], ['B Trial 1', 'B Trial 2']
        )
    else:
        print("Provide 2 or 4 JSON files.")
        sys.exit(1)
