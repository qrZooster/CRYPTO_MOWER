# bb_scan_7.py — EXP LAB (sandbox). Продакшн не трогаем.
# Цели на сегодня:
# 1) Стартовый каркас сканера (секундные свечи из тиков) — минимально.
# 2) Заготовка архитектуры под «факты» (делистинги и прочие события).
# 3) Таймер делистингов внутри flusher() — неблокирующий.
# 4) ТИК-ДЕТЕКТОР: ранний «burst» по частоте тиков, объёму и micro P_OC.
#
# По умолчанию НИЧЕГО в БД не пишет (WRITE_TO_DB=False). Включается через ENV.
# Версия для меток: BMW_M3

import os
import time
import json
import threading
import urllib.request
import urllib.parse
import datetime as dt
from collections import defaultdict, deque
from typing import Any, Dict, Deque, Tuple

from bb_ws import BybitWS
from bb_vars import *
from bb_db import *

mod = None
symbols = None

# --- Параметры ---
WRITE_TO_DB = key_bool('WRITE_TO_DB', 1)
#WRITE_TO_DB = os.getenv("SCAN7_WRITE", "1") == "1"  # включить запись в БД
COOL = 5
MAX_WINDOW = 100
HISTORY_SAFETY = 10
HISTORY_LEN = MAX_WINDOW + max(0, COOL) + HISTORY_SAFETY

#DELIS_INTERVAL = int(os.getenv("DELIS_INTERVAL", "600"))  # секунд
DELIS_INTERVAL = key_int('DELIS_INTERVAL', 600)
_last_delis_check = 0

VERSION = ''


# === ТИК-ДЕТЕКТОР: параметры (env/ZZ$CONFIG) ===
BURST_W_SHORT_MS = key_int('BURST_W_SHORT_MS', 200)     # окно короткое, мс (0.3s)
BURST_W_LONG_MS  = key_int('BURST_W_LONG_MS', 1500)     # окно длинное, мс (1.5s)
BURST_X_RATE_MIN = key_float('BURST_X_RATE_MIN', 4.0)   # rate_short / max(rate_long, eps)
BURST_X_VR_MIN   = key_float('BURST_X_VR_MIN', 3.0)     # volrate_short / max(volrate_long, eps)
BURST_MICRO_POC  = key_float('BURST_MICRO_POC', 0.6)    # % прирост цены за короткое окно
BURST_TTL_SEC    = key_float('BURST_TTL_SEC', 2.0)      # TTL факта TICK_BURST

# === BURST: запись и ограничения ===
BURST_WRITE      = key_bool('BURST_WRITE', True)         # писать ли тик-бурсты в БД
BURST_MIN_SEP_MS = key_int('BURST_MIN_SEP_MS', 1000)     # минимум между BURST по одному символу
_last_burst_ms   = defaultdict(lambda: 0)

# === EARLY (экстренный вход) ===
EARLY_WRITE      = key_bool('EARLY_WRITE', True)         # писать ли ранние входы в ZZ$ORDERS_2
EARLY_TRADE      = key_bool('EARLY_TRADE', False)        # реально ли торговать (по умолчанию — нет)
EARLY_SUM_USDT   = key_float('EARLY_SUM_USDT', 6.5)      # сумма на вход
EARLY_LEVERAGE   = key_int('EARLY_LEVERAGE', 10)         # плечо


# Буферы
_candles: dict[tuple[str, int], dict] = {}
_last_price = defaultdict(lambda: None)
_history = defaultdict(lambda: deque(maxlen=HISTORY_LEN))

# ---------- ФАКТЫ (оперативные флаги, влияющие на правила) ----------
# Пример: set_fact('AIAUSDT','DELISTING', True, ttl_sec=30*24*3600)

_facts: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

def set_fact(symbol: str, name: str, value: Any = True, ttl_sec: int = 3600, meta: dict | None = None):
    _facts[symbol][name] = {
        'value': value,
        'expire': time.time() + max(1, ttl_sec),
        'meta': meta or {}
    }

