import os
from dotenv import load_dotenv
import logging
from models import AskAgentRequest, CleanupElementsRequest
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from datetime import date, datetime

load_dotenv()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
logger = logging.getLogger(__name__)


def to_thread_config(query: AskAgentRequest | CleanupElementsRequest, user_id: str) -> RunnableConfig:
    """Extract request metadata into LangGraph RunnableConfig."""
    return {
            "configurable": {"thread_id": query.session_id, 
                             "user_id": user_id, 
                            "custom_project_id": query.project_id,
                            "llm_model" : query.llm_model},
            "metadata": {"query_id": query.query_id},
        }


def _parse_date(value: date | str | None, default: date) -> str:
    if value is None:
        return default.isoformat()
    if isinstance(value, str):
        return date.fromisoformat(value[:10]).isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise ValueError("date must be a date, datetime, or ISO format string")


_rate_limiters: dict[str, InMemoryRateLimiter] = {}

def _get_rate_limiter(model_name: str, config) -> InMemoryRateLimiter | None:
    """Return a shared (stateful) rate limiter for the given model, or None if disabled."""
    rps = config.async_tasks.llm.requests_per_second
    if not rps:
        return None
    if model_name not in _rate_limiters:
        _rate_limiters[model_name] = InMemoryRateLimiter(
            requests_per_second=rps,
            check_every_n_seconds=0.1,
            max_bucket_size=config.async_tasks.llm.max_burst_size,
        )
    return _rate_limiters[model_name]


PROVIDER_MAP = {
        "google": "google_genai",
        "openai": "openai",
        "meta": "together",
        "qwen": "together",
        "zai" : "together",
        "anthropic": "anthropic", 
    }

THINKING_KWARGS: dict[tuple[str, str], dict] = {
    ("google_genai", "flash"): {"include_thoughts": False},
    # Anthropic extended thinking — add when Claude is wired up:
    # ("anthropic", "claude"): {"thinking": {"type": "enabled", "budget_tokens": 8000}},
}

def pick_llm(llm_model: str, config) -> BaseChatModel:
    """Create LLM via init_chat_model from 'provider_model' string (e.g. 'google_gemini-2.5-flash')."""
    provider_key, model_name = llm_model.split("_", 1)
    model_provider = PROVIDER_MAP.get(provider_key)
    if not model_provider:
        logger.warning(f"⚠️  Unknown provider '{provider_key}' — defaulting to google_genai")
        model_provider = "google_genai"
    kwargs = {}
    for (provider, name_hint), thinking_kwargs in THINKING_KWARGS.items():
        if model_provider == provider and name_hint in model_name:
            kwargs.update(thinking_kwargs)
            break

    rate_limiter = _get_rate_limiter(model_name, config)
    logger.debug(f'🤖 LLM: provider={model_provider} model={model_name} thinking={bool(kwargs)} rps={config.async_tasks.llm.requests_per_second}')

    if model_provider in ["together"]:
        is_qwen3 = "Qwen3" in model_name
        return ChatOpenAI(
                    base_url=config.models.together.base_url,
                    api_key=os.getenv("TOGETHER_API_KEY"),
                    model=model_name,
                    max_tokens=config.models.together.max_tokens,
                    stream_usage=False,
                    stop=["<|im_end|>", "<|endoftext|>"] if is_qwen3 else None,
                    extra_body={"enable_thinking": False} if is_qwen3 else {},
                    rate_limiter=rate_limiter,
                )

    return init_chat_model(model_name, model_provider=model_provider, rate_limiter=rate_limiter, **kwargs)


def apply_retry(llm: BaseChatModel, config) -> BaseChatModel:
    """Wrap a chain with retry logic. Must be called AFTER bind_tools/with_structured_output."""
    retry_attempts = config.async_tasks.llm.retry_attempts
    if retry_attempts > 0:
        return llm.with_retry(stop_after_attempt=retry_attempts, wait_exponential_jitter=True)
    return llm

