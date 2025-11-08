# ======================================================================================================================
# 📁 file        : bb_ws_extended.py — Расширенные WebSocket клиенты/сервер Tradition Core 2025
# 🕒 created     : 18.10.2025 07:45
# 🎉 contains    : TWebSocketServer (WS-сервер ядра), TWebSocketClientExtended (клиент), MockWebSocketClient (эмулятор),
#                  TBinanceWebSocketClient / TBybitWebSocketClient (биржевые клиенты)
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
import asyncio
import json
import random
import time
from typing import Optional, Dict, List, Any
import websockets
from bb_sys import *
from bb_events import TEvent, TEventType, TwsDataChannel, TwsChannelData, create_status_event, create_tick_channel_data
# 💎🧩 ... CONFIG / CONSTS ...
__all__ = ["TLocalWebSocketServer", "TWebSocketClientExtended", "TBybitWebSocketClient"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TLocalWebSocketServer — системный WebSocket-сервер Tradition Core
# ----------------------------------------------------------------------------------------------------------------------
class TLocalWebSocketServer(TSysComponent):
    """
    Асинхронный WebSocket-сервер системного уровня Tradition Core.
    Принимает клиентов, рассылает им сообщения и принимает команды.
    """
    def __init__(self, owner: "TApplication", host: str = "0.0.0.0", port: int = 8082):
        """
        Создаёт WebSocket-сервер и регистрирует его как системный компонент.
        owner — это TApplication.
        """
        super().__init__(owner, "WebSocketServer")
        self.host = host
        self.port = port
        self.subscribers: set = set()
        self._server = None
        self._task_heartbeat = None
        self._task_debug_log = None
        self._stop = False
        self.log("__init__", f"initialized on ws://{host}:{port}")
    # ......................................................................................................................
    # 🌳 Life Cycle
    # ......................................................................................................................
    def do_open(self) -> bool:
        """ Запускает главный цикл локального WS-сервера. """
        self._stop = False
        asyncio.create_task(self.run_main_cycle())
        self.log("do_open", f"server task started ({self.host}:{self.port})")
        return True

    def do_close(self) -> bool:
        """
        Закрывает всех активных клиентов и останавливает сервер.
        Вызывается при close() компонента.
        """
        self._stop = True
        self.log("do_close", "closing...")
        for ws in list(self.subscribers):
            asyncio.create_task(ws.close(code=1001, reason="server shutdown"))
        return True
    # ......................................................................................................................
    # ‍🚀 Run Main Cycle
    # ......................................................................................................................
    async def run_main_cycle(self):
        """
        Главный асинхронный цикл локального WS-сервера:
        - поднимает ws-сервер;
        - принимает подписчиков;
        - запускает heartbeat;
        - ждёт остановки.
        """
        self._server = await websockets.serve(self._serve_subscriber, self.host, self.port)
        self.log("run_main_cycle", f"listening on ws://{self.host}:{self.port}")
        self._task_heartbeat = asyncio.create_task(self._heartbeat())
        self._task_demo_logs = asyncio.create_task(self._demo_log_stream())
        self._task_debug_log = asyncio.create_task(self._debug_log_ticker())
        await self._server.wait_closed()
        self.log("run_main_cycle", "server stopped")

    async def _debug_log_ticker(self):
        """
        Периодически пишет тестовый лог через обычный self.log(),
        чтобы проверить цепочку log() → ws_push_log() → WebSocket → браузер.
        """
        counter = 0
        while not self._stop:
            counter += 1
            self.log(
                "_debug_log_ticker",
                f"test-log #{counter} subscribers={len(self.subscribers)}"
            )
            await asyncio.sleep(5)

    async def _demo_log_stream(self):
        """
        Демонстрационный генератор логов.
        Раз в 3 секунды шлёт строку в канал 'log'.
        """
        i = 0
        while not self._stop:
            i += 1
            line = f"demo-log #{i} at {time.strftime('%H:%M:%S')}"
            await self.send_log_to_monitors(line)
            await asyncio.sleep(3)

    async def _serve_subscriber(self, ws):
        """
        Обслуживание одного подписчика (монитора):
        - добавляем в список подписчиков;
        - шлём приветствие;
        - читаем запросы подписчика;
        - при отключении — убираем из списка.
        """
        self.subscribers.add(ws)
        addr = getattr(ws, "remote_address", None)
        self.log("_serve_subscriber", f"subscriber connected: {addr}")
        try:
            await ws.send(json.dumps({"type": "hello", "msg": "welcome"}))
            async for msg in ws:
                await self._on_subscriber_query(ws, msg)
        except Exception as e:
            self.log("_serve_subscriber", f"⚠️ {e}")
        finally:
            self.subscribers.discard(ws)
            self.log("_serve_subscriber", f"subscriber disconnected: {addr}")
    # ..................................................................................................................
    # 📡 Event sending
    # ..................................................................................................................
    async def _on_subscriber_query(self, ws, msg: str):
        """
        Пришёл запрос от подписчика (браузера).
        Разбираем JSON-команду и отвечаем.
        """
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            await ws.send(json.dumps({
                "type": "system_message",
                "level": "error",
                "text": f"invalid JSON: {msg}"
            }))
            return

        cmd = data.get("cmd")

        if cmd == "ping":
            await ws.send(json.dumps({"type": "system_message", "text": "pong"}))
        elif cmd == "hello":
            await ws.send(json.dumps({
                "type": "system_message",
                "text": "hello from Tradition Core 2025"
            }))
        else:
            await ws.send(json.dumps({
                "type": "system_message",
                "level": "warning",
                "text": f"unknown command: {cmd}"
            }))

    async def send_to_subscribers(self, payload: dict):
        """
        Отправляет payload (как JSON) всем активным подписчикам (мониторам).
        Это универсальный низкоуровневый отправитель.
        """
        if not self.subscribers:
            return
        msg = json.dumps(payload)
        await asyncio.gather(*(ws.send(msg) for ws in list(self.subscribers)), return_exceptions=True)

    async def _heartbeat(self):
        """
        Периодически пингует клиентов, чтобы соединения не засыпали.
        Удаляет "мертвые" сокеты.
        """
        while True:
            dead = []
            for ws in list(self.subscribers):
                try:
                    pong_waiter = await ws.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.subscribers.discard(ws)
            await asyncio.sleep(10)
    # ..................................................................................................................
    # 📺 TV Channels
    # ..................................................................................................................
    async def send_tick_to_monitors(self, symbol: str, price: float, volume: float):
        """
        Шлёт обновление тика всем подключённым мониторам.
        Канал: 'tick', тип: 'tick_update'.
        """
        await self.send_to_subscribers({
            "channel": "tick",
            "type": "tick_update",
            "symbol": symbol,
            "price": price,
            "volume": volume,
        })

    async def send_log_to_monitors(self, line: str):
        """
        Шлёт строку лога в канал 'log'.
        """
        await self.send_to_subscribers({
            "channel": "log",
            "type": "log_line",
            "text": line,
        })

    async def send_system_message_to_monitors(self, text: str, level: str = "info"):
        """
        Служебное сообщение в канал 'system'.
        """
        await self.send_to_subscribers({
            "channel": "system",
            "type": "system_message",
            "level": level,
            "text": text,
        })
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TWebSocketClientExtended — расширенный WS-клиент (события + каналы)
# ----------------------------------------------------------------------------------------------------------------------
class TWebSocketClientExtended(TLiveComponent):
    """
    Расширенный WebSocket-клиент Tradition Core с поддержкой системы событий и каналов.
    Подключается к внешним биржам/сервисам, нормализует входящие сообщения в TEvent/TwsChannelData
    и передаёт их в TApplication.
    """

    def __init__(self, owner, name: str, url: str, event_subscriptions: List[Dict] = None, channel_subscriptions: List[Dict] = None, reconnect_delay: int = 5):
        """
        Создаёт WebSocket-клиент.
        owner — компонент-владелец;
        name — имя клиента;
        url — адрес WebSocket.
        Можно задать event_subscriptions и channel_subscriptions, которые будут отосланы при подключении.
        """
        super().__init__(owner, name)
        self.url = url
        self.event_subscriptions = event_subscriptions or []
        self.channel_subscriptions = channel_subscriptions or []
        self.reconnect_delay = reconnect_delay
        self._stop = False
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        # Метрики
        self.messages_received = 0
        self.messages_sent = 0
        self.last_message_time = 0
        self.connection_start_time = 0
        self.log("__init__", f"extended WS client {name} ready for {url}")
    # ......................................................................................................................
    # 🔌 Жизненный цикл клиента
    # ......................................................................................................................
    def do_open(self) -> bool:
        """
        Запускает клиента в асинхронной задаче.
        Автоматически пытается подключиться к self.url.
        """
        asyncio.create_task(self._amain())
        self.log("do_open", f"connecting to {self.url}")
        return True

    def do_close(self) -> bool:
        """
        Останавливает клиента и закрывает сокет.
        """
        self._stop = True
        if self._websocket:
            asyncio.create_task(self._websocket.close())
        self.log("do_close", "stop requested")
        return True

    async def _amain(self):
        """
        Главный цикл клиента:
        - подключается к WebSocket (с автопереподключением);
        - отправляет подписки;
        - слушает входящие сообщения и прогоняет их через normalize();
        - уведомляет TApplication о статусах.
        """
        while not self._stop:
            try:
                async with websockets.connect(self.url, ping_interval=20) as ws:
                    self._websocket = ws
                    self.connection_start_time = time.time()
                    self._reconnect_attempts = 0
                    # Отправляем подписки при подключении
                    await self._send_subscriptions(ws)
                    # Уведомляем о подключении
                    await self._notify_connection_status("connected", f"Connection established to {self.url}")
                    self.log("_amain", f"✅ connected to {self.url}")
                    # Основной цикл приёма сообщений
                    async for msg in ws:
                        self.last_message_time = time.time()
                        self.messages_received += 1
                        await self._process_message(msg)
            except Exception as e:
                self.log("_amain", f"⚠️ connection error: {e}")
                await self._handle_reconnect_failure()
    # ......................................................................................................................
    # 📡 Подписки / статус соединения
    # ......................................................................................................................
    async def _send_subscriptions(self, ws):
        """
        Отправляет при подключении все event_subscriptions и channel_subscriptions.
        Это нужно биржам/сервисам, чтобы начать слать данные.
        """
        for subscription in self.event_subscriptions:
            await ws.send(json.dumps(subscription))
            self.messages_sent += 1
            self.log("_send_subscriptions", f"sent event subscription: {subscription}")
        for subscription in self.channel_subscriptions:
            await ws.send(json.dumps(subscription))
            self.messages_sent += 1
            self.log("_send_subscriptions", f"sent channel subscription: {subscription}")

    async def _notify_connection_status(self, status: str, message: str = ""):
        """
        Шлёт внутрь Tradition Core событие о статусе подключения клиента.
        Например: connected / reconnecting / error.
        """
        app = self._get_app()
        if app:
            status_event = create_status_event(source=self.Name, status=status, message=message or f"Connection {status} to {self.url}")
            app.handle_event(status_event)
    # ......................................................................................................................
    # 📨 Обработка входящих сообщений
    # ......................................................................................................................
    async def _process_message(self, msg: str):
        """
        Разбирает входящее сообщение WS:
        - прогоняет через normalize();
        - если это TEvent → handle_event();
        - если это TwsChannelData → handle_channel_data().
        """
        try:
            normalized = self.normalize(msg)
            app = self._get_app()
            if isinstance(normalized, TEvent) and app:
                app.handle_event(normalized)
            elif isinstance(normalized, TwsChannelData) and app:
                app.handle_channel_data(normalized)
        except Exception as e:
            self.log("_process_message", f"ERROR processing message: {e}")

    def normalize(self, raw_message: str) -> Any:
        """
        Преобразует сырое сообщение биржи/сервиса в унифицированную структуру:
        - TwsChannelData (тик/рыночные данные),
        - TEvent (системное событие, статус),
        - или create_status_event() как fallback.
        Переопределяй в потомках для специфики конкретной биржи.
        """
        try:
            data = json.loads(raw_message)
            # Примитивная эвристика: тикерные данные
            if "symbol" in data and "price" in data:
                return create_tick_channel_data(
                    source=self.Name,
                    symbol=data.get("symbol", "UNKNOWN"),
                    price=float(data.get("price", 0)),
                    volume=float(data.get("volume", 0))
                )
            # Общее сообщение, не тик
            return create_status_event(
                source=self.Name,
                status="message",
                message=f"Raw data: {data}"
            )
        except json.JSONDecodeError:
            # Не JSON — считаем просто текстовым сообщением
            return create_status_event(
                source=self.Name,
                status="raw_text",
                message=f"Text message: {raw_message}"
            )
        except Exception as e:
            self.log("normalize", f"ERROR normalizing message: {e}")
            return None

    async def _handle_reconnect_failure(self):
        """
        Логика переподключения.
        Вызывается при ошибке соединения.
        Ограничивает число попыток, уведомляет систему о статусе.
        """
        if not self._stop:
            self._reconnect_attempts += 1
            if self._reconnect_attempts > self._max_reconnect_attempts:
                self.log("_handle_reconnect_failure", "max reconnection attempts reached")
                await self._notify_connection_status("error", "Max reconnection attempts reached")
                return
            await self._notify_connection_status("reconnecting", f"Attempt {self._reconnect_attempts} in {self.reconnect_delay}s")
            self.log("_handle_reconnect_failure", f"reconnecting in {self.reconnect_delay}s (attempt {self._reconnect_attempts})")
            await asyncio.sleep(self.reconnect_delay)
    # ......................................................................................................................
    # 📤 Отправка данных наружу
    # ......................................................................................................................
    async def send(self, message: Dict | str):
        """
        Отправляет сообщение во внешний WebSocket.
        Сериализует dict -> JSON.
        """
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")
        if isinstance(message, dict):
            message = json.dumps(message)
        await self._websocket.send(message)
        self.messages_sent += 1

    def send_event(self, event: TEvent):
        """
        Асинхронно отправляет событие event.dict() во внешний WebSocket.
        """
        if self._websocket:
            asyncio.create_task(self.send(event.dict()))
    # ......................................................................................................................
    # 🧠 Вспомогательные / метрики
    # ......................................................................................................................
    def _get_app(self):
        """
        Возвращает корневое приложение (идём вверх по цепочке owner),
        если у него есть handle_event / handle_channel_data.
        """
        node = self
        # поднимаемся по owner до самого верха
        while hasattr(node, "owner") and node.owner is not None:
            node = node.owner

        # проверяем, похоже ли это на приложение
        if hasattr(node, "handle_event") or hasattr(node, "handle_channel_data"):
            return node
        return None

    def get_metrics(self) -> Dict[str, Any]:
        """
        Возвращает метрики работы клиента:
        - состояние подключения,
        - количество отправленных/полученных сообщений,
        - аптайм,
        - время с последнего сообщения.
        """
        uptime = time.time() - self.connection_start_time if self.connection_start_time > 0 else 0
        return {
            "connected": self._websocket is not None and not self._websocket.closed,
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "reconnect_attempts": self._reconnect_attempts,
            "uptime_seconds": uptime,
            "last_message_ago": time.time() - self.last_message_time if self.last_message_time > 0 else None
        }
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TBybitWebSocketClient — клиент Bybit
# ----------------------------------------------------------------------------------------------------------------------
class TBybitWebSocketClient(TWebSocketClientExtended):
    """
    WebSocket-клиент для Bybit.
    Подключается к публичному стриму Bybit и нормализует их сообщения.
    """

    def __init__(self, owner, name: str = "bybit", symbols: Optional[List[str]] = None):
        """
        Создаёт клиента Bybit с заранее известным URL.

        owner   — владелец (обычно TApplication)
        name    — имя компонента
        symbols — список тикеров, которые хотим слушать (["BTCUSDT", "ETHUSDT", ...])

        Мы подписываемся на канал Bybit v5:
            topic = "tickers.<SYMBOL>"
        """
        url = "wss://stream.bybit.com/v5/public/linear"

        # по умолчанию слушаем один инструмент, чтобы просто увидеть живые данные
        symbols = symbols or ["BTCUSDT"]
        self.symbols = symbols

        # Bybit v5: subscribe → {"op":"subscribe","args":["tickers.BTCUSDT", ...]}
        args = [f"tickers.{sym}" for sym in symbols]

        channel_subscriptions = [{
            "op": "subscribe",
            "args": args,
        }]

        super().__init__(
            owner=owner,
            name=name,
            url=url,
            event_subscriptions=None,
            channel_subscriptions=channel_subscriptions,
        )

        self.log("__init__", f"Bybit WS client initialized for: {', '.join(self.symbols)}")

    # ..................................................................................................................
    # 📨 Нормализация входящих сообщений Bybit
    # ..................................................................................................................
    def normalize(self, raw_message: str) -> Any:
        """
        Преобразует сообщение Bybit в общий формат Tradition Core.

        Если это тикер (topic = 'tickers.SYMBOL') — возвращает TwsChannelData.
        Всё остальное отдаём как статусное событие (TEvent).
        """
        try:
            data = json.loads(raw_message)

            topic = str(data.get("topic", "") or "")

            # 1) Тиковые данные: "tickers.BTCUSDT"
            if topic.startswith("tickers."):
                payload = data.get("data", {})

                # Bybit часто шлёт список
                if isinstance(payload, list):
                    payload = payload[0] if payload else {}

                symbol = payload.get("symbol") or topic.split(".", 1)[1]

                price = (
                        payload.get("lastPrice") or
                        payload.get("last_price") or
                        payload.get("price") or
                        0
                )
                volume = (
                        payload.get("volume24h") or
                        payload.get("volume_24h") or
                        payload.get("turnover24h") or
                        0
                )

                tick = create_tick_channel_data(
                    source=self.Name,
                    symbol=str(symbol),
                    price=float(price),
                    volume=float(volume),
                )

                # 👀 маячок для шага 2: каждая живая тика — в лог
                self.log(
                    "tick",
                    f"{symbol} price={float(price):.2f} volume={float(volume):.3f}"
                )

                return tick

            # 2) Всё, что не тикер → статусное сообщение
            return create_status_event(
                source=self.Name,
                status="bybit_message",
                message=f"Bybit data: {data}",
            )

        except Exception as e:
            self.log("normalize", f"ERROR normalizing Bybit message: {e}")
            return None
# ======================================================================================================================
# 📁🌄 bb_ws_extended.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 533 -> 416
# ======================================================================================================================