from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path("/Users/aldrinclement/Documents/programming/marketi")
BACKEND_ROOT = ROOT / "mos" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.services.deerflow_foundational import run_deerflow_foundational_step  # noqa: E402


PROOF_DIR = ROOT / "proof_pack/deerflow-foundational-steps03-04-1to1-2026-05-21"
OUTPUT_DIR = PROOF_DIR / "outputs"
RUNS_DIR = PROOF_DIR / "runs-continuation"


CONTINUATION_PROMPT = """You previously completed the web research for this same Step 04 thread and ended with:
"I now have enough data to produce the comprehensive report. Let me write it now."

Do not do more research unless the prior thread state is unavailable.
Do not respond with planning or status.
Write the final research report now using the data already gathered in this thread.

Return ONLY these tagged blocks:

<SUMMARY>Bounded summary of key findings: primary segments observed, top 3 signals by strength, #1 bottleneck, confidence assessment. Max 500 words.</SUMMARY>
<CONTENT>
Full research document with all 9 categories (A-I), each with:
- synthesized summary
- Quote Bank entries with this exact metadata:
  QUOTE
  SOURCE
  CATEGORY
  EMOTION
  INTENSITY
  BUYER_STAGE
  SEGMENT_HINT

Then include:
- Signal-to-Noise Assessment + top 10 findings table
- Bayesian Confidence Assessment (A-I)
- Bottleneck Identification
- Core Avatar Belief Summary
</CONTENT>
"""


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = run_deerflow_foundational_step(
        prompt=CONTINUATION_PROMPT,
        step_key="04",
        model=settings.STRATEGY_V2_FOUNDATIONAL_STEP01_DEERFLOW_MODEL,
        workflow_run_id="dsv4-foundational-03-04-1to1",
        deerflow_backend_dir=settings.STRATEGY_V2_DEERFLOW_BACKEND_DIR,
        deerflow_config_path=settings.STRATEGY_V2_DEERFLOW_CONFIG_PATH,
        timeout_seconds=settings.STRATEGY_V2_DEERFLOW_TIMEOUT_SECONDS,
        artifact_root=str(RUNS_DIR),
        extra_metadata={"strategy_v2_step": "v2-02.foundation.04.continuation"},
    )
    (OUTPUT_DIR / "dsv4-step04-continuation-raw.md").write_text(result.raw_output + "\n", encoding="utf-8")
    (OUTPUT_DIR / "dsv4-step04-continuation-summary.md").write_text(result.summary + "\n", encoding="utf-8")
    (OUTPUT_DIR / "dsv4-step04-continuation-content.md").write_text(result.content + "\n", encoding="utf-8")
    (OUTPUT_DIR / "dsv4-step04-continuation-run.meta.json").write_text(
        json.dumps(result.run_meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result.run_meta, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
