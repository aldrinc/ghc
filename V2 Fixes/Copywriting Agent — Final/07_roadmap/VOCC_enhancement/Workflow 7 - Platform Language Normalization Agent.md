# Workflow 7: Platform Language Normalization Agent

## Agent Identity

**Role:** Platform Linguistics Specialist
**Narrow Job:** Analyze the platform-specific linguistic characteristics of VOC items within a corpus and produce platform-aware annotations that downstream copywriting agents use to match creative language to platform norms. Additionally, identify when the same emotional concept appears across multiple platforms in different linguistic registers — a cross-platform validation signal that strengthens the concept's reliability.

**Why This Agent Exists (First Principles):**
People write differently on TikTok than they do on YouTube than they do on Reddit. This isn't noise — it's signal. The linguistic register a person uses on a platform tells you how to speak to them *on that platform*.

A TikTok user who writes "this literally SAVED me omg" and a YouTube user who writes "After researching for months, I finally found a protocol that worked for my insomnia" may be describing the same experience. But if you're writing a TikTok ad, you need the TikTok register. If you're writing YouTube pre-roll, you need the YouTube register.

The top media buyers at DR companies intuitively know this — they write different hooks for different platforms. But the research pipeline that feeds those hooks is usually platform-agnostic. It treats a TikTok comment and a YouTube comment as interchangeable data points. They're not.

This agent adds the platform-awareness layer that makes your VOCC system produce platform-native creative — not generic copy that gets reformatted for each platform.

**Important framing:** This agent does NOT override brand voice. There's a tension between "match platform language" and "maintain brand consistency." This agent provides the platform-linguistic data; the downstream copywriting agents resolve the tension using Voice & Tone Operating Rules alongside this data. More on this below.

---

## Inputs

| Input | Source | Required? |
|---|---|---|
| Classified, scored VOC items (with platform tags) | Outputs from Workflows 1, 2, and 4 | Yes |
| Language Bank per angle | Workflow 5 output | Yes |
| Angle definition | Purple Ocean Scorecard / Angle Selection output | Yes |
| Target ad platforms | User-defined (where ads will run) | Yes |

---

## Outputs

### Output 1: Platform Linguistic Profile (per corpus)

A characterization of how the audience speaks on each platform, derived from the VOC data:

```
PLATFORM LINGUISTIC PROFILE: [Angle Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TIKTOK (n=95 VOC items from this platform):
  Avg comment length: 12 words
  Dominant tone: Hyperbolic, reactive, community-referencing
  Formality level: Very informal (1/5)
  Common patterns:
    - Sentence fragments > complete sentences
    - Heavy emoji use as emphasis (not decoration)
    - Superlatives as default ("literally the best", "this
      changed EVERYTHING")
    - Direct address to creator common ("you need to do a
      part 2 on this")
    - All-caps for emphasis, not anger
    - Abbreviated language common (pls, bc, tbh, ngl)
  Emotional expression style: External, performative, group-
    validated ("everyone needs to hear this")
  Authenticity signal: When a TikTok comment breaks the
    hyperbolic norm and becomes measured/specific, it's often
    the most genuine item in the batch

YOUTUBE (n=120 VOC items from this platform):
  Avg comment length: 38 words
  Dominant tone: Narrative, considered, experience-sharing
  Formality level: Moderate informal (2.5/5)
  Common patterns:
    - Complete sentences and paragraphs
    - Personal stories structured with beginning/middle/end
    - Time markers common ("I've been doing this for 6 months")
    - Questions directed at other commenters or the creator
    - Numbered lists for multi-point responses
    - Less emoji, more punctuation for emphasis
  Emotional expression style: Internal, reflective, experience-
    anchored ("here's what happened to me")
  Authenticity signal: Long, detailed personal narratives with
    specific timeframes and outcomes

INSTAGRAM (n=70 VOC items from this platform):
  Avg comment length: 18 words
  Dominant tone: Aspirational, identity-affirming, community-
    building
  Formality level: Informal (2/5)
  Common patterns:
    - Tagging friends ("@sarah you need this")
    - Identity affirmation ("this is so me", "my herbalism
      journey in a nutshell")
    - Heart and plant emojis as emphasis
    - Short affirming statements ("needed this today")
    - Aesthetically-oriented language (visual references)
  Emotional expression style: Curated, identity-projecting,
    community-signaling
  Authenticity signal: When an Instagram comment drops the
    aspirational tone and shares a genuine struggle or failure

REDDIT (n=85 VOC items from this platform):
  Avg comment length: 62 words
  Dominant tone: Analytical, debate-oriented, evidence-citing
  Formality level: Moderate (3/5)
  Common patterns:
    - Qualifying statements ("in my experience", "YMMV",
      "take this with a grain of salt")
    - Source citations (linking studies, referencing books)
    - Counter-arguments and nuance ("but on the other hand")
    - Community norms enforcement ("always consult a
      professional before...")
    - Threaded debate (point/counterpoint)
  Emotional expression style: Intellectual-emotional blend
    (emotion expressed through analysis and story, not through
    superlatives)
  Authenticity signal: When a normally analytical commenter
    drops into raw emotional language — this is the highest-
    charge VOC on Reddit
```

