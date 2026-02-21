from __future__ import annotations

from copy import deepcopy

from app.services.design_system_generation import (
    _required_css_var_keys,
    _validate_tokens,
    load_base_tokens_template,
)


def test_validate_tokens_accepts_base_template():
    tokens = deepcopy(load_base_tokens_template())
    required = _required_css_var_keys()
    assert _validate_tokens(tokens, required_css_vars=required) == tokens


def test_validate_tokens_allows_dark_data_theme():
    tokens = deepcopy(load_base_tokens_template())
    tokens["dataTheme"] = "dark"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_dark_primary_background():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-page-bg"] = "#111827"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_dark_primary_background_var_reference():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-page-bg"] = "var(--pdp-video-bg)"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_transparent_dark_rgb_when_alpha_keeps_it_light():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-page-bg"] = "rgba(0, 0, 0, 0.06)"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_light_gradient_surface():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--hero-bg"] = "linear-gradient(135deg, #fff5f9 0%, #ffe8f1 100%)"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_body_text_coupled_to_brand():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-text"] = "var(--color-brand)"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_low_contrast_muted_text():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-muted"] = "#cbd5e1"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_muted_text_coupled_to_brand():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-muted"] = "var(--color-brand)"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_layout_token_change():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--hero-min-height"] = "600px"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_unlocked_template_style_token_change():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--radius-md"] = "28px"
    tokens["cssVars"]["--radius-sm"] = "12px"
    tokens["cssVars"]["--radius-lg"] = "20px"
    tokens["cssVars"]["--heading-weight"] = "600"
    tokens["cssVars"]["--cta-font-weight"] = "800"
    tokens["cssVars"]["--cta-letter-spacing"] = "0.02em"
    tokens["cssVars"]["--marquee-letter-spacing"] = "0.01em"
    tokens["cssVars"]["--hero-title-letter-spacing"] = "-0.05em"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_brand_color_change():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-brand"] = "#123456"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_low_contrast_pdp_check_bg_for_white_icon():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--pdp-check-bg"] = "#E8F7F0"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_low_contrast_pdp_warning_bg_for_white_icon():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--pdp-warning-bg"] = "#FFF4E5"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_low_contrast_pdp_cta_icon_circle_pair():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--pdp-cta-bg"] = "#6FE3C1"
    tokens["cssVars"]["--pdp-white-96"] = "rgba(255, 255, 255, 0.96)"
    tokens["cssVars"]["--color-cta-text"] = "#061A70"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())


def test_validate_tokens_allows_low_contrast_cta_text_on_pdp_cta_bg():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--pdp-cta-bg"] = "#FFFFFF"
    tokens["cssVars"]["--color-cta-text"] = "#FFFFFF"
    _validate_tokens(tokens, required_css_vars=_required_css_var_keys())
