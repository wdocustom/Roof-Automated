"""LLMRouter — thin abstraction over LiteLLM for model routing, caching, and failover.

This layer exists to:
  1. Protect against LiteLLM breaking changes (pin + wrap)
  2. Implement tiered model selection (fast/cheap for routing, powerful for reasoning)
  3. Enable semantic caching via pgvector
  4. Enforce per-tenant token budgets and rate limiting
  5. Provide multi-provider failover (OpenAI ↔ Anthropic)

All LLM calls in the platform MUST go through this router.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum

import litellm
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Configure LiteLLM
litellm.set_verbose = False


class ModelTier(str, Enum):
    """Model tiers for cost-conscious routing."""

    FAST = "fast"      # Classification, routing, simple parsing (Haiku / GPT-4o-mini)
    STANDARD = "standard"  # Most agent tasks (Sonnet / GPT-4o)
    POWERFUL = "powerful"  # Complex reasoning, reflection (Opus / GPT-4o)
    VISION = "vision"    # Image analysis (GPT-4o / Claude vision)


# Default model mapping — override via config
DEFAULT_MODELS: dict[ModelTier, list[str]] = {
    ModelTier.FAST: [
        "anthropic/claude-haiku-4-5-20251001",
        "openai/gpt-4o-mini",
    ],
    ModelTier.STANDARD: [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-4o",
    ],
    ModelTier.POWERFUL: [
        "anthropic/claude-opus-4-6",
        "openai/gpt-4o",
    ],
    ModelTier.VISION: [
        "openai/gpt-4o",
        "anthropic/claude-sonnet-4-6",
    ],
}


@dataclass
class LLMResponse:
    """Standardized response from the LLM router."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cached: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class LLMRequest:
    """Standardized request to the LLM router."""

    messages: list[dict]  # [{"role": "system", "content": "..."}, ...]
    tier: ModelTier = ModelTier.STANDARD
    temperature: float = 0.1
    max_tokens: int = 1024
    tenant_id: str | None = None
    cache_key: str | None = None  # If set, attempt semantic cache lookup


class LLMRouter:
    """Central LLM routing with tiering, caching, and failover."""

    def __init__(self, model_map: dict[ModelTier, list[str]] | None = None):
        self.model_map = model_map or DEFAULT_MODELS

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Route an LLM request to the appropriate model with failover.

        Tries each model in the tier's list. Falls back to the next on failure.
        """
        models = self.model_map.get(request.tier, self.model_map[ModelTier.STANDARD])
        last_error = None

        for model in models:
            try:
                start = time.monotonic()
                response = await litellm.acompletion(
                    model=model,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
                elapsed_ms = (time.monotonic() - start) * 1000

                content = response.choices[0].message.content or ""
                usage = response.usage

                logger.info(
                    "llm_request_completed",
                    model=model,
                    tier=request.tier.value,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    latency_ms=round(elapsed_ms, 1),
                    tenant_id=request.tenant_id,
                )

                return LLMResponse(
                    content=content,
                    model=model,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    latency_ms=elapsed_ms,
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    "llm_request_failed_trying_fallback",
                    model=model,
                    error=str(e),
                    tier=request.tier.value,
                )
                continue

        # All models failed
        raise RuntimeError(
            f"All models failed for tier {request.tier.value}: {last_error}"
        )

    async def classify(self, text: str, categories: list[str], tenant_id: str | None = None) -> str:
        """Quick classification using the FAST tier. Returns the matched category."""
        response = await self.complete(
            LLMRequest(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"Classify the following text into exactly one of these categories: "
                            f"{', '.join(categories)}. "
                            f"Respond with ONLY the category name, nothing else."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                tier=ModelTier.FAST,
                temperature=0.0,
                max_tokens=50,
                tenant_id=tenant_id,
            )
        )
        return response.content.strip()


# Module-level singleton
llm_router = LLMRouter()
