#!/usr/bin/env python3
"""
HEADLINE <-> BODY CONGRUENCY -- Bidirectional Verification Pass
=================================================================
Zero LLM inference. Pure Python: regex, string matching, keyword
extraction, and set operations.

3 Directions, 13 Tests, 19 Total Points:
  - Headline -> Body   "Promise Payment"       (HP1-HP5, 7 pts)
  - Body -> Headline   "Setup Verification"    (BH1-BH4, 5 pts)
  - Promise Contract   "Contract Enforcement"  (PC1-PC4, 7 pts)

Supports page types: listicle (JSON), advertorial (markdown), sales_page (markdown).

Usage:
  python3 headline_body_congruency.py /path/to/listicle.json
  python3 headline_body_congruency.py /path/to/listicle.json --headline "Custom headline"
  python3 headline_body_congruency.py --headline "Your headline" --body /path/to/body.txt
  python3 headline_body_congruency.py --headline "Your headline" --body /path/to/body.md --page-type advertorial
  python3 headline_body_congruency.py --headline "Your headline" --body /path/to/body.md --page-type advertorial --promise-contract /path/to/contract.json
"""

import re
import sys
import json
import argparse
import os


# ============================================================
# SECTION 1: WORD LISTS (Module-Level Constants)
# ============================================================

# --- Stopwords (150+ common English words to filter from content-word extraction) ---
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
    "doing", "don't", "down", "during", "each", "even", "every", "few", "for",
    "from", "further", "get", "gets", "getting", "got", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "her", "here", "here's",
    "hers", "herself", "him", "himself", "his", "how", "how's", "i", "if",
    "in", "into", "is", "isn't", "it", "it's", "its", "itself", "just",
    "let", "let's", "like", "ll", "may", "me", "might", "more", "most",
    "much", "must", "mustn't", "my", "myself", "no", "nor", "not", "now",
    "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "re", "s", "same", "shall", "shan't",
    "she", "she's", "should", "shouldn't", "so", "some", "still", "such",
    "t", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd",
    "they'll", "they're", "they've", "this", "those", "through", "to", "too",
    "under", "until", "up", "upon", "us", "ve", "very", "was", "wasn't", "we",
    "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's",
    "when", "when's", "where", "where's", "which", "while", "who", "who's",
    "whom", "why", "why's", "will", "with", "won't", "would", "wouldn't",
    "yet", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
    # Additional high-frequency function words
    "a's", "able", "according", "actually", "already", "always", "among",
    "another", "anyway", "anyone", "anything", "around", "away", "back",
    "became", "become", "becomes", "becoming", "behind", "beside", "besides",
    "best", "better", "beyond", "came", "cause", "certain", "certainly",
    "changes", "clearly", "come", "comes", "concerning", "consequently",
    "consider", "considering", "contain", "containing", "contains",
    "corresponding", "course", "currently", "d", "definitely", "described",
    "despite", "different", "done", "e", "eg", "either", "else", "enough",
    "entirely", "especially", "et", "etc", "ever", "example", "except",
    "far", "find", "first", "five", "followed", "following", "former",
    "four", "furthermore", "gave", "generally", "given", "gives", "go",
    "goes", "going", "gone", "gotten", "greetings", "happens", "hardly",
    "hello", "hence", "hereafter", "hereby", "herein", "hereupon",
    "hopefully", "however", "ie", "inasmuch", "indeed", "indicate",
    "indicated", "indicates", "inner", "instead", "keep", "keeps", "kept",
    "know", "known", "knows", "last", "lately", "later", "latter",
    "least", "less", "lest", "likely", "little", "look", "looking",
    "looks", "m", "made", "mainly", "make", "makes", "many", "maybe",
    "mean", "meanwhile", "merely", "moreover", "n't", "namely", "nd",
    "near", "nearly", "necessary", "need", "needs", "neither", "never",
    "nevertheless", "new", "next", "nine", "nobody", "non", "none",
    "noone", "nothing", "novel", "obviously", "often", "oh", "ok", "okay",
    "old", "one", "ones", "onto", "others", "otherwise", "outside",
    "overall", "particular", "particularly", "per", "perhaps", "placed",
    "please", "plus", "possible", "presumably", "probably", "provides",
    "quite", "rather", "rd", "really", "reasonably", "regarding",
    "regardless", "regards", "relatively", "respectively", "right",
    "said", "saw", "say", "saying", "says", "second", "secondly", "see",
    "seeing", "seem", "seemed", "seeming", "seems", "seen", "self",
    "selves", "sensible", "sent", "serious", "seriously", "seven",
    "several", "since", "six", "somebody", "someday", "somehow",
    "someone", "something", "sometime", "sometimes", "somewhat",
    "somewhere", "soon", "specified", "specify", "specifying",
    "sub", "sup", "sure", "take", "taken", "tell", "tends", "th",
    "thank", "thanks", "thanx", "thereafter", "thereby", "therefore",
    "therein", "theres", "thereupon", "think", "third", "thorough",
    "thoroughly", "though", "three", "throughout", "thru", "thus",
    "together", "toward", "towards", "tried", "tries", "truly", "try",
    "trying", "twice", "two", "un", "unfortunately", "unless",
    "unlikely", "unto", "use", "used", "useful", "uses", "using",
    "usually", "value", "various", "want", "wants", "way", "welcome",
    "well", "went", "whatever", "whenever", "whereafter", "whereas",
    "whereby", "wherein", "whereupon", "wherever", "whether", "whither",
    "whoever", "whole", "whose", "widely", "willing", "wish",
    "within", "without", "wonder", "yes", "zero",
}

# --- Number Words Map (headline number extraction) ---
NUMBER_WORD_MAP = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "twenty-one": 21, "twenty-two": 22, "twenty-three": 23,
    "twenty-four": 24, "twenty-five": 25, "thirty": 30, "forty": 40,
    "fifty": 50, "hundred": 100,
}

# --- Curiosity Gap / Open Loop Markers (HP3) ---
OPEN_LOOP_MARKERS = [
    r"\bbut\b", r"\byet\b", r"\bhowever\b",
    r"\bhere'?s why\b", r"\bhere'?s how\b", r"\bhere'?s what\b",
    r"\bthe truth about\b", r"\bthe real reason\b",
    r"\bwhat most\b", r"\bwhat nobody\b", r"\bwhat they\b",
    r"\bthis is why\b", r"\bthis is how\b",
]
OPEN_LOOP_STRINGS = ["\u2014", "—", "--", "..."]

# --- Resolution Language (HP3 body check) ---
RESOLUTION_MARKERS = [
    r"\bthe answer\b", r"\bhere'?s what\b", r"\bhere'?s how\b",
    r"\bhere'?s why\b", r"\bthe reason is\b", r"\bthe reason\b",
    r"\bwhich is why\b", r"\bthat'?s why\b", r"\bthat'?s because\b",
    r"\bthis is why\b", r"\bthis is how\b", r"\bthis is what\b",
    r"\bwhat this means\b", r"\bwhat you need\b", r"\bwhat to do\b",
    r"\binstead\b", r"\bthe fix\b", r"\bthe solution\b",
    r"\bthe difference\b", r"\bthe key\b",
]

# --- Specificity Markers (HP4) ---
SPECIFICITY_HEADLINE_WORDS = {
    "exactly", "specific", "specifically", "precise", "precisely",
}
TIMEFRAME_PATTERN = r"\b\d+\s*(?:hour|hours|day|days|week|weeks|minute|minutes|second|seconds|month|months|year|years)\b"

