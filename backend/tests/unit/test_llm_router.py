"""Tests for the LLMRouter abstraction layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.llm.router import (
    LLMRequest,
    LLMResponse,
    LLMRouter,
    ModelTier,
)


@pytest.fixture
def router():
    return LLMRouter()


class TestLLMRouter:
    @pytest.mark.asyncio
    async def test_complete_success(self, router):
        """Test successful LLM completion."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello!"))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        with patch(
            "app.integrations.llm.router.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response

            result = await router.complete(
                LLMRequest(
                    messages=[{"role": "user", "content": "Hi"}],
                    tier=ModelTier.FAST,
                )
            )

            assert isinstance(result, LLMResponse)
            assert result.content == "Hello!"
            assert result.input_tokens == 10
            assert result.output_tokens == 5

    @pytest.mark.asyncio
    async def test_failover_on_error(self, router):
        """Test that the router falls back to the next model on failure."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Fallback!"))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Primary model down")
            return mock_response

        with patch(
            "app.integrations.llm.router.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = side_effect

            result = await router.complete(
                LLMRequest(
                    messages=[{"role": "user", "content": "Hi"}],
                    tier=ModelTier.FAST,
                )
            )

            assert result.content == "Fallback!"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_models_fail_raises(self, router):
        """Test that RuntimeError is raised when all models fail."""
        with patch(
            "app.integrations.llm.router.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = Exception("All down")

            with pytest.raises(RuntimeError, match="All models failed"):
                await router.complete(
                    LLMRequest(
                        messages=[{"role": "user", "content": "Hi"}],
                        tier=ModelTier.FAST,
                    )
                )

    @pytest.mark.asyncio
    async def test_classify(self, router):
        """Test the classify convenience method."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="lead_inquiry"))]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=3)

        with patch(
            "app.integrations.llm.router.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response

            result = await router.classify(
                text="I need a new roof, can you help?",
                categories=["lead_inquiry", "scheduling", "complaint", "other"],
            )

            assert result == "lead_inquiry"

    def test_model_tiers_have_fallbacks(self, router):
        """Verify each tier has at least 2 models for failover."""
        for tier in ModelTier:
            models = router.model_map[tier]
            assert len(models) >= 2, f"Tier {tier.value} needs at least 2 models for failover"
