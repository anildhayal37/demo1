from dataclasses import dataclass, field


@dataclass
class Config:
    initial_balance: float = 100_000.0
    symbols: list = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    strategy: str = "momentum"
    trade_size_usd: float = 2_000.0
    take_profit_pct: float = 0.004
    stop_loss_pct: float = 0.002
    momentum_window: int = 20
    mean_rev_window: int = 50
    spread_symbols: tuple = ("BTCUSDT", "ETHUSDT")
    spread_z_threshold: float = 2.0
    tick_interval_ms: int = 250
    dashboard_refresh_hz: float = 4.0
    websocket_url: str = "wss://stream.binance.com:9443/stream"
    rest_url: str = "https://api.binance.com/api/v3"
    max_open_positions: int = 5
    fee_pct: float = 0.0001
    price_buffer_size: int = 200
