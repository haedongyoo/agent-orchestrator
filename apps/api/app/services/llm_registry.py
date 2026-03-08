"""
LLM Registry — authoritative list of supported providers and models.

Used by:
  - GET /api/llm/providers          → UI provider dropdown
  - GET /api/llm/providers/{id}/models → UI model dropdown
  - Validation when saving LLMConfig

Adding a new provider: append to PROVIDERS below.
The `model_id` field is the full LiteLLM model string passed to litellm.acompletion().
"""
from __future__ import annotations
from typing import Optional, TypedDict


class ModelEntry(TypedDict):
    id: str           # LiteLLM model string (e.g. "anthropic/claude-opus-4-6")
    name: str         # Human-readable label for UI
    recommended: bool


class ProviderEntry(TypedDict):
    id: str
    name: str
    requires_api_key: bool
    requires_base_url: bool
    base_url_placeholder: str   # hint shown in UI when requires_base_url=True
    api_key_label: str          # label shown in UI (e.g. "Anthropic API Key")
    docs_url: str
    note: str                   # shown as tooltip/info in UI
    models: list[ModelEntry]


PROVIDERS: list[ProviderEntry] = [
    {
        "id": "anthropic",
        "name": "Anthropic",
        "requires_api_key": True,
        "requires_base_url": False,
        "base_url_placeholder": "",
        "api_key_label": "Anthropic API Key",
        "docs_url": "https://console.anthropic.com/keys",
        "note": "",
        "models": [
            {"id": "anthropic/claude-opus-4-6",           "name": "Claude Opus 4.6",    "recommended": True},
            {"id": "anthropic/claude-sonnet-4-6",         "name": "Claude Sonnet 4.6",  "recommended": False},
            {"id": "anthropic/claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5",   "recommended": False},
        ],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "requires_api_key": True,
        "requires_base_url": False,
        "base_url_placeholder": "",
        "api_key_label": "OpenAI API Key",
        "docs_url": "https://platform.openai.com/api-keys",
        "note": "",
        "models": [
            {"id": "gpt-4o",      "name": "GPT-4o",       "recommended": True},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini",  "recommended": False},
            {"id": "o1",          "name": "o1",            "recommended": False},
            {"id": "o3-mini",     "name": "o3-mini",       "recommended": False},
        ],
    },
    {
        "id": "google",
        "name": "Google Gemini",
        "requires_api_key": True,
        "requires_base_url": False,
        "base_url_placeholder": "",
        "api_key_label": "Google AI API Key",
        "docs_url": "https://aistudio.google.com/apikey",
        "note": "",
        "models": [
            {"id": "gemini/gemini-2.5-flash",  "name": "Gemini 2.5 Flash",  "recommended": True},
            {"id": "gemini/gemini-2.0-flash",  "name": "Gemini 2.0 Flash",  "recommended": False},
            {"id": "gemini/gemini-1.5-pro",    "name": "Gemini 1.5 Pro",    "recommended": False},
            {"id": "gemini/gemini-1.5-flash",  "name": "Gemini 1.5 Flash",  "recommended": False},
        ],
    },
    {
        "id": "groq",
        "name": "Groq",
        "requires_api_key": True,
        "requires_base_url": False,
        "base_url_placeholder": "",
        "api_key_label": "Groq API Key",
        "docs_url": "https://console.groq.com/keys",
        "note": "Very fast inference for open-source models.",
        "models": [
            {"id": "groq/llama-3.3-70b-versatile",  "name": "Llama 3.3 70B Versatile", "recommended": True},
            {"id": "groq/llama-3.1-8b-instant",     "name": "Llama 3.1 8B Instant",    "recommended": False},
            {"id": "groq/mixtral-8x7b-32768",        "name": "Mixtral 8x7B",            "recommended": False},
        ],
    },
    {
        "id": "mistral",
        "name": "Mistral AI",
        "requires_api_key": True,
        "requires_base_url": False,
        "base_url_placeholder": "",
        "api_key_label": "Mistral API Key",
        "docs_url": "https://console.mistral.ai/api-keys",
        "note": "",
        "models": [
            {"id": "mistral/mistral-large-latest",  "name": "Mistral Large",  "recommended": True},
            {"id": "mistral/mistral-small-latest",  "name": "Mistral Small",  "recommended": False},
        ],
    },
    {
        "id": "ollama",
        "name": "Ollama (Local / Self-hosted)",
        "requires_api_key": False,
        "requires_base_url": True,
        "base_url_placeholder": "http://ollama:11434",
        "api_key_label": "",
        "docs_url": "https://ollama.com",
        "note": "Run models locally — no API key required. Make sure your Ollama server is reachable from the agent containers on agent-net.",
        "models": [
            {"id": "ollama/llama3.3",   "name": "Llama 3.3",  "recommended": True},
            {"id": "ollama/llama3.2",   "name": "Llama 3.2",  "recommended": False},
            {"id": "ollama/llama3.1",   "name": "Llama 3.1",  "recommended": False},
            {"id": "ollama/qwen2.5",    "name": "Qwen 2.5",   "recommended": False},
            {"id": "ollama/mistral",    "name": "Mistral",     "recommended": False},
            {"id": "ollama/phi4",       "name": "Phi-4",       "recommended": False},
            {"id": "ollama/deepseek-r1","name": "DeepSeek R1", "recommended": False},
        ],
    },
    {
        "id": "bedrock",
        "name": "AWS Bedrock",
        "requires_api_key": False,
        "requires_base_url": False,
        "base_url_placeholder": "",
        "api_key_label": "",
        "docs_url": "https://docs.aws.amazon.com/bedrock",
        "note": "Uses AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION_NAME environment variables. Set these in your orchestrator environment.",
        "models": [
            {"id": "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", "name": "Claude 3.5 Sonnet (Bedrock)", "recommended": True},
            {"id": "bedrock/meta.llama3-70b-instruct-v1:0",            "name": "Llama 3 70B (Bedrock)",       "recommended": False},
            {"id": "bedrock/mistral.mistral-large-2402-v1:0",          "name": "Mistral Large (Bedrock)",     "recommended": False},
        ],
    },
    {
        "id": "azure",
        "name": "Azure OpenAI",
        "requires_api_key": True,
        "requires_base_url": True,
        "base_url_placeholder": "https://<your-resource>.openai.azure.com/",
        "api_key_label": "Azure OpenAI API Key",
        "docs_url": "https://portal.azure.com",
        "note": "Set Base URL to your Azure OpenAI resource endpoint. The model name should be your deployment name.",
        "models": [
            {"id": "azure/gpt-4o",      "name": "GPT-4o (Azure deployment)",       "recommended": True},
            {"id": "azure/gpt-4o-mini", "name": "GPT-4o Mini (Azure deployment)",  "recommended": False},
        ],
    },
]

# Flat lookup by provider id
_PROVIDER_MAP: dict[str, ProviderEntry] = {p["id"]: p for p in PROVIDERS}

# Flat set of all valid model ids (for validation)
VALID_MODEL_IDS: set[str] = {m["id"] for p in PROVIDERS for m in p["models"]}


def get_provider(provider_id: str) -> Optional[ProviderEntry]:
    return _PROVIDER_MAP.get(provider_id)


def get_provider_for_model(model_id: str) -> Optional[ProviderEntry]:
    for provider in PROVIDERS:
        if any(m["id"] == model_id for m in provider["models"]):
            return provider
    return None
