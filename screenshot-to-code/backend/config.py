import os

from llm import Llm


def _read_llm_setting(env_name: str, default: Llm) -> Llm:
    raw_value = os.environ.get(env_name)
    if not raw_value:
        return default

    for candidate in Llm:
        if raw_value in {candidate.name, candidate.value}:
            return candidate

    raise ValueError(
        f"Unsupported {env_name}: {raw_value}. Expected one of the declared Llm enum names or values."
    )


NUM_VARIANTS = 4
NUM_VARIANTS_VIDEO = 2
DEFAULT_VALIDATED_LOOP_MAX_ITERATIONS = int(
    os.environ.get("DEFAULT_VALIDATED_LOOP_MAX_ITERATIONS", "10")
)
MAX_ACCEPTED_VIDEO_SIZE_BYTES = int(
    os.environ.get("MAX_ACCEPTED_VIDEO_SIZE_BYTES", str(100 * 1024 * 1024))
)
MAX_ACCEPTED_VIDEO_DURATION_SECONDS = float(
    os.environ.get("MAX_ACCEPTED_VIDEO_DURATION_SECONDS", "60")
)
VALIDATED_LOOP_PASS_SCORE = float(os.environ.get("VALIDATED_LOOP_PASS_SCORE", "0.95"))
VIDEO_VALIDATED_LOOP_PASS_SCORE = float(
    os.environ.get("VIDEO_VALIDATED_LOOP_PASS_SCORE", "0.98")
)
VIDEO_VALIDATED_LOOP_BEHAVIOR_PASS_SCORE = float(
    os.environ.get("VIDEO_VALIDATED_LOOP_BEHAVIOR_PASS_SCORE", "0.98")
)
VIDEO_VALIDATED_LOOP_ANIMATION_PASS_SCORE = float(
    os.environ.get("VIDEO_VALIDATED_LOOP_ANIMATION_PASS_SCORE", "0.98")
)

# LLM-related
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", None)
MOS_IMPORT_MODEL_SLOT_1 = _read_llm_setting(
    "MOS_IMPORT_MODEL_SLOT_1",
    Llm.GEMINI_3_FLASH_PREVIEW_MINIMAL,
)
MOS_IMPORT_MODEL_SLOT_2 = _read_llm_setting(
    "MOS_IMPORT_MODEL_SLOT_2",
    Llm.CLAUDE_OPUS_4_6,
)

# Image generation (optional)
REPLICATE_API_KEY = os.environ.get("REPLICATE_API_KEY", None)

# Debugging-related
IS_DEBUG_ENABLED = bool(os.environ.get("IS_DEBUG_ENABLED", False))
DEBUG_DIR = os.environ.get("DEBUG_DIR", "")

# Set to True when running in production (on the hosted version)
# Used as a feature flag to enable or disable certain features
IS_PROD = os.environ.get("IS_PROD", False)
