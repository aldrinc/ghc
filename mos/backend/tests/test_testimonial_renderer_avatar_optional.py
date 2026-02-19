from app.testimonial_renderer.validate import validate_payload


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

