"""The agent orchestrator: scan universe -> score -> signals -> sizing -> report."""
from __future__ import annotations

from dataclasses import asdict

from . import data, news, risk, strategies, universe
from .config import DISCLAIMER, AgentConfig


class NSEAgent:
    def __init__(self, config: AgentConfig | None = None):
        self.cfg = config or AgentConfig()

    # ------------------------------------------------------------------
    def run(self, mode: str = "both") -> dict:
        """mode: 'invest', 'intraday', or 'both'. Returns the full report dict."""
        cfg = self.cfg
        symbols = universe.fetch_nifty500(limit=cfg.universe_size)
        daily = data.fetch_daily(symbols, period=cfg.history_period)
        print(f"[agent] {len(daily)} symbols with usable history")

        report: dict = {"capital": cfg.capital, "universe_size": len(daily),
                        "disclaimer": DISCLAIMER}

        scores = self._score_all(daily)
        if mode in ("invest", "both"):
            report["investment_picks"] = self._investment_report(scores)
        if mode in ("intraday", "both"):
            report["intraday_signals"] = self._intraday_report(scores, daily)
        return report

    # ------------------------------------------------------------------
    def _score_all(self, daily: dict) -> list[strategies.StockScore]:
        scores = []
        for i, (sym, df) in enumerate(daily.items(), 1):
            scores.append(strategies.score_stock(sym, df))
            print(f"[agent] scoring {i}/{len(daily)}", end="\r")
        print()
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def _enrich_top(self, top: list[strategies.StockScore], daily_lookup=None):
        """Add fundamentals + news only for the shortlist (keeps the scan fast)."""
        for s in top:
            f = data.fetch_fundamentals(s.symbol)
            nr = news.fetch_news(s.symbol, limit=self.cfg.news_per_stock)
            rescored = strategies.score_stock(
                s.symbol, daily_lookup[s.symbol] if daily_lookup else None,
                fundamentals=f, news_sentiment=nr.sentiment, headlines=nr.headlines,
            ) if daily_lookup else None
            if rescored:
                s.score, s.rating, s.factors = rescored.score, rescored.rating, rescored.factors
            s.news_sentiment = round(nr.sentiment, 2)
            s.headlines = nr.headlines[:5]
        top.sort(key=lambda s: s.score, reverse=True)
        return top

    # ------------------------------------------------------------------
    def _investment_report(self, scores: list[strategies.StockScore]) -> list[dict]:
        cfg = self.cfg
        # Take 2x shortlist, enrich with fundamentals + news, then keep top N.
        shortlist = [s for s in scores if s.rating in ("STRONG BUY", "BUY")][: cfg.top_n * 2]
        # Re-fetch daily frames for rescoring the shortlist with news/fundamentals.
        daily_lookup = data.fetch_daily([s.symbol for s in shortlist], period=cfg.history_period)
        shortlist = [s for s in shortlist if s.symbol in daily_lookup]
        top = self._enrich_top(shortlist, daily_lookup)[: cfg.top_n]

        alloc = risk.allocate_portfolio(cfg.capital, top, cfg.risk)
        picks = []
        for s in top:
            amount = alloc.get(s.symbol, 0.0)
            qty = int(amount / s.close) if s.close else 0
            picks.append({
                **asdict(s),
                "suggested_allocation_inr": amount,
                "suggested_quantity": qty,
                "approx_invest_inr": round(qty * s.close, 2),
            })
        return picks

    # ------------------------------------------------------------------
    def _intraday_report(self, scores: list[strategies.StockScore], daily: dict) -> list[dict]:
        cfg = self.cfg
        # Only hunt intraday setups in liquid, high-scoring names (top 50).
        watch = [s.symbol for s in scores[:50]]
        intra = data.fetch_intraday(watch)
        out = []
        for sym in watch:
            if sym not in intra:
                continue
            for sig in strategies.intraday_signals(
                sym, intra[sym], daily[sym], reward_risk=cfg.risk.reward_risk_ratio
            ):
                plan = risk.size_position(cfg.capital, sig.entry, sig.stop_loss,
                                          sig.target, cfg.risk)
                if plan.quantity <= 0:
                    continue
                out.append({**asdict(sig), "position": asdict(plan)})
        out.sort(key=lambda d: d["confidence"], reverse=True)
        return out[: cfg.top_n]
