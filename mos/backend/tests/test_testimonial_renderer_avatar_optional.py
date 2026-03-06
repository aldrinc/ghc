import threading

import pytest

from app.testimonial_renderer.validate import validate_payload
from app.testimonial_renderer import renderer


def test_social_comment_allows_missing_avatar_url():
    payload = {
        "template": "social_comment",
        "header": {"title": "All comments", "showSortIcon": True},
        "comments": [
            {
                "name": "Jamie Park",
                "text": "This helped a lot.",
                "meta": {"time": "2d"},
                "reactionCount": 3,
                # avatarUrl intentionally omitted
            }
        ],
    }

    validated = validate_payload(payload)
    assert validated["comments"][0]["avatarUrl"] is None


def test_social_comment_no_header_allows_missing_avatar_url():
    payload = {
        "template": "social_comment_no_header",
        "comments": [
            {
                "name": "Jamie Park",
                "text": "This helped a lot.",
                "meta": {"time": "2d"},
                # avatarUrl intentionally omitted
            }
        ],
    }

    validated = validate_payload(payload)
    assert validated["comments"][0]["avatarUrl"] is None


def test_social_comment_instagram_allows_missing_avatar_url_in_post_and_comments():
    payload = {
        "template": "social_comment_instagram",
        "post": {
            "username": "jamie.park",
            # avatarUrl intentionally omitted
            "likeCount": 12,
            "dateLabel": "2026-02-17",
        },
        "comments": [
            {
                "name": "Jamie Park",
                "text": "This helped a lot.",
                "meta": {"time": "2d"},
                # avatarUrl intentionally omitted
            }
        ],
    }

    validated = validate_payload(payload)
    assert validated["post"]["avatarUrl"] is None
    assert validated["comments"][0]["avatarUrl"] is None


def test_pdp_ugc_standard_defaults_avatar_and_accepts_prompt_vars_background():
    payload = {
        "template": "pdp_ugc_standard",
        "output": {"preset": "feed"},
        "brand": {
            "logoText": "SampleLogo",
            "stripBgColor": "#be3b7a",
            "stripTextColor": "#ffffff",
        },
        "rating": {"valueText": "4.9/5", "detailText": "Rated by 10,000+ Customers"},
        "cta": {"text": "BUY ONE, GET ONE FREE TODAY!"},
        "background": {
            "promptVars": {
                "product": "a supplement bottle with a pink label",
                "scene": "indoors at home",
            }
        },
        "comment": {
            "handle": "ValleyGirl64",
            "text": "The product worked really well for me.",
            "avatarUrl": "",
        },
    }

    validated = validate_payload(payload)
    assert validated["output"]["preset"] == "feed"
    assert validated["background"]["promptVars"]["product"] == "a supplement bottle with a pink label"
    assert validated["comment"]["avatarUrl"].startswith("file://")


def test_pdp_ugc_standard_accepts_square_output_preset():
    payload = {
        "template": "pdp_ugc_standard",
        "output": {"preset": "square"},
        "brand": {
            "logoText": "SampleLogo",
            "stripBgColor": "#be3b7a",
            "stripTextColor": "#ffffff",
        },
        "rating": {"valueText": "4.9/5", "detailText": "Rated by 10,000+ Customers"},
        "cta": {"text": "SEE WHY PEOPLE SWITCHED"},
        "background": {
            "promptVars": {
                "product": "a supplement bottle on a bathroom counter",
                "scene": "morning natural light",
            }
        },
        "comment": {
            "handle": "realuser42",
            "text": "This finally fit into my routine.",
        },
    }

    validated = validate_payload(payload)
    assert validated["output"]["preset"] == "square"


def test_pdp_square_preset_requests_square_background_generation(monkeypatch):
    observed: dict[str, str] = {}

    def fake_generate_nano_image_bytes(*, model, prompt, image_config, reference_images, reference_first, base_dir):
        observed["model"] = model
        observed["aspect_ratio"] = str(image_config.get("aspectRatio"))
        return b"\x89PNG\r\n\x1a\n", "image/png"

    monkeypatch.setattr(renderer, "_generate_nano_image_bytes", fake_generate_nano_image_bytes)

    payload = {
        "template": "pdp_ugc_standard",
        "output": {"preset": "square"},
        "brand": {
            "logoText": "SampleLogo",
            "stripBgColor": "#be3b7a",
            "stripTextColor": "#ffffff",
        },
        "rating": {"valueText": "4.9/5", "detailText": "Rated by 10,000+ Customers"},
        "cta": {"text": "SEE WHY PEOPLE SWITCHED"},
        "background": {
            "promptVars": {
                "product": "a supplement bottle on a bathroom counter",
                "scene": "morning natural light",
            },
            "imageModel": "test-model",
        },
        "comment": {
            "handle": "realuser42",
            "text": "This finally fit into my routine.",
        },
    }

    output = renderer.maybe_generate_pdp_background(payload)
    assert observed["model"] == "test-model"
    assert observed["aspect_ratio"] == "1:1"
    assert output["background"]["imageUrl"].startswith("data:image/png;base64,")


def test_threaded_renderer_requires_positive_worker_count():
    with pytest.raises(renderer.TestimonialRenderError, match="worker_count must be >= 1"):
        renderer.ThreadedTestimonialRenderer(worker_count=0)


def test_threaded_renderer_times_out_when_no_worker_response():
    threaded = renderer.ThreadedTestimonialRenderer(response_timeout_ms=10)
    # Simulate a started renderer without an active worker loop.
    threaded._threads = [threading.Thread(name="dead-renderer-worker")]

    with pytest.raises(renderer.TestimonialRenderError, match="Timed out waiting for testimonial renderer output"):
        threaded.render_png({"template": "review_card"})
