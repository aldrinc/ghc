from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.design_system_generation import (
    _blend_over_background,
    _contrast_ratio,
    _parse_css_color,
    _resolve_css_var_value,
    validate_design_system_tokens,
)


@dataclass(frozen=True)
class AuditFinding:
    check_id: str
    status: str
    message: str
    location: str
    foreground: str | None = None
    background: str | None = None
    contrast_ratio: float | None = None
    threshold: float | None = None


def audit_design_system_tokens(tokens: dict[str, Any]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    try:
        validate_design_system_tokens(tokens)
        findings.append(
            AuditFinding(
                check_id="tokens.validate",
                status="pass",
                location="tokens",
                message="Token schema and baseline validation passed.",
            )
        )
    except Exception as exc:  # noqa: BLE001
        findings.append(
            AuditFinding(
                check_id="tokens.validate",
                status="fail",
                location="tokens",
                message=str(exc),
            )
        )
        return findings

    css_vars = tokens.get("cssVars")
    if not isinstance(css_vars, dict):
        return findings

    checks: list[tuple[str, str, str, float]] = [
        ("tokens.contrast.body_on_bg", "--color-text", "--color-bg", 7.0),
        ("tokens.contrast.brand_on_bg", "--color-brand", "--color-bg", 4.5),
        ("tokens.contrast.pdp_brand_strong_on_bg", "--pdp-brand-strong", "--color-bg", 4.5),
        ("tokens.contrast.body_on_page", "--color-text", "--color-page-bg", 7.0),
        ("tokens.contrast.marquee_text_on_marquee_bg", "--marquee-text", "--marquee-bg", 4.5),
        ("tokens.contrast.cta_text_on_cta_bg", "--color-cta-text", "--color-cta", 3.0),
        ("tokens.contrast.cta_text_on_pdp_cta_bg", "--color-cta-text", "--pdp-cta-bg", 3.0),
        ("tokens.contrast.pdp_warning_icon_on_pdp_warning_bg", "--color-bg", "--pdp-warning-bg", 3.0),
        ("tokens.contrast.pdp_header_cta_icon_on_cta_shell", "--color-cta-icon", "--color-cta-shell", 3.0),
    ]

    for check_id, fg_key, bg_key, threshold in checks:
        fg_raw = css_vars.get(fg_key)
        bg_raw = css_vars.get(bg_key)
        if fg_raw is None or bg_raw is None:
            findings.append(
                AuditFinding(
                    check_id=check_id,
                    status="fail",
                    location=f"{fg_key} vs {bg_key}",
                    message="Missing token for contrast check.",
                    threshold=threshold,
                )
            )
            continue

        fg_resolved = _resolve_css_var_value(css_vars=css_vars, value=str(fg_raw), stack=[fg_key])
        bg_resolved = _resolve_css_var_value(css_vars=css_vars, value=str(bg_raw), stack=[bg_key])
        fg_rgba = _parse_css_color(fg_resolved)
        bg_rgba = _parse_css_color(bg_resolved)
        bg_rgb = _blend_over_background(fg=bg_rgba, bg=(255, 255, 255, 1.0))
        fg_rgb = _blend_over_background(fg=fg_rgba, bg=bg_rgba)
        ratio = _contrast_ratio(a=fg_rgb, b=bg_rgb)
        status = "pass" if ratio >= threshold else "fail"
        message = "Contrast check passed." if status == "pass" else "Contrast ratio below threshold."
        findings.append(
            AuditFinding(
                check_id=check_id,
                status=status,
                location=f"{fg_key} vs {bg_key}",
                message=message,
                foreground=fg_resolved,
                background=bg_resolved,
                contrast_ratio=ratio,
                threshold=threshold,
            )
        )

    return findings


def audit_page_contrast(*, url: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 2200})
        page.goto(url, wait_until="networkidle", timeout=60000)

        result = page.evaluate(
            """() => {
  function parseColor(input) {
    if (!input) return null;
    const s = String(input).trim().toLowerCase();
    const m = s.match(/^rgba?\\(([^)]+)\\)$/);
    if (!m) return null;
    const parts = m[1].split(",").map((p) => p.trim());
    if (parts.length < 3) return null;
    const r = Math.max(0, Math.min(255, Number(parts[0])));
    const g = Math.max(0, Math.min(255, Number(parts[1])));
    const b = Math.max(0, Math.min(255, Number(parts[2])));
    const a = parts.length >= 4 ? Math.max(0, Math.min(1, Number(parts[3]))) : 1;
    if ([r, g, b, a].some((n) => Number.isNaN(n))) return null;
    return { r, g, b, a };
  }

  function composite(top, bottom) {
    const outA = top.a + bottom.a * (1 - top.a);
    if (outA <= 0) return { r: 0, g: 0, b: 0, a: 0 };
    return {
      r: (top.r * top.a + bottom.r * bottom.a * (1 - top.a)) / outA,
      g: (top.g * top.a + bottom.g * bottom.a * (1 - top.a)) / outA,
      b: (top.b * top.a + bottom.b * bottom.a * (1 - top.a)) / outA,
      a: outA,
    };
  }

  function toLinear(c) {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  }

  function luminance(rgb) {
    return 0.2126 * toLinear(rgb.r) + 0.7152 * toLinear(rgb.g) + 0.0722 * toLinear(rgb.b);
  }

  function contrast(a, b) {
    const la = luminance(a);
    const lb = luminance(b);
    const lighter = Math.max(la, lb);
    const darker = Math.min(la, lb);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function resolvedBackground(el) {
    const chain = [];
    let node = el;
    while (node) {
      chain.push(node);
      node = node.parentElement;
    }
    chain.reverse();
    let bg = { r: 255, g: 255, b: 255, a: 1 };
    for (const n of chain) {
      const c = parseColor(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) bg = composite(c, bg);
    }
    return bg;
  }

  function isVisible(el) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (Number(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function directText(el) {
    let out = "";
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE && node.textContent) out += node.textContent;
    }
    return out.trim();
  }

  function cssPath(el) {
    if (!(el instanceof Element)) return "";
    const parts = [];
    let cur = el;
    while (cur && parts.length < 5) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) {
        part += "#" + cur.id;
        parts.unshift(part);
        break;
      }
      if (cur.classList.length) part += "." + Array.from(cur.classList).slice(0, 2).join(".");
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(" > ");
  }

  const textFailures = [];
  const textChecks = [];
  const elements = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6,p,li,span,button,a,label,small,strong,em,div"));
  for (const el of elements) {
    if (!isVisible(el)) continue;
    const textValue = directText(el);
    if (!textValue) continue;
    // Skip decorative glyph-only nodes (e.g. quote marks, star icons).
    if (!/[A-Za-z0-9]/.test(textValue)) continue;
    const style = getComputedStyle(el);
    const fg = parseColor(style.color);
    if (!fg) continue;
    const bg = resolvedBackground(el);
    const rendered = composite(fg, bg);
    const ratio = contrast(rendered, bg);
    const size = Number.parseFloat(style.fontSize) || 0;
    const weight = Number.parseInt(style.fontWeight, 10) || 400;
    const isLarge = size >= 24 || (size >= 18.66 && weight >= 700);
    const threshold = isLarge ? 3.0 : 4.5;
    const rec = {
      selector: cssPath(el),
      text: textValue.slice(0, 120),
      color: style.color,
      background: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
      contrastRatio: ratio,
      threshold,
      fontSize: size,
      fontWeight: weight,
    };
    textChecks.push(rec);
    if (ratio < threshold) textFailures.push(rec);
  }

  const borderFailures = [];
  const borderTargets = Array.from(
    document.querySelectorAll(
      '[class*="optionCard"],[class*="sizeCard"],[class*="offerCard"],[class*="swatchCircle"],[class*="faqCard"],[class*="faqCardOpen"],[class*="urgency"],[class*="delayBar"]'
    )
  );
  for (const el of borderTargets) {
    if (!isVisible(el)) continue;
    const style = getComputedStyle(el);
    const bw = Number.parseFloat(style.borderTopWidth || "0");
    if (bw <= 0) continue;
    const border = parseColor(style.borderTopColor);
    if (!border) continue;
    if (border.a <= 0) continue;
    const bg = resolvedBackground(el);
    const borderRgb = composite(border, bg);
    const ratio = contrast(borderRgb, bg);
    const threshold = 3.0;
    if (ratio < threshold) {
      borderFailures.push({
        selector: cssPath(el),
        borderColor: style.borderTopColor,
        background: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
        contrastRatio: ratio,
        threshold,
      });
    }
  }

  const nonTextFailures = [];
  const nonTextChecks = [];
  const nonTextTargets = Array.from(
    document.querySelectorAll('[class*="selectedCheck"] > span,[class*="ctaIconCircle"],[class*="headerCtaIcon"]')
  );
  for (const el of nonTextTargets) {
    if (!isVisible(el)) continue;
    const style = getComputedStyle(el);
    const fg = parseColor(style.color);
    if (!fg) continue;
    const bg = resolvedBackground(el);
    const rendered = composite(fg, bg);
    const ratio = contrast(rendered, bg);
    const threshold = 3.0;
    const rec = {
      selector: cssPath(el),
      color: style.color,
      background: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
      contrastRatio: ratio,
      threshold,
    };
    nonTextChecks.push(rec);
    if (ratio < threshold) nonTextFailures.push(rec);
  }

  return {
    url: location.href,
    textCheckCount: textChecks.length,
    textFailureCount: textFailures.length,
    nonTextCheckCount: nonTextChecks.length,
    nonTextFailureCount: nonTextFailures.length,
    borderFailureCount: borderFailures.length,
    textFailures: textFailures.slice(0, 200),
    nonTextFailures: nonTextFailures.slice(0, 200),
    borderFailures: borderFailures.slice(0, 200),
  };
}"""
        )
        browser.close()
        return result
