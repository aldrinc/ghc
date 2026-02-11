#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.base import session_scope
from app.db.models import DesignSystem, Funnel
from app.services.design_system_audit import audit_design_system_tokens, audit_page_contrast
from app.services.design_systems import resolve_design_system_tokens


def _load_target_tokens(*, design_system_id: str | None, public_id: str | None) -> tuple[dict[str, Any], str]:
    with session_scope() as session:
        if design_system_id:
            ds = session.scalars(select(DesignSystem).where(DesignSystem.id == design_system_id)).first()
            if not ds:
                raise RuntimeError(f"Design system not found: {design_system_id}")
            if not isinstance(ds.tokens, dict):
                raise RuntimeError(f"Design system tokens for {design_system_id} are not a JSON object.")
            return ds.tokens, str(ds.id)

        if not public_id:
            raise RuntimeError("Either design_system_id or public_id is required.")

        funnel = session.scalars(select(Funnel).where(Funnel.public_id == public_id)).first()
        if not funnel:
            raise RuntimeError(f"Funnel not found for public_id={public_id}")
        tokens = resolve_design_system_tokens(
            session=session,
            org_id=str(funnel.org_id),
            client_id=str(funnel.client_id),
            funnel=funnel,
            page=None,
        )
        if not isinstance(tokens, dict):
            raise RuntimeError(
                "No design system tokens resolved for funnel. Ensure a funnel/client/page design system is attached."
            )
        resolved_id = str(funnel.design_system_id) if funnel.design_system_id else "client-default"
        return tokens, resolved_id


def _markdown_summary(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Design System Audit Report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generatedAt']}`")
    lines.append(f"- Design system id: `{report['designSystemId']}`")
    lines.append(f"- Public id: `{report.get('publicId') or ''}`")
    lines.append(f"- Overall status: `{report['overallStatus']}`")
    lines.append("")

    token_findings = report["tokenAudit"]["findings"]
    token_failures = [f for f in token_findings if f["status"] == "fail"]
    lines.append("## Token Audit")
    lines.append(f"- Checks: `{len(token_findings)}`")
    lines.append(f"- Failures: `{len(token_failures)}`")
    for finding in token_failures:
        lines.append(
            f"- `{finding['check_id']}` at `{finding['location']}`: {finding['message']} "
            f"(ratio={finding.get('contrast_ratio')}, threshold={finding.get('threshold')})"
        )
    lines.append("")

    lines.append("## Runtime Audit")
    for page in report["pageAudits"]:
        lines.append(f"- URL: `{page['url']}`")
        lines.append(f"- Text checks: `{page['textCheckCount']}`")
        lines.append(f"- Text failures: `{page['textFailureCount']}`")
        lines.append(f"- Border failures: `{page['borderFailureCount']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic design-system accessibility audit.")
    parser.add_argument("--design-system-id", default=None)
    parser.add_argument("--public-id", default=None)
    parser.add_argument("--host", default="http://localhost:5275")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    if not args.design_system_id and not args.public_id:
        raise RuntimeError("Provide --design-system-id or --public-id.")

    tokens, resolved_design_system_id = _load_target_tokens(
        design_system_id=args.design_system_id,
        public_id=args.public_id,
    )

    token_findings = [asdict(f) for f in audit_design_system_tokens(tokens)]
    token_failures = [f for f in token_findings if f["status"] == "fail"]

    page_audits: list[dict[str, Any]] = []
    if args.public_id:
        for slug in ("sales", "pre-sales"):
            page_url = f"{args.host}/f/{args.public_id}/{slug}"
            page_audits.append(audit_page_contrast(url=page_url))

    page_failure_count = sum(p["textFailureCount"] + p["borderFailureCount"] for p in page_audits)
    overall_status = "fail" if token_failures or page_failure_count else "pass"

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "designSystemId": resolved_design_system_id,
        "publicId": args.public_id,
        "overallStatus": overall_status,
        "tokenAudit": {
            "findings": token_findings,
        },
        "pageAudits": page_audits,
    }

    output_path = (
        Path(args.output)
        if args.output
        else Path("reports") / f"design-system-audit-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_path = output_path.with_suffix(".md")
    md_path.write_text(_markdown_summary(report), encoding="utf-8")

    print(f"Audit JSON: {output_path}")
    print(f"Audit Markdown: {md_path}")
    print(f"Overall status: {overall_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
