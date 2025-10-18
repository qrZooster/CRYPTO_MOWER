# ==============================================================
# bb_ws.py — WebSocket subsystem for Delphi.2025
# Created: 2025-10-12 / Учитель & GPT-5
# ==============================================================

import json
import threading
import time
from collections import defaultdict, deque
import websocket  # pip install websocket-client

import asyncio, subprocess

from bb_sys import *
from bb_db import *

# ==============================================================
#   SIGNAL BUS
# ==============================================================

class TSignalBus(TComponent):
    """Универсальная шина событий для обмена сигналами между компонентами."""

    def __init__(self, owner):
        super().__init__(owner, "SignalBus")
        self.subscribers: dict[str, list[callable]] = {}
        self.log("__init__", "bus ready")

    def subscribe(self, event: str, callback: callable):
        """Регистрирует подписчика на событие."""
        if event not in self.subscribers:
            self.subscribers[event] = []
        self.subscribers[event].append(callback)
        self.log("subscribe", f"{callback.__name__} → {event}")

    def emit(self, event: str, *args, **kwargs):
        """Вызывает всех подписчиков события."""
        for cb in self.subscribers.get(event, []):
            try:
                cb(*args, **kwargs)
            except Exception as e:
                self.log("emit", f"⚠️ {event} {cb.__name__}: {e}")

# ==============================================================
#   TBybitWS — WebSocket компонент
# ==============================================================

