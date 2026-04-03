from app.services.html_funnel_reference import (
    HtmlReferenceError,
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
    assert "htmlPreview" not in prompt_context


def test_summarize_html_reference_rejects_blank_html() -> None:
    try:
        summarize_html_reference(reference_html="   ")
    except HtmlReferenceError as exc:
        assert "non-empty" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected HtmlReferenceError for blank HTML reference.")
