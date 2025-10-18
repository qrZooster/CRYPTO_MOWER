
# bb_scan_5.py
# ALIAS: BB_SCAN_5
# Created: 2025-09-26
# Секундные свечи из publicTrade (МСК, без дыр) + хранение последних 100 свечей
# + AVG_V_20/50/100 + AVG_P_20/50/100 + D + P_OC + запись в БД через db.add()

import datetime as dt
import threading
import time
from collections import defaultdict, deque

from bb_ws import BybitWS
from bb_vars import MSK
import bb_db as db
import pathlib
import shutil

# === Загрузка ВСЕХ символов Bybit через REST ===
import json
import urllib.request
import urllib.parse

def _fetch_symbols_by_category(category: str):
    base = "https://api.bybit.com/v5/market/instruments-info"
    out = []
    cursor = None
    while True:
        params = {"category": category}
        if cursor:
            params["cursor"] = cursor
        url = base + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.load(r)
        except Exception as e:
            print(f"Bybit REST error ({category}): {e}")
            break
        if data.get("retCode") != 0:
            print(f"Bybit REST retCode={data.get('retCode')} msg={data.get('retMsg')}")
            break
        result = data.get("result", {})
        items = result.get("list", [])
        for it in items:
            sym = it.get("symbol")
            status = it.get("status") or it.get("symbolStatus")
            if sym and (status is None or str(status).lower() == "trading"):
                out.append(sym)
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return out


def load_bybit_symbols():
    """Загрузить ТОЛЬКО линейные USDT-символы Bybit."""
    linear = _fetch_symbols_by_category("linear")
    usdt = sorted(s for s in set(linear) if isinstance(s, str) and s.endswith("USDT"))
    if not usdt:
        print("⚠️ Не удалось загрузить линейные USDT символы Bybit — fallback к USDT-тройке")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    print(f"Загружено символов Bybit: {len(usdt)} (linear USDT)")
    return usdt

symbols = load_bybit_symbols()

# key: (symbol, ts_sec) -> candle
_candles = {}
_last_price = {s: None for s in symbols}

# Хранилище последних 100 свечей по каждому символу
_history = defaultdict(lambda: deque(maxlen=100))

# --- Пороговые значения для детектора ORDERS_2 ---
ALERT_VOL_MULT = 5.0   # во сколько раз объём должен превышать базовый (AVG_V_20/50/100)
ALERT_PRICE_PCT = 0.20 # минимальный P_OC в процентах (|O-C|/O*100)
MIN_BASELINE_VOL = 1e-9 # защита от деления на ноль/очень малых baseline


# --- Автобэкап в начале запуска ---
def _auto_backup():
    """Делает копию текущего файла в ./backups/имя_YYYYMMDD_HHMMSS.py (МСК)."""
    try:
        p = pathlib.Path(__file__).resolve()
        bdir = p.parent / "backups"
        bdir.mkdir(exist_ok=True)
        stamp = dt.datetime.now(tz=MSK).strftime("%Y%m%d_%H%M%S")
        dest = bdir / f"{p.stem}_{stamp}{p.suffix}"
        shutil.copy2(p, dest)
        print(f"[backup] {dest.name}")
    except Exception as e:
        print(f"[backup] failed: {e}")

# --- DB helper: save 1-sec candle ---
def insert_candle(symbol: str, c: dict, table_name: str = 'ZZ$CANDELS_S1'):
    """Сохранить секундную свечу в указанную таблицу (по умолчанию ZZ$CANDELS_S1) через db.add()."""
    dt_str = dt.datetime.fromtimestamp(c["start"], tz=MSK).strftime("%Y-%m-%d %H:%M:%S")
    row = {
        'FLD$SYMBOL': symbol,
        'FLD$DATE_TIME': dt_str,
        'FLD$TF': '1SEC',
        'FLD$P_OPEN': c['open'],
        'FLD$P_CLOSE': c['close'],
        'FLD$P_HIGH': c['high'],
        'FLD$P_LOW': c['low'],
        'FLD$VOLUME': round(float(c['volume']), 2),
        'FLD$P_OC': round(float(c['P_OC']), 2),
        'FLD$AVG_V_20': round(float(c['AVG_V_20']), 2),
        'FLD$AVG_V_50': round(float(c['AVG_V_50']), 2),
        'FLD$AVG_V_100': round(float(c['AVG_V_100']), 2),
        'FLD$AVG_P_20': round(float(c['AVG_P_20']), 2),
        'FLD$AVG_P_50': round(float(c['AVG_P_50']), 2),
        'FLD$AVG_P_100': round(float(c['AVG_P_100']), 2),
        'FLD$X_V_20': int(c.get('X_V_20', 0)),
        'FLD$DIRECTION': c['D'],
        'FLD$TCOD': symbol,
    }
    return db.qr_add(table_name, row)


def check_candle(c: dict) -> bool:
    # FLAT сразу False
    if c.get('D') == 'FLAT':
        return False
    # защита от нулевой/малой базы
    avg_v_20 = float(c.get('AVG_V_20', 0) or 0.0)
    if avg_v_20 <= 1:
        return False
    # используем уже подготовленное целочисленное поле кратности
    x_v_20 = int(c.get('X_V_20', 0))
    if x_v_20 < 500:
        return False
    return True


