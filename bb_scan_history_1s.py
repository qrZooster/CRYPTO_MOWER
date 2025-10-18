# bb_scan_history_1s.py
# ALIAS: BB_SCAN_HISTORY_1S
# Created: 2025-09-24
# Сканер для загрузки секундных свечей (цена + объем) по символу ASPUSDT
# Делит заданный интервал на отрезки по 3 минуты и загружает свечи пакетами <200 штук

import requests
from datetime import datetime, timedelta, timezone

from bb_db import DB
from bb_vars import BYBIT_REST

# Часовой пояс (МСК)
MSK = timezone(timedelta(hours=3))

# --- Получение секундных свечей с Bybit ---
def fetch_candles(symbol: str, start_time: datetime, end_time: datetime, interval: str = "1s"):
    url = f"{BYBIT_REST}/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "start": int(start_time.timestamp()) * 1000,
        "end": int(end_time.timestamp()) * 1000,
        "limit": 200
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json().get("result", {}).get("list", [])

    # Bybit отдаёт свечи в обратном порядке (от последних к первым).
    data_sorted = sorted(data, key=lambda x: int(x[0]))  # сортируем по возрастанию времени

    candles = []
    for k in data_sorted:
        ts = datetime.fromtimestamp(int(k[0]) / 1000, tz=MSK)
        candles.append({
            "datetime": ts,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5])
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
    print(f"✅ Сохранено {len(candles)} свечей для {symbol}")

# --- Разделение интервала на отрезки по 3 минуты ---
def split_interval(start_time: datetime, end_time: datetime, chunk_minutes: int = 3):
    intervals = []
    current = start_time
    while current < end_time:
        chunk_end = min(current + timedelta(minutes=chunk_minutes), end_time)
        intervals.append((current, chunk_end))
        # сдвигаем на +1 секунду, чтобы не задвоить последнюю свечу
        current = chunk_end + timedelta(seconds=1)
    return intervals

if __name__ == "__main__":
    symbol = "INUSDT"
    start_time = datetime(2025, 9, 24, 10, 50, tzinfo=MSK)
    end_time = datetime(2025, 9, 24, 11, 45, tzinfo=MSK)

    print(f"🔎 Загружаем секундные свечи {symbol} с {start_time} по {end_time}...")
    all_candles = []

    for chunk_start, chunk_end in split_interval(start_time, end_time, chunk_minutes=3):
        print(f"⏳ Обработка интервала {chunk_start} - {chunk_end}")
        candles = fetch_candles(symbol, chunk_start, chunk_end, interval="1s")
        if candles:
            save_candles_to_db(symbol, candles)
            all_candles.extend(candles)

    if all_candles:
        print(f"🕒 Время последней свечи: {all_candles[-1]['datetime']}")
