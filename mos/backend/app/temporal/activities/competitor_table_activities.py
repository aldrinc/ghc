from __future__ import annotations

from typing import List, Optional

from temporalio import activity

from app.schemas.competitors import CompetitorRow, ExtractCompetitorsRequest, ExtractCompetitorsResult


def _split_cells(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    stripped = line.strip().strip("|").replace(" ", "")
    if not stripped:
        return False
    return all(ch in "-:|" for ch in stripped)


@activity.defn
def extract_competitors_table_activity(request: ExtractCompetitorsRequest) -> ExtractCompetitorsResult:
    """
    Extract competitor rows from the most detailed pipe table that includes a Website column.

    Selection rules (deterministic):
      - consider only pipe tables with a Website column
      - prefer tables that also include a Company/Brand/Name column
      - among candidates, prefer the one with the most data rows
      - if still tied, prefer the last such table in the document
    """
    content = request.step1_content or ""
    lines = content.splitlines()

    candidates = []
    table_index = 0
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        line = lines[i]
        if "|" not in line:
            i += 1
            continue

        header_cells_raw = _split_cells(line)
        header_cells = [c.strip() for c in header_cells_raw]
        header_lower = [c.lower() for c in header_cells]

        if not any("website" in c for c in header_lower):
            i += 1
            continue

        j = i + 1
        # Skip optional separator row
        if j < total_lines and "|" in lines[j] and _is_separator_row(lines[j]):
            j += 1

        rows: List[List[str]] = []
        while j < total_lines:
            row_line = lines[j]
            if "|" not in row_line or not row_line.strip().startswith("|"):
                break
            row_cells = _split_cells(row_line)
            if not any(cell for cell in row_cells):
                break
            rows.append(row_cells)
            j += 1

        if rows:
            website_idx: Optional[int] = None
            name_idx: Optional[int] = None
            for idx, cell in enumerate(header_lower):
                if website_idx is None and "website" in cell:
                    website_idx = idx
                if name_idx is None and (
                    "company" in cell or "brand" in cell or "name" in cell or "competitor" in cell
                ):
                    name_idx = idx

            if website_idx is not None:
                candidates.append(
                    {
                        "header_index": i,
                        "header_cells": header_cells,
                        "rows": rows,
                        "website_idx": website_idx,
                        "name_idx": name_idx,
                        "row_count": len(rows),
                        "table_index": table_index,
                        "markdown": "\n".join(lines[i:j]),
                    }
                )
                table_index += 1
        i = j if rows else i + 1

    if not candidates:
        return ExtractCompetitorsResult(competitors=[], chosen_table_reason="No competitor table with Website column found.")

    # Pick best candidate: has name column, most rows, last in document as tie-breaker.
    def _score(candidate: dict) -> tuple:
        has_name = 1 if candidate.get("name_idx") is not None else 0
        row_count = candidate.get("row_count") or 0
        table_idx = candidate.get("table_index") or 0
        return (has_name, row_count, table_idx)

    best = max(candidates, key=_score)
    website_idx = best["website_idx"]
    name_idx = best.get("name_idx")

    competitors: List[CompetitorRow] = []
    for row_cells in best["rows"]:
        if website_idx >= len(row_cells):
            continue
        website_cell = row_cells[website_idx]
        name_cell = row_cells[name_idx] if (name_idx is not None and name_idx < len(row_cells)) else website_cell
        name = (name_cell or "").strip()
        website = (website_cell or "").strip()
        if not name and not website:
            continue
        competitors.append(CompetitorRow(name=name or website or "Unknown brand", website=website or None))

    reason = (
        f"Selected table with {best['row_count']} rows; "
        f"has_name_column={'yes' if name_idx is not None else 'no'}; "
        f"table_index={best['table_index']} (higher means later in document)."
    )

    return ExtractCompetitorsResult(
        competitors=competitors,
        chosen_table_reason=reason,
        chosen_table_markdown=best.get("markdown", ""),
    )

