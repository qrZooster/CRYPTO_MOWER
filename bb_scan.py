# bb_scan.py
# ALIAS: BB_SCAN
# Created: 2025-09-18
# Сканер паттернов PUMP/DUMP по истории Bybit

import os
import io
import json
import requests
import statistics
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone

from bb_db import DBScan
from bb_vars import BYBIT_MODE, BYBIT_REST
from bb_lib import MSK


# Пороговые значения
STRONG_PRICE_JUMP = 0.03   # 3%
STRONG_VOLUME_MULT = 20.0  # рост объема в 20 раз
AVG_WINDOW = 20            # размер окна для медианы объема

# Ограничение по количеству символов за запуск
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", 50))

# Файл прогресса
SCAN_PROGRESS_FILE = "scan_progress.json"

# --- API Bybit ---
def fetch_symbols():
    url = f"{BYBIT_REST}/v5/market/instruments-info"
    params = {"category": "linear"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    items = r.json().get("result", {}).get("list", [])
    return [it["symbol"] for it in items if it.get("quoteCoin") == "USDT" and it.get("status") == "Trading"]

def fetch_kline(symbol: str, interval: str = "1", limit: int = 200):
    url = f"{BYBIT_REST}/v5/market/kline"
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("result", {}).get("list", [])

# --- Визуализация ---
def generate_pattern_image(prices, volumes, ts_list, symbol, type_sig, interval):
    plt.figure(figsize=(8, 4))
    plt.subplot(2, 1, 1)
    plt.plot(ts_list, prices, label="Price", color="blue")
    plt.title(f"{symbol} {type_sig} ({interval})")
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.grid(True)
    plt.legend()

    plt.subplot(2, 1, 2)
    plt.bar(ts_list, volumes, label="Turnover (USDT)", color="orange")
    plt.xlabel("Time")
    plt.ylabel("Turnover")
    plt.grid(True)
    plt.legend()

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf.read()

# --- Алгоритм поиска паттернов ---
def find_strong_pumps_dumps(symbol: str, interval: str = "1", limit: int = 200):
    db = DBScan()
    klines = fetch_kline(symbol, interval, limit)
    if not klines:
        print(f"Нет данных по {symbol}")
        return

    klines = sorted(klines, key=lambda x: int(x[0]))
    prices, turnovers, ts_list = [], [], []

    for k in klines:
        ts = datetime.fromtimestamp(int(k[0]) / 1000, tz=MSK)
        open_p, high_p, low_p, close_p = map(float, k[1:5])
        turnover = float(k[7]) if len(k) >= 8 else float(k[5])

        if len(turnovers) > 0:
            past_window = turnovers[-AVG_WINDOW:]
            median_v_prev = statistics.median(past_window)
        else:
            past_window = []
            median_v_prev = 0.0

        price_delta = (close_p - open_p) / open_p if open_p else 0.0
        x_volume = turnover / median_v_prev if median_v_prev > 0 else 0

        print(f"[DEBUG] {ts} Δp={price_delta*100:.2f}%, XVol={x_volume:.2f}x, Turnover={turnover}, MedianTurnover={median_v_prev:.2f}, PastWindow={past_window}")

        prices.append(close_p)
        turnovers.append(turnover)
        ts_list.append(ts)

        if median_v_prev > 0 and x_volume > STRONG_VOLUME_MULT and abs(price_delta) > STRONG_PRICE_JUMP:
            type_sig = "PUMP" if price_delta > 0 else "DUMP"
            emoji = "🟢🚀" if type_sig == "PUMP" else "🔴⚠️"
            p_price = price_delta * 100.0
            tf_str = "1MIN" if interval == "1" else "1H"

            print(f"{emoji} STRONG {type_sig} {symbol} ({tf_str})\n"
                  f"{ts}\n"
                  f"Δp={p_price:.2f}%, XVol={x_volume:.2f}x\n"
                  f"O:{open_p} H:{high_p} L:{low_p} C:{close_p} Turnover:{turnover}")

            img_bytes = generate_pattern_image(prices, turnovers, ts_list, symbol, type_sig, interval)

            params = {
                "symbol": symbol,
                "datetime": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "p_price": round(p_price, 2),
                "x_volume": round(x_volume, 2),
                "avg_volume": round(median_v_prev, 2),
                "open": open_p,
                "close": close_p,
                "high": high_p,
                "low": low_p,
                "volume": turnover
            }
            db.insert_pattern(f"Strong {type_sig}", type_sig, tf_str, symbol, params, img_bytes)

# --- Прогресс сканирования ---
def load_progress():
    if os.path.exists(SCAN_PROGRESS_FILE):
        with open(SCAN_PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_index": 0}

def save_progress(data):
    with open(SCAN_PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

if __name__ == "__main__":
    symbols = fetch_symbols()
    progress = load_progress()
    start_index = progress.get("last_index", 0)

    batch = symbols[start_index:start_index+MAX_SYMBOLS]
    print(f"🔎 Поиск сильных пампов/дампов: обрабатываем {len(batch)} символов из {len(symbols)} (с {start_index})...")

    for s in batch:
        find_strong_pumps_dumps(s, "1", 200)
        find_strong_pumps_dumps(s, "60", 200)

    new_index = start_index + len(batch)
    if new_index >= len(symbols):
        new_index = 0
    save_progress({"last_index": new_index})
    print(f"✅ Прогресс сохранён: следующий запуск начнёт с {new_index}")
