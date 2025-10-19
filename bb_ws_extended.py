# bb_ws_extended.py
# ALIAS: BB_WS_EXTENDED
# Created: 2025-10-18 07:45
# Расширенные WebSocket клиенты Tradition Core 2025 с поддержкой событий и каналов

import asyncio
import json
import random
import time
from typing import Optional, Dict, List, Any

import websockets

from bb_sys import TLiveComponent, TApplication
from bb_events import TEvent, TEventType, TwsDataChannel, TwsChannelData, create_status_event, create_tick_channel_data


# ==============================================================
#  TWebSocketClientExtended - расширенный клиент для системы событий
# ==============================================================

class TWebSocketClientExtended(TLiveComponent):
    """
    Расширенный WebSocket-клиент с поддержкой системы событий и каналов.
    Подключается к внешним биржам/сервисам, преобразует сообщения в события/каналы.
    """

    def __init__(self, owner, name: str, url: str,
                 event_subscriptions: List[Dict] = None,
                 channel_subscriptions: List[Dict] = None,
                 reconnect_delay: int = 5):
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

    def do_open(self) -> bool:
        """Запускает клиент в фоновой задаче"""
        asyncio.create_task(self._amain())
        self.log("do_open", f"connecting to {self.url}")
        return True

    def do_close(self) -> bool:
        """Останавливает клиент"""
        self._stop = True
        if self._websocket:
            asyncio.create_task(self._websocket.close())
        self.log("do_close", "stop requested")
        return True

    async def _amain(self):
        """Основной цикл подключения и приема сообщений"""
        while not self._stop:
            try:
                async with websockets.connect(self.url, ping_interval=20) as ws:
                    self._websocket = ws
                    self.connection_start_time = time.time()
                    self._reconnect_attempts = 0

                    # Отправляем подписки при подключении
                    await self._send_subscriptions(ws)

                    # Уведомляем о подключении
                    await self._notify_connection_status("connected")

                    self.log("_amain", f"✅ connected to {self.url}")

                    # Основной цикл приема сообщений
                    async for msg in ws:
                        self.last_message_time = time.time()
                        self.messages_received += 1

                        # Обрабатываем и нормализуем сообщение
                        await self._process_message(msg)

            except Exception as e:
                self.log("_amain", f"⚠️ connection error: {e}")
                await self._handle_reconnect_failure()

    async def _send_subscriptions(self, ws):
        """Отправляет подписки на события и каналы"""
        # Подписки на события
        for subscription in self.event_subscriptions:
            await ws.send(json.dumps(subscription))
            self.messages_sent += 1
            self.log("_send_subscriptions", f"sent event subscription: {subscription}")

        # Подписки на каналы
        for subscription in self.channel_subscriptions:
            await ws.send(json.dumps(subscription))
            self.messages_sent += 1
            self.log("_send_subscriptions", f"sent channel subscription: {subscription}")

    async def _notify_connection_status(self, status: str, message: str = ""):
        """Отправляет событие о статусе подключения"""
        app = self._get_app()
        if app:
            status_event = create_status_event(
                source=self.Name,
                status=status,
                message=message or f"Connection {status} to {self.url}"
            )
            app.handle_event(status_event)

    async def _process_message(self, msg: str):
        """Обрабатывает входящее сообщение и преобразует в события/каналы"""
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
        Преобразует сырое сообщение в TEvent или TwsChannelData.
        Переопределите в потомках для конкретных протоколов бирж.
        """
        try:
            data = json.loads(raw_message)

            # Базовая нормализация для тиковых данных
            if "symbol" in data and "price" in data:
                return create_tick_channel_data(
                    source=self.Name,
                    symbol=data.get("symbol", "UNKNOWN"),
                    price=float(data.get("price", 0)),
                    volume=float(data.get("volume", 0))
                )
            else:
                # Общее сообщение
                return create_status_event(
                    source=self.Name,
                    status="message",
                    message=f"Raw data: {data}"
                )

        except json.JSONDecodeError:
            # Не JSON - создаем событие с текстом
            return create_status_event(
                source=self.Name,
                status="raw_text",
                message=f"Text message: {raw_message}"
            )
        except Exception as e:
            self.log("normalize", f"ERROR normalizing message: {e}")
            return None

    async def _handle_reconnect_failure(self):
        """Обрабатывает неудачную попытку подключения"""
        if not self._stop:
            self._reconnect_attempts += 1

            if self._reconnect_attempts > self._max_reconnect_attempts:
                self.log("_handle_reconnect_failure", "max reconnection attempts reached")
                await self._notify_connection_status("error", "Max reconnection attempts reached")
                return

            # Уведомляем о переподключении
            await self._notify_connection_status("reconnecting",
                                                 f"Attempt {self._reconnect_attempts} in {self.reconnect_delay}s")

            self.log("_handle_reconnect_failure",
                     f"reconnecting in {self.reconnect_delay}s (attempt {self._reconnect_attempts})")

            await asyncio.sleep(self.reconnect_delay)

    async def send(self, message: Dict | str):
        """Отправляет сообщение через WebSocket"""
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")

        if isinstance(message, dict):
            message = json.dumps(message)

        await self._websocket.send(message)
        self.messages_sent += 1

    def send_event(self, event: TEvent):
        """Отправляет событие (синхронная обертка)"""
        if self._websocket:
            asyncio.create_task(self.send(event.dict()))

    def _get_app(self):
        """Вспомогательный метод для получения приложения"""
        try:
            return TApplication.app()
        except:
            return None

    def get_metrics(self) -> Dict[str, Any]:
        """Возвращает метрики клиента"""
        uptime = time.time() - self.connection_start_time if self.connection_start_time > 0 else 0

        return {
            "connected": self._websocket is not None and not self._websocket.closed,
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "reconnect_attempts": self._reconnect_attempts,
            "uptime_seconds": uptime,
            "last_message_ago": time.time() - self.last_message_time if self.last_message_time > 0 else None
        }


# ==============================================================
#  MockWebSocketClient - эмулятор биржи для тестирования
# ==============================================================

class MockWebSocketClient(TWebSocketClientExtended):
    """Эмулятор биржи для тестирования системы событий и каналов"""

    def __init__(self, owner, name: str, symbol: str = "BTCUSDT", interval: float = 1.0):
        # Используем фиктивный URL
        super().__init__(owner, name, f"ws://mock/{name}")

        self.symbol = symbol
        self.interval = interval
        self._price = 50000.0
        self._task: Optional[asyncio.Task] = None

        self.log("__init__", f"mock client for {symbol}, interval {interval}s")

    async def _amain(self):
        """Эмуляция подключения и генерации данных"""
        self.connection_start_time = time.time()

        # Эмулируем успешное подключение
        await self._notify_connection_status("connected",
                                             f"Mock exchange connected for {self.symbol}")

        # Запускаем генерацию данных
        self._task = asyncio.create_task(self._generate_data())

        self.log("_amain", "✅ mock exchange started")

        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _generate_data(self):
        """Генерирует тестовые тиковые данные"""
        while not self._stop:
            # Имитация движения цены
            change = random.uniform(-100, 100)
            self._price = max(1.0, self._price + change)
            volume = random.uniform(1, 100)

            # Создаем данные канала
            tick_data = create_tick_channel_data(
                source=self.Name,
                symbol=self.symbol,
                price=self._price,
                volume=volume
            )

            # Отправляем через приложение
            app = self._get_app()
            if app:
                app.handle_channel_data(tick_data)

            await asyncio.sleep(self.interval)

    def do_close(self) -> bool:
        """Останавливает генерацию данных"""
        self._stop = True
        if self._task:
            self._task.cancel()
        return super().do_close()


# ==============================================================
#  Специализированные клиенты для конкретных бирж
# ==============================================================

class TBinanceWebSocketClient(TWebSocketClientExtended):
    """WebSocket клиент для Binance"""

    def __init__(self, owner, name: str = "binance"):
        url = "wss://stream.binance.com:9443/ws"
        super().__init__(owner, name, url)

        self.log("__init__", "Binance WS client initialized")

    def normalize(self, raw_message: str) -> Any:
        """Специфичная нормализация для протокола Binance"""
        try:
            data = json.loads(raw_message)

            # Обработка тиковых данных Binance
            if "e" in data and data["e"] == "24hrTicker":
                return create_tick_channel_data(
                    source=self.Name,
                    symbol=data.get("s", ""),
                    price=float(data.get("c", 0)),
                    volume=float(data.get("v", 0))
                )
            # Обработка свечных данных Binance
            elif "e" in data and data["e"] == "kline":
                kline = data.get("k", {})
                return create_tick_channel_data(
                    source=self.Name,
                    symbol=data.get("s", ""),
                    price=float(kline.get("c", 0)),
                    volume=float(kline.get("v", 0))
                )
            else:
                return create_status_event(
                    source=self.Name,
                    status="binance_message",
                    message=f"Binance data: {data}"
                )

        except Exception as e:
            self.log("normalize", f"ERROR normalizing Binance message: {e}")
            return None


class TBybitWebSocketClient(TWebSocketClientExtended):
    """WebSocket клиент для Bybit"""

    def __init__(self, owner, name: str = "bybit"):
        url = "wss://stream.bybit.com/v5/public/linear"
        super().__init__(owner, name, url)

        self.log("__init__", "Bybit WS client initialized")

    def normalize(self, raw_message: str) -> Any:
        """Специфичная нормализация для протокола Bybit"""
        try:
            data = json.loads(raw_message)

            # Обработка тиковых данных Bybit
            if "topic" in data and "ticker" in data["topic"]:
                tick_data = data.get("data", {})
                return create_tick_channel_data(
                    source=self.Name,
                    symbol=tick_data.get("symbol", ""),
                    price=float(tick_data.get("last_price", 0)),
                    volume=float(tick_data.get("volume_24h", 0))
                )
            else:
                return create_status_event(
                    source=self.Name,
                    status="bybit_message",
                    message=f"Bybit data: {data}"
                )

        except Exception as e:
            self.log("normalize", f"ERROR normalizing Bybit message: {e}")
            return None


# Экспорты
__all__ = [
    'TWebSocketClientExtended',
    'MockWebSocketClient',
    'TBinanceWebSocketClient',
    'TBybitWebSocketClient'
]