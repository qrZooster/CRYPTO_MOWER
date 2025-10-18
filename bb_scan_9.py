# bb_scan_9.py — SCAN v9
# Refactored for Application / Module architecture
# 2025-10-12 15:35 / Учитель & GPT-5

from collections import defaultdict, deque
import time
import json
import threading
import datetime as dt
import urllib.request

from bb_sys import *
from bb_db import *
from bb_ws import *

class TmodScan9(TModule):
    """
    SCAN v9 — первый рабочий модуль на архитектуре Delphi.2025
    - REST-загрузка списка символов
    - Буфер свечей (deque, maxlen=150)
    - Детектор тиков (на уровне close)
    - Flusher: запись последних свечей в БД через qr_foi
    """

    # таблица для записи свечей (можно вынести в конфиг)
    TBL_CANDLES = 'ZZ$CANDLES'

    # параметры опроса
    MAX_SYMBOLS      = 10     # ограничение на кол-во символов для теста
    POLL_INTERVAL_S  = 60     # период опроса REST-свечей
    FLUSH_INTERVAL_S = 30     # период записи в БД

    def __init__(self, app):
        super().__init__(app, "SCAN", 9)

        # состояние модуля
        self.symbols: list[str] = []
        self.candles: dict[str, deque] = defaultdict(lambda: deque(maxlen=150))
        self.last_price: dict[str, float] = defaultdict(lambda: None)
        self._stop = False
        self._flush_thread = None
        self.log("__init__", "module initialized")

    # ------------------------------------------------------------------
    # REST: загрузка списка символов
    # ------------------------------------------------------------------
    def load_symbols(self) -> list[str]:
        """Берём список линейных инструментов Bybit и фильтруем по *USDT."""
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

    # ------------------------------------------------------------------
    # REST: опрос минутных свечей и наполнение локального буфера
    # ------------------------------------------------------------------
    def update_candles(self, symbol: str):
        """Загружает минутные свечи (interval=1) и добавляет в буфер."""
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

            # Tick detector: изменение close
            if self.candles[symbol]:
                last_close = self.candles[symbol][-1]["close"]
                prev_close = self.last_price[symbol]
                if prev_close is None or last_close != prev_close:
                    self.last_price[symbol] = last_close
                    self.log("tick", f"{symbol} close={last_close}")

            self.log("update_candles", f"{symbol}: {len(self.candles[symbol])} buffered")

        except Exception as e:
            self.log("update_candles", f"⚠️ {symbol}: {e}")

    # ------------------------------------------------------------------
    # Flusher: периодическая запись последних свечей в БД
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def do_open(self) -> bool:
        """Основной запуск модуля SCAN_9."""
        self.log("do_open", "starting WS tick scan...")

        # 1) Диагностика среды
        app = self.owner
        self.log("do_open", f"Active project: {app.project_tag}")
        self.log("do_open", f"Session active: {app.Session.active}")
        self.log("do_open", f"Database active: {app.Database.active}")
        self.log("do_open", f"Config vars loaded: {len(app.Config.env)}")

        # 2) Загрузка списка символов
        self.symbols = self.load_symbols()
        if not self.symbols:
            self.log("do_open", "⚠️ no symbols loaded — exiting do_open()")
            return False
        self.log("do_open", f"{len(self.symbols)} symbols ready for WS subscription")

        # 3) Инициализация тик-детектора
        self.tick_detector = TTickDetector(self)
        self.tick_detector.bus.subscribe("tick_spike", db_signal_writer)
        self.log("do_open", "TickDetector and SignalBus initialized")

        # 4) Подключение WebSocket
        try:
            self.ws = TBybitWS(self, self.symbols, self.tick_detector.feed)
            self.ws.open()
            self.log("do_open", "WebSocket connection started")
        except Exception as e:
            self.log("do_open", f"⚠️ failed to start WebSocket: {e}")
            return False

        # 5) Цикл heartbeat
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        self._flush_thread = threading.Thread(target=self.flusher, daemon=True)
        self._flush_thread.start()
        return True

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

        # дождаться завершения flusher
        th = self._flush_thread
        if th and th.is_alive():
            try:
                th.join(timeout=5)
            except Exception:
                pass

        self.log("do_close", "module stopped gracefully")
        return True

# ==============================================================
#   MAIN ENTRY POINT
# ==============================================================

def main():
    app = Application()          # создаёт Database, Session, Config
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
    mod.open()                    # активирует модуль
    try:
        # держим процесс живым, пока systemd не пришлёт SIGTERM
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        mod.close()               # корректно остановить модуль
        CloseApplication()       # graceful shutdown

if __name__ == '__main__':
    main()
