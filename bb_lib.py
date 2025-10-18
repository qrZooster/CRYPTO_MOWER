# bb_lib.py
# ALIAS: BB_LIB
# Created: 2025-09-18

import requests
from collections import deque, defaultdict
from bb_db import *
from bb_vars import *

MARKET_FILTER_QUOTE = USDT

# --- Настройки стратегии ---
WINDOW = 30
VOLUME_MULTIPLIER = 3.0
PRICE_CHANGE = 0.003
STRONG_PRICE_JUMP = 0.03
STRONG_VOLUME_MULT = 20.0
# Часовой пояс для вывода (МСК)

class RollingStats:
    def __init__(self):
        self.volumes = deque(maxlen=WINDOW)
        self.last_price = None

    def update(self, price: float, volume: float):
        self.last_price = price
        self.volumes.append(volume)

    def ready(self) -> bool:
        return len(self.volumes) == self.volumes.maxlen and self.last_price is not None

    def avg_volume(self) -> float:
        return sum(self.volumes)/len(self.volumes) if self.volumes else 0.0

class BybitSymbols:
    @staticmethod
    def fetch_linear_usdt_symbols() -> list:
        r = requests.get(f"{BYBIT_REST}/v5/market/instruments-info", params={"category": "linear"}, timeout=10)
        r.raise_for_status()
        items = r.json().get("result", {}).get("list", [])
        return [it["symbol"] for it in items if it.get("quoteCoin") == MARKET_FILTER_QUOTE and it.get("status") == "Trading"]

class PumpDumpStrategy:
    def __init__(self):#WINDOW, VOLUME_MULTIPLIER, PRICE_CHANGE , window=WINDOW, v_mult=VOLUME_MULTIPLIER, price_change=PRICE_CHANGE
        self.window = WINDOW
        self.v_mult = VOLUME_MULTIPLIER
        self.price_change = PRICE_CHANGE
        self.stats = defaultdict(lambda: RollingStats())
        self.last_sec_price = defaultdict(lambda: deque(maxlen=2))

    def on_trade(self, symbol: str, ts_ms: int, price: float, volume: float, db: bbDB):
        self.stats[symbol].update(price, volume)
        self.last_sec_price[symbol].append(price)
        self._maybe_emit_signal(symbol, ts_ms, price, volume, db)

    def _maybe_emit_signal(self, symbol: str, ts_ms: int, price: float, volume: float, db: bbDB):
        rs = self.stats[symbol]
        if not rs.ready() or len(self.last_sec_price[symbol]) < 2:
            return
        avg_v = rs.avg_volume()
        if avg_v == 0:
            return
        last, curr = self.last_sec_price[symbol][0], self.last_sec_price[symbol][1]
        price_delta = (curr - last) / last if last else 0.0
        x_volume = volume / avg_v if avg_v > 0 else 0.0

        # STRONG PUMP/DUMP
        if x_volume > STRONG_VOLUME_MULT and abs(price_delta) > STRONG_PRICE_JUMP:
            type_sig = "PUMP" if price_delta > 0 else "DUMP"
            action = BUY if type_sig == "PUMP" else SELL
            p_price = price_delta * 100.0
            strength = x_volume * abs(price_delta)
            reason = f"strong {type_sig.lower()} Δp={price_delta:.4f}, vol×={x_volume:.2f}"
            db.insert_signal(symbol, ts_ms, action, price, strength, reason, x_volume, p_price, type_sig)

        # Обычный PUMP
        elif x_volume > self.v_mult and price_delta > self.price_change:
            p_price = price_delta * 100.0
            strength = x_volume * price_delta
            reason = f"pump Δp={price_delta:.4f}, vol×={x_volume:.2f}"
            db.insert_signal(symbol, ts_ms, BUY, price, strength, reason, x_volume, p_price, "PUMP")

        # Обычный DUMP
        elif x_volume > self.v_mult and price_delta < -self.price_change:
            p_price = price_delta * 100.0
            strength = x_volume * abs(price_delta)
            reason = f"dump Δp={price_delta:.4f}, vol×={x_volume:.2f}"
            db.insert_signal(symbol, ts_ms, SELL, price, strength, reason, x_volume, p_price, "DUMP")