---

### Output 2: Platform-Weighted Language Bank Annotations

For each item in the Language Bank (from Workflow 5), add platform annotations:

```
{
  "phrase": "lying there replaying the day at 2am",
  "source_platform": "reddit",
  "platform_register": "reflective_narrative",

  // === ADDED BY THIS AGENT ===
  "platform_usage_map": {
    "tiktok_ad": {
      "usable_as_is": false,
      "adapted_version": "that 2am thing where ur brain won't shut off",
      "adaptation_notes": "Shortened, made more conversational, added 'that [thing]' TikTok pattern. Emotional core preserved.",
      "confidence": "HIGH — pattern validated by 12+ TikTok comments expressing the same concept in similar register"
    },
    "youtube_ad": {
      "usable_as_is": true,
      "adapted_version": null,
      "adaptation_notes": "Reddit narrative register maps well to YouTube. Use as-is in pre-roll VO or body copy.",
      "confidence": "HIGH"
    },
    "meta_ad": {
      "usable_as_is": true,
      "adapted_version": null,
      "adaptation_notes": "Works for Meta feed ads. Slightly more formal than TikTok but less formal than landing page.",
      "confidence": "MEDIUM"
    },
    "landing_page": {
      "usable_as_is": true,
      "adapted_version": null,
      "adaptation_notes": "Perfect register for landing page copy. Specific, vivid, relatable.",
      "confidence": "HIGH"
    }
  }
}
```

**Critical rule for adaptation:** When adapting language for a different platform register, the agent MUST preserve the emotional core — the specific pain, desire, image, or insight. What changes is the delivery: word choice, sentence length, formality, punctuation style. What never changes is the emotional truth.

**The adaptation spectrum:**
- "Usable as-is" = the original register matches the target platform
- "Light adaptation" = minor tweaks (adding/removing abbreviations, adjusting formality by one notch)
- "Register shift" = rewriting the delivery while preserving the emotional core
- "Not adaptable" = the phrase is so platform-specific that transplanting it would feel inauthentic (rare, but possible — e.g., a Reddit in-joke)

---

### Output 3: Cross-Platform Validation Report

When the same emotional concept appears on multiple platforms in different linguistic registers, that's a signal of genuine, widespread audience resonance. This report identifies those cross-platform validations:

```
CROSS-PLATFORM VALIDATION: [Angle Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONCEPT: "Fear of accidentally harming child with wrong herb/dose"
Platforms: TikTok (4 items), YouTube (7 items), Reddit (5 items), Instagram (2 items)
Total independent mentions: 18
Validation strength: VERY HIGH (4 platforms, 18 independent mentions)

Platform expressions:
  TikTok: "omg the thought of giving my baby the wrong herb literally terrifies me"
  YouTube: "As a mom of two, my biggest fear is accidentally giving them something that interacts with their medication. I spent months researching before I felt confident enough to even try chamomile."
  Reddit: "PSA for new parents getting into herbalism: please, PLEASE research contraindications before giving herbs to children. Dosing for kids is not just 'half the adult dose' — some herbs are flat-out unsafe under certain ages."
  Instagram: "that feeling when you want to go natural for your kids but you're scared you'll mess up"

Synthesis: This concept is a core audience anxiety that transcends platform culture. The emotional truth is identical; only the expression varies. This is a HIGH-CONFIDENCE angle territory for creative development.

Creative implication: Any creative built on this territory should perform across platforms (with platform-appropriate language adaptation).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONCEPT: "Frustration with conflicting information across herb sources"
Platforms: YouTube (9 items), Reddit (12 items)
Total independent mentions: 21
Validation strength: HIGH (2 platforms, 21 mentions — but notably ABSENT from TikTok/Instagram)

Platform expressions:
  YouTube: "I have 10 herb books and every one says something slightly different. It's exhausting."
  Reddit: "The amount of contradictory information in herbalism is staggering. One source says X is safe, another says it's toxic. How is a beginner supposed to navigate this?"

Synthesis: Strong concept but platform-skewed. The information-overload frustration resonates most with longer-form, analytical audiences (YouTube + Reddit). TikTok/Instagram audiences may not express this pain because the platform format doesn't encourage detailed complaints about information quality.

Creative implication: This territory is strongest for YouTube ads and landing page copy. May underperform as a TikTok hook (test required — the audience may feel it but not express it on TikTok).
```

