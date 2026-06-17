"""Minimal HTTP client for a local LLM.

Defaults to Ollama at http://localhost:11434. To use a different host or model,
pass ``--host`` and ``--model`` to the CLI, or set ``OLLAMA_HOST`` /
``RESUME_AGENT_MODEL`` in the environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class LLMConfig:
    base_url: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model: str = os.environ.get("RESUME_AGENT_MODEL", "llama3.1")
    temperature: float = 0.2
    timeout: int = 180


class LLMError(RuntimeError):
    """Raised when the local LLM is unreachable or returns malformed output."""


def chat(messages: list[dict], cfg: LLMConfig | None = None) -> str:
    cfg = cfg or LLMConfig()
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": cfg.temperature},
    }
    req = urllib.request.Request(
        f"{cfg.base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise LLMError(
            f"could not reach local LLM at {cfg.base_url} -- is Ollama running? "
            f"(`ollama serve` and `ollama pull {cfg.model}`). underlying error: {e}"
        ) from e
    return ((data.get("message") or {}).get("content") or "").strip()
