"""Settings for the OpenAI-compatible LLM gateway (base URL + bearer token), read from scripts/.env.

  LLM_GATEWAY_BASE     e.g. https://gateway.example.com   (OpenAI routes live under /openai/v1/...)
  LLM_GATEWAY_TOKEN    bearer token
  LLM_GATEWAY_PROJECT  optional; sent as "Bearer <token>:<project>" (some gateways use this for usage tracking)
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env() -> None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def has_gateway() -> bool:
    load_env()
    return bool(os.environ.get("LLM_GATEWAY_TOKEN") and os.environ.get("LLM_GATEWAY_BASE"))


def base() -> str:
    load_env()
    return os.environ["LLM_GATEWAY_BASE"].rstrip("/")


def auth_header() -> dict:
    load_env()
    tok = os.environ["LLM_GATEWAY_TOKEN"]
    proj = os.environ.get("LLM_GATEWAY_PROJECT", "wa-virtmic")
    return {"Authorization": f"Bearer {tok}:{proj}" if proj else f"Bearer {tok}"}


# ---- model defaults (newest that work through the gateway, checked 2026-11-19) --------------------------
CHAT_MODEL = os.environ.get("LLM_CHAT_MODEL", "gpt-5.4-mini")          # fast helper calls (was gpt-4.1-mini)
TTS_MODEL = os.environ.get("LLM_GATEWAY_TTS_MODEL", "gpt-4o-mini-tts-2025-12-15")


def adapt_chat(body: dict) -> dict:
    """Make a chat.completions body valid for GPT-5 / o-series models: they reject temperature and max_tokens
    (use max_completion_tokens, which also counts reasoning tokens) and take reasoning_effort."""
    m = str(body.get("model", ""))
    if m.startswith(("gpt-5", "o1", "o3", "o4")):
        body = dict(body)
        body.pop("temperature", None)
        if "max_tokens" in body:
            body["max_completion_tokens"] = max(300, int(body.pop("max_tokens")))
        body.setdefault("reasoning_effort", "none" if m.startswith(("gpt-5.4", "gpt-5.5", "gpt-5.6")) else "minimal")
    return body
