# bybit_pump_bot.py
# Торговый бот для отслеживания пампов/дампов на Bybit (с форматированием сигналов для Telegram)

import os
import json
import time
import asyncio
import requests
import mysql.connector as mysql
import websocket
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone
from telegram import Bot

# --- Переключение между боевым и тестовым режимом ---
BYBIT_MODE = os.getenv("BYBIT_MODE", "prod")  # prod | test

if BYBIT_MODE == "test":
    BYBIT_WS_PUBLIC_LINEAR = "wss://stream-testnet.bybit.com/v5/public/linear"
    BYBIT_REST = "https://api-testnet.bybit.com"
else:
    BYBIT_WS_PUBLIC_LINEAR = "wss://stream.bybit.com/v5/public/linear"
    BYBIT_REST = "https://api.bybit.com"

MARKET_FILTER_QUOTE = "USDT"

# --- Настройки стратегии ---
WINDOW = 30
VOLUME_MULTIPLIER = 3.0
PRICE_CHANGE = 0.003
STRONG_PRICE_JUMP = 0.03
STRONG_VOLUME_MULT = 20.0

# Часовой пояс для вывода (МСК)
MSK = timezone(timedelta(hours=3))

# --- Конфигурация БД ---
DB_CFG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "u267510"),
    "password": os.getenv("DB_PASS", "_n2FeRUP.6"),
    "database": os.getenv("DB_NAME", "u267510_tg")
}

# --- Telegram ---
TG_TOKEN = os.getenv("TG_TOKEN", "7640786990:AAHFDfJy0iqwhxaO_nCLk-RCJpETH_7Fux8")
TG_USER_ID = int(os.getenv("TG_USER_ID", 694169894))

async def _send_telegram_async(bot, chat_id, msg):
    try:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        print("Telegram error:", e)

def send_telegram(bot, chat_id, msg):
    try:
        asyncio.run(_send_telegram_async(bot, chat_id, msg))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(_send_telegram_async(bot, chat_id, msg))

# --- Класс для БД ---
class DB:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.conn = mysql.connect(**self.cfg)
        self.conn.autocommit = True

    def exec(self, sql: str, params=None):
        cur = self.conn.cursor()
        cur.execute(sql, params or [])
        return cur

    def insert_signal(self, symbol: str, ts_ms: int, action: str, price: float,
                      strength: float, reason: str, p_volume: float, p_price: float,
                      type_sig: str, tg_bot=None, tg_user_id=None):
        self.exec(
            "INSERT INTO ZZ$SIGNALS(FLD$SYMBOL, FLD$TS_MS, FLD$ACTION, FLD$PRICE, FLD$STRENGTH, FLD$REASON, FLD$P_VOLUME, FLD$P_PRICE, FLD$TYPE, FLD$DATE_OTP) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            (symbol, ts_ms, action, price, strength, reason, p_volume, p_price, type_sig)
        )
        dt_str = datetime.fromtimestamp(ts_ms/1000, tz=MSK).strftime("%H:%M:%S")
        emoji = "🟢🚀" if type_sig == "PUMP" else "🔴⚠️"
        link = f"https://www.coinglass.com/tv/Bybit_{symbol}"
        msg = (
            f"{emoji} {type_sig} [{symbol}]({link})\n"
            f"{dt_str}\n"
            f"ΔP= {p_price:.2f}%, ΔVol= x{(p_volume/100+1):.1f}"
        )
        print(msg)
        if tg_bot and tg_user_id:
            send_telegram(tg_bot, tg_user_id, msg)

# --- Вспомогательные классы ---
class RollingStats:
    def __init__(self, window: int):
        self.volumes = deque(maxlen=window)
        self.last_price = None

    def update(self, price: float, volume: float):
        self.last_price = price
        self.volumes.append(volume)

    def ready(self) -> bool:
        return len(self.volumes) == self.volumes.maxlen and self.last_price is not None

    def avg_volume(self) -> float:
        return sum(self.volumes)/len(self.volumes) if self.volumes else 0.0

