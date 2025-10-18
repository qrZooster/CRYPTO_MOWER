# bb_scan_history.py
# ALIAS: BB_SCAN_HISTORY
# Created: 2025-09-24
# Универсальный сканер для загрузки свечей (по разным таймфреймам) по всем символам Bybit
# Фильтрует свечи, где разница между ценой открытия и high >= rate% вверх или low <= rate% вниз
# Загружает историю по заданному временному диапазону пакетами по 180 записей (универсально для всех ТФ)
# Записывает отобранные свечи в общую таблицу ZZ$CANDELS с проставлением TCOD, VENDOR и DIRECTION

import requests
from datetime import datetime, timezone, timedelta
import time

from bb_db import DB
from bb_vars import BYBIT_REST

# Часовой пояс (МСК)
MSK = timezone(timedelta(hours=3))

# Задержка между запросами к API (секунды)
REQUEST_DELAY = 0.2

# --- Генерация TCOD ---
def make_tcod(symbol: str, tf: str, when: datetime | None = None, *, vendor: str = "BYBIT") -> str:
    vendor = (vendor or "BYBIT").upper()
    symbol = symbol.strip().upper()
    tf = tf.strip().upper()

    if when is None:
        when = datetime.now(tz=timezone.utc)
    else:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        else:
            when = when.astimezone(timezone.utc)

    return f"{vendor}_{when.strftime('%Y%m%d_%H%M%S')}_{symbol}_{tf}"

# --- Получение списка всех символов ---
def fetch_all_symbols(only_usdt: bool = True):
    url = f"{BYBIT_REST}/v5/market/instruments-info"
    params = {"category": "linear", "limit": 1000}
    symbols = []
    cursor = None
    try:
        while True:
            if cursor:
                params["cursor"] = cursor
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            result = r.json().get("result", {})
            chunk = result.get("list", [])
            if not chunk:
                break
            for d in chunk:
                sym = d.get("symbol")
                if not sym:
                    continue
                if only_usdt and not sym.endswith("USDT"):
                    continue
                symbols.append(sym)
            cursor = result.get("nextPageCursor")
            if not cursor:
                break
            time.sleep(REQUEST_DELAY)
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Ошибка сети при загрузке списка символов: {e}")
        return []

    # Диагностика: покажем размер и первые элементы
    print(f"ℹ️ fetch_all_symbols: получено {len(symbols)} символов")
    if symbols:
        print(f"   примеры: {', '.join(symbols[:10])}{' ...' if len(symbols) > 10 else ''}")
    return symbols

# --- Определение последней даты в базе (только для 1D) ---
def get_last_date_from_db(symbol: str, tf: str):
    if tf != "1D":
        return None
    db = DB()
    sql = "SELECT MAX(FLD$DATE_TIME) as last_date FROM ZZ$CANDELS WHERE FLD$SYMBOL=%s AND FLD$TIME_FRAME=%s"
    cur = db.conn.cursor(dictionary=True)
    cur.execute(sql, (symbol, tf))
    row = cur.fetchone()
    cur.close()
    if row and row["last_date"]:
        return row["last_date"]
    return None

