from __future__ import annotations

from copy import deepcopy

from app.services.design_system_audit import audit_design_system_tokens
from app.services.design_system_generation import load_base_tokens_template


def test_token_audit_passes_for_base_template():
    tokens = deepcopy(load_base_tokens_template())
    findings = audit_design_system_tokens(tokens)
    assert findings
    assert all(f.status == "pass" for f in findings)
    assert not any(f.check_id == "tokens.contrast.pdp_check_icon_on_pdp_check_bg" for f in findings)
    assert not any(f.check_id == "tokens.contrast.pdp_cta_icon_on_pdp_white_96" for f in findings)


def test_token_audit_allows_low_contrast_muted_text():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-muted"] = "#cbd5e1"
    findings = audit_design_system_tokens(tokens)
    assert findings
    assert all(f.status == "pass" for f in findings)
    assert not any(f.check_id == "tokens.contrast.muted_on_bg" for f in findings)
    assert not any(f.check_id == "tokens.contrast.muted_on_page" for f in findings)
