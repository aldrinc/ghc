from __future__ import annotations

from copy import deepcopy

from app.services.design_system_audit import audit_design_system_tokens
from app.services.design_system_generation import load_base_tokens_template


def test_token_audit_passes_for_base_template():
    tokens = deepcopy(load_base_tokens_template())
    findings = audit_design_system_tokens(tokens)
    assert findings
    assert all(f.status == "pass" for f in findings)


def test_token_audit_fails_low_contrast_muted_text():
    tokens = deepcopy(load_base_tokens_template())
    tokens["cssVars"]["--color-muted"] = "#cbd5e1"
    findings = audit_design_system_tokens(tokens)
    failed = [f for f in findings if f.status == "fail"]
    assert failed
    assert any(f.check_id == "tokens.validate" for f in failed)
