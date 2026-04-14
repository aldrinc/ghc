import pytest
from unittest.mock import AsyncMock
from routes.generate_code import ModelSelectionStage
from llm import Llm


class TestModelSelectionAllKeys:
    """Test model selection when Gemini, Anthropic, and OpenAI API keys are present."""

    def setup_method(self):
        """Set up test fixtures."""
        mock_throw_error = AsyncMock()
        self.model_selector = ModelSelectionStage(mock_throw_error)

    @pytest.mark.asyncio
    async def test_gemini_anthropic_create(self):
        """All keys create: picks a single primary model."""
        models = await self.model_selector.select_models(
            generation_type="create",
            input_mode="text",
            openai_api_key="key",
            anthropic_api_key="key",
            gemini_api_key="key",
        )

        expected = [Llm.GEMINI_3_FLASH_PREVIEW_MINIMAL]
        assert models == expected

    @pytest.mark.asyncio
    async def test_gemini_anthropic_update_text(self):
        """All keys text update: picks a single primary model."""
        models = await self.model_selector.select_models(
            generation_type="update",
            input_mode="text",
            openai_api_key="key",
            anthropic_api_key="key",
            gemini_api_key="key",
        )

        expected = [Llm.GEMINI_3_FLASH_PREVIEW_MINIMAL]
        assert models == expected

    @pytest.mark.asyncio
    async def test_gemini_anthropic_update(self):
        """All keys image update: picks a single primary model."""
        models = await self.model_selector.select_models(
            generation_type="update",
            input_mode="image",
            openai_api_key="key",
            anthropic_api_key="key",
            gemini_api_key="key",
        )

        expected = [Llm.GEMINI_3_FLASH_PREVIEW_MINIMAL]
        assert models == expected

    @pytest.mark.asyncio
    async def test_video_create_prefers_gemini_3_1_high(self):
        """Video create uses a single Gemini primary model."""
        models = await self.model_selector.select_models(
            generation_type="create",
            input_mode="video",
            openai_api_key="key",
            anthropic_api_key="key",
            gemini_api_key="key",
        )

        expected = [Llm.GEMINI_3_1_PRO_PREVIEW_HIGH]
        assert models == expected

    @pytest.mark.asyncio
    async def test_video_update_prefers_gemini_3_1_high(self):
        """Video update uses the same single Gemini primary model as video create."""
        models = await self.model_selector.select_models(
            generation_type="update",
            input_mode="video",
            openai_api_key="key",
            anthropic_api_key="key",
            gemini_api_key="key",
        )

        expected = [Llm.GEMINI_3_1_PRO_PREVIEW_HIGH]
        assert models == expected


class TestModelSelectionOpenAIAnthropic:
    """Test model selection when only OpenAI and Anthropic keys are present."""

    def setup_method(self):
        """Set up test fixtures."""
        mock_throw_error = AsyncMock()
        self.model_selector = ModelSelectionStage(mock_throw_error)

    @pytest.mark.asyncio
    async def test_openai_anthropic(self):
        """OpenAI + Anthropic: picks a single primary model."""
        models = await self.model_selector.select_models(
            generation_type="create",
            input_mode="text",
            openai_api_key="key",
            anthropic_api_key="key",
            gemini_api_key=None,
        )

        expected = [Llm.CLAUDE_OPUS_4_6]
        assert models == expected


class TestModelSelectionAnthropicOnly:
    """Test model selection when only Anthropic key is present."""

    def setup_method(self):
        """Set up test fixtures."""
        mock_throw_error = AsyncMock()
        self.model_selector = ModelSelectionStage(mock_throw_error)

    @pytest.mark.asyncio
    async def test_anthropic_only(self):
        """Anthropic only: picks a single primary model."""
        models = await self.model_selector.select_models(
            generation_type="create",
            input_mode="text",
            openai_api_key=None,
            anthropic_api_key="key",
            gemini_api_key=None,
        )

        expected = [Llm.CLAUDE_OPUS_4_6]
        assert models == expected


class TestModelSelectionOpenAIOnly:
    """Test model selection when only OpenAI key is present."""

    def setup_method(self):
        """Set up test fixtures."""
        mock_throw_error = AsyncMock()
        self.model_selector = ModelSelectionStage(mock_throw_error)

    @pytest.mark.asyncio
    async def test_openai_only(self):
        """OpenAI only: picks a single primary model."""
        models = await self.model_selector.select_models(
            generation_type="create",
            input_mode="text",
            openai_api_key="key",
            anthropic_api_key=None,
            gemini_api_key=None,
        )

        expected = [Llm.GPT_5_2_CODEX_HIGH]
        assert models == expected


class TestModelSelectionNoKeys:
    """Test model selection when no API keys are present."""

    def setup_method(self):
        """Set up test fixtures."""
        mock_throw_error = AsyncMock()
        self.model_selector = ModelSelectionStage(mock_throw_error)

    @pytest.mark.asyncio
    async def test_no_keys_raises_error(self):
        """No keys: Should raise an exception"""
        with pytest.raises(Exception, match="No API key"):
            await self.model_selector.select_models(
                generation_type="create",
                input_mode="text",
                openai_api_key=None,
                anthropic_api_key=None,
                gemini_api_key=None,
            )


class TestMosImportModelSelection:
    def setup_method(self):
        mock_throw_error = AsyncMock()
        self.model_selector = ModelSelectionStage(mock_throw_error)

    @pytest.mark.asyncio
    async def test_mos_import_uses_explicit_slots_only(self):
        models = await self.model_selector.select_models(
            generation_type="create",
            input_mode="image",
            openai_api_key="openai-key",
            anthropic_api_key="anthropic-key",
            gemini_api_key="gemini-key",
            request_source="mos_import",
            model_slots=[1, 2],
        )

        assert models == [
            Llm.GEMINI_3_FLASH_PREVIEW_MINIMAL,
            Llm.CLAUDE_OPUS_4_6,
        ]

    @pytest.mark.asyncio
    async def test_mos_import_rejects_unsupported_slot(self):
        with pytest.raises(ValueError, match="Unsupported MOS import model slot"):
            await self.model_selector.select_models(
                generation_type="create",
                input_mode="image",
                openai_api_key=None,
                anthropic_api_key="anthropic-key",
                gemini_api_key="gemini-key",
                request_source="mos_import",
                model_slots=[3],
            )

    @pytest.mark.asyncio
    async def test_mos_import_requires_gemini_key_for_slot_one(self):
        with pytest.raises(ValueError, match="requires GEMINI_API_KEY"):
            await self.model_selector.select_models(
                generation_type="create",
                input_mode="image",
                openai_api_key=None,
                anthropic_api_key="anthropic-key",
                gemini_api_key=None,
                request_source="mos_import",
                model_slots=[1],
            )

    @pytest.mark.asyncio
    async def test_mos_import_requires_anthropic_key_for_slot_two(self):
        with pytest.raises(ValueError, match="requires ANTHROPIC_API_KEY"):
            await self.model_selector.select_models(
                generation_type="create",
                input_mode="image",
                openai_api_key=None,
                anthropic_api_key=None,
                gemini_api_key="gemini-key",
                request_source="mos_import",
                model_slots=[2],
            )
