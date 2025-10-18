# bb_scan_5.py — WORKING COPY (restored)
# Реал-тайм секундные свечи для Bybit linear USDT
# - символы тянем с REST
# - секунды без дыр (догоняем last_ts..now-1)
# - не пишем 0-объёмные свечи в БД
# - метрики AVG_V/P с «охлаждением» COOL
# - X_V_20/50/100 и X_P_20/50/100
# - check_candle(): D!=FLAT, AVG_V_20>1, X_V_20>=500
# - insert_candle(table_name=...) пишет FLD$DATE_TIME_GET

import datetime as dt
import threading
import time
import json
import urllib.request
import urllib.parse
from collections import defaultdict, deque
import pathlib
import shutil

from bb_ws import BybitWS
from bb_vars import MSK
import bb_db as db

# === Автобэкап скрипта перед запуском ===
def _auto_backup():
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


# === Загрузка символов Bybit (linear USDT) ===

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
            if sym and str(status).lower() == "trading":
                out.append(sym)
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    return out


def load_bybit_symbols():
    linear = _fetch_symbols_by_category("linear")
    usdt = sorted(s for s in set(linear) if isinstance(s, str) and s.endswith("USDT"))
    if not usdt:
        print("⚠️ Не удалось загрузить линейные USDT символы Bybit — fallback к USDT-тройке")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    print(f"Загружено символов Bybit: {len(usdt)} (linear USDT)")
    return usdt

symbols = load_bybit_symbols()

# key: (symbol, ts_sec) -> candle
_candles: dict[tuple[str, int], dict] = {}
_last_price = {s: None for s in symbols}

# --- Параметры ---
COOL = 5                 # глобальный период «охлаждения»
MAX_WINDOW = 100         # максимальное окно средних (20/50/100)
HISTORY_SAFETY = 10      # запас ячеек
HISTORY_LEN = MAX_WINDOW + max(0, COOL) + HISTORY_SAFETY
ALERT_VOL_MULT = 5.0     # зарезервировано
ALERT_PRICE_PCT = 0.20 # зарезервировано
MIN_BASELINE_VOL = 1e-9
LOG_EVERY = 10          # логируем не-хиты раз в 10 секунд
# Пер-символьный троттлинг логов, чтобы не было «порций»
_LOG_THROTTLE = LOG_EVERY
_last_log_ts = defaultdict(lambda: 0)

# последние HISTORY_LEN свечей на символ (зависит от COOL)
_history = defaultdict(lambda: deque(maxlen=HISTORY_LEN))


# === Хелперы средних с «охлаждением» ===

def _avg_tail(seq, n, cool):
    k = max(0, cool)
    if k == 0:
        if len(seq) < n:
            return 0.0
        tail = seq[-n:]
    else:
        if len(seq) < n + k:
            return 0.0
        tail = seq[-(n + k):-k]
    return sum(tail) / n


def _calc_avg_volumes(symbol: str, cool: int = COOL):
    vols = [c["volume"] for c in list(_history[symbol])]
    avg20 = round(_avg_tail(vols, 20, cool), 2)
    avg50 = round(_avg_tail(vols, 50, cool), 2)
    avg100 = round(_avg_tail(vols, 100, cool), 2)
    return avg20, avg50, avg100


def _calc_avg_poc(symbol: str, cool: int = COOL):
    pocs = [c["P_OC"] for c in list(_history[symbol]) if "P_OC" in c]
    avg20 = round(_avg_tail(pocs, 20, cool), 4)
    avg50 = round(_avg_tail(pocs, 50, cool), 4)
    avg100 = round(_avg_tail(pocs, 100, cool), 4)
    return avg20, avg50, avg100

# === ATR% (Average True Range percent) ===

def _tr_sequence(symbol: str):
    """Последовательность True Range по истории символа."""
    seq = []
    prev_close = None
    for c in list(_history[symbol]):
        high = float(c["high"]) ; low = float(c["low"]) ; close = float(c["close"])
        if prev_close is None:
            tr = abs(high - low)
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        seq.append(tr)
        prev_close = close
    return seq


