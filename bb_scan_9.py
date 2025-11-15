# ======================================================================================================================
# 📁 file        : bb_scan_9.py — SCAN v9 (REST tick buffer + WS tick detector)
# 🕒 created     : 29.10.2025 09:50
# 🎉 contains    : TmodScan9 (REST+WS module), main() launcher
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from collections import defaultdict, deque
import datetime as dt
import json
import threading
import time
import urllib.request

from bb_sys import *
from bb_db import *
from bb_ws import *
# 💎 ... CONFIG / CONSTS ...
SCAN_CANDLES_TABLE = "ZZ$CANDLES"
SCAN_DEFAULT_MAX_SYMBOLS = 10
SCAN_POLL_INTERVAL_S = 60
SCAN_FLUSH_INTERVAL_S = 30
SCAN_BUFFER_MAXLEN = 150

# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TmodScan9 — SCAN v9: REST loader + WS tick detector + DB flusher
# ----------------------------------------------------------------------------------------------------------------------
class TmodScan9(TModule):
    """SCAN v9 — REST-сбор символов + минутные свечи + TickDetector через WebSocket."""

    TBL_CANDLES = SCAN_CANDLES_TABLE
    MAX_SYMBOLS = SCAN_DEFAULT_MAX_SYMBOLS
    POLL_INTERVAL_S = SCAN_POLL_INTERVAL_S
    FLUSH_INTERVAL_S = SCAN_FLUSH_INTERVAL_S
    CANDLE_BUFFER_MAXLEN = SCAN_BUFFER_MAXLEN
    # ⚡🛠️ ▸ __init__
    def __init__(self, app):
        """Регистрирует модуль SCAN_9, настраивает буферы и потоки фоновой обработки."""
        super().__init__(app, "SCAN", 9)
        # --- Runtime state ---
        self.symbols: list[str] = []
        self.candles: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.CANDLE_BUFFER_MAXLEN)
        )
        self.last_price: dict[str, float] = defaultdict(lambda: None)
        # --- Background services ---
        self._stop = False
        self._flush_thread = None
        self.ws = None
        self.tick_detector = None
        # ... 🔊 ...
        self.log("__init__", "module initialized")
        # ⚡🛠️ TmodScan9 ▸ End of __init__

    # ..................................................................................................................
    # 🌐 REST — загрузка списка символов
    # ..................................................................................................................
    def load_symbols(self) -> list[str]:
        """Берёт список линейных инструментов Bybit и фильтрует по *USDT."""
        url = f"{BYBIT_REST}/v5/market/instruments-info?category=linear"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            rows = (data or {}).get("result", {}).get("list", []) or []
            symbols = [r["symbol"] for r in rows if str(r.get("symbol", "")).endswith("USDT")]
            symbols.sort()
            if self.MAX_SYMBOLS and len(symbols) > self.MAX_SYMBOLS:
                symbols = symbols[: self.MAX_SYMBOLS]
            self.log("load_symbols", f"{len(symbols)} symbols loaded")
            return symbols
        except Exception as e:
            self.log("load_symbols", f"⚠️ failed: {e}")
            return []

    # ..................................................................................................................
    # 🌐 REST — опрос минутных свечей и буферизация
    # ..................................................................................................................
    def update_candles(self, symbol: str):
        """Загружает минутные свечи (interval=1) и добавляет их в локальный буфер."""
        url = f"{BYBIT_REST}/v5/market/kline?category=linear&symbol={symbol}&interval=1"
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            items = (data or {}).get("result", {}).get("list", []) or []
            for row in items:
                if not isinstance(row, (list, tuple)) or len(row) < 6:
                    continue
                ts_ms = int(row[0])
                o, h, l, c, v = row[1:6]
                candle = {
                    "ts": ts_ms,
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": float(v),
                }
                self.candles[symbol].append(candle)
            if self.candles[symbol]:
                last_close = self.candles[symbol][-1]["close"]
                prev_close = self.last_price[symbol]
                if prev_close is None or last_close != prev_close:
                    self.last_price[symbol] = last_close
                    self.log("tick", f"{symbol} close={last_close}")
            self.log("update_candles", f"{symbol}: {len(self.candles[symbol])} buffered")
        except Exception as e:
            self.log("update_candles", f"⚠️ {symbol}: {e}")

    # ..................................................................................................................
    # 💾 Flusher — периодическая запись последних свечей в БД
    # ..................................................................................................................
    def flusher(self):
        """Раз в FLUSH_INTERVAL_S записывает последнюю свечу каждого символа в БД."""
        app = self.owner
        while not self._stop:
            saved = 0
            try:
                for sym, buf in list(self.candles.items()):
                    if not buf:
                        continue
                    last = buf[-1]
                    dt_msk = dt.datetime.fromtimestamp(last["ts"] / 1000.0, tz=MSK)
                    record = {
                        FLD_SYMBOL: sym,
                        FLD_DATE_TIME: dt_msk,
                        FLD_PRICE: last["close"],
                        FLD_VOLUME: last["volume"],
                        FLD_TYPE: "CANDLE_1M",
                        FLD_SOURCE: "SCAN9",
                    }
                    qr_foi(
                        self.TBL_CANDLES,
                        {FLD_SYMBOL: sym, FLD_DATE_TIME: dt_msk},
                        record,
                    )
                    saved += 1
                if saved:
                    self.log("flusher", f"batch saved ({saved} rows)")
            except Exception as e:
                self.log("flusher", f"⚠️ {e}")
            time.sleep(self.FLUSH_INTERVAL_S)

    # ..................................................................................................................
    # 🚀 Lifecycle — open/heartbeat/close
    # ..................................................................................................................
    def do_open(self) -> bool:
        """Основной запуск модуля SCAN_9."""
        self.log("do_open", "starting WS tick scan...")
        app = self.owner
        self.log("do_open", f"Active project: {app.project_tag}")
        self.log("do_open", f"Session active: {app.Session.active}")
        self.log("do_open", f"Database active: {app.Database.active}")
        self.log("do_open", f"Config vars loaded: {len(app.Config.env)}")
        self.symbols = self.load_symbols()
        if not self.symbols:
            self.log("do_open", "⚠️ no symbols loaded — exiting do_open()")
            return False
        self.log("do_open", f"{len(self.symbols)} symbols ready for WS subscription")
        self.tick_detector = TTickDetector(self)
        self.tick_detector.bus.subscribe("tick_spike", db_signal_writer)
        self.log("do_open", "TickDetector and SignalBus initialized")
        try:
            self.ws = TBybitWS(self, self.symbols, self.tick_detector.feed)
            self.ws.open()
            self.log("do_open", "WebSocket connection started")
        except Exception as e:
            self.log("do_open", f"⚠️ failed to start WebSocket: {e}")
            return False
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        self._flush_thread = threading.Thread(target=self.flusher, daemon=True)
        self._flush_thread.start()
        return True

    # --- Heartbeat монитор ---
    def _heartbeat_loop(self):
        while not self._stop:
            ws_state = getattr(self.ws, "_connected", False)
            self.log("heartbeat", f"active symbols={len(self.symbols)}  ws_connected={ws_state}")
            time.sleep(30)

    def do_close(self) -> bool:
        """Завершает работу SCAN_9."""
        self._stop = True
        self.log("do_close", "stopping background threads...")
        try:
            if self.ws:
                self.ws.close()
        except Exception as e:
            self.log("do_close", f"⚠️ ws close error: {e}")
        th = self._flush_thread
        if th and th.is_alive():
            try:
                th.join(timeout=5)
            except Exception:
                pass
        self.log("do_close", "module stopped gracefully")
        return True

# ----------------------------------------------------------------------------------------------------------------------
# 🚀 main() — автономный запуск SCAN v9
# ----------------------------------------------------------------------------------------------------------------------
def main():
    app = Application()
    app.echo('Hello world!))')
    app.echo("🧠 TSchema initialized")
    app.echo("<b>Loaded:</b> 37 tables")
    app.echo("⚙️ Config vars: " + str(len(app.Config.env)))
    s = ""
    s += "<table border='1'>"
    s += "<tr>"
    s += "<td>"
    s += "column_1"
    s += "</td>"
    s += "<td>"
    s += "column_2"
    s += "</td>"
    s += "<td>"
    s += "column_3"
    s += "</td>"
    s += "</tr>"
    s += "</table>"
    app.echo(s)
    mod = TmodScan9(app)
    mod.open()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        mod.close()
        CloseApplication()

if __name__ == '__main__':
    main()
# ======================================================================================================================
# 📁🌄 bb_scan_9.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10
# ======================================================================================================================