class SecondCandleStrategy:
    def on_trade(self, symbol: str, ts_ms: int, price: float, volume: float, db=None):
        ts_sec = ts_ms // 1000
        key = (symbol, ts_sec)

        _last_price[symbol] = price

        if key not in _candles:
            _candles[key] = {
                "start": ts_sec,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": round(volume, 2),
            }
        else:
            c = _candles[key]
            if price > c["high"]:
                c["high"] = price
            if price < c["low"]:
                c["low"] = price
            c["close"] = price
            c["volume"] = round(c["volume"] + volume, 2)


def _calc_avg_volumes(symbol: str):
    vols = [c["volume"] for c in list(_history[symbol])]
    def avg(n):
        return round(sum(vols[-n:]) / n, 2) if len(vols) >= n else 0.00
    return avg(20), avg(50), avg(100)


def _calc_avg_poc(symbol: str):
    pocs = [c["P_OC"] for c in list(_history[symbol]) if "P_OC" in c]
    def avg(n):
        return round(sum(pocs[-n:]) / n, 4) if len(pocs) >= n else 0.00
    return avg(20), avg(50), avg(100)


def _finalize_candle(symbol: str, c: dict):
    # направление D
    if c["close"] > c["open"]:
        c["D"] = "UP"
    elif c["close"] < c["open"]:
        c["D"] = "DOWN"
    else:
        c["D"] = "FLAT"
    # разница в % между O и C (модуль)
    if c["open"] != 0:
        c["P_OC"] = round(abs((c["close"] - c["open"]) / c["open"] * 100), 4)
    else:
        c["P_OC"] = 0.0

    # средние объёмы
    avg20, avg50, avg100 = _calc_avg_volumes(symbol)
    c["AVG_V_20"] = avg20
    c["AVG_V_50"] = avg50
    c["AVG_V_100"] = avg100
    # кратность объёма к среднему за 20 (целое число)
    c["X_V_20"] = int(c["volume"] / avg20) if avg20 > 0 else 0

    # средние P_OC
    avgp20, avgp50, avgp100 = _calc_avg_poc(symbol)
    c["AVG_P_20"] = avgp20
    c["AVG_P_50"] = avgp50
    c["AVG_P_100"] = avgp100

    return c


def flusher():
    """Флашим ПОСЕКУНДНО без пропусков секундами.
    Обрабатываем все секунды от last_ts до (now-1). Это защищает от лагов >1s.
    """
    last_ts = int(time.time()) - 1  # начнём с предыдущей секунды
    while True:
        now = int(time.time())
        # Обработать все секунды, которые уже закрылись
        while last_ts <= now - 1:
            for symbol in symbols:
                key = (symbol, last_ts)
                c = _candles.pop(key, None)
                if c is None:
                    # не было трейдов — синтезируем 0-volume свечу по последней цене
                    price = _last_price.get(symbol)
                    if price is None:
                        continue  # ещё не знаем цену по символу
                    c = {
                        "start": last_ts,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": 0.0,
                    }
                # финализация, лог и запись
                c = _finalize_candle(symbol, c)
                when = dt.datetime.fromtimestamp(last_ts, tz=MSK).strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{when}] {symbol} O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{c['volume']} D:{c['D']} P_OC:{c['P_OC']}% AVG20:{c['AVG_V_20']} AVG50:{c['AVG_V_50']} AVG100:{c['AVG_V_100']} AVG_P20:{c['AVG_P_20']} AVG_P50:{c['AVG_P_50']} AVG_P100:{c['AVG_P_100']}")
                # ⛳ Вариант 1: не пишем 0-volume свечи в БД (но оставляем в истории)
                if c['volume'] == 0.0:
                    _history[symbol].append(c)
                    continue
                # Сначала проверяем на сигнал и, при необходимости, пишем в ZZ$ORDERS_2
                try:
                    if check_candle(c):
                        insert_candle(symbol, c, table_name='ZZ$ORDERS_2')
                except Exception as e:
                    print(f"DB ORDERS_2 error: {e}")
                # Затем добавляем в историю и пишем в основную таблицу свечей
                _history[symbol].append(c)
                try:
                    insert_candle(symbol, c, table_name='ZZ$CANDELS_S1')
                except Exception as e:
                    print(f"DB insert error: {e}")
            last_ts += 1
        time.sleep(0.2)

def get_last_poc(symbol: str, n: int = 10):
    """Вернуть последние n значений P_OC для символа."""
    return [c["P_OC"] for c in list(_history[symbol])[-n:]]


def main():
    strat = SecondCandleStrategy()
    # гарантируем инициализацию БД перед запуском WS
    _ = db.init_db()
    ws = BybitWS(symbols=symbols, strategy=strat, db=db._db)

    t = threading.Thread(target=flusher, daemon=True)
    t.start()

    ws.run()


if __name__ == "__main__":
    _auto_backup()
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped by user")
        db.close_db()

