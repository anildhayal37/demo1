"""Configuration for the NSE stock analysis agent."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    """Risk management settings (defaults follow common professional practice)."""

    # Fraction of total capital risked on a single trade (2% rule).
    risk_per_trade: float = 0.02
    # Max fraction of capital deployed into one position.
    max_position_pct: float = 0.20
    # Max fraction of capital deployed intraday at once.
    max_intraday_exposure: float = 0.60
    # Reward-to-risk ratio used for intraday targets.
    reward_risk_ratio: float = 2.0
    # ATR multiple used for stop-loss placement.
    atr_stop_multiple: float = 1.5


@dataclass
class AgentConfig:
    # Total capital available for investing (INR).
    capital: float = 100_000.0
    # How many top picks to show in each report.
    top_n: int = 10
    # Limit the universe (None = full Nifty 500). Useful to keep scans fast.
    universe_size: int | None = None
    # Lookback period for daily data.
    history_period: str = "1y"
    # News lookback per stock (articles).
    news_per_stock: int = 8
    # Enable the Claude-powered AI analyst summary (needs ANTHROPIC_API_KEY
    # or an `ant auth login` profile).
    use_ai_analyst: bool = False
    risk: RiskConfig = field(default_factory=RiskConfig)

    @classmethod
    def from_env(cls) -> "AgentConfig":
        cfg = cls()
        if cap := os.environ.get("NSE_AGENT_CAPITAL"):
            cfg.capital = float(cap)
        if n := os.environ.get("NSE_AGENT_TOP_N"):
            cfg.top_n = int(n)
        return cfg


DISCLAIMER = (
    "This tool is for education and research only. It is NOT investment advice. "
    "Markets carry risk of loss; algorithmic signals can and do fail. Consult a "
    "SEBI-registered investment adviser before trading real money."
)