class TBybitWS(TLiveComponent):
    """
    WebSocket-компонент для получения тиков Bybit (publicTrade.*).
    Может жить внутри любого модуля, наследуется от TLiveComponent.
    """

    def __init__(self, owner, symbols, on_tick):
        super().__init__(owner, "BybitWS")
        self.symbols = symbols
        self.on_tick = on_tick  # callback → TickDetector.feed()
        self.ws = None
        self._connected = False
        self._stop = False
        self.log("__init__", f"initialized for {len(symbols)} symbols")

    # ----------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------
    def do_open(self) -> bool:
        """Запускает поток WebSocket."""
        self._stop = False
        threading.Thread(target=self._run_ws, daemon=True).start()
        self.log("do_open", "WebSocket thread started")
        return True

    def do_close(self) -> bool:
        """Останавливает WebSocket."""
        self._stop = True
        if self.ws:
            try:
                self.ws.close()
                self.log("do_close", "WebSocket closed")
            except Exception as e:
                self.log("do_close", f"⚠️ close error: {e}")
        self._connected = False
        return True

    # ----------------------------------------------------------
    # Основной WS-цикл
    # ----------------------------------------------------------
    def _run_ws(self):
        """Главный reconnect-цикл WebSocket."""

        def on_open(ws):
            self._connected = True
            args = [f"publicTrade.{s}" for s in self.symbols]
            ws.send(json.dumps({"op": "subscribe", "args": args}))
            self.log("on_open", f"subscribed {len(args)} symbols")

        def on_message(ws, msg):
            if self._stop:
                return
            try:
                data = json.loads(msg)
                topic = data.get("topic", "")
                if topic.startswith("publicTrade."):
                    symbol = topic.split(".", 1)[1]
                    for row in data.get("data", []):
                        tick = {
                            "symbol": symbol,
                            "ts": int(row.get("T", 0)),
                            "price": float(row.get("p", 0)),
                            "side": row.get("S", ""),
                            "volume": float(row.get("v", 0)),
                        }
                        self.on_tick(tick)
            except Exception as e:
                self.log("on_message", f"⚠️ {e}")

        def on_error(ws, err):
            self.log("on_error", str(err))

        def on_close(ws, code, msg):
            self._connected = False
            self.log("on_close", f"{code}: {msg}")

        while not self._stop:
            try:
                self.ws = websocket.WebSocketApp(
                    BYBIT_WS_PUBLIC_LINEAR,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                self.log("_run_ws", f"⚠️ {e}")
            if not self._stop:
                time.sleep(5)


# ==============================================================
#   TLogEkranWS — WebSocket сервер для трансляции логов TEkran
#   Потоково шлёт journalctl bbscan.service в браузер (/logs)
# ==============================================================

class TLogEkranWS(TLiveComponent):
    """Локальный WebSocket-сервер, стримящий journalctl лог сервиса в TEkran /logs."""

    def __init__(self, owner, port=8082, service="bbscan.service", initial_tail=100):
        super().__init__(owner, "LogEkranWS")
        self.port = port
        self.service = service
        self.initial_tail = int(initial_tail)
        self.clients: set = set()
        self._stop = False
        self._thread = None
        self._proc: subprocess.Popen | None = None
        self._server = None

    # ----------------------- lifecycle ------------------------
    def do_open(self) -> bool:
        """Стартует WS-сервер в отдельном потоке (asyncio)."""
        if self._thread and self._thread.is_alive():
            return True
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.log("do_open", f"ws://0.0.0.0:{self.port} for {self.service}")
        return True

    def do_close(self) -> bool:
        """Останавливает WS и tail-процесс journalctl."""
        self._stop = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self.log("do_close", "stop requested")
        return True

    # ----------------------- asyncio core ---------------------
    def _run(self):
        asyncio.run(self._amain())

    async def _amain(self):
        self._server = await websockets.serve(self._ws_handler, "0.0.0.0", self.port)
        self.log("run", f"listening ws://0.0.0.0:{self.port}")
        pump_task = asyncio.create_task(self._pump_journal())
        while not self._stop:
            await asyncio.sleep(0.5)
        pump_task.cancel()
        await self._server.wait_closed()

    async def _ws_handler(self, ws):
        self.clients.add(ws)
        async for _ in ws:
            pass
        self.clients.discard(ws)

    async def _pump_journal(self):
        """
        Запускает `journalctl -fu <service> -n <initial_tail>` и ретранслирует строки всем клиентам.
        """
        cmd = ["journalctl", "-fu", self.service, "-n", str(self.initial_tail)]
        self.log("journalctl", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # построчно
        )

        while not self._stop and self._proc.stdout:
            line = self._proc.stdout.readline()
            if not line:
                await asyncio.sleep(0.05)
                continue
            await self._broadcast_json("log", line.rstrip("\n"))

        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    async def _broadcast_json(self, event: str, data):
        if not self.clients:
            return
        msg = json.dumps({"event": event, "data": data})
        dead = []
        for ws in self.clients:
            try:
                await ws.send(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

# ==============================================================
#   TTickDetector — анализ тиков и генерация событий
# ==============================================================

class TTickDetector(TComponent):
    """Анализирует входящие тики, ищет аномалии (price spikes)."""

    def __init__(self, owner):
        super().__init__(owner, "TickDetector")
        self.last_price = defaultdict(lambda: None)
        self.history = defaultdict(lambda: deque(maxlen=500))
        self.threshold = 0.003  # 0.3%
        self.bus = TSignalBus(self)
        self.log("__init__", "detector ready")

    def feed(self, tick: dict):
        """Принимает тик от WebSocket."""
        sym = tick["symbol"]
        price = tick["price"]
        ts = tick["ts"]
        prev = self.last_price[sym]

        self.history[sym].append((ts, price))
        self.last_price[sym] = price

        if prev is not None:
            delta = (price - prev) / prev if prev else 0
            if abs(delta) >= self.threshold:
                self._trigger(sym, ts, price, delta)

    def _trigger(self, symbol, ts, price, delta):
        """Создаёт событие tick_spike через SignalBus."""
        msg = f"{symbol} Δ={delta:+.3%} → {price}"
        self.log("trigger", msg)
        self.bus.emit("tick_spike", symbol, price, delta, ts)

# ==============================================================
#   Пример подписчика для SignalBus
# ==============================================================

def db_signal_writer(symbol, price, delta, ts):
    """Пример обработчика сигналов — запись в ZZ$SIGNALS."""
    try:
        record = {
            FLD_SYMBOL: symbol,
            FLD_DATE_TIME: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts / 1000)),
            FLD_PRICE: price,
            FLD_VOLUME: 0.0,
            FLD_TYPE: "TICK_SPIKE",
            FLD_SOURCE: "WS",
        }
        qr_add("ZZ$SIGNALS_2", record)
        print(f"[SignalBus] saved tick_spike {symbol} → {price}")
    except Exception as e:
        print(f"[db_signal_writer] ⚠️ {e}")

# ==============================================================
#   Public exports
# ==============================================================

__all__ = ["TBybitWS", "TTickDetector", "TSignalBus", "db_signal_writer"]