def get_fact(symbol: str, name: str, default: Any = None) -> Any:
    rec = _facts.get(symbol, {}).get(name)
    if not rec:
        return default
    if rec['expire'] <= time.time():
        # протух — выбросим при следующем GC
        return default
    return rec['value']

def gc_facts():
    now_ = time.time()
    for sym, d in list(_facts.items()):
        for k, rec in list(d.items()):
            if rec['expire'] <= now_:
                del d[k]
        if not d:
            del _facts[sym]

# ---------------- Загрузка символов Bybit (linear USDT) ----------------

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
        print("⚠️ Не удалось загрузить линейные USDT символы — fallback")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    msg = f'Загружено символов: {len(usdt)} (linear USDT)'
    mod.log('load_bybit_symbols', msg)
    #print(f"[SCAN7] Загружено символов: {len(usdt)} (linear USDT)")
    return usdt

# ---------------- Метрики минимально (для совместимости) ---------------

def _finalize_candle(symbol: str, c: dict) -> dict:
    if c['close'] > c['open']:
        c['D'] = 'UP'
    elif c['close'] < c['open']:
        c['D'] = 'DOWN'
    else:
        c['D'] = 'FLAT'
    c['P_OC'] = round(abs((c['close'] - c['open']) / c['open'] * 100), 4) if c['open'] else 0.0
    return c

# ---------------- Делистинги: заготовка таймера и прогрева фактов ------

def check_delisting_once():
    """Идемпотентная проверка делистингов и прогрев _facts из БД. Лёгкая версия."""
    import bb_delisting  # локальный импорт, чтобы не тянуть зависимость до желания
    try:
        bb_delisting.run_once(limit=50)
    except Exception as e:
        log(f"[delisting] fetch error: {e}")
    # прогреем факты (последние 60 дней)
    try:
        rows = qr(
            'ZZ$DELISTING',
            where='`FLD$DATE_TIME` >= NOW() - INTERVAL 60 DAY'
        )

        for rw in rows:
            symbol = rw[FLD_SYMBOL]
            dt_str = rw[FLD_DATE_TIME]
            if symbol:
                set_fact(symbol, 'DELISTING', True, ttl_sec=60 * 24 * 3600, meta={'publish_time': dt_str})
    except Exception as e:
        log(f"[delisting] cache load error: {e}")


# ---------------- ТИК-ДЕТЕКТОР -----------------------------------------

