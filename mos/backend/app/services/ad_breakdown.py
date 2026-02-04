from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.db.models import Ad, MediaAsset

_PROMPT_CACHE: Dict[str, Tuple[str, str]] = {}


def load_ad_breakdown_prompt() -> Tuple[str, str]:
    """
    Load the creative analysis / ad breakdown prompt template and compute its SHA256.
    """
    cache_key = "ad_breakdown"
    if cache_key in _PROMPT_CACHE:
        return _PROMPT_CACHE[cache_key]

    # ad_breakdown.py lives at app/services/, and prompts are under app/prompts/
    backend_app_root = Path(__file__).resolve().parents[1]
    prompt_path = backend_app_root / "prompts" / "creative_analysis" / "ad_breakdown.md"
    text = prompt_path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    _PROMPT_CACHE[cache_key] = (text, sha)
    return text, sha


def summarize_raw_json(raw_json: Dict[str, Any], *, max_fields: int = 40, max_string_len: int = 300) -> Dict[str, Any]:
    """
    Build a compact summary of the platform-native ad payload to avoid dumping the full raw_json.
    """
    summary: Dict[str, Any] = {}
    for key, value in raw_json.items():
        if len(summary) >= max_fields:
            break
        if isinstance(value, (dict, list)):
            continue
        if isinstance(value, str) and len(value) > max_string_len:
            summary[key] = value[: max_string_len - 3] + "..."
        else:
            summary[key] = value
    return summary


def build_media_summary(media_rows: Iterable[Tuple[MediaAsset, Optional[str]]]) -> List[Dict[str, Any]]:
    """
    Build a compact description of media assets linked to the ad.
    """
    items: List[Dict[str, Any]] = []
    for media, role in media_rows:
        items.append(
            {
                "id": str(media.id),
                "role": role,
                "asset_type": getattr(media.asset_type, "value", str(media.asset_type)),
                "mime_type": media.mime_type,
                "size_bytes": media.size_bytes,
                "width": media.width,
                "height": media.height,
                "duration_ms": media.duration_ms,
                "stored_url": media.stored_url,
                "source_url": media.source_url,
                "storage_key": media.storage_key,
                "preview_storage_key": media.preview_storage_key,
                "bucket": media.bucket,
                "preview_bucket": media.preview_bucket,
                "mirror_status": getattr(media, "mirror_status", None),
            }
        )
    return items


def build_ad_context_block(
    *,
    ad: Ad,
    brand_name: Optional[str],
    research_run_id: Optional[str],
    media_summary: List[Dict[str, Any]],
    raw_json_summary: Dict[str, Any],
) -> str:
    """
    Build a deterministic, text-only Ad Context block for the LLM prompt.
    """
    channel_value = getattr(ad.channel, "value", str(ad.channel))
    lines: List[str] = []
    lines.append("## AD CONTEXT")
    lines.append(f"Ad ID: {ad.id}")
    lines.append(f"Research Run ID: {research_run_id or ''}")
    lines.append(f"Brand ID: {ad.brand_id}")
    lines.append(f"Brand Name: {brand_name or ''}")
    lines.append(f"Channel: {channel_value}")
    lines.append(f"External Ad ID: {ad.external_ad_id}")
    lines.append("")
    lines.append("Platform Fields (normalized):")
    lines.append(f"- Primary Text: {ad.body_text or '[UNKNOWN]'}")
    lines.append(f"- Headline: {ad.headline or '[UNKNOWN]'}")
    lines.append(f"- CTA Type: {ad.cta_type or '[UNKNOWN]'}")
    lines.append(f"- CTA Text: {ad.cta_text or '[UNKNOWN]'}")
    lines.append(f"- Destination URL: {ad.landing_url or '[UNKNOWN]'}")
    lines.append(f"- Destination Domain: {ad.destination_domain or '[UNKNOWN]'}")
    lines.append(f"- Started Running At: {ad.started_running_at or ''}")
    lines.append(f"- Ended Running At: {ad.ended_running_at or ''}")
    lines.append(f"- First Seen At: {ad.first_seen_at or ''}")
    lines.append(f"- Last Seen At: {ad.last_seen_at or ''}")
    lines.append("")

    if media_summary:
        lines.append("Media Assets:")
        for idx, item in enumerate(media_summary, start=1):
            lines.append(
                f"- [{idx}] id={item['id']}, role={item.get('role')}, "
                f"type={item.get('asset_type')}, mime={item.get('mime_type')}, "
                f"size_bytes={item.get('size_bytes')}, duration_ms={item.get('duration_ms')}"
            )
        lines.append("")

    if raw_json_summary:
        lines.append("Platform Raw JSON Summary (selected fields):")
        lines.append(json.dumps(raw_json_summary, ensure_ascii=False, indent=2))
        lines.append("")

    lines.append(
        "Use ONLY the information above plus the attached media to perform the structured ad breakdown. "
        "If any detail is missing or unclear, mark it as [UNKNOWN] or [UNREADABLE] instead of guessing."
    )
    return "\n".join(lines)


