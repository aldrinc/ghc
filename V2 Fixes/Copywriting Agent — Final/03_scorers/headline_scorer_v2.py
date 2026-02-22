#!/usr/bin/env python3
"""
HEADLINE SCORER v2.1 -- Deterministic Multi-Dimensional Headline Evaluation
============================================================================
Zero LLM inference. Pure Python: regex, string matching, word counting,
syllable counting, and established word lists.

Replaces v1 (headline_scorer.py) which had 36 tests / 36 pts across
overlapping dimensions.

v2.1 changes from v2.0:
  - IA2 tightened: FK <= 5.0 (5th grade reading level) instead of <= 8.0
  - NEW PT10: Emotional Intensity (amygdala activation) -- 2 pts
  - Total points: 44 (was 40)

4 Dimensions, 29 Tests, 44 Total Points:

  DIMENSION 1: INFORMATION ARCHITECTURE (6 tests, 10 pts)
    IA1  Word count in target range              (1 pt)
    IA2  Readability: FK <=5.0 AND avg syl <=1.6 (2 pts)
    IA3  Low cognitive load <=1 sub. structure    (1 pt)
    IA4  No passive voice                        (2 pts)
    IA5  Single clear idea, not compound         (2 pts)
    IA6  Front-loaded key info (first 6 words)   (2 pts)

  DIMENSION 2: PSYCHOLOGICAL TRIGGERS (10 tests, 14 pts)
    PT1  Open loop / curiosity gap               (2 pts)
    PT2  Loss/threat framing                     (1 pt)
    PT3  Identity activation                     (1 pt)
    PT4  Reader-directness                       (2 pts)
    PT5  Pattern interrupt / schema disruption   (1 pt)
    PT6  Emotional arousal                       (2 pts)
    PT7  Forward pull / implicit promise          (1 pt)
    PT8  Novelty/uniqueness framing              (1 pt)
    PT9  Narrative hook                          (1 pt)
    PT10 Emotional intensity (amygdala)          (2 pts)

  DIMENSION 3: CREDIBILITY & SPECIFICITY (6 tests, 8 pts)
    CS1  Specificity >=2 specific elements       (2 pts)
    CS2  Contains number or quantifier           (1 pt)
    CS3  Mechanism hint                          (1 pt)
    CS4  Credibility signal                      (1 pt)
    CS5  Concrete noun present                   (2 pts)
    CS6  Power word density >=12%                (1 pt)

  DIMENSION 4: BRAND & COMPLIANCE (7 tests, 12 pts)
    BC1  Zero banned words       (2 pts, HARD GATE)
    BC2  Zero disease claims     (2 pts, HARD GATE)
    BC3  Zero prohibited phrases (2 pts, HARD GATE)
    BC4  Brand voice (anti-hype)                 (1 pt)
    BC5  No personal-attribute targeting         (1 pt)
    BC6  No vague hype words                     (1 pt)
    BC7  Time compression safety                 (1 pt)

Hard Gate Logic:
  BC1, BC2, BC3 are hard gates. If ANY of them fail, the headline is
  DISQUALIFIED and its composite score is set to 0, regardless of how
  well it performs on other tests.
  IA2 (readability) is a scored test but NOT a hard gate.

Tier System:
  S = 90%+   A = 80-89%   B = 70-79%   C = 60-69%   D = <60%
  DISQUALIFIED = hard gate failure (score forced to 0)

Each test returns a 3-tuple: (passed: bool, detail: str, fix_hint: str)
  - passed: whether the test passed
  - detail: diagnostic info about what was found
  - fix_hint: short, actionable suggestion for QA loop LLM (no threshold leaks)

Usage:
  python3 headline_scorer_v2.py "Your headline here"
  python3 headline_scorer_v2.py "Your headline here" --page-type listicle
  python3 headline_scorer_v2.py --batch headlines.txt
  python3 headline_scorer_v2.py --batch headlines.txt --page-type sales_page
  python3 headline_scorer_v2.py --json /path/to/listicle.json
  python3 headline_scorer_v2.py "Your headline here" --output-json
"""

import re
import sys
import json
import argparse
from collections import Counter

SCORER_VERSION = "2.1"


# ============================================================
# SECTION 1: WORD LISTS (Module-Level Constants)
# ============================================================

# --- Banned Words (full list from Voice & Tone + Compliance rules) ---
BANNED_WORDS = [
    "miracle", "revolutionary", "breakthrough", "superfood", "detox", "cleanse",
    "shocking", "mind-blowing", "hack", "synergy", "guru", "warrior", "goddess",
    "queen", "magic", "magical", "babe", "mama",
    "game-changer", "game changer", "life-changing",
    # Phrases treated as banned words
    "big pharma", "chemical-free", "all-natural",
    "guaranteed to",
    # Disease claim verbs (from compliance)
    "cure", "cures", "treat", "treats", "heal", "heals",
    "prevent", "prevents", "diagnose",
]

# "secret" is banned when used standalone, per brand voice rules.
BANNED_WORDS_STANDALONE = [
    "secret", "secrets",
]

# Combine for full banned set (used in BC1)
BANNED_WORDS_ALL = BANNED_WORDS + BANNED_WORDS_STANDALONE

# Build a set of lowercase banned stems for filtering power words
_BANNED_SET = set(w.lower() for w in BANNED_WORDS_ALL)

# --- Power Words (expanded from ~92 to ~150 post-filter) ---
_RAW_POWER_WORDS = [
    "secret", "discover", "free", "proven", "guaranteed", "instant", "new",
    "warning", "dangerous", "mistake", "hidden", "shocking", "truth", "finally",
    "breakthrough", "simple", "easy", "fast", "save", "avoid", "stop", "never",
    "always", "worst", "best", "only", "first", "last", "exclusive", "limited",
    "urgent", "critical", "essential", "forgotten", "overlooked", "ignored",
    "exposed", "revealed", "unleash", "unlock", "transform", "eliminate",
    "destroy", "protect", "survive", "escape", "rescue", "overcome",
    "powerful", "deadly", "alert", "beware", "controversial", "forbidden",
    "remarkable", "stunning", "surprising", "unexpected", "unusual",
    "terrifying", "alarming", "astonishing", "devastating", "explosive",
    "eye-opening", "frightening", "incredible", "jaw-dropping", "life-saving",
    "outrageous", "phenomenal", "rare", "sensational", "startling",
    "tremendous", "unbelievable", "unheard-of", "unprecedented",
    "vital", "wonder", "absolute", "confidential", "covert",
    "insider", "private", "classified", "undisclosed", "unknown",
    "tested", "certified", "endorsed", "expert", "legitimate",
    "official", "reliable", "trusted", "verified",
    "bonus", "cheap", "discount", "fortune", "jackpot",
    "lucrative", "profit", "reduced", "savings", "valuable",
    "bargain", "priceless", "quick", "immediately", "now",
    "rapid", "hurry", "deadline", "running out", "before",
    "bold", "brazen", "courage", "daring", "fearless",
    "grit", "heroic", "mighty", "unstoppable", "victorious",
    "blissful", "grateful", "heartwarming", "inspiring",
    "jubilant", "uplifting", "hopeful", "triumphant",
    "captivating", "enchanting", "gripping", "hypnotic",
    "intriguing", "irresistible", "magnetic", "mesmerizing",
    "provocative", "riveting", "spellbinding",
    "effortless", "foolproof", "painless", "straightforward",
    "basic", "uncomplicated", "no-brainer",
    "authentic", "backed", "dependable", "guaranteed-result",
    "honest", "ironclad", "lifetime", "moneyback",
    "promise", "research-backed", "unconditional",
    "announcing", "introducing", "presenting", "latest",
    "cutting-edge", "fresh", "modern", "novel",
    "pioneering", "state-of-the-art", "updated",
    "banned", "blacklisted", "censored", "concealed",
    "cover-up", "silenced", "suppressed", "underground",
    "unspoken", "withheld",
    # --- v2 additions: domain-specific safety/vigilance power words ---
    "documented", "flagged", "verified", "cross-referenced", "reviewed",
    "referenced", "precise", "measured", "calibrated", "evidence-informed",
    "preventable", "avoidable", "irreversible", "overlooked", "missed",
    "undetected", "undisclosed", "unverified", "untested",
    "indexed", "organized", "systematic", "comprehensive", "thorough",
    "complete", "definitive", "authoritative", "curated",
    "transparent", "honest", "straightforward", "practical", "grounded",
    "safety-first", "evidence-based", "research-backed",
]

# Filter out any power words that appear on the banned list
POWER_WORDS = sorted(set(
    w for w in _RAW_POWER_WORDS
    if w.lower() not in _BANNED_SET
))

# --- Common Verbs for Front-Loading Check ---
COMMON_VERBS = {
    "discover", "learn", "find", "get", "see", "try", "use", "make", "take",
    "give", "know", "think", "feel", "want", "need", "start", "stop", "keep",
    "read", "watch", "avoid", "protect", "save", "fix", "solve", "build",
    "create", "grow", "boost", "cut", "drop", "eat", "drink", "cook", "brew",
    "mix", "add", "check", "test", "ask", "tell", "show", "prove", "fight",
    "run", "walk", "move", "turn", "open", "close", "buy", "sell", "pick",
    "choose", "grab", "hold", "put", "set", "pull", "push", "help", "support",
    "reduce", "improve", "change", "replace", "consider", "explore", "unlock",
    "reveal", "expose", "ignore", "forget", "remember", "imagine", "believe",
    "trust", "doubt", "question", "wonder", "worry", "hope", "fear",
    "do", "does", "did", "go", "going", "gone", "are", "is", "was", "were",
    "have", "has", "had", "can", "could", "should", "would", "will", "may",
    "might", "must", "shall",
}

