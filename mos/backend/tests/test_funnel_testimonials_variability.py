import pytest

from app.services import funnel_testimonials


def test_social_comment_without_attachment_indices_empty_for_small_totals():
    assert funnel_testimonials._select_social_comment_without_attachment_indices(0, seed=123) == set()
    assert funnel_testimonials._select_social_comment_without_attachment_indices(1, seed=123) == set()


def test_social_comment_without_attachment_indices_selects_some_but_not_all():
    indices = funnel_testimonials._select_social_comment_without_attachment_indices(8, seed=123)
    assert indices
    assert len(indices) < 8
    assert all(0 <= idx < 8 for idx in indices)
    assert indices == funnel_testimonials._select_social_comment_without_attachment_indices(8, seed=123)


def test_review_card_without_hero_indices_empty_for_small_totals():
    assert funnel_testimonials._select_review_card_without_hero_indices(0, seed=123) == set()
    assert funnel_testimonials._select_review_card_without_hero_indices(1, seed=123) == set()


def test_review_card_without_hero_indices_selects_some_but_not_all():
    indices = funnel_testimonials._select_review_card_without_hero_indices(10, seed=123)
    assert indices
    assert len(indices) < 10
    assert all(0 <= idx < 10 for idx in indices)
    assert indices == funnel_testimonials._select_review_card_without_hero_indices(10, seed=123)


def test_variability_index_selectors_reject_negative_totals():
    with pytest.raises(funnel_testimonials.TestimonialGenerationError):
        funnel_testimonials._select_social_comment_without_attachment_indices(-1, seed=123)

    with pytest.raises(funnel_testimonials.TestimonialGenerationError):
        funnel_testimonials._select_review_card_without_hero_indices(-1, seed=123)

