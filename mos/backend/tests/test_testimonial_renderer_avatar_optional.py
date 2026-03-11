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


def test_pdp_ugc_standard_accepts_dual_comments():
    payload = {
        "template": "pdp_ugc_standard",
        "output": {"preset": "feed"},
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
        "comments": [
            {
                "handle": "skeptical_user",
                "text": "Is this actually worth it?",
                "verified": True,
            },
            {
                "handle": "realuser42",
                "text": "It gave me a clear checklist instead of more guesswork.",
                "verified": True,
            },
        ],
    }

    validated = validate_payload(payload)
    assert len(validated["comments"]) == 2
    assert validated["comment"]["handle"] == "skeptical_user"
    assert validated["comments"][1]["handle"] == "realuser42"


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


def test_pdp_background_prompt_file_is_hydrated(tmp_path):
    prompt_file = tmp_path / "pdp-structure.md"
    prompt_file.write_text("Structured prompt from file.", encoding="utf-8")

    payload = {
        "template": "pdp_ugc_standard",
        "output": {"preset": "feed"},
        "brand": {
            "logoText": "SampleLogo",
            "stripBgColor": "#be3b7a",
            "stripTextColor": "#ffffff",
        },
        "rating": {"valueText": "4.9/5", "detailText": "Rated by 10,000+ Customers"},
        "cta": {"text": "SEE WHY PEOPLE SWITCHED"},
        "background": {
            "promptFile": "pdp-structure.md",
        },
        "comment": {
            "handle": "realuser42",
            "text": "This finally fit into my routine.",
        },
    }

    validated = validate_payload(payload, base_dir=tmp_path)
    assert validated["background"]["prompt"] == "Structured prompt from file."
    assert validated["background"]["promptVars"] is None


def test_pdp_background_generation_uses_prompt_from_hydrated_prompt_file(monkeypatch, tmp_path):
    prompt_file = tmp_path / "pdp-structure.md"
    prompt_file.write_text("Structured prompt from file.", encoding="utf-8")
    observed: dict[str, str] = {}

    def fake_generate_nano_image_bytes(*, model, prompt, image_config, reference_images, reference_first, base_dir):
        observed["model"] = model
        observed["prompt"] = prompt
        observed["aspect_ratio"] = str(image_config.get("aspectRatio"))
        return b"\x89PNG\r\n\x1a\n", "image/png"

    monkeypatch.setattr(renderer, "_generate_nano_image_bytes", fake_generate_nano_image_bytes)

    payload = {
        "template": "pdp_ugc_standard",
        "output": {"preset": "feed"},
        "brand": {
            "logoText": "SampleLogo",
            "stripBgColor": "#be3b7a",
            "stripTextColor": "#ffffff",
        },
        "rating": {"valueText": "4.9/5", "detailText": "Rated by 10,000+ Customers"},
        "cta": {"text": "SEE WHY PEOPLE SWITCHED"},
        "background": {
            "promptFile": "pdp-structure.md",
            "imageModel": "test-model",
        },
        "comment": {
            "handle": "realuser42",
            "text": "This finally fit into my routine.",
        },
    }

    validated = validate_payload(payload, base_dir=tmp_path)
    output = renderer.maybe_generate_pdp_background(validated)

    assert observed["model"] == "test-model"
    assert observed["prompt"].startswith("Structured prompt from file.")
    assert "Logo text: SampleLogo." in observed["prompt"]
    assert "Primary brand color: #be3b7a." in observed["prompt"]
    assert "Contrast text color: #ffffff." in observed["prompt"]
    assert observed["aspect_ratio"] == "4:5"
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