def _calc_atr_percent(symbol: str, close_price: float, cool: int = COOL):
    """Возвращает (ATR%20, ATR%50, ATR%100), % от текущей цены."""
    trs = _tr_sequence(symbol)
    if not trs or close_price <= 0:
        return 0.0, 0.0, 0.0
    atr20 = _avg_tail(trs, 20, cool) if len(trs) >= max(20 + max(0, cool), 1) else 0.0
    atr50 = _avg_tail(trs, 50, cool) if len(trs) >= max(50 + max(0, cool), 1) else 0.0
    atr100 = _avg_tail(trs, 100, cool) if len(trs) >= max(100 + max(0, cool), 1) else 0.0
    atrp20 = (atr20 / close_price * 100.0) if atr20 > 0 else 0.0
    atrp50 = (atr50 / close_price * 100.0) if atr50 > 0 else 0.0
    atrp100 = (atr100 / close_price * 100.0) if atr100 > 0 else 0.0
    # округляем для in-memory до 4 знаков (в БД пишем до 2)
    return round(atrp20, 4), round(atrp50, 4), round(atrp100, 4)


# === Финализация секунды ===

def _finalize_candle(symbol: str, c: dict) -> dict:
    # D
    if c["close"] > c["open"]:
        c["D"] = "UP"
    elif c["close"] < c["open"]:
        c["D"] = "DOWN"
    else:
        c["D"] = "FLAT"
    # P_OC (в % по модулю)
    if c["open"] != 0:
        c["P_OC"] = round(abs((c["close"] - c["open"]) / c["open"] * 100), 4)
    else:
        c["P_OC"] = 0.0

    # средние по истории с учётом COOL
    avg20, avg50, avg100 = _calc_avg_volumes(symbol)
    c["AVG_V_20"], c["AVG_V_50"], c["AVG_V_100"] = avg20, avg50, avg100
    avgp20, avgp50, avgp100 = _calc_avg_poc(symbol)
    c["AVG_P_20"], c["AVG_P_50"], c["AVG_P_100"] = avgp20, avgp50, avgp100

    # кратности объёма
    c["X_V_20"] = int(c["volume"] / avg20) if avg20 > 0 else 0
    c["X_V_50"] = int(c["volume"] / avg50) if avg50 > 0 else 0
    c["X_V_100"] = int(c["volume"] / avg100) if avg100 > 0 else 0

    # ATR% по истории считаем ТОЛЬКО если X_V_20 >= 1000 (экономия CPU)
    if c["X_V_20"] >= 1000:
        atrp20, atrp50, atrp100 = _calc_atr_percent(symbol, float(c["close"]))
    else:
        atrp20 = atrp50 = atrp100 = 0.0
    c["ATR_P_20"], c["ATR_P_50"], c["ATR_P_100"] = atrp20, atrp50, atrp100


    # кратности цены (относительно средних P_OC)
    c["X_P_20"] = int(c["P_OC"] / avgp20) if avgp20 > 0 else 0
    c["X_P_50"] = int(c["P_OC"] / avgp50) if avgp50 > 0 else 0
    c["X_P_100"] = int(c["P_OC"] / avgp100) if avgp100 > 0 else 0

    return c


# === Запись свечи в БД ===

def insert_candle(symbol: str, c: dict, table_name: str = 'ZZ$CANDELS_S1'):
    dt_str = dt.datetime.fromtimestamp(c["start"], tz=MSK).strftime("%Y-%m-%d %H:%M:%S")
    row = {
        'FLD$SYMBOL': symbol,
        'FLD$DATE_TIME': dt_str,
        'FLD$DATE_TIME_GET': dt.datetime.fromtimestamp(c.get('time_get', time.time()), tz=MSK).strftime("%Y-%m-%d %H:%M:%S"),
        'FLD$TF': '1SEC',
        'FLD$P_OPEN': c['open'],
        'FLD$P_CLOSE': c['close'],
        'FLD$P_HIGH': c['high'],
        'FLD$P_LOW': c['low'],
        'FLD$VOLUME': round(float(c['volume']), 2),
        'FLD$P_OC': round(float(c['P_OC']), 2),
        'FLD$X_P_20': int(c.get('X_P_20', 0)),
        'FLD$X_P_50': int(c.get('X_P_50', 0)),
        'FLD$X_P_100': int(c.get('X_P_100', 0)),
        'FLD$AVG_V_20': round(float(c['AVG_V_20']), 2),
        'FLD$AVG_V_50': round(float(c['AVG_V_50']), 2),
        'FLD$AVG_V_100': round(float(c['AVG_V_100']), 2),
        'FLD$AVG_P_20': round(float(c['AVG_P_20']), 2),
        'FLD$AVG_P_50': round(float(c['AVG_P_50']), 2),
        'FLD$AVG_P_100': round(float(c['AVG_P_100']), 2),
        'FLD$ATR_P_20': round(float(c.get('ATR_P_20', 0.0)), 2),
        'FLD$ATR_P_50': round(float(c.get('ATR_P_50', 0.0)), 2),
        'FLD$ATR_P_100': round(float(c.get('ATR_P_100', 0.0)), 2),
        'FLD$X_V_20': int(c.get('X_V_20', 0)),
        'FLD$X_V_50': int(c.get('X_V_50', 0)),
        'FLD$X_V_100': int(c.get('X_V_100', 0)),
        'FLD$DIRECTION': c['D'],
        'FLD$TCOD': symbol,
    }
    return db.qr_add(table_name, row)