class TickBurstDetector:
    """Ранний детектор импульса по тикам.
    Держим два окна per symbol: короткое и длинное. Считаем частоту и объём в окнах,
    micro P_OC% за короткое окно. Если выполнены пороги — возвращаем (True, features).
    """
    def __init__(self):
        self.short: Dict[str, Deque[Tuple[int, float, float]]] = defaultdict(lambda: deque())  # (ts_ms, price, qty)
        self.long:  Dict[str, Deque[Tuple[int, float, float]]] = defaultdict(lambda: deque())
        self.vol_s: Dict[str, float] = defaultdict(float)
        self.vol_l: Dict[str, float] = defaultdict(float)

    def on_tick(self, symbol: str, ts_ms: int, price: float, qty: float) -> tuple[bool, dict]:
        dq_s = self.short[symbol]
        dq_l = self.long[symbol]
        dq_s.append((ts_ms, price, qty))
        dq_l.append((ts_ms, price, qty))
        self.vol_s[symbol] += qty
        self.vol_l[symbol] += qty

        # trim windows
        cutoff_s = ts_ms - BURST_W_SHORT_MS
        cutoff_l = ts_ms - BURST_W_LONG_MS
        while dq_s and dq_s[0][0] < cutoff_s:
            _, _, q = dq_s.popleft()
            self.vol_s[symbol] -= q
        while dq_l and dq_l[0][0] < cutoff_l:
            _, _, q = dq_l.popleft()
            self.vol_l[symbol] -= q

        dur_s = max(1, BURST_W_SHORT_MS) / 1000.0
        dur_l = max(1, BURST_W_LONG_MS) / 1000.0
        ticks_s = len(dq_s);  ticks_l = len(dq_l)
        rate_s = ticks_s / dur_s
        rate_l = ticks_l / dur_l if dur_l > 0 else ticks_l
        vol_s = max(0.0, self.vol_s[symbol])
        vol_l = max(0.0, self.vol_l[symbol])
        vr_s = vol_s / dur_s
        vr_l = (vol_l / dur_l) if dur_l > 0 else vol_l

        # micro P_OC: цена сейчас vs цена начала короткого окна
        p0 = dq_s[0][1] if dq_s else price
        micro_p = abs((price - p0) / p0 * 100) if p0 else 0.0

        eps = 1e-9
        x_rate = rate_s / max(rate_l, eps)
        x_vr   = vr_s   / max(vr_l, eps)

        ok = (
            x_rate >= BURST_X_RATE_MIN and
            x_vr   >= BURST_X_VR_MIN   and
            micro_p >= BURST_MICRO_POC
        )
        feats = {
            'ticks_s': ticks_s, 'ticks_l': ticks_l,
            'rate_s': round(rate_s, 2), 'rate_l': round(rate_l, 2), 'x_rate': round(x_rate, 2),
            'vr_s': round(vr_s, 4), 'vr_l': round(vr_l, 4), 'x_vr': round(x_vr, 2),
            'micro_p': round(micro_p, 4), 'p0': p0, 'p1': price,
            'ws_ms': BURST_W_SHORT_MS, 'wl_ms': BURST_W_LONG_MS,
        }
        return ok, feats

_tickdet = TickBurstDetector()

# ---------------- Стратегия (секундная) ----------------

class SecondCandleStrategy7:
    def on_trade(self, symbol: str, ts_ms: int, price: float, volume: float, db=None):
        ts_sec = ts_ms // 1000
        key = (symbol, ts_sec)
        _last_price[symbol] = price
        c = _candles.get(key)
        if not c:
            c = _candles[key] = {
                'start': ts_sec,
                'time_get': int(time.time()),
                'open': price, 'high': price, 'low': price, 'close': price,
                'volume': float(volume),
            }
        else:
            if price > c['high']: c['high'] = price
            if price < c['low']:  c['low']  = price
            c['close'] = price
            c['volume'] = float(c['volume']) + float(volume)

        # ---- ТИК-ДЕТЕКТОР: ранняя метка BURST → факт с коротким TTL ----
        try:
            ok, feats = _tickdet.on_tick(symbol, ts_ms, price, float(volume))
            if ok:
                set_fact(symbol, 'TICK_BURST', True, ttl_sec=BURST_TTL_SEC, meta=feats)
                log(f"[BURST] {symbol} xr={feats['x_rate']} xv={feats['x_vr']} micro={feats['micro_p']}% tps={feats['rate_s']}")
                insert_tick_burst(symbol, ts_ms, price, float(volume), feats)
        except Exception as e:
            log(f"[burst] error: {e}")

# ---------------- Флашер ----------------