# --- Number Words ---
NUMBER_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "every", "most", "all", "half", "twice", "triple",
    "double", "single",
}

# --- Subordinating Conjunctions ---
SUBORDINATING_CONJUNCTIONS = {
    "because", "although", "though", "while", "whereas", "if", "unless",
    "when", "whenever", "since", "until", "after", "before", "whether",
    "even though", "even if", "so that", "in order that", "provided that",
}

# --- Concrete Nouns (expanded from 64 to ~100) ---
CONCRETE_NOUNS = {
    "herb", "herbs", "plant", "plants", "tea", "teas", "tincture", "tinctures",
    "kitchen", "child", "children", "kids", "toddler", "toddlers", "baby",
    "babies", "mother", "mom", "moms", "mothers", "doctor", "doctors",
    "pharmacist", "pharmacists", "book", "books", "handbook", "handbooks",
    "guide", "guides", "reference", "references", "spice", "spices",
    "rack", "cabinet", "cabinets", "prescription", "prescriptions",
    "medication", "medications", "pill", "pills", "bottle", "bottles",
    "dose", "doses", "dosing", "blood", "skin", "stomach", "sleep",
    "fever", "cough", "rash", "pain", "headache", "headaches",
    "garden", "root", "roots", "leaf", "leaves", "flower", "flowers",
    "seed", "seeds", "bark", "oil", "oils", "salve", "poultice",
    "syrup", "capsule", "capsules", "powder", "extract", "remedy",
    "remedies", "recipe", "recipes", "woman", "women", "man", "men",
    "family", "families", "parent", "parents", "daughter", "son",
    "table", "bed", "shelf", "counter", "bathroom", "bedroom",
    "eye", "eyes", "hand", "hands", "throat", "heart", "brain",
    "chest", "joint", "joints", "muscle", "muscles", "bone", "bones",
    "chamomile", "valerian", "elderberry", "echinacea", "ginger",
    "peppermint", "lavender", "turmeric", "garlic",
    # --- v2 additions ---
    "ashwagandha", "passionflower", "goldenseal", "kava", "licorice",
    "hawthorn", "mullein", "motherwort", "feverfew",
    "interaction", "contraindication", "allergy", "reaction",
    "pantry", "drawer", "nightstand", "teapot", "mortar", "pestle",
    "dropper", "jar", "label", "chart", "checklist", "index",
    "pediatrician", "nurse", "midwife", "naturopath", "practitioner",
    "herbalist", "grandmother", "toddler", "infant", "teenager",
    "aspirin", "ibuprofen", "antibiotic", "statin",
}

# --- Emotional / Arousal Words (expanded from 40 to ~90) ---
EMOTIONAL_WORDS = {
    "afraid", "angry", "anxious", "confused", "desperate", "frustrated",
    "worried", "scared", "overwhelmed", "exhausted", "nervous", "helpless",
    "relieved", "confident", "safe", "secure", "trusted", "peaceful", "proud",
    "surprised", "delighted", "amazed", "love", "hate", "fear", "hope",
    "trust", "doubt", "shame", "guilt", "regret", "panic", "calm", "joy",
    "risk", "danger", "threat", "mistake", "wrong", "right", "hurt", "harm",
    "protect", "save",
    # --- v2 additions: domain-specific protective urgency ---
    "dosing", "interaction", "interactions", "safety", "unsafe", "caution",
    "careful", "precision", "accurate", "reliable", "contraindication",
    "warning", "alert", "concern", "vigilance", "responsible",
    "preventable", "avoidable", "uncertain", "guessing",
    "conflicting", "contradictory", "misleading", "unreliable",
    "vulnerable", "innocent", "precious", "dependent", "fragile",
    "irreversible", "permanent", "critical", "urgent", "essential",
    "non-negotiable", "alarming",
    "confusing", "overwhelming", "paralyzing", "second-guessing",
    "distrust", "skeptical", "suspicious",
}

# --- Amygdala-Activation Words (PT10: Emotional Intensity) ---
# These words trigger fight-or-flight, parental protection instinct,
# or visceral threat response. Distinct from general emotional arousal.
# Organized by neurochemical pathway:
#   Cortisol (self-threat, shame, competence attack)
#   Norepinephrine (danger, fear, survival threat)
#   Oxytocin-violation (betrayal, broken trust, parental threat)
AMYGDALA_WORDS = {
    # --- FEAR / DANGER (norepinephrine) ---
    "dangerous", "danger", "deadly", "fatal", "toxic", "poison", "poisoned",
    "poisoning", "lethal", "kill", "killed", "die", "dying", "death",
    "emergency", "urgent", "critical", "alarming", "terrifying",
    "frightening", "horrifying", "nightmare", "panic", "threat",
    "warning", "alert", "harm", "harming", "harmful", "hurt", "hurting",
    "damage", "damaging", "destroy", "destroying", "irreversible",
    # --- PARENTAL THREAT (oxytocin-violation) ---
    "child", "children", "kids", "kid", "baby", "babies", "infant",
    "toddler", "son", "daughter", "pregnant", "pregnancy",
    "newborn", "nursing", "breastfeeding",
    # --- SHAME / COMPETENCE ATTACK (cortisol) ---
    "wrong", "mistake", "mistakes", "fool", "foolish", "ignorant",
    "careless", "reckless", "negligent", "guilty", "blame", "fault",
    "failure", "failing", "failed", "stupid", "blind", "clueless",
    "guessing", "gambling", "winging",
    # --- BETRAYAL / BROKEN TRUST (anterior insula) ---
    "lied", "lying", "lie", "lies", "deceived", "fake", "fraud",
    "scam", "hoax", "betrayed", "betrayal", "misleading", "mislead",
    "manipulated", "exploited", "conned", "tricked",
    # --- PAIN / SUFFERING (visceral) ---
    "pain", "agony", "suffering", "screaming", "crying", "bleeding",
    "vomiting", "choking", "gasping", "seizure", "overdose",
    "allergic", "reaction", "rash", "swelling",
}

# Amygdala phrases (multi-word triggers)
AMYGDALA_PHRASES = [
    r"\b2\s*a\.?m\.?\b",  # "2 AM" — parental crisis scenario
    r"\bmiddle of the night\b",
    r"\byour child\b", r"\byour kids?\b", r"\byour baby\b",
    r"\byour family\b", r"\byour son\b", r"\byour daughter\b",
    r"\bwhat if\b",  # catastrophizing trigger
    r"\btoo late\b",
    r"\bwithout knowing\b", r"\bwithout realizing\b",
    r"\bbefore checking\b", r"\bbefore reading\b",
    r"\bgot it wrong\b", r"\bgetting it wrong\b",
    r"\bdon'?t know\b", r"\bnever told\b",
]

# Minimum threshold: need 2+ amygdala signals (words or phrases) for PASS
AMYGDALA_THRESHOLD = 2

# --- Loss/Pain Words (merged from v1 PAIN_WORDS + LOSS_WORDS + additions) ---
LOSS_PAIN_WORDS = {
    # From v1 PAIN_WORDS
    "struggle", "fail", "failing", "wrong", "mistake", "problem", "issue",
    "frustrate", "frustrated", "frustrating", "confuse", "confused",
    "overwhelming", "overwhelmed", "stuck", "broken", "lost", "missing",
    "lack", "can't", "won't", "don't", "never", "stop", "quit", "worst",
    "bad", "poor", "weak", "difficult", "hard", "impossible", "scary",
    "dangerous", "risk", "harm", "hurt", "damage", "ruin", "destroy",
    "waste", "cost", "lose", "losing", "afraid", "worry", "worried",
    "anxious", "stress", "stressed", "exhausted", "tired", "sick",
    "pain", "ache", "suffer",
    # From v1 LOSS_WORDS
    "miss", "costs", "wasting", "risking", "danger", "harmful",
    "threat", "error", "avoid", "prevent",
    # v2 additions
    "guessing", "guesswork", "contradicting", "conflicting", "unreliable",
    "unverified", "misinformation", "second-guessing", "uncertainty",
    "harmful",
}

# --- Open Loop / Curiosity Gap Patterns ---
OPEN_LOOP_PATTERNS = [
    r"\bbut\b", r"\byet\b", r"\bhowever\b",
    r"\bthe one\b", r"\bthe secret\b", r"\bthe truth\b",
    r"\bthe real reason\b", r"\bwhat most\b", r"\bwhat nobody\b",
    r"\bwhat they\b", r"\bhere'?s why\b", r"\bhere'?s how\b",
    r"\bthis is why\b",
]
OPEN_LOOP_STRINGS = ["...", "\u2014 and", "\u2014 and", "-- and"]

# --- Pointing Words ---
POINTING_WORDS = {"this", "these", "that", "the one"}

# --- Mechanism Words ---
MECHANISM_WORDS = {
    "how", "why", "method", "system", "trigger", "process", "approach",
    "framework", "principle", "secret", "trick", "strategy", "technique",
    "formula", "protocol", "pathway", "mechanism",
}
MECHANISM_PATTERNS = [r"\bthe\s+\w+\s+that\b"]

# --- Identity Markers ---
IDENTITY_NOUNS = {
    "women", "woman", "moms", "mom", "mothers", "mother", "parents", "parent",
    "families", "family", "herbalists", "herbalist", "beginners", "beginner",
    "experts", "expert", "readers", "reader", "caregivers", "caregiver",
}
IDENTITY_PATTERNS = [r"\banyone who\b", r"\bpeople who\b", r"\bif you\b"]