# --- Получение свечей с Bybit (с пагинацией) ---
def fetch_all_candels(symbol: str, tf: str, rate: float, date_time_start: datetime | None = None, date_time_end: datetime | None = None):
    url = f"{BYBIT_REST}/v5/market/kline"
    limit = 180

    # карта таймфреймов под Bybit
    tf_map = {
        "1S": "1",
        "1M": "1",
        "5M": "5",
        "15M": "15",
        "1H": "60",
        "4H": "240",
        "1D": "D",
    }
    bybit_tf = tf_map.get(tf.upper())
    if not bybit_tf:
        raise ValueError(f"Неподдерживаемый таймфрейм: {tf}")

    all_candels = []

    if tf.upper() == "1D":
        today_start = datetime.now(tz=MSK).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_time_start is None:
            date_time_start = datetime(2017, 1, 1, tzinfo=MSK)
        if date_time_end is None or date_time_end >= today_start:
            date_time_end = today_start - timedelta(seconds=1)  # не трогаем текущий день
        end = int(date_time_end.timestamp()) * 1000
    else:
        end = int((date_time_end or datetime.now(tz=MSK)).timestamp()) * 1000

    more_data = True

    while more_data:
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": bybit_tf,
            "end": end,
            "limit": limit
        }
        if date_time_start:
            params["start"] = int(date_time_start.timestamp()) * 1000

        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Ошибка сети при загрузке {symbol}: {e}")
            break

        result = r.json().get("result", {})
        data = result.get("list", [])

        if not data:
            more_data = False
            break

        data_sorted = sorted(data, key=lambda x: int(x[0]))

        for k in data_sorted:
            ts = datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc).astimezone(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
            open_price = float(k[1])
            high_price = float(k[2])
            low_price = float(k[3])
            close_price = float(k[4])
            volume = float(k[5])

            if high_price >= open_price * (1 + rate / 100):
                direction = "UP"
                all_candels.append({
                    "datetime": ts,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                    "direction": direction
                })
            elif low_price <= open_price * (1 - rate / 100):
                direction = "DOWN"
                all_candels.append({
                    "datetime": ts,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                    "direction": direction
                })

        oldest_ts = int(data_sorted[0][0])
        end = oldest_ts - 1

        time.sleep(REQUEST_DELAY)

    return all_candels

# --- Сохранение в БД ---
def save_candels_to_db(symbol: str, candels: list, tf: str, vendor: str = "BYBIT"):
    db = DB()
    for c in candels:
        tcod = make_tcod(symbol, tf, c["datetime"], vendor=vendor)
        db.exec(
            "INSERT IGNORE INTO ZZ$CANDELS(FLD$VENDOR, FLD$SYMBOL, FLD$TIME_FRAME, FLD$DATE_TIME, FLD$P_OPEN, FLD$P_CLOSE, FLD$P_HIGH, FLD$P_LOW, FLD$VOLUME, FLD$DIRECTION, FLD$TCOD, FLD$DATE_OTP) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            (
                vendor,
                symbol,
                tf,
                c["datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                c["open"],
                c["close"],
                c["high"],
                c["low"],
                c["volume"],
                c["direction"],
                tcod
            )
        )
    print(f"✅ Сохранено {len(candels)} свечей для {symbol} на TF {tf}")

if __name__ == "__main__":
    tf = "1D"
    vendor = "BYBIT"
    rate = 25

    date_time_start = None
    date_time_end = None

    if tf in ("1S", "1M"):
        date_time_start = datetime(2025, 9, 1, 0, 0, 0, tzinfo=MSK)
        date_time_end = datetime(2025, 9, 2, 0, 0, 0, tzinfo=MSK)

    symbols = []
    if not symbols:
        symbols = fetch_all_symbols()

    start_symbol = None
    if tf == "1D" and start_symbol and start_symbol in symbols:
        start_index = symbols.index(start_symbol)
        symbols = symbols[start_index:]

    print(f"🔎 Найдено {len(symbols)} символов для сканирования: {symbols[:10]}...")

    for symbol in symbols:
        print(f"➡️ Обработка {symbol} на TF {tf}...")

        # Определяем последнюю дату в базе (только для 1D)
        last_date = get_last_date_from_db(symbol, tf)
        if tf == "1D" and last_date:
            date_time_start = last_date + timedelta(days=1)
            print(f"ℹ️ Для {symbol} найдено последнее значение в базе: {last_date}, начинаем с {date_time_start}")

        candels = fetch_all_candels(symbol, tf, rate, date_time_start, date_time_end)
        if candels:
            save_candels_to_db(symbol, candels, tf, vendor=vendor)
            print(f"🕒 Последняя свеча {symbol} ({tf}): {candels[-1]['datetime']}")
        else:
            print(f"⚠️ Подходящих свечей для {symbol} ({tf}) не найдено.")