# --- Identity Markers (HP5) ---
IDENTITY_WORDS = {
    "you", "your", "you're", "yourself",
    "parents", "parent", "moms", "mom", "mothers", "mother",
    "dads", "dad", "fathers", "father", "families", "family",
    "women", "woman", "men", "man", "kids", "children", "child",
    "beginners", "beginner", "experts", "expert",
    "herbalists", "herbalist", "readers", "reader",
    "caregivers", "caregiver", "homeowners", "homeowner",
    "teachers", "teacher", "nurses", "nurse",
    "professionals", "professional",
}

# --- Negative Framing Words (BH4) ---
NEGATIVE_FRAME_WORDS = {
    "mistakes", "mistake", "wrong", "fail", "fails", "failing", "failure",
    "never", "don't", "doesn't", "won't", "can't", "shouldn't", "stop",
    "avoid", "problem", "problems", "risk", "risks", "danger", "dangerous",
    "miss", "missing", "skip", "skips", "skipping", "leave", "leaving",
    "lose", "lost", "losing", "broken", "worst", "bad", "poor", "lack",
    "lacking", "ignore", "ignoring", "neglect", "neglecting", "ruin",
    "ruining", "destroy", "destroying", "harm", "harmful", "hurt",
    "warning", "beware", "trap", "traps", "pitfall", "pitfalls",
    "lie", "lies", "myth", "myths", "scam", "fraud",
}

# --- Positive Framing Words (BH4) ---
POSITIVE_FRAME_WORDS = {
    "discover", "discovers", "discovering", "unlock", "unlocks", "unlocking",
    "achieve", "achieves", "achieving", "build", "builds", "building",
    "create", "creates", "creating", "improve", "improves", "improving",
    "grow", "grows", "growing", "gain", "gains", "boost", "boosts",
    "win", "wins", "winning", "master", "mastering", "transform",
    "transforming", "upgrade", "upgrading", "empower", "empowering",
    "thrive", "thriving", "succeed", "succeeding", "success",
    "proven", "best", "better", "great", "powerful", "effective",
    "simple", "easy", "fast", "smart", "ultimate", "essential",
    "perfect", "ideal", "amazing", "incredible",
}


# ============================================================
# SECTION 2: UTILITY FUNCTIONS
# ============================================================

def get_words(text):
    """Get list of lowercase words from text."""
    return [w.lower() for w in re.findall(r"[a-zA-Z'-]+", text)]


def get_content_words(text):
    """Extract content words (nouns, verbs, adjectives) by removing stopwords."""
    words = get_words(text)
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def word_in_text(word, text_lower):
    """Check if a word appears in text using word boundaries."""
    pattern = r'\b' + re.escape(word.lower()) + r'\b'
    return bool(re.search(pattern, text_lower))


def simple_stem(word):
    """
    Simple suffix stripping for English words.
    Strips: -ing, -ed, -s, -ly, -tion, -ment, -ness, -ful, -less, -ity, -er, -est, -ous, -ive, -able, -ible
    Returns the stem (lowercase).
    """
    word = word.lower().strip()
    if len(word) <= 4:
        return word

    # Order matters: try longer suffixes first
    suffixes = [
        "ation", "ition", "tion", "sion",
        "ment", "ness", "less", "ible", "able",
        "ling", "ting", "ious", "eous", "ous",
        "ful", "ity", "ive", "ing", "est",
        "ily", "lly",
        "ly", "ed", "er", "es",
        "s",
    ]

    for suffix in suffixes:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]

    return word


def stems_match(word1, word2):
    """Check if two words share a root via simple stemming or 4+ char prefix."""
    w1 = word1.lower()
    w2 = word2.lower()

    # Exact match
    if w1 == w2:
        return True

    # Stem match
    if simple_stem(w1) == simple_stem(w2):
        return True

    # Shared 4+ character prefix
    min_len = min(len(w1), len(w2))
    if min_len >= 4:
        prefix_len = 0
        for i in range(min_len):
            if w1[i] == w2[i]:
                prefix_len += 1
            else:
                break
        if prefix_len >= 4:
            return True

    return False


def extract_headline_number(headline):
    """
    Extract the primary number from a headline.
    Returns (number: int, label: str) or (None, None) if no number found.
    The label is the word following the number (e.g., "reasons", "tips").
    """
    headline_lower = headline.lower()

    # Check digit-based numbers first: "7 Reasons", "10 Tips"
    m = re.search(r'\b(\d+)\s+([a-zA-Z]+)', headline)
    if m:
        num = int(m.group(1))
        label = m.group(2).lower()
        return num, label

    # Check word-based numbers: "Seven Reasons"
    for word, val in sorted(NUMBER_WORD_MAP.items(), key=lambda x: -len(x[0])):
        pattern = r'\b' + re.escape(word) + r'\s+([a-zA-Z]+)'
        m = re.search(pattern, headline_lower)
        if m:
            label = m.group(1).lower()
            return val, label

    return None, None


def count_specific_elements(text):
    """
    Count specific elements in text: numbers, percentages, named items.
    Returns the count.
    """
    count = 0
    # Numbers (digits)
    count += len(re.findall(r'\b\d+(?:\.\d+)?(?:%|\b)', text))
    # Percentages written as words
    count += len(re.findall(r'\b\d+\s*percent\b', text.lower()))
    # Timeframes
    count += len(re.findall(TIMEFRAME_PATTERN, text.lower()))
    # Deduplicate: timeframes also contain numbers, so subtract overlap
    timeframe_nums = re.findall(r'(\d+)\s*(?:hour|day|week|minute|second|month|year)', text.lower())
    count -= len(timeframe_nums)
    return max(0, count)


def has_specificity_promise(headline):
    """Check if headline promises specificity (number, 'exactly', timeframe, etc.)."""
    headline_lower = headline.lower()

    # Contains a number
    if re.search(r'\b\d+\b', headline):
        return True

    # Contains specificity words
    for w in SPECIFICITY_HEADLINE_WORDS:
        if word_in_text(w, headline_lower):
            return True

    # Contains a timeframe
    if re.search(TIMEFRAME_PATTERN, headline_lower):
        return True

    return False


# ============================================================
# SECTION 3: DATA EXTRACTION FROM JSON
# ============================================================