class PumpDumpStrategy:
    def __init__(self, window=WINDOW, v_mult=VOLUME_MULTIPLIER, price_change=PRICE_CHANGE, tg_bot=None):
        self.window = window
        self.v_mult = v_mult
        self.price_change = price_change
        self.stats = defaultdict(lambda: RollingStats(window))
        self.last_sec_price = defaultdict(lambda: deque(maxlen=2))
        self.tg_bot = tg_bot

    def on_trade(self, symbol: str, ts_ms: int, price: float, volume: float, db: DB):
        self.stats[symbol].update(price, volume)
        self.last_sec_price[symbol].append(price)
        self._maybe_emit_signal(symbol, ts_ms, price, volume, db)

    def _maybe_emit_signal(self, symbol: str, ts_ms: int, price: float, volume: float, db: DB):
        rs = self.stats[symbol]
        if not rs.ready() or len(self.last_sec_price[symbol]) < 2:
            return
        avg_v = rs.avg_volume()
        if avg_v == 0:
            return
        last, curr = self.last_sec_price[symbol][0], self.last_sec_price[symbol][1]
        price_delta = (curr - last) / last if last else 0.0

        # STRONG PUMP/DUMP
        if volume > STRONG_VOLUME_MULT * avg_v and abs(price_delta) > STRONG_PRICE_JUMP:
            type_sig = "PUMP" if price_delta > 0 else "DUMP"
            action = "BUY" if type_sig == "PUMP" else "SELL"
            p_volume = (volume / avg_v - 1.0) * 100.0
            p_price = price_delta * 100.0
            strength = (volume / max(avg_v, 1e-12)) * abs(price_delta)
            reason = f"strong {type_sig.lower()} Δp={price_delta:.4f}, vol×={volume/avg_v:.2f}"
            db.insert_signal(symbol, ts_ms, action, price, strength, reason,
                             p_volume, p_price, type_sig, self.tg_bot, TG_USER_ID)

        # Обычный PUMP
        elif volume > self.v_mult * avg_v and price_delta > self.price_change:
            p_volume = (volume / avg_v - 1.0) * 100.0
            p_price = price_delta * 100.0
            strength = (volume / max(avg_v, 1e-12)) * price_delta
            reason = f"pump Δp={price_delta:.4f}, vol×={volume/avg_v:.2f}"
            db.insert_signal(symbol, ts_ms, "BUY", price, strength, reason,
                             p_volume, p_price, "PUMP", self.tg_bot, TG_USER_ID)

        # Обычный DUMP
        elif volume > self.v_mult * avg_v and price_delta < -self.price_change:
            p_volume = (volume / avg_v - 1.0) * 100.0
            p_price = price_delta * 100.0
            strength = (volume / max(avg_v, 1e-12)) * abs(price_delta)
            reason = f"dump Δp={price_delta:.4f}, vol×={volume/avg_v:.2f}"
            db.insert_signal(symbol, ts_ms, "SELL", price, strength, reason,
                             p_volume, p_price, "DUMP", self.tg_bot, TG_USER_ID)

class BybitSymbols:
    @staticmethod
    def fetch_linear_usdt_symbols() -> list:
        r = requests.get(f"{BYBIT_REST}/v5/market/instruments-info", params={"category": "linear"}, timeout=10)
        r.raise_for_status()
        items = r.json().get("result", {}).get("list", [])
        return [it["symbol"] for it in items if it.get("quoteCoin") == MARKET_FILTER_QUOTE and it.get("status") == "Trading"]

class BybitWS:
    def __init__(self, symbols: list, strategy: PumpDumpStrategy, db: DB):
        self.symbols = symbols
        self.strategy = strategy
        self.db = db
        self.ws = None

    def _subscribe_chunks(self, ws, args, chunk=8):
        for i in range(0, len(args), chunk):
            payload = {"op": "subscribe", "args": args[i:i+chunk]}
            ws.send(json.dumps(payload))
            time.sleep(0.1)

    def on_open(self, ws):
        topics = [f"publicTrade.{s}" for s in self.symbols]
        self._subscribe_chunks(ws, topics)
        mode = "TESTNET" if BYBIT_MODE == "test" else "MAINNET"
        print(f"Subscribed to {len(topics)} symbols (linear futures, {mode})")

    def on_message(self, ws, message):
        data = json.loads(message)
        if data.get("topic", "").startswith("publicTrade.") and "data" in data:
            symbol = data.get("topic").split(".")[1]
            for tr in data["data"]:
                price = float(tr["p"])
                volume = float(tr["v"])
                ts_ms = int(tr["T"])
                self.strategy.on_trade(symbol, ts_ms, price, volume, self.db)
        elif data.get("op") == "ping":
            ws.send(json.dumps({"op": "pong"}))

    def on_error(self, ws, err):
        print("WS error:", err)

    def on_close(self, ws, code, msg):
        print("WS closed:", code, msg)

    def run(self):
        self.ws = websocket.WebSocketApp(
            BYBIT_WS_PUBLIC_LINEAR,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        while True:
            try:
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                print("run_forever exception:", e)
            time.sleep(5)

if __name__ == "__main__":
    db = DB(DB_CFG)
    tg_bot = Bot(TG_TOKEN) if TG_TOKEN else None

    symbols = BybitSymbols.fetch_linear_usdt_symbols()
    mode = "TESTNET" if BYBIT_MODE == "test" else "MAINNET"
    print(f"Loaded {len(symbols)} linear USDT futures from Bybit ({mode})")

    strategy = PumpDumpStrategy(WINDOW, VOLUME_MULTIPLIER, PRICE_CHANGE, tg_bot)
    ws = BybitWS(symbols, strategy, db)
    ws.run()
