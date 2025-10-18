# bb_scan_1s.py
# ALIAS: BB_SCAN_1S
# Created: 2025-09-24
# Онлайн-сканер: получает сделки в реальном времени, агрегирует в секундные свечи
# и сохраняет в таблицу ZZ$CANDELS_S1

import time
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from bb_db import DB
from bb_vars import BYBIT_REST

# Часовой пояс (МСК)
MSK = timezone(timedelta(hours=3))

# --- Получение последних сделок с Bybit ---
def fetch_recent_trades(symbol: str, limit: int = 1000):
    url = f"{BYBIT_REST}/v5/market/recent-trade"
    params = {
        "category": "linear",
        "symbol": symbol,
        "limit": limit
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("result", {}).get("list", [])

# --- Агрегация сделок в 1-секундные свечи ---
def aggregate_to_candles(trades: list):
    buckets = defaultdict(list)
    for t in trades:
        ts = datetime.fromtimestamp(int(t["time"]) / 1000, tz=MSK).replace(microsecond=0)
        buckets[ts].append({
            "price": float(t["price"]),
            "volume": float(t["size"])
        })

    candles = []
    for ts, bucket in sorted(buckets.items()):
        prices = [b["price"] for b in bucket]
        volumes = [b["volume"] for b in bucket]
        candles.append({
            "datetime": ts,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(volumes)
        })
    return candles

# --- Сохранение в БД ---
def save_candles_to_db(symbol: str, candles: list):
    db = DB()
    for c in candles:
        db.exec(
            "INSERT INTO ZZ$CANDELS_S1(FLD$SYMBOL, FLD$DATE_TIME, FLD$P_OPEN, FLD$P_CLOSE, FLD$P_HIGH, FLD$P_LOW, FLD$VOLUME, FLD$DATE_OTP) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,NOW())",
            (
                symbol,
                c["datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                c["open"],
                c["close"],
                c["high"],
                c["low"],
                c["volume"]
            )
        )
    if candles:
        print(f"✅ Сохранено {len(candles)} свечей для {symbol}")

if __name__ == "__main__":
    symbol = "BTCUSDT"
    print(f"🚀 Запущен онлайн-сканер для {symbol} (таймфрейм 1s)...")

    last_seen = None
    while True:
        try:
            trades = fetch_recent_trades(symbol)
            if not trades:
                time.sleep(1)
                continue

            candles = aggregate_to_candles(trades)
            # сохраняем только новые свечи
            new_candles = [c for c in candles if last_seen is None or c["datetime"] > last_seen]
            if new_candles:
                last_seen = new_candles[-1]["datetime"]
                save_candles_to_db(symbol, new_candles)
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(1)