# === Правило ORDERS (минимальная версия по объёму) ===

def check_candle(c: dict) -> bool:
    # 1) форма свечи
    if c.get('D') == 'FLAT':
        return False

    # 2) объёмный фильтр
    avg_v_20 = float(c.get('AVG_V_20', 0) or 0.0)
    if avg_v_20 <= 1:
        return False
    x_v_20 = int(c.get('X_V_20', 0))
    if x_v_20 < 500:
        return False

    # 3) ценовой фильтр
    p_oc = float(c.get('P_OC', 0) or 0.0)       # в процентах
    x_p_20 = int(c.get('X_P_20', 0))
    if p_oc <= 0.3:
        return False
    if x_p_20 <= 100:
        return False

    return True


# === Стратегия: собираем секунды из сделок ===
class SecondCandleStrategy:
    def on_trade(self, symbol: str, ts_ms: int, price: float, volume: float, db=None):
        ts_sec = ts_ms // 1000
        key = (symbol, ts_sec)
        _last_price[symbol] = price
        if key not in _candles:
            _candles[key] = {
                "start": ts_sec,
                "time_get": int(time.time()),
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


# === Флашер секунд без пропусков ===

def flusher():
    last_ts = int(time.time()) - 1
    while True:
        now = int(time.time())
        while last_ts <= now - 1:
            checked = 0
            hits = 0
            hit_lines = []
            for symbol in symbols:
                key = (symbol, last_ts)
                c = _candles.pop(key, None)
                if c is None:
                    price = _last_price.get(symbol)
                    if price is None:
                        continue
                    c = {
                        "start": last_ts,
                        "time_get": int(time.time()),
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": 0.0,
                    }
                c = _finalize_candle(symbol, c)
                when = dt.datetime.fromtimestamp(last_ts, tz=MSK).strftime("%Y-%m-%d %H:%M:%S")
                checked += 1

                # Не пишем 0-объёмные свечи в БД — только в историю
                if c['volume'] == 0.0:
                    _history[symbol].append(c)
                    continue

                is_hit = False
                try:
                    if check_candle(c):
                        is_hit = True
                        hits += 1
                        insert_candle(symbol, c, table_name='ZZ$ORDERS_2')
                except Exception as e:
                    print(f"DB ORDERS_2 error: {e}")

                # Основная таблица
                _history[symbol].append(c)
                try:
                    insert_candle(symbol, c, table_name='ZZ$CANDELS_S1')
                except Exception as e:
                    print(f"DB insert error: {e}")

                # Полный лог на ХИТ
                if is_hit:
                    hit_lines.append(
                        f"[{when}] {symbol} O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} "
                        f"V:{c['volume']} D:{c['D']} P_OC:{c['P_OC']}% "
                        f"AVG20:{c['AVG_V_20']} AVG50:{c['AVG_V_50']} AVG100:{c['AVG_V_100']} "
                        f"X_V20:{c['X_V_20']} X_V50:{c['X_V_50']} X_V100:{c['X_V_100']} "
                        f"X_P20:{c['X_P_20']} X_P50:{c['X_P_50']} X_P100:{c['X_P_100']}"
                    )
            # Summary по секунде
            when_sec = dt.datetime.fromtimestamp(last_ts, tz=MSK).strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{when_sec}] checked:{checked} found:{hits}")
            if hit_lines:
                for _line in hit_lines:
                    print(_line)
            last_ts += 1
        time.sleep(0.2)


# === run ===

def main():
    _ = db.init_db()
    strat = SecondCandleStrategy()
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