def flusher7():
    global _last_delis_check
    last_ts = int(time.time()) - 1
    while True:
        now = int(time.time())
        while last_ts <= now - 1:
            gc_facts()  # подчищаем протухшие факты

            # таймер делистингов (неблокирующий запуск)
            if now - _last_delis_check >= DELIS_INTERVAL:
                _last_delis_check = now
                threading.Thread(target=check_delisting_once, daemon=True).start()

            checked = 0
            hits = 0
            for symbol in symbols:
                key = (symbol, last_ts)
                c = _candles.pop(key, None)
                if c is None:
                    price = _last_price.get(symbol)
                    if price is None:
                        continue
                    c = {
                        'start': last_ts,
                        'time_get': int(time.time()),
                        'open': price, 'high': price, 'low': price, 'close': price,
                        'volume': 0.0,
                    }
                c = _finalize_candle(symbol, c)
                _history[symbol].append(c)
                checked += 1

                # DEMO: «хит» — просто по P_OC для видимости потока
                is_hit = (c['P_OC'] >= 4.0)
                if is_hit:
                    hits += 1

                # Базовая таблица по желанию
                if WRITE_TO_DB:
                    try:
                        insert_candle(symbol, c, table_name='ZZ$CANDELS_S1')
                    except Exception as e:
                        log(f" DB insert error: {e}")

            when_sec = dt.datetime.fromtimestamp(last_ts, tz=MSK).strftime("%Y-%m-%d %H:%M:%S")
            #print(f"[SCAN7 {when_sec}] checked:{checked} found:{hits}")
            log(f'{when_sec} checked:{checked} found:{hits}')
            last_ts += 1
        time.sleep(0.2)

# --------------- Запись BURST (тик-импульс) в БД -----------------------

