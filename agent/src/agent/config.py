import asyncio
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Controls concurrency and throttling for LLM calls.

    max_concurrent: max simultaneous astream calls (asyncio.Semaphore)
    throttle_value: seconds to sleep after each LLM call (inside the semaphore)

    Usage:
        AgentConfig.for_model("anthropic_claude-sonnet-4-6")
        AgentConfig(max_concurrent=2, throttle_value=3.0)
    """

    max_concurrent: int = 10
    throttle_value: float = 0.0

    def __post_init__(self):
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if self.throttle_value < 0:
            raise ValueError("throttle_value must be >= 0")

    # Per-provider defaults derived from typical API tier limits.
    # Anthropic tier-1: 30k input tokens/min → typically only 1-2 calls/min with full context.
    # OpenAI gpt-4o: 800k TPM → more headroom.
    # Gemini / open-source (Together): very high or no hard limits.
    _PROVIDER_DEFAULTS: dict = field(default_factory=dict, init=False, repr=False)

    @classmethod
    def for_model(cls, llm_model: str) -> "AgentConfig":
        """Return sensible defaults based on the provider prefix of the model string.

        Provider prefix is the part before the first underscore:
            "anthropic_claude-sonnet-4-6"  → "anthropic"
            "google_gemini-2.5-flash"      → "google"
            "openai_gpt-4o"                → "openai"
        """
        provider = llm_model.split("_", 1)[0] if llm_model else ""
        defaults = {
            "anthropic": cls(max_concurrent=1, throttle_value=5.0),
            "openai":    cls(max_concurrent=3, throttle_value=1.0),
        }
        return defaults.get(provider, cls())