_SECTION_RE = re.compile(r"^##\s+(\d+)\)\s*(.+)$", re.MULTILINE)


def segment_ad_breakdown_output(raw_markdown: str) -> Dict[str, Any]:
    """
    Coarsely segment the ad breakdown markdown into numbered sections.

    Returns a dict with:
      - intro: optional preamble before the first numbered heading
      - sections: mapping of section_key -> section_text
    """
    sections: Dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(raw_markdown))
    if matches:
        intro = raw_markdown[: matches[0].start()].strip()
        if intro:
            sections["intro"] = intro

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_markdown)
        number = match.group(1)
        title = match.group(2).strip()
        base_key = title.split("(")[0].strip().lower().replace(" ", "_")
        key = f"{number}_{base_key}"
        sections[key] = raw_markdown[start:end].strip()

    return {
        "sections": sections,
    }


def _find_section_text(sections: Dict[str, str], prefix: str) -> str:
    """
    Find the first section whose key starts with the given prefix (e.g. \"0_\" or \"1_\").
    """
    for key, text in sections.items():
        if key.startswith(prefix):
            return text or ""
    return ""


def extract_teardown_header_fields(sections: Dict[str, str]) -> Dict[str, Any]:
    """
    Extract high-level teardown header fields from segmented ad breakdown markdown.

    Fields:
      - one_liner: 1-sentence why-it-wins hypothesis (or None)
      - algorithmic_thesis: targeting thesis sentence (or None)
      - hook_score: overall hook strength 0-10 (int or None)
    """
    one_liner: Optional[str] = None
    algorithmic_thesis: Optional[str] = None
    hook_score: Optional[int] = None

    # Section 0) Ad Identification – one-liner
    sec0 = _find_section_text(sections, "0_")
    if sec0:
        lines = sec0.splitlines()
        for idx, line in enumerate(lines):
            if "1-Sentence" in line and "Why It Wins" in line:
                # Look ahead for the next non-empty bullet line.
                for j in range(idx + 1, len(lines)):
                    candidate = lines[j].strip()
                    if not candidate:
                        continue
                    if candidate.startswith("-"):
                        text = candidate.lstrip("-").strip()
                        # Strip surrounding quotes if present.
                        if (text.startswith("\"") and text.endswith("\"")) or (
                            text.startswith("“") and text.endswith("”")
                        ):
                            text = text[1:-1].strip()
                        one_liner = text or None
                        break
                break

    # Section 1) Creative is targeting payload – algorithmic thesis
    sec1 = _find_section_text(sections, "1_")
    if sec1:
        lines = sec1.splitlines()
        for idx, line in enumerate(lines):
            if "Algorithmic thesis" in line:
                for j in range(idx + 1, len(lines)):
                    candidate = lines[j].strip()
                    if not candidate:
                        continue
                    if candidate.startswith("-"):
                        text = candidate.lstrip("-").strip()
                        if (text.startswith("\"") and text.endswith("\"")) or (
                            text.startswith("“") and text.endswith("”")
                        ):
                            text = text[1:-1].strip()
                        algorithmic_thesis = text or None
                        break
                break

    # Section 2) Hook Autopsy – overall hook strength (0-10)
    sec2 = _find_section_text(sections, "2_")
    if sec2:
        match = re.search(r"Overall Hook Strength\s*\(0.?10\)\s*:\s*([0-9]{1,2})", sec2)
        if match:
            try:
                value = int(match.group(1))
                if 0 <= value <= 10:
                    hook_score = value
            except Exception:
                hook_score = None

    return {
        "one_liner": one_liner,
        "algorithmic_thesis": algorithmic_thesis,
        "hook_score": hook_score,
    }