---

## The Platform-Brand Voice Tension

### The Core Tension:

Your brand has a defined voice (from Voice & Tone Operating Rules). Your audience speaks differently on different platforms. When writing a TikTok ad for your brand, do you match TikTok's hyper-casual register or maintain your brand's measured, honest-expert voice?

### How This Agent Handles It:

This agent does NOT resolve the tension. It provides the data. The resolution is the downstream copywriting agent's job, guided by the Voice & Tone Operating Rules. But this agent provides the framework:

**The Platform-Voice Compatibility Matrix:**

| Brand Voice Element | TikTok Compatibility | YouTube Compatibility | Instagram Compatibility | Meta Feed Compatibility |
|---|---|---|---|---|
| Measured honesty | LOW (TikTok rewards bold claims) — adapt by using bold phrasing for honest claims | HIGH (YouTube rewards depth) | MEDIUM | MEDIUM-HIGH |
| Specific language | MEDIUM (TikTok likes specifics but in casual delivery) | HIGH | MEDIUM | HIGH |
| Safety-first positioning | MEDIUM (can work as pattern interrupt: "wait, did you know this can actually be dangerous?") | HIGH (educational framing natural) | MEDIUM | HIGH |
| Conversational formality | Needs to drop 1-2 formality notches for TikTok | Good as-is | Drop 0.5-1 notch | Good as-is |
| Humor/personality | TikTok expects more personality | YouTube accepts range | Instagram expects curated personality | Meta is flexible |

**The rule this agent provides to downstream agents:**
"Match platform register for the DELIVERY. Maintain brand voice for the SUBSTANCE. If the brand voice says 'never use superlatives,' you don't write 'literally the BEST herb book ever' on TikTok. But you can write 'ngl this is the herb book I wish I had when I started' — which is casual TikTok register but honest brand substance."

---

## Agent Prompt (The Operational Instruction)

```
SYSTEM:

You are the Platform Language Normalization Agent. Your job is
to analyze the platform-specific linguistic characteristics of
VOC items, annotate Language Bank entries with platform-specific
usage guidance, and identify cross-platform validation signals.

You receive classified, scored VOC items with platform tags,
plus the Language Bank from Workflow 5. You:

1. Build a Platform Linguistic Profile for each platform
   represented in the corpus (characterize how the audience
   speaks on each platform)
2. Annotate each Language Bank item with platform-specific
   usage guidance (usable as-is, needs adaptation, suggested
   adaptation, confidence level)
3. Identify cross-platform validated concepts (same emotional
   concept expressed on 2+ platforms) and report validation
   strength
4. Provide the Platform-Voice Compatibility Matrix so
   downstream agents understand how to balance platform
   register with brand voice

WHEN ADAPTING LANGUAGE:
- ALWAYS preserve the emotional core (the specific pain,
  desire, image, or insight)
- ONLY change the delivery (word choice, sentence length,
  formality, punctuation style)
- NEVER fabricate platform-specific language that wasn't in
  the corpus. If you don't have TikTok VOC expressing a
  concept, say "no TikTok expression found" — don't invent
  one
- When suggesting adaptations, note confidence level:
  HIGH = pattern validated by 3+ corpus items on that platform
  MEDIUM = pattern validated by 1-2 items
  LOW = adaptation is inferred from platform norms, not
  validated by corpus data

INPUTS:
- Classified + scored VOC items with platform tags: [INSERT]
- Language Bank: [INSERT]
- Angle definition: [INSERT]
- Target ad platforms: [INSERT]

OUTPUTS:
1. Platform Linguistic Profile (per platform)
2. Platform-Weighted Language Bank Annotations
3. Cross-Platform Validation Report
4. Platform-Voice Compatibility Matrix

QUALITY RULES:
- Never stereotype a platform. Your linguistic profile must
  be derived from the ACTUAL corpus data, not from assumptions
  about "how people talk on TikTok." If your TikTok corpus
  is unusually formal, report that — don't force it to match
  the expected pattern.
- Cross-platform validation requires INDEPENDENT mentions
  (not the same user posting on multiple platforms, not
  quotes shared across platforms).
- When the corpus has <20 items from a platform, label
  that platform's profile as "LOW CONFIDENCE — small sample"
  and note that patterns may not be representative.
- Platform adaptation suggestions must be tasteful. Never
  suggest "dumbing down" language — suggest translating it
  to the platform's native register, which is a different
  thing entirely.
```

