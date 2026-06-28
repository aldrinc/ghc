from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


ROOT = Path("/Users/aldrinclement/Documents/programming/marketi")
DEERFLOW_ROOT = ROOT / ".local/deer-flow"
CONFIG_PATH = DEERFLOW_ROOT / "config.yaml"
PROOF_DIR = ROOT / "proof_pack/deerflow-sidecar-2026-05-21"
OUTPUT_DIR = PROOF_DIR / "outputs"
EVENTS_PATH = OUTPUT_DIR / "deerflow-step01-smoke-events.jsonl"
FINAL_PATH = OUTPUT_DIR / "deerflow-step01-smoke-final.md"


PROMPT = """Run a bounded DeerFlow sidecar smoke test for foundational docs Step 01 competitor research.

Context:
- Current date: 2026-05-21.
- Product: Tenor Daily Protocol.
- Product description: Helps support male testosterone.
- Price: $59.
- Seed competitor URL: https://mengotomars.com/products/30-day-supply-starter-kit
- Existing GPT Step 01 example is mounted read-only at /mnt/tenor-gpt-example/03-v2-02.foundation.01-raw.md.

Use the DeerFlow harness:
- Use web_search for discovery.
- Use web_fetch only for exact URLs returned by web_search or provided above.
- Use write_file to save the final report to /mnt/marketi-foundation/deerflow-step01-smoke.md.
- Do not use bash.

Bounds for this smoke:
- Use at most 3 web_search calls.
- Use at most 4 web_fetch calls.
- Do not limit final answer length by token count, but keep the smoke focused.

Hard evidence rules:
- Do not fabricate competitors, URLs, numeric claims, pricing, dates, or performance labels.
- Every factual claim must cite the exact source URL inline.
- If evidence is missing, write `not_captured`.
- Include a source ledger with stable `source_id`, URL, source type, and whether full content was fetched.

Output sections:
1. Source ledger.
2. Candidate competitors and why each is direct/adjacent.
3. Citation compliance notes.
4. Short comparison vs the GPT example: where this DeerFlow+DeepSeek run is stronger, weaker, and what needs a production wrapper.
"""


def event_to_jsonable(event) -> dict:
    return {
        "type": getattr(event, "type", None),
        "data": getattr(event, "data", None),
    }


def main() -> int:
    required = ["DEEPSEEK_API_KEY", "SERPER_API_KEY", "JINA_API_KEY"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.write_text("", encoding="utf-8")

    from deerflow.client import DeerFlowClient

    client = DeerFlowClient(
        config_path=str(CONFIG_PATH),
        model_name="deepseek-v4-pro",
        thinking_enabled=True,
        subagent_enabled=True,
        plan_mode=False,
        available_skills={"deep-research"},
        environment="local-sidecar",
    )

    final_chunks: list[str] = []
    started = time.time()
    thread_id = "marketi-step01-smoke-2026-05-21"

    with EVENTS_PATH.open("a", encoding="utf-8") as events_file:
        for event in client.stream(PROMPT, thread_id=thread_id, recursion_limit=80):
            events_file.write(json.dumps(event_to_jsonable(event), ensure_ascii=False) + "\n")
            events_file.flush()
            if event.type == "messages-tuple" and event.data.get("type") == "ai":
                content = event.data.get("content")
                if isinstance(content, str):
                    final_chunks.append(content)

    final_text = "".join(final_chunks).strip()
    if not final_text:
        final_text = "(No final AI text captured; inspect event log.)"
    FINAL_PATH.write_text(final_text + "\n", encoding="utf-8")

    metadata = {
        "thread_id": thread_id,
        "elapsed_seconds": round(time.time() - started, 3),
        "events_path": str(EVENTS_PATH),
        "final_path": str(FINAL_PATH),
        "sidecar_workspace_report": str(PROOF_DIR / "sidecar-workspace/deerflow-step01-smoke.md"),
    }
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
