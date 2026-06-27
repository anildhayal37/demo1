import asyncio
import time
from collections import deque

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import Config
from data_feed import DataFeed
from portfolio import Portfolio


def _color_val(val: float, positive_color="green", negative_color="red") -> Text:
    color = positive_color if val >= 0 else negative_color
    sign = "+" if val > 0 else ""
    return Text(f"{sign}{val:,.2f}", style=color)


def _price_arrow(feed: DataFeed, symbol: str) -> str:
    cur = feed.get_price(symbol)
    prev = feed.get_prev_price(symbol)
    if cur is None or prev is None:
        return "─"
    if cur > prev:
        return "[green]▲[/green]"
    if cur < prev:
        return "[red]▼[/red]"
    return "─"


def build_prices_table(feed: DataFeed, symbols: list) -> Table:
    t = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    t.add_column("Symbol", style="bold white", width=10)
    t.add_column("Price", justify="right", width=14)
    t.add_column("Trend", width=4)
    for sym in symbols:
        price = feed.get_price(sym)
        arrow = _price_arrow(feed, sym)
        ticker = sym.replace("USDT", "")
        if price:
            t.add_row(ticker, f"${price:,.4f}", arrow)
        else:
            t.add_row(ticker, "connecting...", "─")
    return t


def build_positions_table(portfolio: Portfolio, feed: DataFeed) -> Table:
    t = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    t.add_column("Symbol", width=8)
    t.add_column("Side", width=6)
    t.add_column("Entry", justify="right", width=12)
    t.add_column("Current", justify="right", width=12)
    t.add_column("P&L", justify="right", width=10)
    positions = portfolio.get_open_positions()
    if not positions:
        t.add_row("[dim]no open positions[/dim]", "", "", "", "")
    for pos in positions:
        cur = feed.get_price(pos.symbol)
        if cur is None:
            upnl = 0.0
        elif pos.side == "long":
            upnl = (cur - pos.entry_price) * pos.qty
        else:
            upnl = (pos.entry_price - cur) * pos.qty
        side_color = "green" if pos.side == "long" else "red"
        pnl_text = _color_val(upnl)
        ticker = pos.symbol.replace("USDT", "")
        t.add_row(
            ticker,
            Text(pos.side.upper(), style=side_color),
            f"${pos.entry_price:,.2f}",
            f"${cur:,.2f}" if cur else "─",
            pnl_text,
        )
    return t


def build_stats_panel(portfolio: Portfolio, feed: DataFeed, start_time: float) -> Text:
    prices = feed.get_all_prices()
    equity = portfolio.get_total_equity(prices)
    rpnl = portfolio.get_realized_pnl()
    upnl = portfolio.get_unrealized_pnl(prices)
    stats = portfolio.get_stats()
    uptime = int(time.time() - start_time)
    h, m, s = uptime // 3600, (uptime % 3600) // 60, uptime % 60

    lines = [
        f"[bold]Cash Balance:[/bold]  [cyan]${portfolio.cash_balance:>12,.2f}[/cyan]",
        f"[bold]Total Equity:[/bold]  [cyan]${equity:>12,.2f}[/cyan]",
        "",
        f"[bold]Realized P&L:[/bold]  {'+' if rpnl >= 0 else ''}[{'green' if rpnl >= 0 else 'red'}]${rpnl:,.2f}[/{'green' if rpnl >= 0 else 'red'}]",
        f"[bold]Unrealized P&L:[/bold]{'+' if upnl >= 0 else ''}[{'green' if upnl >= 0 else 'red'}]${upnl:,.2f}[/{'green' if upnl >= 0 else 'red'}]",
        "",
        f"[bold]Total Trades:[/bold]  [white]{stats['total_trades']}[/white]",
        f"[bold]Win Rate:[/bold]      [white]{stats['win_rate']:.1f}%[/white]",
        f"[bold]Avg P&L/Trade:[/bold] [white]${stats['avg_pnl']:.2f}[/white]",
        "",
        f"[bold]Uptime:[/bold]        [dim]{h:02d}:{m:02d}:{s:02d}[/dim]",
    ]
    return Text.from_markup("\n".join(lines))


