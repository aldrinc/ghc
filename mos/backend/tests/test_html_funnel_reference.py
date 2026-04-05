from app.services.html_funnel_reference import (
    HtmlReferenceError,
    HtmlStructureMismatchError,
    MAX_TEXT_PREVIEW_CHARS,
    assert_html_text_only_rewrite,
    build_html_reference_prompt_context,
    summarize_html_reference,
)


def test_summarize_html_reference_extracts_conversion_structure() -> None:
    html = """
    <!doctype html>
    <html lang="en">
      <head>
        <title>Deep Sleep Blueprint</title>
        <meta name="description" content="A printable guide for better sleep." />
      </head>
      <body>
        <header>
          <a href="#hero">See How It Works</a>
          <a href="#faq">FAQ</a>
        </header>
        <main>
          <section id="hero">
            <h1>Fall asleep without melatonin</h1>
            <p>Trusted by 10,000 readers.</p>
            <a href="/checkout">Get My Guide</a>
          </section>
          <section id="problem">
            <h2>Why this works</h2>
            <p>Simple routines, printable checklists, and calming bedtime prompts.</p>
          </section>
          <section id="proof">
            <h2>Reviews</h2>
            <p>4.9 stars from verified customers.</p>
          </section>
          <section id="faq">
            <h2>Frequently asked questions</h2>
            <button>Is it printable?</button>
          </section>
          <form action="/subscribe" method="post">
            <input type="email" name="email" placeholder="Email address" />
            <button>Claim My Offer</button>
          </form>
          <img src="/hero.jpg" alt="Sleep guide cover" />
        </main>
        <footer>60-day guarantee.</footer>
      </body>
    </html>
    """

    summary = summarize_html_reference(reference_html=html, label="sleep-guide.html")
    prompt_context = build_html_reference_prompt_context(summary)

    assert summary.label == "sleep-guide.html"
    assert summary.title == "Deep Sleep Blueprint"
    assert summary.metaDescription == "A printable guide for better sleep."
    assert summary.sectionOrder[:4] == [
        "Fall asleep without melatonin",
        "Why this works",
        "Reviews",
        "Frequently asked questions",
    ]
    assert "Get My Guide" in summary.ctaTexts
    assert "Claim My Offer" in summary.ctaTexts
    assert "Is it printable?" in summary.faqQuestions
    assert "Reviews / ratings" in summary.proofSignals
    assert "Guarantee / refund" in summary.proofSignals
    assert summary.imageCount == 1
    assert summary.imageAltTexts == ["Sleep guide cover"]
    assert summary.formCount == 1
    assert "email: Email address" in summary.formFieldHints
    assert "Fall asleep without melatonin" in summary.textPreview
    assert prompt_context["sectionOrder"] == summary.sectionOrder
    assert prompt_context["imageCount"] == 1
    assert prompt_context["htmlPreview"].startswith("<!doctype html>")


def test_summarize_html_reference_rejects_blank_html() -> None:
    try:
        summarize_html_reference(reference_html="   ")
    except HtmlReferenceError as exc:
        assert "non-empty" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected HtmlReferenceError for blank HTML reference.")


def test_summarize_html_reference_clips_long_text_preview_without_validation_error() -> None:
    repeated = " ".join(f"Section {index} conversion proof guarantee faq" for index in range(120))
    html = f"<html><body><main><section><h1>Hero</h1><p>{repeated}</p></section></main></body></html>"

    summary = summarize_html_reference(reference_html=html, label="long.html")

    assert summary.label == "long.html"
    assert len(summary.textPreview) <= MAX_TEXT_PREVIEW_CHARS
    assert summary.textPreview


def test_assert_html_text_only_rewrite_allows_text_changes_only() -> None:
    original = "<!doctype html><html><body><section><h1>Original title</h1><p>Original body.</p></section></body></html>"
    rewritten = "<!doctype html><html><body><section><h1>Updated title</h1><p>Updated body.</p></section></body></html>"

    assert_html_text_only_rewrite(original_html=original, rewritten_html=rewritten)


def test_assert_html_text_only_rewrite_rejects_attribute_or_structure_changes() -> None:
    original = "<!doctype html><html><body><section class='hero'><h1>Original title</h1></section></body></html>"
    rewritten = "<!doctype html><html><body><section class='hero-alt'><h1>Updated title</h1></section></body></html>"

    try:
        assert_html_text_only_rewrite(original_html=original, rewritten_html=rewritten)
    except HtmlStructureMismatchError as exc:
        assert "Only visible text content may change" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected HtmlStructureMismatchError for attribute changes.")
