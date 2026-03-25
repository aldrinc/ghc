from unittest.mock import AsyncMock

import pytest

from routes.generate_code import ParameterExtractionStage


@pytest.mark.asyncio
async def test_extracts_gemini_api_key_from_settings_dialog() -> None:
    stage = ParameterExtractionStage(AsyncMock())

    extracted = await stage.extract_and_validate(
        {
            "generatedCodeConfig": "html_tailwind",
            "inputMode": "text",
            "openAiApiKey": "",
            "anthropicApiKey": "",
            "geminiApiKey": "gemini-from-ui",
            "prompt": {"text": "hello"},
        }
    )

    assert extracted.gemini_api_key == "gemini-from-ui"


@pytest.mark.asyncio
async def test_extracts_gemini_api_key_from_env_when_not_in_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("routes.generate_code.GEMINI_API_KEY", "gemini-from-env")
    stage = ParameterExtractionStage(AsyncMock())

    extracted = await stage.extract_and_validate(
        {
            "generatedCodeConfig": "html_tailwind",
            "inputMode": "text",
            "prompt": {"text": "hello"},
        }
    )

    assert extracted.gemini_api_key == "gemini-from-env"


@pytest.mark.asyncio
async def test_extracts_mos_import_model_slots() -> None:
    stage = ParameterExtractionStage(AsyncMock())

    extracted = await stage.extract_and_validate(
        {
            "generatedCodeConfig": "react_tailwind",
            "inputMode": "image",
            "requestSource": "mos_import",
            "modelSlots": [1, 2],
            "prompt": {
                "images": ["data:image/png;base64,abc"],
                "text": "Import this page",
            },
        }
    )

    assert extracted.request_source == "mos_import"
    assert extracted.model_slots == [1, 2]


@pytest.mark.asyncio
async def test_rejects_duplicate_mos_import_model_slots() -> None:
    stage = ParameterExtractionStage(AsyncMock())

    with pytest.raises(ValueError, match="Duplicate MOS import model slot"):
        await stage.extract_and_validate(
            {
                "generatedCodeConfig": "react_tailwind",
                "inputMode": "image",
                "requestSource": "mos_import",
                "modelSlots": [1, 1],
                "prompt": {
                    "images": ["data:image/png;base64,abc"],
                    "text": "Import this page",
                },
            }
        )
