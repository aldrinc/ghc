from llm import Llm
from loop.analyzer import LoopAnalyzer


def test_loop_analyzer_defaults_to_latest_gemini_pro() -> None:
    analyzer = LoopAnalyzer("key")

    assert analyzer.model == Llm.GEMINI_3_1_PRO_PREVIEW_HIGH
