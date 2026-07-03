"""Optional Claude-powered analyst layer.

Feeds the quantitative scan (scores, signals, news) to Claude and asks for a
readable analyst brief: which picks look strongest, what the news implies,
and what risks the numbers might be hiding. Requires the `anthropic` package
and credentials (ANTHROPIC_API_KEY or an `ant auth login` profile).
"""
from __future__ import annotations

import json

MODEL = "claude-opus-4-8"

SYSTEM = (
    "You are a cautious equity research analyst covering NSE (India) stocks. "
    "You are given the output of a quantitative screen: multi-factor scores, "
    "intraday algorithmic signals, position sizing, and news headlines. "
    "Write a concise brief: (1) which investment picks look strongest and why, "
    "(2) which intraday setups have the best confluence, (3) what the news "
    "sentiment implies, (4) key risks and what would invalidate each idea. "
    "Never overstate certainty; always note that this is research, not advice."
)


def analyze(report: dict) -> str:
    """Return an AI analyst brief for the scan report, or an explanation of
    why the AI layer is unavailable."""
    try:
        import anthropic
    except ImportError:
        return "[ai] `pip install anthropic` to enable the AI analyst brief."

    client = anthropic.Anthropic()
    payload = json.dumps(report, indent=1, default=str)
    # Keep the prompt bounded even for a full 500-stock scan.
    if len(payload) > 150_000:
        payload = payload[:150_000] + "\n...[truncated]"

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Today's NSE scan output:\n\n{payload}\n\nWrite the analyst brief.",
            }],
        ) as stream:
            message = stream.get_final_message()
        return "".join(b.text for b in message.content if b.type == "text")
    except Exception as e:  # noqa: BLE001 — degrade gracefully, scan still useful
        return f"[ai] analyst brief unavailable: {e}"