---

## Tools This Agent Has Access To

| Tool | Purpose | Access Level |
|---|---|---|
| Read (classified + scored VOC with platform tags) | Analyze platform-specific linguistic patterns | Read-only |
| Read (Language Bank) | Annotate extractions with platform guidance | Read-only |
| Read (Voice & Tone Operating Rules) | Reference brand voice constraints for compatibility matrix | Read-only |
| Write (Platform Linguistic Profile) | Output platform characterization | Write (new file) |
| Write (Platform-Annotated Language Bank) | Output annotated language bank | Write (new file) |
| Write (Cross-Platform Validation Report) | Output validation analysis | Write (new file) |

**Tools explicitly NOT available:** Web search, scraping, ad platform APIs, copy generation. This agent analyzes and annotates. It does not produce creative.

---

## Evaluation Criteria

### Platform Profile Accuracy:

| Criterion | Pass | Fail |
|---|---|---|
| Data-derived | Profile is based on actual corpus statistics (avg length, tone distribution, pattern frequency) | Profile reads like a generic description of the platform without corpus-specific data |
| Sample size noted | Each platform profile includes sample size and confidence | No sample size context — a profile based on 8 items presented with same confidence as one based on 120 |
| Pattern examples | Each claimed pattern includes 2+ corpus examples | Patterns asserted without evidence |
| Surprises noted | If the corpus deviates from expected platform norms, this is flagged and analyzed | Unexpected patterns ignored or forced to match assumptions |

### Language Bank Annotation Quality:

| Criterion | Pass | Fail |
|---|---|---|
| Emotional core preserved | Every suggested adaptation preserves the original phrase's emotional truth | Adaptation loses the specificity, imagery, or emotional charge |
| Confidence calibrated | HIGH confidence backed by 3+ corpus examples; LOW labeled when inferred | All items marked HIGH regardless of evidence |
| "Not adaptable" used when appropriate | Some items acknowledged as platform-specific or not transferable | Every item forced into every platform |
| Brand voice compatible | Suggested adaptations don't violate Voice & Tone Operating Rules | Adaptations use language that's on the brand's banned list |

### Cross-Platform Validation Quality:

| Criterion | Pass | Fail |
|---|---|---|
| Independence verified | Cross-platform matches are genuinely independent (different users, different contexts) | Same quote or user counted across platforms |
| Synthesis is insight, not summary | The synthesis explains WHY the concept resonates across platforms and what this means for creative | Synthesis just restates that the concept appeared on multiple platforms |
| Absent-platform analysis | When a concept is absent from a platform, the agent hypothesizes why (platform culture, audience segment, expression style) | Absences ignored |

---

## Downstream Consumers

| Consumer Agent | What It Receives |
|---|---|
| TikTok Creative Agent | Platform profile + TikTok-specific annotations + cross-platform validations |
| YouTube Creative Agent | Platform profile + YouTube-specific annotations + cross-platform validations |
| Meta/Instagram Creative Agent | Platform profile + Meta/IG-specific annotations + cross-platform validations |
| Landing Page Agent | Cross-platform validated concepts (strongest territories for platform-agnostic copy) |
| Ad Strategy/Media Buying | Cross-platform validation report (which concepts to test on which platforms) |
| Angle Dossier Assembly | All outputs as a "Platform Intelligence" section of the dossier |

---

## Why This Matters From a DR First Principles Perspective

The best media buyers think in platform-native creative. They don't make one ad and resize it — they make platform-specific creative that feels like it belongs in the feed. A TikTok ad that looks and sounds like a TikTok. A YouTube pre-roll that respects the YouTube viewer's expectations. An Instagram ad that matches the visual and linguistic style of the content it interrupts.

This principle extends to language. The words that stop a scroll on TikTok are different from the words that hold attention on YouTube. Not because the audience is different (often it's the same person on different platforms), but because the *mode of consumption* is different. On TikTok, you scan fast and react emotionally. On YouTube, you settle in and evaluate. On Reddit, you analyze and debate.

Your VOC corpus captures how your audience expresses themselves in each of these modes. This agent extracts that platform-specific expression data and makes it available to the creative agents who need to write for each platform.

Without this agent, you produce platform-generic copy that gets the emotional territory right but the delivery wrong. With it, you produce platform-native copy that feels like it was written by someone who lives on that platform — because in a sense, it was. It was written from the language of people who actually do.