# --- Credibility Signals ---
CREDIBILITY_WORDS = {
    "study", "studies", "research", "researcher", "researchers", "doctor",
    "doctors", "expert", "experts", "scientist", "scientists", "published",
    "clinical", "evidence", "data", "survey", "report", "proven", "tested",
    "verified",
}
CREDIBILITY_PATTERNS = [r"\baccording to\b"]

# --- Novelty / Uniqueness ---
NOVELTY_WORDS = {
    "new", "first", "only", "unusual", "unexpected", "surprising", "unique",
    "rare", "uncommon", "little-known", "overlooked", "forgotten", "hidden",
    "underground", "insider",
}
NOVELTY_PHRASES = [r"\bnever before\b", r"\bnever been\b"]

# --- Pattern Interrupt / Contradiction Markers (used for merged PT5) ---
INTERRUPT_WORDS = {
    "but", "yet", "however", "not", "never", "wrong", "mistake", "myth",
    "lie", "actually", "really", "in fact", "contrary", "opposite", "instead",
}
INTERRUPT_PHRASES = [r"\btruth is\b"]

# --- Schema Disruption (used for merged PT5) ---
SCHEMA_PHRASES = [
    r"\bmost people think\b", r"\byou'?ve been told\b", r"\beveryone says\b",
    r"\bconventional wisdom\b", r"\bwhat you think you know\b",
    r"\bwhat most \w+\b", r"\bactually\b", r"\bin reality\b",
    r"\bthe real reason\b", r"\bthe truth about\b",
    r"\bwhat \w+ get wrong\b", r"\bmyth\b", r"\blie\b",
]

# --- Forward Pull / Promise Words ---
PROMISE_WORDS = {
    "here's", "heres", "this is", "the answer", "the key", "the fix",
    "the solution", "the way", "the secret", "the method", "discover",
    "learn", "find out", "see why", "see how", "see what", "understand",
    "know",
}

# --- Hype Words (BC4) ---
HYPE_WORDS = {
    "incredible", "unbelievable", "insane", "crazy", "epic", "ultimate",
    "killer", "explosive", "massive", "huge", "amazing",
}

# --- Vague Words (BC6) ---
VAGUE_WORDS = {
    "amazing", "incredible", "awesome", "great", "wonderful", "fantastic",
    "best ever", "life-changing", "game-changing", "mind-blowing",
}

# --- Disease Names (BC2) ---
DISEASE_NAMES = {
    "cancer", "diabetes", "heart disease", "depression", "anxiety disorder",
    "adhd", "autism", "alzheimer's", "alzheimers", "arthritis",
}

# --- Personal Attribute Targeting Patterns (BC5) ---
PERSONAL_TARGETING_PATTERNS = [
    r"\bdo you suffer from\b",
    r"\bare you \w+ing\b",  # "are you suffering"
    r"\bif you have \w+\b",
    r"\bpeople with \w+\b",
    r"\bdiagnosed with\b",
    r"\bstruggling with \w+\b",
]

# --- Story / Narrative Markers ---
STORY_MARKERS_WORDS = {
    "when", "after", "before", "last", "she", "he", "i", "we", "they",
}
STORY_PHRASES = [r"\bone day\b", r"\bfirst time\b"]

# --- Prohibited Phrases (BC3) -- from compliance.md ---
PROHIBITED_PHRASES = [
    "they don't want you to know",
    "ancient secret",
    "lost remedy",
    "lost cure",
    "you need this",
    "don't miss out",
    "act now",
    "limited time",
    "just trust me",
    "toxins",
    "cure for",
    "treat your",
    "heal your",
    "prevent disease",
    "diagnose",
    "guaranteed results",
    "miracle herb",
    "miracle remedy",
    "miracle cure",
    "clinically proven",
    "doctor-recommended",
    "no side effects",
    "replaces medication",
    "fda-approved herbs",
    "scientifically proven to",
    "eliminates pain",
    "instant relief",
    "100% effective",
    "secret remedy",
    "reverse your",
]

# --- Health Outcome Verbs (BC7) ---
HEALTH_OUTCOME_VERBS = {
    "heal", "improve", "reduce", "boost", "fix", "cure", "treat",
    "eliminate", "reverse", "relieve", "restore", "recover", "remedy",
}

# --- Time Words / Phrases / Pattern ---
TIME_WORDS = {
    "overnight", "immediately", "instantly", "today", "tonight",
    "right now",
}
TIME_PHRASES = [
    r"\bthis morning\b", r"\bthis week\b", r"\bone evening\b",
    r"\bin minutes\b", r"\bthis evening\b",
]
TIME_UNIT_PATTERN = r"\b\d+\s*(?:hour|hours|day|days|week|weeks|minute|minutes|second|seconds|month|months|year|years)\b"

# --- Emotional Register Markers (for batch mode register detection) ---
CLINICAL_MARKERS = {
    "study", "research", "evidence", "data", "clinical", "measured",
    "documented", "published",
}
EMPATHETIC_MARKERS = {
    "you", "your", "feel", "worry", "scared", "confused", "overwhelmed",
    "understand", "safe", "protect", "care", "trust",
}
PROVOCATIVE_MARKERS = {
    "wrong", "lie", "myth", "never", "stop", "worst", "don't", "actually",
    "truth",
}


# ============================================================
# SECTION 2: UTILITY FUNCTIONS
# ============================================================

def count_syllables(word):
    """
    Estimate syllable count for a single word using vowel-group heuristic.
    Handles silent-e, -le endings, and common patterns.
    """
    word = word.lower().strip()
    if not word:
        return 0
    # Remove trailing punctuation
    word = re.sub(r'[^a-z]', '', word)
    if not word:
        return 0
    if len(word) <= 2:
        return 1

    # Count vowel groups
    vowel_groups = re.findall(r'[aeiouy]+', word)
    count = len(vowel_groups)

    # Silent-e at end (but not "le" ending which adds a syllable)
    if word.endswith('e') and not word.endswith('le'):
        count -= 1
    # Words ending in "le" preceded by a consonant get a syllable
    if word.endswith('le') and len(word) > 2 and word[-3] not in 'aeiouy':
        count += 0  # Already counted by vowel groups usually

    # Adjust for common suffixes
    if word.endswith('ed'):
        # "ed" is usually silent unless preceded by t or d
        if len(word) > 2 and word[-3] not in 'td':
            count -= 1

    # Ensure at least 1 syllable
    return max(1, count)


def count_words(text):
    """Count words in text."""
    words = text.split()
    return len(words)


def get_words(text):
    """Get list of lowercase words from text."""
    return [w.lower() for w in re.findall(r"[a-zA-Z'-]+", text)]


def flesch_kincaid_grade(text):
    """
    Calculate Flesch-Kincaid grade level for text.
    FK = 0.39*(words/sentences) + 11.8*(syllables/words) - 15.59
    For headlines, treat as single sentence.
    """
    words = get_words(text)
    if not words:
        return 0.0
    num_words = len(words)
    num_sentences = 1  # Headlines are single sentences
    total_syllables = sum(count_syllables(w) for w in words)

    fk = 0.39 * (num_words / num_sentences) + 11.8 * (total_syllables / num_words) - 15.59
    return round(fk, 1)


def avg_syllables_per_word(text):
    """Calculate average syllables per word."""
    words = get_words(text)
    if not words:
        return 0.0
    total = sum(count_syllables(w) for w in words)
    return round(total / len(words), 2)


def word_in_text(word, text_lower):
    """Check if a word appears in text using word boundaries."""
    pattern = r'\b' + re.escape(word.lower()) + r'\b'
    return bool(re.search(pattern, text_lower))


def any_word_in_text(word_set, text_lower):
    """Check if any word from set appears in text. Returns matching words."""
    found = []
    for w in word_set:
        if word_in_text(w, text_lower):
            found.append(w)
    return found


# ============================================================
# SECTION 3: TEST FUNCTIONS (28 tests)
# Each returns (passed: bool, detail: str, fix_hint: str)
# ============================================================

# --- DIMENSION 1: INFORMATION ARCHITECTURE (6 tests, 10 pts) ---

def test_ia1(headline, page_type):
    """IA1: Word count in target range (1pt)."""
    ranges = {
        "listicle": (8, 14),
        "advertorial": (10, 18),
        "sales_page": (8, 20),
    }
    lo, hi = ranges.get(page_type, (8, 20))
    wc = count_words(headline)
    passed = lo <= wc <= hi
    pt_label = page_type if page_type else "default"
    detail = f"Word count: {wc} (target {lo}-{hi} for {pt_label})"
    fix_hint = f"Adjust headline length to {lo}-{hi} words for {pt_label}"
    return passed, detail, fix_hint


def test_ia2(headline):
    """IA2: Readability: FK <=5.0 AND avg syllables <=1.6 (2pts, HARD GATE).
    5th grade reading level. This is a hard gate -- failure = disqualification."""
    fk = flesch_kincaid_grade(headline)
    avg = avg_syllables_per_word(headline)
    fk_pass = fk <= 5.0
    avg_pass = avg <= 1.6
    passed = fk_pass and avg_pass

    parts = []
    if not fk_pass:
        parts.append("FK FAILED")
    if not avg_pass:
        parts.append("Syllables FAILED")

    detail = f"FK grade: {fk} (target <=5.0 / 5th grade). Avg syllables: {avg} (<=1.6)."
    if parts:
        detail += " " + ". ".join(parts) + "."
    else:
        detail += " Both passed."

    fix_hint = "HARD GATE: Must be 5th grade reading level. Use 1-2 syllable words only. Replace any word a 10-year-old wouldn't know."
    return passed, detail, fix_hint


