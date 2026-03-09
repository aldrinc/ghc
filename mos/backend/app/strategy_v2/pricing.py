from __future__ import annotations

import re

from app.strategy_v2.errors import StrategyV2MissingContextError


_PRICE_NUMBER_RE = re.compile(r"\d+(?:\.\d{1,2})?")


def _format_price_text(*, cents: int, currency: str) -> str:
    amount = cents / 100
    rendered_amount = f"{amount:.2f}".rstrip("0").rstrip(".")
    if currency == "USD":
        return f"${rendered_amount}"
    return f"{currency} {rendered_amount}"


def parse_price_to_cents_and_currency(*, price_text: str, context: str) -> tuple[int, str]:
    normalized = str(price_text or "").strip()
    if not normalized:
        raise StrategyV2MissingContextError(
            f"{context} requires a price before continuing. "
            "Remediation: provide a price like '$49' or '49.99'."
        )
    if normalized.upper() == "TBD":
        raise StrategyV2MissingContextError(
            f"{context} requires a concrete price before continuing. "
            "Remediation: provide a price like '$49' or '49.99'."
        )

    currency = "USD"
    working = normalized
    if working.upper().startswith("USD"):
        working = working[3:].strip()
    if working.startswith("$"):
        working = working[1:].strip()

    number_match = _PRICE_NUMBER_RE.search(working.replace(",", ""))
    if number_match is None:
        raise StrategyV2MissingContextError(
            f"{context} requires a parseable price before continuing. "
            "Remediation: provide a price like '$49' or '49.99'."
        )

    amount = float(number_match.group(0))
    return int(round(amount * 100)), currency


def require_concrete_price(
    *,
    price: str | None,
    context: str,
) -> str:
    cents, currency = parse_price_to_cents_and_currency(price_text=str(price or ""), context=context)
    return _format_price_text(cents=cents, currency=currency)
