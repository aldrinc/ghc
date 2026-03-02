from app.services.compliance import markdown_to_shopify_html


def test_markdown_to_shopify_html_renders_bold_and_hard_breaks():
    markdown = (
        "# Privacy Policy\n\n"
        "**Brand:** Radiant  \n"
        "**Operator:** Radiant  \n"
        "**Contact:** example@gmail.com\n"
    )

    html = markdown_to_shopify_html(markdown)

    assert "<h1>Privacy Policy</h1>" in html
    assert "<strong>Brand:</strong> Radiant<br/>" in html
    assert "<strong>Operator:</strong> Radiant<br/>" in html
    assert "<strong>Contact:</strong> example@gmail.com" in html
    assert "**Brand:**" not in html