def test_ia3(headline):
    """IA3: Low cognitive load <=1 subordinating structure (1pt)."""
    hl_lower = headline.lower()
    count = 0
    for conj in SUBORDINATING_CONJUNCTIONS:
        if word_in_text(conj, hl_lower):
            count += 1
    # Count clause separators
    count += headline.count(';')
    # Em-dash with words on both sides (clause joiner)
    em_dash_clauses = len(re.findall(r'\w\s*[\u2014]\s*\w', headline))
    if em_dash_clauses > 0:
        count += em_dash_clauses

    passed = count <= 1
    detail = f"Subordinating structures: {count} (target <=1)"
    fix_hint = "Simplify sentence structure. Remove subordinating clauses or em-dash asides."
    return passed, detail, fix_hint


def test_ia4(headline):
    """IA4: No passive voice (1pt)."""
    passive_pattern = r'\b(?:is|was|were|been|being|are)\s+\w+(?:ed|en|ght|wn|nt)\b'
    matches = re.findall(passive_pattern, headline.lower())
    passed = len(matches) == 0
    if matches:
        detail = f"Passive voice detected: {matches}"
    else:
        detail = "No passive voice detected"
    fix_hint = "Rewrite in active voice. Put the subject before the action."
    return passed, detail, fix_hint


def test_ia5(headline):
    """IA5: Single clear idea, not compound (2pts)."""
    hl_lower = headline.lower()

    # Count periods (exclude Dr., Mr., Mrs., etc.)
    cleaned = re.sub(r'\b(?:Dr|Mr|Mrs|Ms|St|Jr|Sr|vs)\.\s*', '', headline)
    period_count = cleaned.count('.')
    # Remove trailing period
    if cleaned.strip().endswith('.'):
        period_count -= 1
    period_count = max(0, period_count)

    # Count " and " conjunctions
    and_count = len(re.findall(r'\band\b', hl_lower))

    # Count semicolons
    semi_count = headline.count(';')

    # Count em-dash clause-joiners (words on both sides)
    em_dash_count = len(re.findall(r'\w\s*[\u2014]\s*\w', headline))

    total = period_count + and_count + semi_count + em_dash_count
    passed = total <= 1
    detail = (f"Compound signals: {total} (periods={period_count}, "
              f"'and'={and_count}, semicolons={semi_count}, em-dashes={em_dash_count})")
    fix_hint = "Focus on one idea. Remove 'and' or split compound thoughts."
    return passed, detail, fix_hint


def test_ia6(headline):
    """IA6: Front-loaded key info: verb or concrete noun in first 6 words (1pt)."""
    words = get_words(headline)
    first_6 = words[:6]
    found_verbs = [w for w in first_6 if w in COMMON_VERBS]
    found_nouns = [w for w in first_6 if w in CONCRETE_NOUNS]
    found = found_verbs + found_nouns
    passed = len(found) > 0

    if found_verbs and found_nouns:
        detail = f"First 6 words contain verb(s): {found_verbs} and noun(s): {found_nouns}"
    elif found_verbs:
        detail = f"Verbs in first 6 words: {found_verbs}"
    elif found_nouns:
        detail = f"Concrete nouns in first 6 words: {found_nouns}"
    else:
        detail = "No verb or concrete noun in first 6 words"

    fix_hint = "Start with a verb or concrete noun in the first 6 words."
    return passed, detail, fix_hint


# --- DIMENSION 2: PSYCHOLOGICAL TRIGGERS (9 tests, 12 pts) ---

def test_pt1(headline):
    """PT1: Open loop / curiosity gap (2pts). Merges v1 DR1 + NS2."""
    hl_lower = headline.lower()

    # Check open-loop patterns
    for pattern in OPEN_LOOP_PATTERNS:
        match = re.search(pattern, hl_lower)
        if match:
            return True, f"Open loop detected: '{match.group()}'", \
                "Create unresolved tension. Use 'here's why', 'but', or a question that demands an answer."

    # Check open-loop strings
    for s in OPEN_LOOP_STRINGS:
        if s in headline:
            return True, f"Open loop detected: '{s}'", \
                "Create unresolved tension. Use 'here's why', 'but', or a question that demands an answer."

    # Check for ellipsis
    if '...' in headline or '\u2026' in headline:
        return True, "Open loop detected: ellipsis", \
            "Create unresolved tension. Use 'here's why', 'but', or a question that demands an answer."

    # Check for em-dash
    if '\u2014' in headline or '-- ' in headline:
        return True, "Open loop detected: em-dash", \
            "Create unresolved tension. Use 'here's why', 'but', or a question that demands an answer."

    # Check pointing-word-without-resolution (NS2 logic)
    has_pointing = False
    for pw in POINTING_WORDS:
        if pw in hl_lower:
            has_pointing = True
            break
    if has_pointing:
        has_resolution = any(w in hl_lower for w in ["is the", "is a", "means", "equals"])
        if not has_resolution:
            return True, "Curiosity gap: pointing word without resolution", \
                "Create unresolved tension. Use 'here's why', 'but', or a question that demands an answer."

    # Check question format
    if headline.strip().endswith('?'):
        return True, "Open loop detected: question format", \
            "Create unresolved tension. Use 'here's why', 'but', or a question that demands an answer."

    fix_hint = "Create unresolved tension. Use 'here's why', 'but', or a question that demands an answer."
    return False, "No open loop/curiosity gap detected", fix_hint


def test_pt2(headline):
    """PT2: Loss/threat framing (1pt). Merges v1 DR4 + NS3."""
    hl_lower = headline.lower()
    words = get_words(headline)
    found = []

    for w in LOSS_PAIN_WORDS:
        if "'" in w:
            if w in hl_lower:
                found.append(w)
        elif word_in_text(w, hl_lower):
            found.append(w)

    found = list(set(found))
    passed = len(found) > 0
    if found:
        detail = f"Loss/threat signals: {found[:5]}"
    else:
        detail = "No loss/threat framing detected"
    fix_hint = "Name a risk, pain, or consequence the reader faces."
    return passed, detail, fix_hint


def test_pt3(headline):
    """PT3: Identity activation (1pt). Same logic as v1 DR5."""
    hl_lower = headline.lower()
    found = []

    if word_in_text("you", hl_lower) or word_in_text("your", hl_lower) or word_in_text("you're", hl_lower):
        found.append("you/your")

    for noun in IDENTITY_NOUNS:
        if word_in_text(noun, hl_lower):
            found.append(noun)

    for pattern in IDENTITY_PATTERNS:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(match.group())

    found = list(set(found))
    passed = len(found) > 0
    if found:
        detail = f"Identity markers: {found[:5]}"
    else:
        detail = "No identity marker detected"
    fix_hint = "Address the reader directly or reference their identity (parent, herbalist, caregiver)."
    return passed, detail, fix_hint


def test_pt4(headline):
    """PT4: Reader-directness (1pt). Same logic as v1 ATT11."""
    hl_lower = headline.lower()
    has_you = (word_in_text("you", hl_lower) or
               word_in_text("your", hl_lower) or
               word_in_text("you're", hl_lower))
    is_question = headline.strip().endswith('?')
    passed = has_you or is_question
    reasons = []
    if has_you:
        reasons.append("reader-direct ('you'/'your')")
    if is_question:
        reasons.append("question format")
    if reasons:
        detail = f"Engagement: {', '.join(reasons)}"
    else:
        detail = "No reader-directness detected"
    fix_hint = "Use 'you' or 'your', or rephrase as a question."
    return passed, detail, fix_hint


def test_pt5(headline):
    """PT5: Pattern interrupt / schema disruption (1pt). Merges v1 NS1 + NS7."""
    hl_lower = headline.lower()
    found = []

    # Check INTERRUPT_WORDS
    for w in INTERRUPT_WORDS:
        if ' ' in w:
            if w in hl_lower:
                found.append(w)
        else:
            if word_in_text(w, hl_lower):
                found.append(w)

    # Check INTERRUPT_PHRASES
    for pattern in INTERRUPT_PHRASES:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(match.group())

    # Check SCHEMA_PHRASES
    for pattern in SCHEMA_PHRASES:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(match.group())

    found = list(set(found))
    passed = len(found) > 0
    if found:
        detail = f"Pattern interrupt/schema disruption: {found[:5]}"
    else:
        detail = "No pattern interrupt or schema disruption detected"
    fix_hint = "Challenge an assumption. Use 'actually', 'but', 'not', or 'what most [people] get wrong'."
    return passed, detail, fix_hint


def test_pt6(headline):
    """PT6: Emotional arousal (2pts). Uses expanded EMOTIONAL_WORDS."""
    words = get_words(headline)
    found = [w for w in words if w in EMOTIONAL_WORDS]
    passed = len(found) >= 1
    if found:
        detail = f"Emotional words: {found[:5]}"
    else:
        detail = "No emotional/arousal words found"
    fix_hint = "Add a word that evokes emotion: concern, safety, risk, worry, trust, doubt, or protective urgency."
    return passed, detail, fix_hint


def test_pt7(headline):
    """PT7: Forward pull / implicit promise (1pt). Same logic as v1 NS8."""
    hl_lower = headline.lower()

    found_promise = False
    promise_word = ""
    for pw in PROMISE_WORDS:
        if pw in hl_lower:
            found_promise = True
            promise_word = pw
            break

    if not found_promise:
        return False, "No forward pull detected", \
            "Promise the reader will learn or gain something by continuing. Use 'here's', 'discover', or 'find out'."

    # Check for non-resolution
    is_question = headline.strip().endswith('?')
    has_colon_answer = ':' in headline and len(headline.split(':')[1].strip().split()) > 5

    if is_question or not has_colon_answer:
        return True, f"Forward pull: '{promise_word}' + unresolved", \
            "Promise the reader will learn or gain something by continuing. Use 'here's', 'discover', or 'find out'."
    return False, f"Promise word '{promise_word}' found but headline appears to resolve", \
        "Promise the reader will learn or gain something by continuing. Use 'here's', 'discover', or 'find out'."


