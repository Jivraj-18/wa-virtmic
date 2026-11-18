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