def build_trades_table(portfolio: Portfolio) -> Table:
    t = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    t.add_column("Time", width=10)
    t.add_column("Symbol", width=8)
    t.add_column("Side", width=6)
    t.add_column("Entry", justify="right", width=12)
    t.add_column("Exit", justify="right", width=12)
    t.add_column("P&L", justify="right", width=10)
    t.add_column("Reason", width=14)
    for trade in portfolio.get_trade_history(10):
        ts = time.strftime("%H:%M:%S", time.localtime(trade.timestamp))
        pnl_text = _color_val(trade.pnl)
        ticker = trade.symbol.replace("USDT", "")
        side_color = "green" if trade.side == "long" else "red"
        t.add_row(
            ts, ticker,
            Text(trade.side.upper(), style=side_color),
            f"${trade.entry_price:,.2f}",
            f"${trade.exit_price:,.2f}",
            pnl_text,
            Text(trade.exit_reason, style="dim"),
        )
    if not portfolio.get_trade_history(1):
        t.add_row("[dim]no trades yet[/dim]", "", "", "", "", "", "")
    return t


def build_log_panel(agent_log: deque) -> Text:
    lines = list(agent_log)[:12]
    if not lines:
        return Text("waiting for signals...", style="dim")
    parts = []
    for line in lines:
        if "BUY" in line or "LONG" in line:
            parts.append(Text(line, style="green"))
        elif "SELL" in line or "SHORT" in line or "CLOSED" in line:
            parts.append(Text(line, style="red"))
        elif "error" in line.lower():
            parts.append(Text(line, style="bold red"))
        else:
            parts.append(Text(line, style="dim white"))
    result = Text()
    for i, p in enumerate(parts):
        result.append_text(p)
        if i < len(parts) - 1:
            result.append("\n")
    return result


class Dashboard:
    def __init__(self, config: Config, feed: DataFeed, portfolio: Portfolio, agent_log: deque, start_time: float):
        self.config = config
        self.feed = feed
        self.portfolio = portfolio
        self.agent_log = agent_log
        self.start_time = start_time

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="trades", size=14),
            Layout(name="log", size=16),
        )
        layout["main"].split_row(
            Layout(name="prices", ratio=1),
            Layout(name="positions", ratio=2),
            Layout(name="stats", ratio=2),
        )

        prices = self.feed.get_all_prices()
        equity = self.portfolio.get_total_equity(prices)
        rpnl = self.portfolio.get_realized_pnl()
        sign = "+" if rpnl >= 0 else ""
        pnl_color = "green" if rpnl >= 0 else "red"

        header_text = Text(justify="center")
        header_text.append("  CRYPTO HFT PAPER TRADER  ", style="bold white on blue")
        header_text.append(f"  Strategy: {self.config.strategy.upper()}  ", style="bold yellow")
        header_text.append(f"  Equity: ${equity:,.2f}  ", style="bold cyan")
        header_text.append(f"  P&L: {sign}${rpnl:,.2f}  ", style=f"bold {pnl_color}")
        layout["header"].update(Panel(header_text, style="blue"))

        layout["prices"].update(
            Panel(build_prices_table(self.feed, self.config.symbols), title="[bold]Live Prices[/bold]", border_style="cyan")
        )
        layout["positions"].update(
            Panel(build_positions_table(self.portfolio, self.feed), title="[bold]Open Positions[/bold]", border_style="yellow")
        )
        layout["stats"].update(
            Panel(build_stats_panel(self.portfolio, self.feed, self.start_time), title="[bold]Portfolio Stats[/bold]", border_style="green")
        )
        layout["trades"].update(
            Panel(build_trades_table(self.portfolio), title="[bold]Recent Trades[/bold]", border_style="magenta")
        )
        layout["log"].update(
            Panel(build_log_panel(self.agent_log), title="[bold]Agent Activity Log[/bold]", border_style="dim")
        )
        return layout

    async def run(self):
        interval = 1.0 / self.config.dashboard_refresh_hz
        with Live(self._render(), refresh_per_second=self.config.dashboard_refresh_hz, screen=True) as live:
            while True:
                live.update(self._render())
                await asyncio.sleep(interval)