def test_pt8(headline):
    """PT8: Novelty/uniqueness framing (1pt). Same logic as v1 DR8."""
    hl_lower = headline.lower()
    words = get_words(headline)
    found = []

    for w in words:
        if w in NOVELTY_WORDS:
            found.append(w)

    for pattern in NOVELTY_PHRASES:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(match.group())

    found = list(set(found))
    passed = len(found) > 0
    if found:
        detail = f"Novelty markers: {found[:5]}"
    else:
        detail = "No novelty framing detected"
    fix_hint = "Frame as new, overlooked, or little-known information."
    return passed, detail, fix_hint


def test_pt9(headline):
    """PT9: Narrative hook (1pt). Simplified from v1 NS6.
    >=2 narrative signals from story words, phrases, or past-tense words."""
    hl_lower = headline.lower()
    words = get_words(headline)
    found = []

    for w in words:
        if w in STORY_MARKERS_WORDS:
            found.append(w)

    for pattern in STORY_PHRASES:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(match.group())

    # Past tense heuristic: words ending in "ed"
    past_tense = [w for w in words if w.endswith('ed') and len(w) > 3]
    for pt in past_tense:
        found.append(f"past-tense({pt})")

    found = list(set(found))
    passed = len(found) >= 2
    detail = f"Story markers: {len(found)} ({found[:5]})"
    fix_hint = "Add a story element: 'when', 'before', 'after', or a past-tense verb."
    return passed, detail, fix_hint


def test_pt10(headline):
    """PT10: Emotional intensity / amygdala activation (2pts).
    Measures gut-punch, fear, parental threat, betrayal, shame signals.
    Requires 2+ amygdala signals (words or phrases) to pass.
    Distinct from PT6 (general arousal) -- this measures visceral threat response."""
    hl_lower = headline.lower()
    words = get_words(headline)
    found = []

    # Check amygdala words
    for w in words:
        if w in AMYGDALA_WORDS:
            found.append(w)

    # Check amygdala phrases
    for pattern in AMYGDALA_PHRASES:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(match.group())

    found = list(set(found))
    passed = len(found) >= AMYGDALA_THRESHOLD

    if found:
        detail = f"Amygdala signals: {len(found)} ({found[:6]})"
    else:
        detail = "No amygdala-activation signals detected"

    fix_hint = ("Add visceral emotional weight: parental threat (child, kids, baby), "
                "fear/danger (wrong, harmful, dangerous), shame (mistake, guessing, foolish), "
                "or betrayal (fake, lied, misleading). Need 2+ signals.")
    return passed, detail, fix_hint


# --- DIMENSION 3: CREDIBILITY & SPECIFICITY (6 tests, 8 pts) ---

def test_cs1(headline):
    """CS1: Specificity >=2 specific elements (2pts). Same logic as v1 DR2 with expanded nouns."""
    hl_lower = headline.lower()
    count = 0
    elements = []

    # Digits/numbers
    nums = re.findall(r'\d+', headline)
    if nums:
        count += len(nums)
        elements.append(f"numbers: {nums}")

    # Timeframes
    timeframes = ["days", "hours", "weeks", "minutes", "years", "morning",
                   "evening", "night", "tonight", "afternoon"]
    for tf in timeframes:
        if word_in_text(tf, hl_lower):
            count += 1
            elements.append(f"timeframe: {tf}")

    # Concrete nouns
    words = get_words(headline)
    concrete = [w for w in words if w in CONCRETE_NOUNS]
    if concrete:
        count += len(concrete)
        elements.append(f"concrete: {concrete[:3]}")

    # Percentages
    if re.search(r'\d+\s*%', headline):
        count += 1
        elements.append("percentage")

    passed = count >= 2
    if elements:
        detail = f"Specific elements: {count}. {'; '.join(elements)}"
    else:
        detail = "No specific elements found"
    fix_hint = "Add specific details: a number, a named herb, a timeframe, or a percentage."
    return passed, detail, fix_hint


def test_cs2(headline):
    """CS2: Contains number or quantifier (1pt). Same logic as v1 ATT7."""
    has_digit = bool(re.search(r'\d', headline))
    words = get_words(headline)
    has_number_word = any(w in NUMBER_WORDS for w in words)
    passed = has_digit or has_number_word

    if has_digit:
        nums = re.findall(r'\d+', headline)
        detail = f"Numbers found: {nums}"
    elif has_number_word:
        found = [w for w in words if w in NUMBER_WORDS]
        detail = f"Quantifiers found: {found}"
    else:
        detail = "No numbers or quantifiers found"

    fix_hint = "Include a specific number or quantifier (e.g., '7 herbs', '90% of guides')."
    return passed, detail, fix_hint


def test_cs3(headline):
    """CS3: Mechanism hint (1pt). Same logic as v1 DR3."""
    hl_lower = headline.lower()
    words = get_words(headline)

    for w in words:
        if w in MECHANISM_WORDS:
            return True, f"Mechanism word: '{w}'", \
                "Hint at a mechanism or method: 'how', 'why', 'the [noun] that', 'method', 'process'."

    for pattern in MECHANISM_PATTERNS:
        match = re.search(pattern, hl_lower)
        if match:
            return True, f"Mechanism pattern: '{match.group()}'", \
                "Hint at a mechanism or method: 'how', 'why', 'the [noun] that', 'method', 'process'."

    return False, "No mechanism hint detected", \
        "Hint at a mechanism or method: 'how', 'why', 'the [noun] that', 'method', 'process'."


def test_cs4(headline):
    """CS4: Credibility signal (1pt). Same logic as v1 DR6."""
    hl_lower = headline.lower()
    words = get_words(headline)
    found = []

    # Check for numbers
    if re.search(r'\d', headline):
        found.append("number")

    for w in words:
        if w in CREDIBILITY_WORDS:
            found.append(w)

    for pattern in CREDIBILITY_PATTERNS:
        if re.search(pattern, hl_lower):
            found.append("according to")

    found = list(set(found))
    passed = len(found) > 0
    if found:
        detail = f"Credibility signals: {found[:5]}"
    else:
        detail = "No credibility signal detected"
    fix_hint = "Add a credibility marker: a number, 'study', 'research', 'expert', or 'published'."
    return passed, detail, fix_hint


def test_cs5(headline):
    """CS5: Concrete noun present (1pt). Same logic as v1 ATT10 with expanded list."""
    words = get_words(headline)
    found = [w for w in words if w in CONCRETE_NOUNS]
    # Also check multi-word nouns
    hl_lower = headline.lower()
    for noun in CONCRETE_NOUNS:
        if ' ' in noun and noun in hl_lower:
            found.append(noun)
    passed = len(found) > 0
    if found:
        detail = f"Concrete nouns: {list(set(found))[:5]}"
    else:
        detail = "No concrete nouns found"
    fix_hint = "Use a concrete noun: an herb name, body part, household item, or specific object."
    return passed, detail, fix_hint


def test_cs6(headline):
    """CS6: Power word density >=12% (1pt). Modified from v1 ATT4 (was 15%)."""
    words = get_words(headline)
    if not words:
        return False, "No words found", \
            "Strengthen word choices. Replace generic verbs/adjectives with more impactful alternatives."
    pw_count = sum(1 for w in words if w in POWER_WORDS or w.lower() in POWER_WORDS)
    # Also check multi-word power words
    hl_lower = headline.lower()
    for pw in POWER_WORDS:
        if ' ' in pw and pw in hl_lower:
            pw_count += 1
    density = pw_count / len(words) * 100 if words else 0
    passed = density >= 12.0
    found = [w for w in words if w in POWER_WORDS][:5]
    detail = f"Power word density: {density:.1f}% ({pw_count}/{len(words)} words). Found: {found}"
    fix_hint = "Strengthen word choices. Replace generic verbs/adjectives with more impactful alternatives."
    return passed, detail, fix_hint


# --- DIMENSION 4: BRAND & COMPLIANCE (7 tests, 10 pts) ---

def test_bc1(headline):
    """BC1: Zero banned words (2pts, HARD GATE)."""
    hl_lower = headline.lower()
    found = []

    for bw in BANNED_WORDS_ALL:
        pattern = r'\b' + re.escape(bw.lower()) + r'\b'
        if re.search(pattern, hl_lower):
            found.append(bw)

    passed = len(found) == 0
    if found:
        detail = f"BANNED words found: {found}"
        fix_hint = f"Remove banned word: '{found[0]}'. Replace with a compliant alternative."
    else:
        detail = "Zero banned words"
        fix_hint = "Remove banned word: '<found>'. Replace with a compliant alternative."
    return passed, detail, fix_hint


def test_bc2(headline):
    """BC2: Zero disease claims (2pts, HARD GATE)."""
    hl_lower = headline.lower()
    found = []

    # Disease-claim verbs
    claim_patterns = [
        r'\bcures?\b', r'\btreats?\b', r'\bheals?\b',
        r'\bprevents?\b', r'\bdiagnos\w*\b',
    ]
    for pattern in claim_patterns:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(f"claim verb: {match.group()}")

    # "remedy for [disease]", "fix [condition]"
    if re.search(r'\bremedy for\b', hl_lower):
        found.append("'remedy for'")
    if re.search(r'\bfix\s+\w+\b', hl_lower):
        for d in DISEASE_NAMES:
            if re.search(r'\bfix\s+' + re.escape(d), hl_lower):
                found.append(f"'fix {d}'")

    # Disease names
    for d in DISEASE_NAMES:
        if d in hl_lower:
            found.append(f"disease name: {d}")

    passed = len(found) == 0
    if found:
        detail = f"Disease claims/names found: {found}"
        fix_hint = "Remove disease claim language. Use 'support', 'traditional use', or 'studied for' instead."
    else:
        detail = "Zero disease claims"
        fix_hint = "Remove disease claim language. Use 'support', 'traditional use', or 'studied for' instead."
    return passed, detail, fix_hint