def load_listicle_json(filepath):
    """
    Load a listicle JSON file and extract structured data.
    Returns a dict with:
      - headline: str
      - subtitle: str
      - reasons: list of {title: str, body: str, number: int}
      - slides: list of {title: str, text: str} (review slides)
      - pitch_title: str
      - pitch_bullets: list of str
      - cta_label: str
      - full_body_text: str (all body text concatenated)
      - section_titles: list of str (reason/slide titles)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {
        "headline": "",
        "subtitle": "",
        "reasons": [],
        "slides": [],
        "pitch_title": "",
        "pitch_bullets": [],
        "cta_label": "",
        "floating_cta_label": "",
        "full_body_text": "",
        "section_titles": [],
    }

    page = data.get("page", {})

    # Hero section
    hero = page.get("hero", {})
    result["headline"] = hero.get("title", "")
    result["subtitle"] = hero.get("subtitle", hero.get("description", ""))

    # Reasons
    reasons = page.get("reasons", [])
    for r in reasons:
        reason_body = r.get("body", "")
        # Handle body_paragraphs format (list of strings)
        if not reason_body and "body_paragraphs" in r:
            reason_body = " ".join(r.get("body_paragraphs", []))
        result["reasons"].append({
            "title": r.get("title", ""),
            "body": reason_body,
            "number": r.get("number", 0),
        })
        result["section_titles"].append(r.get("title", ""))

    # Review slides
    reviews = page.get("reviews", {})
    slides = reviews.get("slides", [])
    for s in slides:
        result["slides"].append({
            "title": s.get("title", s.get("author", "")),
            "text": s.get("text", ""),
        })

    # Pitch section
    pitch = page.get("pitch", {})
    result["pitch_title"] = pitch.get("title", "")
    result["pitch_bullets"] = pitch.get("bullets", [])

    # CTA
    cta = pitch.get("cta", {})
    result["cta_label"] = cta.get("label", "")

    # Floating CTA
    floating = page.get("floatingCta", {})
    result["floating_cta_label"] = floating.get("label", "")

    # Build full body text
    body_parts = []
    if result["subtitle"]:
        body_parts.append(result["subtitle"])
    for r in result["reasons"]:
        if r["title"]:
            body_parts.append(r["title"])
        if r["body"]:
            body_parts.append(r["body"])
    for bullet in result["pitch_bullets"]:
        body_parts.append(bullet)
    if result["pitch_title"]:
        body_parts.append(result["pitch_title"])
    if result["cta_label"]:
        body_parts.append(result["cta_label"])
    if result["floating_cta_label"]:
        body_parts.append(result["floating_cta_label"])

    result["full_body_text"] = "\n".join(body_parts)

    return result


# ============================================================
# SECTION 4: INDIVIDUAL TEST FUNCTIONS
# Each returns (passed: bool, detail: str)
# ============================================================

# --- DIRECTION 1: HEADLINE -> BODY (Promise Payment) ---

def test_hp1(headline, listicle_data):
    """
    HP1: Number Promise Payment (2 pts).
    If headline contains a number (e.g., "7 Reasons"), body must contain
    exactly that many items of that type.
    """
    num, label = extract_headline_number(headline)

    if num is None:
        return True, "No number promise in headline (N/A -- auto-pass)"

    # Determine what to count in the body
    item_count = 0
    item_type = "items"

    # Map label to actual body structure
    reasons = listicle_data.get("reasons", [])
    slides = listicle_data.get("slides", [])

    # Common labels for listicle sections
    reason_labels = {
        "reasons", "reason", "tips", "tip", "ways", "way", "things", "thing",
        "signs", "sign", "steps", "step", "facts", "fact", "mistakes",
        "mistake", "secrets", "secret", "lessons", "lesson", "rules", "rule",
        "habits", "habit", "myths", "myth", "truths", "truth", "lies", "lie",
        "questions", "question", "problems", "problem", "principles",
        "principle", "strategies", "strategy", "ideas", "idea", "hacks",
        "hack", "benefits", "benefit",
    }

    slide_labels = {
        "slides", "slide", "reviews", "review", "testimonials", "testimonial",
        "examples", "example", "stories", "story", "cases", "case",
    }

    if label in reason_labels or not label:
        item_count = len(reasons)
        item_type = label if label else "reasons"
    elif label in slide_labels:
        item_count = len(slides)
        item_type = label if label else "slides"
    else:
        # Default: check reasons first, then slides
        item_count = len(reasons) if reasons else len(slides)
        item_type = label

    if item_count == num:
        return True, f"Headline promises {num}; body contains {item_count} {item_type}"
    else:
        return False, f"Headline promises {num}; body contains {item_count} {item_type} (MISMATCH)"


def test_hp2(headline, full_body_text):
    """
    HP2: Topic Word Continuity (2 pts).
    At least 80% of headline content words must appear in the body text.
    """
    content_words = get_content_words(headline)

    if not content_words:
        return True, "No content words extracted from headline (N/A -- auto-pass)"

    body_lower = full_body_text.lower()
    found = []
    missing = []

    for w in content_words:
        if word_in_text(w, body_lower):
            found.append(w)
        else:
            missing.append(w)

    total = len(content_words)
    found_count = len(found)
    pct = (found_count / total * 100) if total > 0 else 0

    passed = pct >= 80.0

    detail = f"{found_count}/{total} headline content words found in body ({pct:.0f}%)"
    if missing:
        detail += f"\n           Missing: {', '.join(missing)}"

    return passed, detail


def test_hp3(headline, full_body_text):
    """
    HP3: Curiosity Gap Closure (1 pt).
    If headline contains an open loop marker, the body must contain
    resolution language.
    """
    headline_lower = headline.lower()

    # Check for open loop markers in headline
    has_open_loop = False
    found_marker = None

    for pattern in OPEN_LOOP_MARKERS:
        m = re.search(pattern, headline_lower)
        if m:
            has_open_loop = True
            found_marker = m.group(0)
            break

    if not has_open_loop:
        for s in OPEN_LOOP_STRINGS:
            if s in headline:
                has_open_loop = True
                found_marker = s
                break

    if not has_open_loop:
        return True, "No open loop in headline (N/A -- auto-pass)"

    # Check for resolution markers in body
    body_lower = full_body_text.lower()
    resolution_found = []

    for pattern in RESOLUTION_MARKERS:
        m = re.search(pattern, body_lower)
        if m:
            resolution_found.append(m.group(0))

    if resolution_found:
        return True, (f"Open loop \"{found_marker}\" resolved; "
                      f"body contains: {', '.join(resolution_found[:3])}")
    else:
        return False, (f"Open loop \"{found_marker}\" in headline but "
                       f"no resolution language found in body")


def test_hp4(headline, full_body_text):
    """
    HP4: Specificity Payoff (1 pt).
    If headline promises specificity, the body must contain at least
    as many specific elements as the headline promises.
    """
    if not has_specificity_promise(headline):
        return True, "No specificity promise in headline (N/A -- auto-pass)"

    headline_specifics = count_specific_elements(headline)
    body_specifics = count_specific_elements(full_body_text)

    # The body should have MORE specifics than the headline
    # (the headline sets expectations, the body delivers)
    passed = body_specifics >= headline_specifics

    if passed:
        return True, (f"Headline has {headline_specifics} specific elements; "
                      f"body has {body_specifics} (payoff delivered)")
    else:
        return False, (f"Headline has {headline_specifics} specific elements; "
                       f"body has only {body_specifics} (underpayment)")


def test_hp5(headline, full_body_text):
    """
    HP5: Identity Echo (1 pt).
    If headline contains identity markers, the body must use the same
    identity language within the first 20% of body text.
    """
    headline_lower = headline.lower()

    # Find identity words in headline
    headline_identity = []
    for w in IDENTITY_WORDS:
        if word_in_text(w, headline_lower):
            headline_identity.append(w)

    if not headline_identity:
        return True, "No identity markers in headline (N/A -- auto-pass)"

    # Get first 20% of body text
    body_words = full_body_text.split()
    cutoff = max(1, int(len(body_words) * 0.20))
    first_20_pct = " ".join(body_words[:cutoff]).lower()

    # Check if identity words appear in first 20%
    echoed = []
    missing = []
    for w in headline_identity:
        if word_in_text(w, first_20_pct):
            echoed.append(w)
        else:
            missing.append(w)

    # Pass if at least one identity word is echoed
    passed = len(echoed) > 0

    if passed:
        return True, (f"Identity markers echoed in first 20% of body: "
                      f"{', '.join(echoed)}")
    else:
        return False, (f"Identity markers \"{', '.join(headline_identity)}\" "
                       f"not found in first 20% of body text")


# --- DIRECTION 2: BODY -> HEADLINE (Setup Verification) ---

def test_bh1(headline, section_titles):
    """
    BH1: Theme Coverage (2 pts).
    At least 60% of section topic words must have a semantic connection
    to the headline (exact match, stem match, or shared 4+ char prefix).
    """
    if not section_titles:
        return True, "No section titles found (N/A -- auto-pass)"

    headline_content = get_content_words(headline)

    if not headline_content:
        return True, "No content words in headline (N/A -- auto-pass)"

    connected = 0
    connected_titles = []
    disconnected_titles = []

    for title in section_titles:
        title_words = get_content_words(title)
        if not title_words:
            connected += 1  # Empty titles don't penalize
            continue

        # Check if any title content word connects to any headline word
        has_connection = False
        for tw in title_words:
            for hw in headline_content:
                if stems_match(tw, hw):
                    has_connection = True
                    break
            if has_connection:
                break

        if has_connection:
            connected += 1
            connected_titles.append(title[:50])
        else:
            disconnected_titles.append(title[:50])

    total = len(section_titles)
    pct = (connected / total * 100) if total > 0 else 0
    passed = pct >= 60.0

    detail = f"{connected}/{total} section topics connected to headline ({pct:.0f}%)"
    if disconnected_titles:
        detail += f"\n           Disconnected: \"{disconnected_titles[0]}\"..."

    return passed, detail


def test_bh2(headline, listicle_data):
    """
    BH2: Strongest Section in Headline (1 pt).
    The longest body section (by word count) should have at least one
    content word from its title appearing in the headline.
    """
    reasons = listicle_data.get("reasons", [])

    if not reasons:
        return True, "No body sections found (N/A -- auto-pass)"

    # Find the longest section by word count
    longest = None
    max_words = 0

    for r in reasons:
        body_text = r.get("body", "")
        wc = len(body_text.split())
        if wc > max_words:
            max_words = wc
            longest = r

    if longest is None or not longest.get("title"):
        return True, "No section titles found (N/A -- auto-pass)"

    # Check if any content word from longest section's title is in headline
    title_words = get_content_words(longest["title"])
    headline_lower = headline.lower()
    headline_content = get_content_words(headline)

    found_connection = False
    connecting_word = None

    for tw in title_words:
        # Direct match
        if word_in_text(tw, headline_lower):
            found_connection = True
            connecting_word = tw
            break
        # Stem match
        for hw in headline_content:
            if stems_match(tw, hw):
                found_connection = True
                connecting_word = f"{tw} ~ {hw}"
                break
        if found_connection:
            break

    title_preview = longest["title"][:60]

    if found_connection:
        return True, (f"Longest section \"{title_preview}\" "
                      f"connects via \"{connecting_word}\" ({max_words} words)")
    else:
        return False, (f"Longest section \"{title_preview}\" "
                       f"has no headline connection ({max_words} words)")


def test_bh3(headline, listicle_data):
    """
    BH3: CTA Alignment (1 pt).
    If the body contains a CTA, the CTA's language should echo the
    headline's implicit promise (share at least 1 content word).
    """
    cta_label = listicle_data.get("cta_label", "")
    floating_cta = listicle_data.get("floating_cta_label", "")
    pitch_title = listicle_data.get("pitch_title", "")

    # Combine all CTA-like text
    cta_text = " ".join(filter(None, [cta_label, floating_cta, pitch_title]))

    if not cta_text.strip():
        return True, "No CTA found in body (N/A -- auto-pass)"

    cta_words = get_content_words(cta_text)
    headline_words = get_content_words(headline)

    if not cta_words or not headline_words:
        return True, "No content words to compare (N/A -- auto-pass)"

    # Check for shared content words (exact or stem match)
    shared = []
    for cw in cta_words:
        for hw in headline_words:
            if stems_match(cw, hw):
                shared.append(f"{cw} ~ {hw}")
                break

    if shared:
        return True, (f"CTA echoes headline: {', '.join(shared[:3])}")
    else:
        return False, (f"CTA \"{cta_text[:50]}\" shares no content words "
                       f"with headline")


def test_bh4(headline, full_body_text):
    """
    BH4: Belief Consistency (1 pt).
    If headline uses negative framing, body's opening (first 15%) should
    use the same valence. If positive framing, same requirement.
    Mismatch = jarring transition.
    """
    headline_lower = headline.lower()

    # Count negative and positive words in headline
    neg_count = 0
    pos_count = 0

    for w in NEGATIVE_FRAME_WORDS:
        if word_in_text(w, headline_lower):
            neg_count += 1

    for w in POSITIVE_FRAME_WORDS:
        if word_in_text(w, headline_lower):
            pos_count += 1

    # Determine headline framing
    if neg_count == 0 and pos_count == 0:
        return True, "No strong framing detected in headline (N/A -- auto-pass)"

    headline_framing = "negative" if neg_count > pos_count else "positive"
    if neg_count == pos_count:
        return True, "Mixed framing in headline (N/A -- auto-pass)"

    # Get first 15% of body text
    body_words = full_body_text.split()
    cutoff = max(1, int(len(body_words) * 0.15))
    opening = " ".join(body_words[:cutoff]).lower()

    # Count framing in opening
    body_neg = 0
    body_pos = 0

    for w in NEGATIVE_FRAME_WORDS:
        if word_in_text(w, opening):
            body_neg += 1

    for w in POSITIVE_FRAME_WORDS:
        if word_in_text(w, opening):
            body_pos += 1

    if body_neg == 0 and body_pos == 0:
        # No strong framing in body opening -- mild pass
        return True, (f"Headline is {headline_framing}; body opening is neutral "
                      f"(acceptable)")

    body_framing = "negative" if body_neg > body_pos else "positive"
    if body_neg == body_pos:
        body_framing = "mixed"

    passed = (headline_framing == body_framing) or body_framing == "mixed"

    if passed:
        return True, (f"Headline framing ({headline_framing}) matches body "
                      f"opening ({body_framing})")
    else:
        return False, (f"Headline framing ({headline_framing}) MISMATCHES body "
                       f"opening ({body_framing}) -- jarring transition")


# ============================================================
# SECTION 5: SCORING ENGINE
# ============================================================

def score_congruency(headline, listicle_data):
    """
    Score headline-body congruency across all 9 tests.
    Returns a dict with all results and composite score.
    """
    headline = headline.strip()
    full_body = listicle_data.get("full_body_text", "")
    section_titles = listicle_data.get("section_titles", [])

    # Direction 1: Headline -> Body (Promise Payment)
    hp_tests = [
        ("HP1", "Number promise payment", 2,
         test_hp1(headline, listicle_data)),
        ("HP2", "Topic word continuity", 2,
         test_hp2(headline, full_body)),
        ("HP3", "Curiosity gap closure", 1,
         test_hp3(headline, full_body)),
        ("HP4", "Specificity payoff", 1,
         test_hp4(headline, full_body)),
        ("HP5", "Identity echo", 1,
         test_hp5(headline, full_body)),
    ]

    # Direction 2: Body -> Headline (Setup Verification)
    bh_tests = [
        ("BH1", "Theme coverage", 2,
         test_bh1(headline, section_titles)),
        ("BH2", "Strongest section in headline", 1,
         test_bh2(headline, listicle_data)),
        ("BH3", "CTA alignment", 1,
         test_bh3(headline, listicle_data)),
        ("BH4", "Belief consistency", 1,
         test_bh4(headline, full_body)),
    ]

    return {
        "headline": headline,
        "hp": hp_tests,
        "bh": bh_tests,
    }


def compute_composite(result):
    """Compute composite score from result dict."""
    scores = {}
    for dim_key, dim_label in [("hp", "Headline -> Body"),
                                ("bh", "Body -> Headline")]:
        tests = result[dim_key]
        earned = sum(weight for _, _, weight, (passed, _) in tests if passed)
        maximum = sum(weight for _, _, weight, _ in tests)
        scores[dim_key] = (earned, maximum, dim_label)

    total = sum(s[0] for s in scores.values())
    maximum = sum(s[1] for s in scores.values())
    pct = (total / maximum * 100) if maximum > 0 else 0

    # Pass/Fail threshold: 75% (9/12)
    passed = pct >= 75.0

    # Hard gate: HP1 must pass if applicable
    hp1_passed = True
    hp1_applicable = True
    for test_id, _, _, (p, detail) in result["hp"]:
        if test_id == "HP1":
            hp1_passed = p
            hp1_applicable = "N/A" not in detail
            break

    hard_gate_pass = hp1_passed

    return {
        "total": total,
        "max": maximum,
        "pct": pct,
        "passed": passed and hard_gate_pass,
        "threshold_pass": passed,
        "hard_gate_pass": hard_gate_pass,
        "hp1_applicable": hp1_applicable,
        "hp1_passed": hp1_passed,
        "dimensions": scores,
    }


# ============================================================
# SECTION 6: OUTPUT FORMATTING
# ============================================================

def print_congruency_report(result, source_path=None):
    """Print formatted congruency report for a headline-body pair."""
    composite = compute_composite(result)

    print(f"\n  {'='*71}")
    print(f"    HEADLINE <-> BODY CONGRUENCY: \"{result['headline']}\"")
    if source_path:
        print(f"    Source: {source_path}")
    print(f"  {'='*71}")

    # Direction 1: HP tests
    hp_earned, hp_max, _ = composite["dimensions"]["hp"]
    print(f"\n    HEADLINE -> BODY (Promise Payment)")
    print(f"    {'-'*67}")

    for test_id, test_name, weight, (passed, detail) in result["hp"]:
        mark = "PASS" if passed else "FAIL"
        pts_label = f"({weight} pts)" if weight > 1 else f"({weight} pt)"
        print(f"    [{mark}] {test_id}: {test_name} {pts_label}")
        # Handle multi-line details
        for i, line in enumerate(detail.split("\n")):
            if i == 0:
                print(f"           {line}")
            else:
                print(f"           {line.strip()}")

    print(f"    Score: {hp_earned}/{hp_max}")

    # Direction 2: BH tests
    bh_earned, bh_max, _ = composite["dimensions"]["bh"]
    print(f"\n    BODY -> HEADLINE (Setup Verification)")
    print(f"    {'-'*67}")

    for test_id, test_name, weight, (passed, detail) in result["bh"]:
        mark = "PASS" if passed else "FAIL"
        pts_label = f"({weight} pts)" if weight > 1 else f"({weight} pt)"
        print(f"    [{mark}] {test_id}: {test_name} {pts_label}")
        for i, line in enumerate(detail.split("\n")):
            if i == 0:
                print(f"           {line}")
            else:
                print(f"           {line.strip()}")

    print(f"    Score: {bh_earned}/{bh_max}")

    # Composite
    verdict = "PASS" if composite["passed"] else "FAIL"
    threshold_verdict = "PASS" if composite["threshold_pass"] else "FAIL"
    hp1_mark = "PASS" if composite["hp1_passed"] else "FAIL"
    hp1_note = "" if composite["hp1_applicable"] else " (N/A)"

    print(f"\n    {'='*67}")
    print(f"    COMPOSITE: {composite['total']}/{composite['max']} "
          f"({composite['pct']:.1f}%) -- {verdict}")
    print()
    print(f"    Hard Gates: HP1 [{hp1_mark}]{hp1_note}")
    print(f"    Threshold:  {composite['total']}/{composite['max']} >= "
          f"9/12 (75%) [{threshold_verdict}]")
    print(f"    {'='*67}")

    return composite


# ============================================================
# SECTION 7: MARKDOWN PAGE-TYPE PARSERS
# ============================================================

def load_advertorial_md(filepath):
    """
    Parse an advertorial markdown file into structured data.
    Expects ## headers for section titles. Extracts sections, body text,
    and pre-pivot content for promise timing checks.

    Returns a dict compatible with the scoring engine:
      - headline: str (from first # header)
      - sections: list of {title: str, body: str, number: int}
      - full_body_text: str
      - section_titles: list of str
      - pre_pivot_text: str (sections before "Pivot" or "Solution")
      - cta_text: str (last section's text)
      - reasons: [] (empty, for backward compat)
      - slides: [] (empty)
      - pitch_title: ""
      - pitch_bullets: []
      - cta_label: str
      - floating_cta_label: ""
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    headline = ""
    sections = []
    current_title = None
    current_body_lines = []

    for line in lines:
        stripped = line.strip()

        # H1 = headline
        if stripped.startswith('# ') and not stripped.startswith('## '):
            headline = stripped[2:].strip()
            continue

        # H2 = section title
        if stripped.startswith('## '):
            # Save previous section
            if current_title is not None:
                body_text = '\n'.join(current_body_lines).strip()
                if body_text:  # Only add sections with actual body content
                    sections.append({
                        "title": current_title,
                        "body": body_text,
                        "number": len(sections) + 1,
                    })
                current_body_lines = []
            current_title = stripped[3:].strip()
            continue

        # Skip metadata lines (lines starting with * or | in tables, or ---)
        if stripped.startswith('---') or stripped.startswith('|') or stripped.startswith('*'):
            continue

        # Skip comment-style lines (italic metadata)
        if stripped.startswith('*Job:') or stripped.startswith('*Belief'):
            continue

        # Body content
        if current_title is not None and stripped:
            current_body_lines.append(stripped)

    # Save last section
    if current_title is not None:
        body_text = '\n'.join(current_body_lines).strip()
        if body_text:
            sections.append({
                "title": current_title,
                "body": body_text,
                "number": len(sections) + 1,
            })

    # Build full body text
    body_parts = []
    for s in sections:
        body_parts.append(s["title"])
        body_parts.append(s["body"])
    full_body = '\n'.join(body_parts)

    # Identify pre-pivot text (sections before "Pivot" or "Solution Category")
    pre_pivot_parts = []
    pivot_keywords = ["pivot", "solution category", "what you actually need",
                      "what you need", "system tease", "reference built"]
    for s in sections:
        title_lower = s["title"].lower()
        is_pivot_or_later = any(kw in title_lower for kw in pivot_keywords)
        if is_pivot_or_later:
            break
        pre_pivot_parts.append(s["body"])
    pre_pivot_text = '\n'.join(pre_pivot_parts)

    # Extract CTA text (last section)
    cta_text = sections[-1]["body"] if sections else ""
    cta_label = ""
    # Look for link-style CTA: [text →] or **[text]**
    cta_match = re.search(r'\[([^\]]+)\]', cta_text)
    if cta_match:
        cta_label = cta_match.group(1)

    section_titles = [s["title"] for s in sections]

    return {
        "headline": headline,
        "subtitle": "",
        "sections": sections,
        "reasons": sections,  # Alias for backward compat with BH tests
        "slides": [],
        "pitch_title": "",
        "pitch_bullets": [],
        "cta_label": cta_label,
        "floating_cta_label": "",
        "full_body_text": full_body,
        "section_titles": section_titles,
        "pre_pivot_text": pre_pivot_text,
    }


def load_sales_page_md(filepath):
    """
    Parse a sales page markdown file. Same structure as advertorial parser
    but with sales-page-specific pivot detection.
    """
    # Reuse advertorial parser — structure is the same (## headers)
    data = load_advertorial_md(filepath)

    # Override pre-pivot detection for sales pages
    # Sales page pivot is at "Mechanism" or "Honest System" (Section 3)
    pre_pivot_parts = []
    mechanism_keywords = ["mechanism", "honest system", "how it works",
                          "what makes", "the system"]
    for s in data["sections"]:
        title_lower = s["title"].lower()
        is_mechanism_or_later = any(kw in title_lower for kw in mechanism_keywords)
        if is_mechanism_or_later:
            break
        pre_pivot_parts.append(s["body"])
    data["pre_pivot_text"] = '\n'.join(pre_pivot_parts)

    return data


# ============================================================
# SECTION 8: PROMISE CONTRACT TESTS (PC1-PC4)
# ============================================================

# --- Domain vocabulary for promise content detection (PC2) ---
PHYSIOLOGICAL_WORDS = {
    "immune", "inflammation", "inflammatory", "liver", "kidney", "enzyme",
    "cytokine", "cortisol", "hormone", "hormonal", "receptor", "metabolize",
    "metabolism", "bioavailability", "absorption", "toxicity", "toxic",
    "overdose", "overstimulate", "overstimulation", "contraindicated",
    "contraindication", "platelet", "blood-thinner", "blood-thinning",
    "serotonin", "dopamine", "gaba", "sedative", "stimulant",
    "hypotension", "hypertension", "tachycardia", "nausea", "vomiting",
    "headache", "drowsiness", "insomnia", "diarrhea", "cramping",
    "rash", "allergic", "anaphylaxis", "photosensitivity",
    "therapeutic", "subtherapeutic", "supratherapeutic",
    "pharmacokinetic", "pharmacognosy", "bioactive", "compound",
    "alkaloid", "flavonoid", "terpene", "glycoside",
}

DOSING_CONSEQUENCE_WORDS = {
    "overstimulate", "overstimulation", "underdose", "overdose",
    "ineffective", "subtherapeutic", "accumulate", "accumulation",
    "interact", "interaction", "potentiate", "inhibit", "suppress",
    "deplete", "depletion", "sensitize", "desensitize",
    "tolerance", "dependency", "withdrawal", "rebound",
    "side-effect", "adverse", "reaction", "complication",
}

SAFETY_WORDS = {
    "safety", "safe", "unsafe", "danger", "dangerous", "risk", "risky",
    "warning", "caution", "contraindicated", "interaction", "flag",
    "harm", "harmful", "injury", "damage", "poison", "poisoning",
    "emergency", "hospitalize", "hospitalization",
}


def load_promise_contract(filepath):
    """
    Load a Promise Contract from a JSON file.
    Expected format:
    {
        "loop_question": "What happens?",
        "specific_promise": "...",
        "delivery_test": "The body must contain...",
        "minimum_delivery": "Begin in Section 1..."
    }
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {
        "loop_question": data.get("loop_question", ""),
        "specific_promise": data.get("specific_promise", ""),
        "delivery_test": data.get("delivery_test", ""),
        "minimum_delivery": data.get("minimum_delivery", ""),
    }


def extract_delivery_keywords(delivery_test):
    """
    Extract key content words from a DELIVERY_TEST string for body matching.
    Filters out common instruction words to focus on the substance.
    """
    # Remove the standard prefix
    text = delivery_test.lower()
    for prefix in ["the body must contain ", "the body must include ",
                   "the body must describe ", "the body must name "]:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    # Get content words
    words = get_content_words(text)

    # Additional filter: remove meta-instruction words
    meta_words = {"least", "concrete", "specific", "example", "must",
                  "contain", "include", "describe", "named", "actual",
                  "generic", "vague", "simply", "merely", "just"}
    return [w for w in words if w not in meta_words]


def test_pc1(contract):
    """
    PC1: Promise Contract Present (1 pt).
    Does the headline have an associated Promise Contract with all fields?
    """
    if not contract:
        return False, "No Promise Contract provided"

    missing = []
    for field in ["loop_question", "specific_promise", "delivery_test", "minimum_delivery"]:
        if not contract.get(field, "").strip():
            missing.append(field)

    if missing:
        return False, f"Promise Contract incomplete — missing: {', '.join(missing)}"

    # Check DELIVERY_TEST format
    dt = contract["delivery_test"].strip().lower()
    if not dt.startswith("the body must"):
        return False, (f"DELIVERY_TEST does not start with 'The body must...' — "
                       f"got: \"{contract['delivery_test'][:60]}\"")

    return True, "Promise Contract present with all 4 fields"


def test_pc2(contract, full_body_text):
    """
    PC2: Delivery Test Satisfied (3 pts) -- HARD GATE.
    Extract key content from the DELIVERY_TEST and check whether the body
    contains matching content. Uses both keyword matching and domain vocabulary.
    """
    if not contract or not contract.get("delivery_test"):
        return True, "No DELIVERY_TEST provided (N/A -- auto-pass)"

    delivery_test = contract["delivery_test"]
    body_lower = full_body_text.lower()

    # Extract keywords from the delivery test
    dt_keywords = extract_delivery_keywords(delivery_test)

    if not dt_keywords:
        return True, "No content keywords extracted from DELIVERY_TEST (N/A -- auto-pass)"

    # Check how many delivery test keywords appear in the body
    found_keywords = []
    missing_keywords = []

    for kw in dt_keywords:
        if word_in_text(kw, body_lower):
            found_keywords.append(kw)
        else:
            # For PC2, use exact word matching only (no stem/prefix matching).
            # The DELIVERY_TEST is author-controlled, so we don't need fuzzy matching.
            # Stem matching produces false positives (e.g. "consequence" ~ "consult"
            # via shared 4-char prefix) that dilute the hard gate.
            missing_keywords.append(kw)

    keyword_coverage = len(found_keywords) / len(dt_keywords) if dt_keywords else 0

    # Also check for domain vocabulary presence
    # (the DELIVERY_TEST might say "physiological consequence" but the body
    #  might use "immune overstimulation" — both are valid delivery)
    domain_hits = 0
    domain_words_found = []

    # Check all domain word lists
    for word_set_name, word_set in [("physiological", PHYSIOLOGICAL_WORDS),
                                     ("dosing_consequence", DOSING_CONSEQUENCE_WORDS),
                                     ("safety", SAFETY_WORDS)]:
        for w in word_set:
            if word_in_text(w, body_lower):
                domain_hits += 1
                if len(domain_words_found) < 5:
                    domain_words_found.append(w)

    # Pass criteria — both conditions must be met (AND gate):
    #   1. Keyword coverage >= 25%  (at least some DELIVERY_TEST terms are present)
    #   2. Domain vocabulary hits >= 5  (body uses domain-specific terms indicating
    #      substantive delivery, not just passing mentions)
    # Using AND prevents both failure modes:
    #   - High keyword coverage with no domain substance (body repeats words without content)
    #   - High domain hits with low keyword coverage (incidental medical terms in
    #     ecosystem indictment sections, not actual promise delivery)
    passed = keyword_coverage >= 0.25 and domain_hits >= 5

    detail_parts = []
    detail_parts.append(
        f"Keyword coverage: {len(found_keywords)}/{len(dt_keywords)} "
        f"({keyword_coverage:.0%})"
    )
    if found_keywords:
        detail_parts.append(f"Found: {', '.join(found_keywords[:5])}")
    if missing_keywords:
        detail_parts.append(f"Missing: {', '.join(missing_keywords[:5])}")
    detail_parts.append(f"Domain vocabulary hits: {domain_hits}")
    if domain_words_found:
        detail_parts.append(f"Domain words: {', '.join(domain_words_found)}")

    verdict = "DELIVERY SATISFIED" if passed else "DELIVERY NOT SATISFIED — trust violation"
    detail_parts.append(verdict)

    return passed, "; ".join(detail_parts)


def test_pc3(contract, page_data):
    """
    PC3: Promise Timing (2 pts).
    The promised content must appear in pre-pivot sections.
    """
    if not contract or not contract.get("delivery_test"):
        return True, "No DELIVERY_TEST provided (N/A -- auto-pass)"

    pre_pivot = page_data.get("pre_pivot_text", "")
    if not pre_pivot:
        return True, "No pre-pivot text extracted (N/A -- auto-pass)"

    pre_pivot_lower = pre_pivot.lower()
    dt_keywords = extract_delivery_keywords(contract["delivery_test"])

    if not dt_keywords:
        return True, "No keywords to check timing for (N/A -- auto-pass)"

    # Check if delivery keywords appear in pre-pivot text
    found_in_prepivot = []
    for kw in dt_keywords:
        if word_in_text(kw, pre_pivot_lower):
            found_in_prepivot.append(kw)
        else:
            body_words = get_words(pre_pivot)
            for bw in body_words:
                if stems_match(kw, bw):
                    found_in_prepivot.append(f"{kw}~{bw}")
                    break

    # Also check domain vocabulary in pre-pivot
    domain_in_prepivot = 0
    for word_set in [PHYSIOLOGICAL_WORDS, DOSING_CONSEQUENCE_WORDS, SAFETY_WORDS]:
        for w in word_set:
            if word_in_text(w, pre_pivot_lower):
                domain_in_prepivot += 1

    coverage = len(found_in_prepivot) / len(dt_keywords) if dt_keywords else 0
    passed = coverage >= 0.30 or domain_in_prepivot >= 2

    if passed:
        return True, (f"Promise content found in pre-pivot sections: "
                      f"{len(found_in_prepivot)}/{len(dt_keywords)} keywords; "
                      f"{domain_in_prepivot} domain terms")
    else:
        return False, (f"Promise content NOT in pre-pivot sections: "
                       f"{len(found_in_prepivot)}/{len(dt_keywords)} keywords; "
                       f"{domain_in_prepivot} domain terms. "
                       f"Promise is deferred past the structural pivot.")


def test_pc4(contract, full_body_text):
    """
    PC4: Promise Completeness (1 pt).
    The body must have substantial content matching the promise —
    not just a passing mention. At least 3 sentences containing
    promise-related content.
    """
    if not contract or not contract.get("delivery_test"):
        return True, "No DELIVERY_TEST provided (N/A -- auto-pass)"

    dt_keywords = extract_delivery_keywords(contract["delivery_test"])
    if not dt_keywords:
        return True, "No keywords to check completeness for (N/A -- auto-pass)"

    # Split body into sentences
    sentences = re.split(r'[.!?]+', full_body_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    # Count sentences that contain at least one delivery keyword or domain word
    all_signal_words = set(dt_keywords)
    all_signal_words.update(PHYSIOLOGICAL_WORDS)
    all_signal_words.update(DOSING_CONSEQUENCE_WORDS)

    matching_sentences = 0
    for sent in sentences:
        sent_lower = sent.lower()
        for w in all_signal_words:
            if word_in_text(w, sent_lower):
                matching_sentences += 1
                break

    passed = matching_sentences >= 3

    if passed:
        return True, (f"{matching_sentences} sentences contain promise-related content "
                      f"(threshold: 3)")
    else:
        return False, (f"Only {matching_sentences} sentences contain promise-related "
                       f"content (threshold: 3). Promise delivery is a passing mention, "
                       f"not substantive.")


# ============================================================
# SECTION 9: EXTENDED SCORING ENGINE
# ============================================================

def score_congruency_extended(headline, page_data, contract=None):
    """
    Score headline-body congruency across all tests including Promise Contract.
    Returns a dict with all results and composite score.
    """
    headline = headline.strip()
    full_body = page_data.get("full_body_text", "")
    section_titles = page_data.get("section_titles", [])

    # Direction 1: Headline -> Body (Promise Payment) — original tests
    hp_tests = [
        ("HP1", "Number promise payment", 2,
         test_hp1(headline, page_data)),
        ("HP2", "Topic word continuity", 2,
         test_hp2(headline, full_body)),
        ("HP3", "Curiosity gap closure", 1,
         test_hp3(headline, full_body)),
        ("HP4", "Specificity payoff", 1,
         test_hp4(headline, full_body)),
        ("HP5", "Identity echo", 1,
         test_hp5(headline, full_body)),
    ]

    # Direction 2: Body -> Headline (Setup Verification) — original tests
    bh_tests = [
        ("BH1", "Theme coverage", 2,
         test_bh1(headline, section_titles)),
        ("BH2", "Strongest section in headline", 1,
         test_bh2(headline, page_data)),
        ("BH3", "CTA alignment", 1,
         test_bh3(headline, page_data)),
        ("BH4", "Belief consistency", 1,
         test_bh4(headline, full_body)),
    ]

    # Direction 3: Promise Contract (Contract Enforcement)
    pc_tests = []
    if contract:
        pc_tests = [
            ("PC1", "Promise contract present", 1,
             test_pc1(contract)),
            ("PC2", "Delivery test satisfied", 3,
             test_pc2(contract, full_body)),
            ("PC3", "Promise timing", 2,
             test_pc3(contract, page_data)),
            ("PC4", "Promise completeness", 1,
             test_pc4(contract, full_body)),
        ]

    return {
        "headline": headline,
        "hp": hp_tests,
        "bh": bh_tests,
        "pc": pc_tests,
    }


def compute_composite_extended(result):
    """Compute composite score from extended result dict (with PC tests)."""
    dims = [("hp", "Headline -> Body"), ("bh", "Body -> Headline")]
    if result.get("pc"):
        dims.append(("pc", "Promise Contract"))

    scores = {}
    for dim_key, dim_label in dims:
        tests = result.get(dim_key, [])
        earned = sum(weight for _, _, weight, (passed, _) in tests if passed)
        maximum = sum(weight for _, _, weight, _ in tests)
        scores[dim_key] = (earned, maximum, dim_label)

    total = sum(s[0] for s in scores.values())
    maximum = sum(s[1] for s in scores.values())
    pct = (total / maximum * 100) if maximum > 0 else 0

    # Pass/Fail threshold: 75%
    passed = pct >= 75.0

    # Hard gates
    # HP1: number promise must match
    hp1_passed = True
    hp1_applicable = True
    for test_id, _, _, (p, detail) in result.get("hp", []):
        if test_id == "HP1":
            hp1_passed = p
            hp1_applicable = "N/A" not in detail
            break

    # PC2: delivery test satisfied (hard gate when contract present)
    pc2_passed = True
    pc2_applicable = False
    for test_id, _, _, (p, detail) in result.get("pc", []):
        if test_id == "PC2":
            pc2_passed = p
            pc2_applicable = "N/A" not in detail
            break

    hard_gate_pass = hp1_passed and pc2_passed

    return {
        "total": total,
        "max": maximum,
        "pct": pct,
        "passed": passed and hard_gate_pass,
        "threshold_pass": passed,
        "hard_gate_pass": hard_gate_pass,
        "hp1_applicable": hp1_applicable,
        "hp1_passed": hp1_passed,
        "pc2_applicable": pc2_applicable,
        "pc2_passed": pc2_passed,
        "dimensions": scores,
    }


def print_extended_report(result, source_path=None):
    """Print formatted congruency report including Promise Contract tests."""
    composite = compute_composite_extended(result)

    print(f"\n  {'='*71}")
    print(f"    HEADLINE <-> BODY CONGRUENCY: \"{result['headline']}\"")
    if source_path:
        print(f"    Source: {source_path}")
    print(f"  {'='*71}")

    # Direction 1: HP tests
    hp_earned, hp_max, _ = composite["dimensions"]["hp"]
    print(f"\n    HEADLINE -> BODY (Promise Payment)")
    print(f"    {'-'*67}")

    for test_id, test_name, weight, (passed, detail) in result["hp"]:
        mark = "PASS" if passed else "FAIL"
        pts_label = f"({weight} pts)" if weight > 1 else f"({weight} pt)"
        print(f"    [{mark}] {test_id}: {test_name} {pts_label}")
        for i, line in enumerate(detail.split("\n")):
            print(f"           {line.strip()}" if i > 0 else f"           {line}")

    print(f"    Score: {hp_earned}/{hp_max}")

    # Direction 2: BH tests
    bh_earned, bh_max, _ = composite["dimensions"]["bh"]
    print(f"\n    BODY -> HEADLINE (Setup Verification)")
    print(f"    {'-'*67}")

    for test_id, test_name, weight, (passed, detail) in result["bh"]:
        mark = "PASS" if passed else "FAIL"
        pts_label = f"({weight} pts)" if weight > 1 else f"({weight} pt)"
        print(f"    [{mark}] {test_id}: {test_name} {pts_label}")
        for i, line in enumerate(detail.split("\n")):
            print(f"           {line.strip()}" if i > 0 else f"           {line}")

    print(f"    Score: {bh_earned}/{bh_max}")

    # Direction 3: PC tests (if present)
    if result.get("pc"):
        pc_earned, pc_max, _ = composite["dimensions"]["pc"]
        print(f"\n    PROMISE CONTRACT (Contract Enforcement)")
        print(f"    {'-'*67}")

        for test_id, test_name, weight, (passed, detail) in result["pc"]:
            mark = "PASS" if passed else "FAIL"
            gate_label = " [HARD GATE]" if test_id == "PC2" else ""
            pts_label = f"({weight} pts)" if weight > 1 else f"({weight} pt)"
            print(f"    [{mark}] {test_id}: {test_name} {pts_label}{gate_label}")
            # Handle semicolon-delimited multi-part details
            for part in detail.split("; "):
                print(f"           {part}")

        print(f"    Score: {pc_earned}/{pc_max}")

    # Composite
    verdict = "PASS" if composite["passed"] else "FAIL"
    threshold_verdict = "PASS" if composite["threshold_pass"] else "FAIL"

    print(f"\n    {'='*67}")
    print(f"    COMPOSITE: {composite['total']}/{composite['max']} "
          f"({composite['pct']:.1f}%) -- {verdict}")
    print()

    # Hard gates
    hp1_mark = "PASS" if composite["hp1_passed"] else "FAIL"
    hp1_note = "" if composite["hp1_applicable"] else " (N/A)"
    print(f"    Hard Gates: HP1 [{hp1_mark}]{hp1_note}", end="")

    if composite["pc2_applicable"]:
        pc2_mark = "PASS" if composite["pc2_passed"] else "FAIL"
        print(f"  |  PC2 [{pc2_mark}]")
    else:
        print()

    print(f"    Threshold:  {composite['total']}/{composite['max']} >= "
          f"75% [{threshold_verdict}]")
    print(f"    {'='*67}")

    return composite


# ============================================================
# SECTION 10: CLI INTERFACE
# ============================================================

def build_listicle_data_from_body_text(body_text):
    """
    Build a minimal listicle_data dict from raw body text (for --body mode).
    Attempts to detect numbered sections and extract structure.
    """
    lines = body_text.strip().split("\n")

    # Try to detect numbered sections: "1. Title" or "Reason 1:" etc.
    reasons = []
    current_title = None
    current_body_lines = []
    section_pattern = re.compile(
        r'^(?:(?:reason|tip|step|way|sign|fact|mistake|secret|lesson|rule|habit|myth)\s+)?'
        r'#?(\d+)[.:)\s]+\s*(.+)',
        re.IGNORECASE
    )

    for line in lines:
        m = section_pattern.match(line.strip())
        if m:
            # Save previous section
            if current_title is not None:
                reasons.append({
                    "title": current_title,
                    "body": " ".join(current_body_lines),
                    "number": len(reasons) + 1,
                })
                current_body_lines = []
            current_title = m.group(2).strip()
        elif current_title is not None:
            if line.strip():
                current_body_lines.append(line.strip())
        # Lines before first section are ignored as intro

    # Save last section
    if current_title is not None:
        reasons.append({
            "title": current_title,
            "body": " ".join(current_body_lines),
            "number": len(reasons) + 1,
        })

    section_titles = [r["title"] for r in reasons]

    return {
        "headline": "",
        "subtitle": "",
        "reasons": reasons,
        "slides": [],
        "pitch_title": "",
        "pitch_bullets": [],
        "cta_label": "",
        "floating_cta_label": "",
        "full_body_text": body_text,
        "section_titles": section_titles,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Headline <-> Body Congruency Scorer (deterministic, zero LLM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Listicle (original mode)
  python3 headline_body_congruency.py /path/to/listicle.json
  python3 headline_body_congruency.py /path/to/listicle.json --headline "Custom headline"

  # Plain text body
  python3 headline_body_congruency.py --headline "Your headline" --body /path/to/body.txt

  # Advertorial with Promise Contract
  python3 headline_body_congruency.py --headline "Your headline" --body /path/to/body.md \\
      --page-type advertorial --promise-contract /path/to/contract.json

  # Sales page (no contract — runs HP + BH tests only)
  python3 headline_body_congruency.py --headline "Your headline" --body /path/to/page.md \\
      --page-type sales_page
        """,
    )

    parser.add_argument(
        "json_file", nargs="?", default=None,
        help="Path to a listicle JSON file (default page type)",
    )
    parser.add_argument(
        "--headline", type=str, default=None,
        help="Custom headline text (overrides JSON headline if both provided)",
    )
    parser.add_argument(
        "--body", type=str, default=None,
        help="Path to a body file (plain text, or markdown for advertorial/sales_page)",
    )
    parser.add_argument(
        "--page-type", type=str, default="listicle",
        choices=["listicle", "advertorial", "sales_page"],
        help="Page type for body parsing (default: listicle)",
    )
    parser.add_argument(
        "--promise-contract", type=str, default=None,
        help="Path to a Promise Contract JSON file (enables PC1-PC4 tests)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.json_file and not (args.headline and args.body):
        parser.error("Provide a JSON file, or both --headline and --body")

    if args.body and not args.headline:
        parser.error("--body requires --headline")

    if args.json_file and args.page_type != "listicle":
        parser.error("JSON file input only supports --page-type listicle")

    if args.promise_contract and not os.path.isfile(os.path.abspath(args.promise_contract)):
        parser.error(f"Promise contract file not found: {args.promise_contract}")

    # Load Promise Contract (if provided)
    contract = None
    if args.promise_contract:
        contract = load_promise_contract(os.path.abspath(args.promise_contract))

    # Load page data
    if args.json_file:
        # Original listicle JSON mode
        filepath = os.path.abspath(args.json_file)
        if not os.path.isfile(filepath):
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            sys.exit(1)

        page_data = load_listicle_json(filepath)
        headline = args.headline if args.headline else page_data["headline"]
        source = filepath

    elif args.headline and args.body:
        body_path = os.path.abspath(args.body)
        if not os.path.isfile(body_path):
            print(f"Error: File not found: {body_path}", file=sys.stderr)
            sys.exit(1)

        if args.page_type == "advertorial":
            page_data = load_advertorial_md(body_path)
        elif args.page_type == "sales_page":
            page_data = load_sales_page_md(body_path)
        else:
            # listicle from plain text
            with open(body_path, 'r', encoding='utf-8') as f:
                body_text = f.read()
            page_data = build_listicle_data_from_body_text(body_text)

        headline = args.headline
        source = body_path

    else:
        parser.error("Invalid argument combination")
        sys.exit(1)

    if not headline:
        print("Error: No headline found in JSON or provided via --headline",
              file=sys.stderr)
        sys.exit(1)

    # Score and report
    if contract or args.page_type != "listicle":
        # Extended mode: use extended scorer (supports all page types + PC tests)
        result = score_congruency_extended(headline, page_data, contract=contract)
        composite = print_extended_report(result, source_path=source)
    else:
        # Original mode: backward-compatible listicle scoring
        result = score_congruency(headline, page_data)
        composite = print_congruency_report(result, source_path=source)

    # Exit code: 0 if PASS, 1 if FAIL
    sys.exit(0 if composite["passed"] else 1)


if __name__ == "__main__":
    main()
