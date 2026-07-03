"""Position sizing and risk management.

Answers "how much do I buy/sell": quantity and rupee amounts derived from
your capital using the fixed-fractional (2%) risk rule that professional
traders use — risk a fixed slice of capital per trade, let the distance to
the stop-loss determine the share quantity.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import RiskConfig


@dataclass
class PositionPlan:
    quantity: int
    invest_amount: float      # rupees deployed at entry
    risk_amount: float        # rupees lost if stop-loss hits
    potential_profit: float   # rupees gained if target hits
    note: str = ""


def size_position(capital: float, entry: float, stop_loss: float,
                  target: float | None = None,
                  risk: RiskConfig | None = None) -> PositionPlan:
    """Fixed-fractional sizing: qty = (capital x risk%) / per-share risk."""
    risk = risk or RiskConfig()
    per_share_risk = abs(entry - stop_loss)
    if per_share_risk <= 0 or entry <= 0:
        return PositionPlan(0, 0.0, 0.0, 0.0, "invalid entry/stop")

    risk_budget = capital * risk.risk_per_trade
    qty = int(risk_budget / per_share_risk)

    # Cap by max position size so one trade can't dominate the book.
    max_qty = int(capital * risk.max_position_pct / entry)
    note = ""
    if qty > max_qty:
        qty = max_qty
        note = f"capped at {risk.max_position_pct:.0%} of capital"
    if qty <= 0:
        return PositionPlan(0, 0.0, 0.0, 0.0,
                            "stock too expensive/volatile for this capital at 2% risk")

    per_share_reward = abs((target or entry) - entry)
    return PositionPlan(
        quantity=qty,
        invest_amount=round(qty * entry, 2),
        risk_amount=round(qty * per_share_risk, 2),
        potential_profit=round(qty * per_share_reward, 2),
        note=note,
    )


def allocate_portfolio(capital: float, picks: list, risk: RiskConfig | None = None) -> dict[str, float]:
    """Score-weighted rupee allocation across investment picks."""
    risk = risk or RiskConfig()
    total_score = sum(p.score for p in picks) or 1.0
    alloc: dict[str, float] = {}
    for p in picks:
        amt = capital * (p.score / total_score)
        alloc[p.symbol] = round(min(amt, capital * risk.max_position_pct), 2)
    return alloc