def test_bc3(headline):
    """BC3: Zero prohibited phrases (2pts, HARD GATE). NEW test."""
    hl_lower = headline.lower()
    found = []

    for phrase in PROHIBITED_PHRASES:
        if phrase.lower() in hl_lower:
            found.append(phrase)

    passed = len(found) == 0
    if found:
        detail = f"Prohibited phrases found: {found}"
        fix_hint = f"Remove prohibited phrase: '{found[0]}'. Reframe without conspiracy or pressure language."
    else:
        detail = "Zero prohibited phrases"
        fix_hint = "Remove prohibited phrase: '<found>'. Reframe without conspiracy or pressure language."
    return passed, detail, fix_hint


def test_bc4(headline):
    """BC4: Brand voice alignment, anti-hype (1pt). Same logic as v1 BC3."""
    hl_lower = headline.lower()
    found = []
    for hw in HYPE_WORDS:
        if word_in_text(hw, hl_lower):
            found.append(hw)
    passed = len(found) == 0
    if found:
        detail = f"Hype words found: {found}"
    else:
        detail = "No hype words (brand-aligned)"
    fix_hint = "Remove hype language. Use calm, evidence-grounded alternatives."
    return passed, detail, fix_hint


def test_bc5(headline):
    """BC5: No personal-attribute targeting (1pt). Same logic as v1 BC4."""
    hl_lower = headline.lower()
    found = []

    for pattern in PERSONAL_TARGETING_PATTERNS:
        match = re.search(pattern, hl_lower)
        if match:
            found.append(match.group())

    # Also check specific phrases
    specific_phrases = [
        "do you suffer from", "are you suffering",
        "if you have", "people with", "diagnosed with",
    ]
    for phrase in specific_phrases:
        if phrase in hl_lower:
            if phrase not in found:
                found.append(phrase)

    passed = len(found) == 0
    if found:
        detail = f"Personal-attribute targeting found: {found}"
    else:
        detail = "No personal-attribute targeting"
    fix_hint = "Remove personal-attribute targeting. Don't address the reader's health condition directly."
    return passed, detail, fix_hint


def test_bc6(headline):
    """BC6: No vague hype words (1pt). Moved from v1 DR9."""
    hl_lower = headline.lower()
    found_vague = []
    for vw in VAGUE_WORDS:
        if vw in hl_lower:
            found_vague.append(vw)
    passed = len(found_vague) == 0
    if found_vague:
        detail = f"Vague words found: {found_vague}"
    else:
        detail = "No vague hype words (specific promise)"
    fix_hint = "Replace vague words ('amazing', 'incredible') with specific, concrete language."
    return passed, detail, fix_hint


def test_bc7(headline):
    """BC7: Time compression safety (1pt). NEW test.
    FAIL if headline contains (digit + time unit) AND a health-outcome verb."""
    hl_lower = headline.lower()
    words = get_words(headline)

    # Check for digit + time unit
    has_time_unit = bool(re.search(TIME_UNIT_PATTERN, hl_lower))

    # Check for health outcome verb
    has_health_verb = any(w in HEALTH_OUTCOME_VERBS for w in words)

    # Also check for verb forms: heals, improves, reduces, etc.
    health_verb_patterns = [
        r'\b(?:heals?|improves?|reduces?|boosts?|fix(?:es)?|cures?|treats?)\b',
        r'\b(?:eliminates?|reverses?|relieves?|restores?|recovers?|remedies?)\b',
    ]
    for pattern in health_verb_patterns:
        if re.search(pattern, hl_lower):
            has_health_verb = True
            break

    if has_time_unit and has_health_verb:
        passed = False
        time_matches = re.findall(TIME_UNIT_PATTERN, hl_lower)
        health_found = [w for w in words if w in HEALTH_OUTCOME_VERBS]
        detail = f"Time compression + health outcome: timeframe={time_matches}, health verbs={health_found}"
    else:
        passed = True
        if has_time_unit:
            detail = "Timeframe present but no health-outcome verb (OK)"
        elif has_health_verb:
            detail = "Health verb present but no timeframe (OK)"
        else:
            detail = "No time compression safety issue"

    fix_hint = "Remove health-outcome promise tied to a timeframe. Timeframes are OK for information access, not health results."
    return passed, detail, fix_hint


# ============================================================
# SECTION 4: SCORING ENGINE
# ============================================================

def score_headline(headline, page_type=None):
    """Score a single headline across all 4 dimensions, 28 tests. Returns dict."""
    headline = headline.strip()

    # Dimension 1: Information Architecture (10 pts)
    ia_tests = [
        ("IA1", "Word count range", 1, test_ia1(headline, page_type)),
        ("IA2", "Readability (FK + syllables)", 2, test_ia2(headline)),
        ("IA3", "Low cognitive load", 1, test_ia3(headline)),
        ("IA4", "No passive voice", 2, test_ia4(headline)),
        ("IA5", "Single clear idea", 2, test_ia5(headline)),
        ("IA6", "Front-loaded key info", 2, test_ia6(headline)),
    ]

    # Dimension 2: Psychological Triggers (14 pts)
    pt_tests = [
        ("PT1", "Open loop / curiosity gap", 2, test_pt1(headline)),
        ("PT2", "Loss/threat framing", 1, test_pt2(headline)),
        ("PT3", "Identity activation", 1, test_pt3(headline)),
        ("PT4", "Reader-directness", 2, test_pt4(headline)),
        ("PT5", "Pattern interrupt / schema disruption", 1, test_pt5(headline)),
        ("PT6", "Emotional arousal", 2, test_pt6(headline)),
        ("PT7", "Forward pull / implicit promise", 1, test_pt7(headline)),
        ("PT8", "Novelty/uniqueness", 1, test_pt8(headline)),
        ("PT9", "Narrative hook", 1, test_pt9(headline)),
        ("PT10", "Emotional intensity (amygdala)", 2, test_pt10(headline)),
    ]

    # Dimension 3: Credibility & Specificity (8 pts)
    cs_tests = [
        ("CS1", "Specificity (>=2 elements)", 2, test_cs1(headline)),
        ("CS2", "Number or quantifier", 1, test_cs2(headline)),
        ("CS3", "Mechanism hint", 1, test_cs3(headline)),
        ("CS4", "Credibility signal", 1, test_cs4(headline)),
        ("CS5", "Concrete noun present", 2, test_cs5(headline)),
        ("CS6", "Power word density >=12%", 1, test_cs6(headline)),
    ]

    # Dimension 4: Brand & Compliance (10 pts)
    bc_tests = [
        ("BC1", "Zero banned words", 2, test_bc1(headline)),
        ("BC2", "Zero disease claims", 2, test_bc2(headline)),
        ("BC3", "Zero prohibited phrases", 2, test_bc3(headline)),
        ("BC4", "Brand voice (anti-hype)", 1, test_bc4(headline)),
        ("BC5", "No personal-attribute targeting", 1, test_bc5(headline)),
        ("BC6", "No vague hype words", 1, test_bc6(headline)),
        ("BC7", "Time compression safety", 1, test_bc7(headline)),
    ]

    return {
        "headline": headline,
        "page_type": page_type,
        "information_architecture": ia_tests,
        "psychological_triggers": pt_tests,
        "credibility_specificity": cs_tests,
        "brand_compliance": bc_tests,
    }


def compute_composite(result):
    """Compute composite score with hard gate enforcement.
    Hard gates: BC1, BC2, BC3 only. IA2 is scored but not a gate."""
    BC_HARD_GATES = {"BC1", "BC2", "BC3"}

    # Check hard gates first
    hard_gate_pass = True
    disqualification_reasons = []

    # Check BC hard gates
    for test_id, test_name, weight, (passed, detail, fix_hint) in result["brand_compliance"]:
        if test_id in BC_HARD_GATES and not passed:
            hard_gate_pass = False
            disqualification_reasons.append(f"{test_id}: {detail}")

    # Compute dimension scores
    scores = {}
    for dim_key, dim_label in [
        ("information_architecture", "Information Architecture"),
        ("psychological_triggers", "Psychological Triggers"),
        ("credibility_specificity", "Credibility & Specificity"),
        ("brand_compliance", "Brand & Compliance"),
    ]:
        tests = result[dim_key]
        earned = sum(weight for _, _, weight, (passed, _, _) in tests if passed)
        maximum = sum(weight for _, _, weight, _ in tests)
        scores[dim_key] = (earned, maximum, dim_label)

    total = sum(s[0] for s in scores.values())
    maximum = sum(s[1] for s in scores.values())

    if not hard_gate_pass:
        return {
            "total": 0,
            "max": maximum,
            "pct": 0.0,
            "tier": "DISQUALIFIED",
            "hard_gate_pass": False,
            "disqualification_reasons": disqualification_reasons,
            "dimensions": scores,
            "actual_total": total,
        }

    pct = (total / maximum * 100) if maximum > 0 else 0

    if pct >= 90:
        tier = "S"
    elif pct >= 80:
        tier = "A"
    elif pct >= 70:
        tier = "B"
    elif pct >= 60:
        tier = "C"
    else:
        tier = "D"

    return {
        "total": total,
        "max": maximum,
        "pct": pct,
        "tier": tier,
        "hard_gate_pass": True,
        "dimensions": scores,
    }