def insert_tick_burst(symbol: str, ts_ms: int, price: float, qty: float, feats: dict):
    """Записывает прошедший порог тик-бурст в ZZ$TICK_BURSTS с максимальными фичами.
    Дедупликация: не чаще BURST_MIN_SEP_MS по одному символу.
    Управляется флагом BURST_WRITE.
    """
    if not BURST_WRITE:
        return
    try:
        last = _last_burst_ms[symbol]
        if ts_ms - last < BURST_MIN_SEP_MS:
            return
        _last_burst_ms[symbol] = ts_ms

        dt_str = dt.datetime.fromtimestamp(ts_ms / 1000.0, tz=MSK).strftime('%Y-%m-%d %H:%M:%S')
        rw = {
            FLD_SYMBOL: symbol,
            FLD_DATE_TIME: dt_str,
            FLD_PRICE: float(price),
            FLD_TCOD: mk_tcod(symbol, ts_ms // 1000, 'BURST', BYBIT),
            FLD_VERSION: v_module(False),
            'FLD$DATE_TIME_MS': int(ts_ms),
            'FLD$TF': 'TICK',
            'FLD$QTY': float(qty),
            'FLD$WS_MS': int(feats.get('ws_ms', BURST_W_SHORT_MS)),
            'FLD$WL_MS': int(feats.get('wl_ms', BURST_W_LONG_MS)),
            'FLD$TICKS_S': int(feats.get('ticks_s', 0)),
            'FLD$TICKS_L': int(feats.get('ticks_l', 0)),
            'FLD$RATE_S': float(feats.get('rate_s', 0.0)),
            'FLD$RATE_L': float(feats.get('rate_l', 0.0)),
            'FLD$X_RATE': float(feats.get('x_rate', 0.0)),
            'FLD$VR_S': float(feats.get('vr_s', 0.0)),
            'FLD$VR_L': float(feats.get('vr_l', 0.0)),
            'FLD$X_VR': float(feats.get('x_vr', 0.0)),
            'FLD$MICRO_POC': float(feats.get('micro_p', 0.0)),
            'FLD$P0': float(feats.get('p0', 0.0)),
            'FLD$P1': float(feats.get('p1', 0.0)),
            'FLD$THR_X_RATE': float(BURST_X_RATE_MIN),
            'FLD$THR_X_VR': float(BURST_X_VR_MIN),
            'FLD$THR_MICRO': float(BURST_MICRO_POC),
            'FLD$SRC': 'TICK_BURST',
        }
        qr_add('ZZ$TICK_BURSTS', rw)

        # после записи BURST — возможен экстренный вход
        insert_early_order(symbol, ts_ms, price, qty, feats)

    except Exception as e:
        log(f"[BURST][DB] {symbol} err: {e}")

# --------------- Ранний вход (экстренный) → ORDERS_2 -------------------

def insert_early_order(symbol: str, ts_ms: int, price: float, qty: float, feats: dict):
    """Пишет экстренный вход в ZZ$ORDERS_2 с признаком TF='TICK_EARLY'.
    Направление: BUY если p1>p0, иначе SELL. При активном DELISTING — BUY блокируем.
    """
    if not EARLY_WRITE:
        return
    try:
        dt_sec = ts_ms // 1000
        dt_str = dt.datetime.fromtimestamp(dt_sec, tz=MSK).strftime('%Y-%m-%d %H:%M:%S')
        p0 = float(feats.get('p0', price))
        p1 = float(feats.get('p1', price))
        direction = 'UP' if p1 > p0 else ('DOWN' if p1 < p0 else 'FLAT')
        poc = float(feats.get('micro_p', 0.0))

        operation = BUY if direction == 'UP' else (SELL if direction == 'DOWN' else 'NONE')
        if get_fact(symbol, 'DELISTING', False) and operation == BUY:
            operation = 'NONE'

        rw = {
            FLD_SYMBOL: symbol,
            FLD_DATE_TIME: dt_str,
            FLD_VOLUME: float(qty),
            FLD_SUM: float(EARLY_SUM_USDT),
            FLD_TCOD: mk_tcod(symbol, dt_sec, 'EARLY', BYBIT),
            FLD_VERSION: v_module(False),
            'FLD$DATE_TIME_GET': dt.datetime.fromtimestamp(time.time(), tz=MSK).strftime('%Y-%m-%d %H:%M:%S'),
            'FLD$TF': 'TICK_EARLY',
            'FLD$P_OPEN': p1,
            'FLD$P_CLOSE': p1,
            'FLD$P_HIGH': p1,
            'FLD$P_LOW':  p1,
            'FLD$P_OC': round(poc, 4),
            'FLD$DIRECTION': direction,
            'FLD$OPERATION': operation,
            'FLD$LEVERAGE': int(EARLY_LEVERAGE),
        }
        qr_add('ZZ$ORDERS_2', rw)
        log(f"[EARLY] {symbol} op={operation} lev={EARLY_LEVERAGE} sum={EARLY_SUM_USDT} poc={poc}%")
    except Exception as e:
        log(f"[EARLY][DB] {symbol} err: {e}")

# --------------- Запись свечи (унифицировано, как в prod) --------------

def insert_candle(symbol: str, c: dict, table_name: str = 'ZZ$CANDELS_S1', tf: str = '1SEC'):
    dt_str = dt.datetime.fromtimestamp(c['start'], tz=MSK).strftime('%Y-%m-%d %H:%M:%S')
    rw = {
        FLD_SYMBOL: symbol,
        FLD_DATE_TIME: dt_str,
        FLD_VOLUME: round(float(c['volume']), 2),
        FLD_TCOD: mk_tcod(symbol, c['start'], tf, BYBIT),
        FLD_VERSION: v_module(False),
        'FLD$DATE_TIME_GET': dt.datetime.fromtimestamp(c.get('time_get', time.time()), tz=MSK).strftime('%Y-%m-%d %H:%M:%S'),
        'FLD$TF': tf,
        'FLD$P_OPEN': c['open'],
        'FLD$P_CLOSE': c['close'],
        'FLD$P_HIGH': c['high'],
        'FLD$P_LOW': c['low'],
        'FLD$P_OC': round(float(c.get('P_OC', 0.0)), 2),
        'FLD$DIRECTION': c.get('D', 'FLAT'),
    }
    return qr_add(table_name, rw)

# ---------------- run ----------------

def main():
    mod = get_module('SCAN', 8)
    mod.log('main', f'Started')
    _ = db_init()
    symbols = load_bybit_symbols()
    strat = SecondCandleStrategy7()
    ws = BybitWS(symbols=symbols, strategy=strat, db=_db)
    t = threading.Thread(target=flusher7, daemon=True)
    t.start()
    ws.run()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log('Stopped by user')
        db_close()