def _parse_timecode_mmss(value: str) -> Optional[int]:
    """
    Parse a mm:ss timecode into milliseconds.
    """
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
    except ValueError:
        return None
    if minutes < 0 or seconds < 0 or seconds >= 60:
        return None
    return (minutes * 60 + seconds) * 1000


def _extract_subsection(text: str, marker: str) -> str:
    """
    Extract lines between a heading containing `marker` and the next heading.
    """
    lines = text.splitlines()
    start_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if marker in line:
            start_idx = i + 1
            break
    if start_idx is None:
        return ""
    end_idx = len(lines)
    for j in range(start_idx, len(lines)):
        if lines[j].startswith("### ") or lines[j].startswith("## "):
            end_idx = j
            break
    return "\n".join(lines[start_idx:end_idx])


def extract_transcript_rows(sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Extract transcript rows from Section 8A (Full Transcript).

    Expected format per line:
      mm:ss–mm:ss | Spoken Audio | On-screen text | Music/SFX
    """
    results: List[Dict[str, Any]] = []
    # Section 8) covers storyboarding; transcript is under 8A inside that section.
    sec8 = _find_section_text(sections, "8_")
    if not sec8:
        return results

    subsection = _extract_subsection(sec8, "8A) Full Transcript")
    if not subsection:
        return results

    line_re = re.compile(
        r"^\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*)\s*$"
    )
    for line in subsection.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        m = line_re.match(line)
        if not m:
            continue
        start_tc, end_tc, spoken, ost, music = m.groups()
        start_ms = _parse_timecode_mmss(start_tc)
        end_ms = _parse_timecode_mmss(end_tc)
        # Extract optional speaker label like [CREATOR] from spoken text.
        speaker_label = None
        spoken_text = spoken.strip()
        label_match = re.match(r"^\[(?P<label>[A-Z\-]+)\]\s*(.*)$", spoken_text)
        if label_match:
            speaker_label = label_match.group("label")
            spoken_text = label_match.group(2).strip()

        results.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "spoken_text": spoken_text,
                "onscreen_text": ost.strip() or None,
                "audio_notes": music.strip() or None,
                "speaker_label": speaker_label,
            }
        )
    return results


def extract_storyboard_rows(sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Extract storyboard rows from Section 8B (Scene-by-Scene Breakdown).
    """
    results: List[Dict[str, Any]] = []
    sec8 = _find_section_text(sections, "8_")
    if not sec8:
        return results

    subsection = _extract_subsection(sec8, "8B) Scene-by-Scene Breakdown")
    if not subsection:
        return results

    lines = subsection.splitlines()
    header_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if "|" in line and "Scene" in line and "Timestamp" in line:
            header_idx = i
            break
    if header_idx is None:
        return results

    header_line = lines[header_idx].strip()
    if not header_line.startswith("|"):
        return results
    headers = [h.strip().lower() for h in header_line.strip("|").split("|")]

    # Map column names to indices
    def _find_col(substr: str) -> Optional[int]:
        for idx, name in enumerate(headers):
            if substr in name:
                return idx
        return None

    scene_idx = _find_col("scene")
    ts_idx = _find_col("timestamp")
    visual_idx = _find_col("what we see")
    if visual_idx is None:
        visual_idx = _find_col("visual description")
    action_idx = _find_col("action/blocking")
    narrative_idx = _find_col("narrative job")
    ost_idx = _find_col("on-screen text")

    # Data rows start after header and optional separator.
    row_start = header_idx + 1
    if row_start < len(lines) and "---" in lines[row_start]:
        row_start += 1

    for line in lines[row_start:]:
        if "|" not in line:
            break
        row = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(row) < len(headers):
            continue
        try:
            scene_no = int(row[scene_idx]) if scene_idx is not None and row[scene_idx] else None
        except Exception:
            scene_no = None

        start_ms = None
        end_ms = None
        if ts_idx is not None and row[ts_idx]:
            ts = row[ts_idx]
            m = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", ts)
            if m:
                start_ms = _parse_timecode_mmss(m.group(1))
                end_ms = _parse_timecode_mmss(m.group(2))

        results.append(
            {
                "scene_no": scene_no,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "visual_description": row[visual_idx] if visual_idx is not None else None,
                "action_blocking": row[action_idx] if action_idx is not None else None,
                "narrative_job": row[narrative_idx] if narrative_idx is not None else None,
                "onscreen_text": row[ost_idx] if ost_idx is not None else None,
            }
        )

    return results