def to_json(result, composite):
    """Convert to machine-readable JSON for headline_qa_loop.py."""
    tests_list = []
    failing = []
    passing = []

    for dim_key in ["information_architecture", "psychological_triggers",
                     "credibility_specificity", "brand_compliance"]:
        for test_id, test_name, weight, (passed, detail, fix_hint) in result[dim_key]:
            test_obj = {
                "id": test_id,
                "name": test_name,
                "weight": weight,
                "passed": passed,
                "detail": detail,
                "fix_hint": fix_hint,
            }
            tests_list.append(test_obj)
            if passed:
                passing.append(test_id)
            else:
                failing.append(test_id)

    output = {
        "headline": result["headline"],
        "page_type": result["page_type"],
        "scorer_version": SCORER_VERSION,
        "hard_gate_pass": composite.get("hard_gate_pass", True),
        "tier": composite["tier"],
        "composite": {
            "total": composite["total"],
            "max": composite["max"],
            "pct": round(composite["pct"], 1),
        },
        "dimensions": {
            k: {"earned": v[0], "max": v[1], "label": v[2]}
            for k, v in composite["dimensions"].items()
        },
        "tests": tests_list,
        "failing_tests": failing,
        "passing_tests": passing,
    }

    if not composite.get("hard_gate_pass", True):
        output["disqualification_reasons"] = composite.get("disqualification_reasons", [])
        output["actual_total"] = composite.get("actual_total", 0)

    return output


# ============================================================
# SECTION 5: OUTPUT FORMATTING
# ============================================================

def bar_chart(earned, maximum, width=12):
    """Create a simple bar chart: filled + empty blocks."""
    if maximum == 0:
        return " " * width
    filled = round(earned / maximum * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def print_headline_report(result):
    """Print formatted report for a single headline."""
    composite = compute_composite(result)
    pt_label = result["page_type"] if result["page_type"] else "default"

    is_disqualified = composite["tier"] == "DISQUALIFIED"

    print(f"\n  {'='*69}")

    if is_disqualified:
        print(f"    \u26a0 DISQUALIFIED \u2014 Hard Gate Failure")
        print(f"    HEADLINE: \"{result['headline']}\"")
        for reason in composite.get("disqualification_reasons", []):
            print(f"    Reason: {reason}")
    else:
        print(f"    HEADLINE SCORE: \"{result['headline']}\"")
        print(f"    Page Type: {pt_label}")
        print(f"    Scorer: v{SCORER_VERSION}")

    print(f"  {'='*69}")

    dim_labels = [
        ("information_architecture", "INFORMATION ARCHITECTURE", None),
        ("psychological_triggers", "PSYCHOLOGICAL TRIGGERS", None),
        ("credibility_specificity", "CREDIBILITY & SPECIFICITY", None),
        ("brand_compliance", "BRAND & COMPLIANCE", "[HARD GATE]"),
    ]

    for dim_key, dim_title, suffix in dim_labels:
        tests = result[dim_key]
        earned, maximum, _ = composite["dimensions"][dim_key]
        num_tests = len(tests)

        title_line = f"    {dim_title} ({num_tests} tests, {maximum} pts max)"
        if suffix:
            title_line += f" {suffix}"
        print(f"\n{title_line}")
        print(f"    {'-'*65}")

        for test_id, test_name, weight, (passed, detail, fix_hint) in tests:
            mark = "PASS" if passed else "FAIL"
            pts_label = f"({weight} pt{'s' if weight > 1 else ''})"
            print(f"    [{mark}] {test_id}: {test_name} {pts_label}")
            print(f"           {detail}")

        print(f"    Score: {earned}/{maximum}")

    # Composite
    print(f"\n  {'='*69}")

    if is_disqualified:
        actual = composite.get("actual_total", 0)
        actual_max = composite["max"]
        actual_pct = (actual / actual_max * 100) if actual_max > 0 else 0
        # Determine what tier would have been
        if actual_pct >= 90:
            would_tier = "S"
        elif actual_pct >= 80:
            would_tier = "A"
        elif actual_pct >= 70:
            would_tier = "B"
        elif actual_pct >= 60:
            would_tier = "C"
        else:
            would_tier = "D"
        print(f"    ACTUAL SCORE (without disqualification): "
              f"{actual}/{actual_max} ({actual_pct:.1f}%) \u2014 would be Tier {would_tier}")
    else:
        print(f"    COMPOSITE: {composite['total']}/{composite['max']} ({composite['pct']:.1f}%) "
              f"-- TIER {composite['tier']}")

    print()
    print(f"    Dimension Profile:")
    for dim_key in ["information_architecture", "psychological_triggers",
                     "credibility_specificity", "brand_compliance"]:
        earned, maximum, label = composite["dimensions"][dim_key]
        pct = (earned / maximum * 100) if maximum > 0 else 0
        chart = bar_chart(earned, maximum)
        print(f"      {label + ':':<28} {chart} {earned}/{maximum} ({pct:.0f}%)")
    print()
    print(f"    Tier Scale: S (90%+), A (80-89%), B (70-79%), C (60-69%), D (<60%)")
    print(f"  {'='*69}")

    return composite


# ============================================================
# SECTION 6: BATCH MODE & HOOKBANK ANALYSIS
# ============================================================

def detect_archetype(headline, result):
    """Detect headline archetype using keyword heuristics. Returns set of archetype numbers."""
    hl_lower = headline.lower()
    words = get_words(headline)
    archetypes = set()

    # Archetype 1: Problem Callout -- pain words + "you" address
    pain_found = (any(w in LOSS_PAIN_WORDS for w in words) or
                  any(p in hl_lower for p in ["can't", "won't", "don't"]))
    has_you = "you" in words or "your" in words
    if pain_found and has_you:
        archetypes.add(1)

    # Archetype 2: Identity Callout -- identity nouns + "you are"
    has_identity_noun = any(w in IDENTITY_NOUNS for w in words)
    has_you_are = "you are" in hl_lower or "you're" in hl_lower
    if has_identity_noun and (has_you_are or has_you):
        archetypes.add(2)

    # Archetype 3: Contrarian Claim -- contradiction markers
    contrarian = any(w in hl_lower for w in
                     ["wrong", "myth", "lie", "actually", "truth", "not", "never"])
    if contrarian:
        archetypes.add(3)

    # Archetype 4: Curiosity Gap -- withholding + pointing words
    has_pointing = any(pw in hl_lower for pw in POINTING_WORDS)
    if has_pointing:
        archetypes.add(4)

    # Archetype 5: Safety Warning
    safety_words = {"safe", "safety", "risk", "interaction", "medication", "warning",
                    "danger", "dangerous", "caution"}
    if any(w in words for w in safety_words):
        archetypes.add(5)

    # Archetype 6: Social Proof Lead
    has_number = bool(re.search(r'\d', headline))
    social_words = {"women", "people", "readers", "moms", "mothers", "parents", "families"}
    if has_number and any(w in words for w in social_words):
        archetypes.add(6)

    # Archetype 7: Story/Anecdote
    past_tense = any(w.endswith('ed') and len(w) > 3 for w in words)
    char_refs = any(w in words for w in ["she", "he", "i", "we", "they"])
    if past_tense and char_refs:
        archetypes.add(7)

    # Archetype 8: Direct Benefit -- concrete benefit + number
    has_concrete = any(w in CONCRETE_NOUNS for w in words)
    if has_concrete and has_number:
        archetypes.add(8)

    # Archetype 9: Expert Insight -- authority/credential markers
    authority = {"doctor", "doctors", "expert", "experts", "research", "researcher",
                 "study", "studies", "published", "clinical", "scientist", "scientists"}
    if any(w in words for w in authority):
        archetypes.add(9)

    return archetypes


def detect_beliefs(headline):
    """Detect which belief stages (B1-B8) a headline touches."""
    hl_lower = headline.lower()
    beliefs = set()

    # B1: Herbs work (positive herb framing)
    b1_kw = ["herbs can", "herbal", "traditionally used", "remedy", "natural remedies",
             "herbs have", "plants that", "botanical", "track record", "traditional use",
             "well-documented"]
    if any(k in hl_lower for k in b1_kw):
        beliefs.add("B1")

    # B2: Herbs carry risk
    b2_kw = ["not automatically safe", "interaction", "interfere", "risk", "caution",
             "side effect", "wrong herb", "dangerous", "careful", "too much",
             "natural doesn't mean", "natural isn't"]
    if any(k in hl_lower for k in b2_kw):
        beliefs.add("B2")

    # B3: Info ecosystem is broken
    b3_kw = ["misinformation", "blog posts", "conflicting", "contradictory",
             "information overload", "guesswork", "unreliable", "broken"]
    if any(k in hl_lower for k in b3_kw):
        beliefs.add("B3")

    # B4: You need a reliable reference
    b4_kw = ["reference", "handbook", "guide", "reliable", "trusted", "companion"]
    if any(k in hl_lower for k in b4_kw):
        beliefs.add("B4")

    # B5: This product is that reference
    b5_kw = ["honest herbalist", "this handbook", "this guide", "this book"]
    if any(k in hl_lower for k in b5_kw):
        beliefs.add("B5")

    # B6: Safety-first approach
    b6_kw = ["safety", "safe", "interaction", "dosing", "dose", "medication"]
    if any(k in hl_lower for k in b6_kw):
        beliefs.add("B6")

    # B7: Worth the investment
    b7_kw = ["worth", "value", "investment", "save", "cost", "price", "money"]
    if any(k in hl_lower for k in b7_kw):
        beliefs.add("B7")

    # B8: Act now (consequence urgency)
    b8_kw = ["today", "now", "sooner", "every day", "waiting", "before"]
    if any(k in hl_lower for k in b8_kw):
        beliefs.add("B8")

    return beliefs


def detect_register(headline):
    """Detect emotional register of a headline. Returns register label."""
    words = get_words(headline)

    c_count = sum(1 for w in words if w in CLINICAL_MARKERS)
    e_count = sum(1 for w in words if w in EMPATHETIC_MARKERS)
    p_count = sum(1 for w in words if w in PROVOCATIVE_MARKERS)

    if c_count >= 2 and e_count < 2 and p_count < 2:
        return "clinical"
    elif e_count >= 2 and c_count < 2 and p_count < 2:
        return "empathetic"
    elif p_count >= 2 and c_count < 2 and e_count < 2:
        return "provocative"
    else:
        return "mixed"


def print_batch_report(headlines, page_type=None, output_json=False):
    """Score multiple headlines and print batch analysis."""
    all_results = []
    all_composites = []
    all_archetypes = []
    all_beliefs = []
    all_registers = []
    json_outputs = []

    for hl in headlines:
        hl = hl.strip()
        if not hl:
            continue
        result = score_headline(hl, page_type)
        composite = compute_composite(result)

        if not output_json:
            print_headline_report(result)

        all_results.append(result)
        all_composites.append(composite)

        if output_json:
            json_outputs.append(to_json(result, composite))

        # Collect archetypes
        archetypes = detect_archetype(hl, result)
        all_archetypes.append(archetypes)

        # Collect beliefs
        beliefs = detect_beliefs(hl)
        all_beliefs.append(beliefs)

        # Collect register
        register = detect_register(hl)
        all_registers.append(register)

    if not all_composites:
        if output_json:
            print(json.dumps([], indent=2))
        else:
            print("  No headlines to score.")
        return

    if output_json:
        # Build batch JSON output
        batch_output = _build_batch_json(
            json_outputs, all_composites, all_archetypes,
            all_beliefs, all_registers
        )
        print(json.dumps(batch_output, indent=2))
        return

    # --- Batch summary report (text mode) ---
    _print_batch_summary(all_composites, all_archetypes, all_beliefs, all_registers)


def _build_batch_json(json_outputs, all_composites, all_archetypes,
                      all_beliefs, all_registers):
    """Build batch-level JSON output."""
    # Tier distribution
    tier_counts = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0, "DISQUALIFIED": 0}
    for c in all_composites:
        tier = c["tier"]
        if tier in tier_counts:
            tier_counts[tier] += 1

    disqualified = tier_counts.pop("DISQUALIFIED", 0)

    avg_total = sum(c["total"] for c in all_composites) / len(all_composites)
    avg_max = all_composites[0]["max"]
    avg_pct = avg_total / avg_max * 100 if avg_max > 0 else 0

    # Archetype and belief coverage
    all_arch_union = set()
    for a in all_archetypes:
        all_arch_union.update(a)

    all_belief_union = set()
    for b in all_beliefs:
        all_belief_union.update(b)

    reg_counts = Counter(all_registers)

    # Dimension weakness
    dim_avgs = _compute_dim_averages(all_composites)

    return {
        "headlines": json_outputs,
        "batch_summary": {
            "count": len(all_composites),
            "disqualified": disqualified,
            "tier_distribution": tier_counts,
            "average_composite": {
                "total": round(avg_total, 1),
                "max": avg_max,
                "pct": round(avg_pct, 1),
            },
            "archetype_coverage": sorted(list(all_arch_union)),
            "belief_coverage": sorted(list(all_belief_union)),
            "register_distribution": dict(reg_counts),
            "dimension_averages": dim_avgs,
        },
    }


