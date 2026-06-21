"""
Unified LLM client. Reads env vars in priority order:
  XAI_API_KEY    → xAI / Grok (requires credits)
  GROQ_API_KEY   → Groq / Llama (free tier, recommended)
  GEMINI_API_KEY → Google Gemini (free tier)
"""
import os
from openai import OpenAI

_client: OpenAI | None = None
_provider: str = ""


def get_client() -> tuple[OpenAI, str]:
    """Returns (client, default_model)."""
    global _client, _provider

    if _client is not None:
        return _client, _provider

    if os.environ.get("XAI_API_KEY"):
        _client = OpenAI(
            api_key=os.environ["XAI_API_KEY"],
            base_url="https://api.x.ai/v1",
        )
        _provider = "grok-3-mini"

    elif os.environ.get("GROQ_API_KEY"):
        _client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        _provider = "llama-3.3-70b-versatile"

    elif os.environ.get("GEMINI_API_KEY"):
        _client = OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        _provider = "gemini-1.5-flash"

    else:
        raise RuntimeError(
            "No LLM API key found. Set one of: XAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY in .env"
        )

    return _client, _provider


def chat(messages: list[dict], model: str | None = None, **kwargs) -> str:
    client, default_model = get_client()
    resp = client.chat.completions.create(
        model=model or default_model,
        messages=messages,
        **kwargs,
    )
    return resp.choices[0].message.content or ""