def _compute_dim_averages(all_composites):
    """Compute average scores per dimension across all composites."""
    dim_keys = ["information_architecture", "psychological_triggers",
                "credibility_specificity", "brand_compliance"]
    dim_avgs = {}
    for dk in dim_keys:
        earned_list = [c["dimensions"][dk][0] for c in all_composites]
        max_val = all_composites[0]["dimensions"][dk][1]
        label = all_composites[0]["dimensions"][dk][2]
        avg_earned = sum(earned_list) / len(earned_list) if earned_list else 0
        avg_pct = (avg_earned / max_val * 100) if max_val > 0 else 0
        dim_avgs[dk] = {
            "label": label,
            "avg_earned": round(avg_earned, 1),
            "max": max_val,
            "avg_pct": round(avg_pct, 1),
        }
    return dim_avgs


def _print_batch_summary(all_composites, all_archetypes, all_beliefs, all_registers):
    """Print text-mode batch summary."""
    # Tier distribution
    tier_counts = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    disqualified = 0
    for c in all_composites:
        tier = c["tier"]
        if tier == "DISQUALIFIED":
            disqualified += 1
        elif tier in tier_counts:
            tier_counts[tier] += 1

    avg_total = sum(c["total"] for c in all_composites) / len(all_composites)
    avg_max = all_composites[0]["max"]
    avg_pct = avg_total / avg_max * 100 if avg_max > 0 else 0

    # Archetype coverage
    all_arch_union = set()
    for a in all_archetypes:
        all_arch_union.update(a)
    arch_coverage = len(all_arch_union)

    # Belief coverage
    all_belief_union = set()
    for b in all_beliefs:
        all_belief_union.update(b)
    belief_coverage = len(all_belief_union)

    # Register diversity
    reg_counts = Counter(all_registers)

    print(f"\n\n  {'='*69}")
    print(f"    HOOKBANK ANALYSIS")
    print(f"  {'='*69}")
    print(f"    Headlines scored: {len(all_composites)}")
    print(f"    Disqualified: {disqualified}")
    tier_str = ", ".join(f"{t}={tier_counts[t]}" for t in ["S", "A", "B", "C", "D"])
    print(f"    Tier distribution: {tier_str}")
    print(f"    Average composite: {avg_total:.1f}/{avg_max} ({avg_pct:.1f}%)")
    print()

    print(f"    Diversity Checks:")
    arch_pass = arch_coverage >= 4
    print(f"    [{'PASS' if arch_pass else 'FAIL'}] Archetype coverage: "
          f"{arch_coverage} of 9 (need 4+)")

    belief_pass = belief_coverage >= 3
    print(f"    [{'PASS' if belief_pass else 'FAIL'}] Belief coverage: "
          f"{belief_coverage} of B1-B8 (need 3+)")

    reg_str = ", ".join(f"{k}={v}" for k, v in sorted(reg_counts.items()))
    reg_diverse = sum(1 for v in reg_counts.values() if v > 0) >= 2
    print(f"    [{'PASS' if reg_diverse else 'FAIL'}] Register diversity: {reg_str}")

    # Dimension weakness report
    print()
    dim_avgs = _compute_dim_averages(all_composites)

    weakest_key = min(dim_avgs, key=lambda k: dim_avgs[k]["avg_pct"])
    strongest_key = max(dim_avgs, key=lambda k: dim_avgs[k]["avg_pct"])

    w = dim_avgs[weakest_key]
    s = dim_avgs[strongest_key]

    print(f"    Dimension Weakness:")
    print(f"    Weakest: {w['label']} \u2014 avg {w['avg_earned']}/{w['max']} ({w['avg_pct']:.0f}%)")
    print(f"    Strongest: {s['label']} \u2014 avg {s['avg_earned']}/{s['max']} ({s['avg_pct']:.0f}%)")
    print(f"  {'='*69}")


# ============================================================
# SECTION 7: CLI INTERFACE
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=f"Deterministic Headline Scorer v{SCORER_VERSION} -- Zero LLM Inference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 headline_scorer_v2.py "Your headline here"
  python3 headline_scorer_v2.py "Your headline here" --page-type listicle
  python3 headline_scorer_v2.py --batch headlines.txt
  python3 headline_scorer_v2.py --batch headlines.txt --page-type sales_page
  python3 headline_scorer_v2.py --json /path/to/listicle.json
  python3 headline_scorer_v2.py "Your headline here" --output-json
        """
    )
    parser.add_argument("headline", nargs="?", help="Headline text to score")
    parser.add_argument("--page-type", choices=["listicle", "advertorial", "sales_page"],
                        default=None, help="Page type for word count targeting")
    parser.add_argument("--batch", metavar="FILE",
                        help="Score multiple headlines from a file (one per line)")
    parser.add_argument("--json", metavar="FILE",
                        help="Score headline from a JSON file (extracts hero.title)")
    parser.add_argument("--output-json", action="store_true",
                        help="Output machine-readable JSON (for headline_qa_loop.py)")

    args = parser.parse_args()

    if args.batch:
        # Batch mode
        try:
            with open(args.batch, 'r') as f:
                headlines = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"  ERROR: File not found: {args.batch}")
            sys.exit(1)

        if not headlines:
            print("  ERROR: No headlines found in file.")
            sys.exit(1)

        print_batch_report(headlines, args.page_type, output_json=args.output_json)

    elif args.json:
        # JSON mode -- extract hero.title
        try:
            with open(args.json, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"  ERROR: File not found: {args.json}")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"  ERROR: Invalid JSON: {args.json}")
            sys.exit(1)

        headline = data.get("page", {}).get("hero", {}).get("title", "")
        if not headline:
            headline = data.get("hero", {}).get("title", "")
        if not headline:
            headline = data.get("title", "")
        if not headline:
            print("  ERROR: Could not find headline in JSON "
                  "(looked for page.hero.title, hero.title, title)")
            sys.exit(1)

        result = score_headline(headline, args.page_type)
        composite = compute_composite(result)

        if args.output_json:
            print(json.dumps(to_json(result, composite), indent=2))
        else:
            print_headline_report(result)

    elif args.headline:
        # Single headline mode
        result = score_headline(args.headline, args.page_type)
        composite = compute_composite(result)

        if args.output_json:
            print(json.dumps(to_json(result, composite), indent=2))
        else:
            print_headline_report(result)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
