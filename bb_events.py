# ======================================================================================================================
# 📁 file        : bb_events.py — Схема событий и система подписок Tradition Core 2025
# 🕒 created     : 18.10.2025 07:26
# 🎉 contains    : TEventType/TEvent, TSubscription/TSubscriptionIndex, TwsDataChannel/TwsChannelData и фабрики событий
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

# 💎 ... CONFIG / CONSTS ...
# ALIAS: BB_EVENTS
__all__ = ["TEventType", "TEvent", "TSubscription", "TSubscriptionIndex", "TwsDataChannel", "TwsChannelSubscription",
           "TwsChannelData", "TwsChannelSubscriptionIndex", "create_tick_event", "create_status_event",
           "create_ui_command", "create_tick_channel_data", "create_candle_channel_data"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TEventType — Типы событий Tradition Core
# ----------------------------------------------------------------------------------------------------------------------
class TEventType(str, Enum):
    TICK = "tick"
    STATUS = "status"
    LOG = "log"
    COMMAND = "command"
    UI = "ui"
    SYSTEM = "system"
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TEvent — Унифицированное событие шины
# ----------------------------------------------------------------------------------------------------------------------
class TEvent(BaseModel):
    type: TEventType
    source: str
    topic: str
    timestamp: float
    payload: Dict[str, Any]

    @classmethod
    def create(
        cls,
        event_type: TEventType,
        source: str,
        topic: str,
        payload: Dict[str, Any],
    ) -> "TEvent":
        return cls(
            type=event_type,
            source=source,
            topic=topic,
            timestamp=time.time(),
            payload=payload,
        )

    def to_json(self) -> str:
        return self.json()

    @classmethod
    def from_json(cls, json_str: str) -> Optional["TEvent"]:
        try:
            data = json.loads(json_str)
            return cls(**data)
        except Exception:
            return None
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TSubscription — Подписка и фильтрация событий
# ----------------------------------------------------------------------------------------------------------------------
@dataclass
class TSubscription:
    target_id: str  # id компонента-получателя
    topic: str  # тема для подписки
    filters: Dict[str, Any]  # условия фильтрации

    def matches(self, event: TEvent) -> bool:
        """Проверяет, соответствует ли событие подписке."""
        if self.topic != event.topic:
            return False

        for key, expected_value in self.filters.items():
            actual_value = event.payload.get(key)
            if actual_value != expected_value:
                return False

        return True
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TwsDataChannel — Каналы WebSocket-данных (непрерывные потоки)
# ----------------------------------------------------------------------------------------------------------------------
class TwsDataChannel(str, Enum):
    MARKET_TICKS = "market.ticks"  # Поток тиков
    MARKET_CANDLES_1S = "market.candles.1s"  # Секундные свечи
    MARKET_CANDLES_1M = "market.candles.1m"  # Минутные свечи
    MARKET_DEPTH = "market.depth"  # Стакан заявок
    TRADES = "market.trades"  # Сделки
    SYSTEM_METRICS = "system.metrics"  # Метрики системы
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TwsChannelSubscription — Подписка на WebSocket-канал данных
# ----------------------------------------------------------------------------------------------------------------------
@dataclass
class TwsChannelSubscription:
    """Подписка на непрерывный канал WebSocket данных."""
    target_id: str  # id компонента-получателя
    channel: TwsDataChannel  # канал данных
    symbols: List[str]  # список инструментов
    filters: Dict[str, Any]  # дополнительные фильтры

    def matches(self, data_point: "TwsChannelData") -> bool:
        """Проверяет, соответствует ли точка данных подписке."""
        if self.channel != data_point.channel:
            return False

        if self.symbols and data_point.symbol not in self.symbols:
            return False

        for key, expected_value in self.filters.items():
            actual_value = data_point.data.get(key)
            if actual_value != expected_value:
                return False

        return True
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TwsChannelData — Точка данных в непрерывном WebSocket-потоке
# ----------------------------------------------------------------------------------------------------------------------
class TwsChannelData(BaseModel):
    """Точка данных в непрерывном потоке WebSocket."""
    channel: TwsDataChannel
    symbol: str
    timestamp: float
    sequence: int = 0  # порядковый номер в потоке
    data: Dict[str, Any]

    @classmethod
    def create(
        cls,
        channel: TwsDataChannel,
        symbol: str,
        data: Dict[str, Any],
        sequence: int = 0,
    ) -> "TwsChannelData":
        return cls(
            channel=channel,
            symbol=symbol,
            timestamp=time.time(),
            sequence=sequence,
            data=data,
        )
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TSubscriptionIndex — Индекс подписок по событиям
# ----------------------------------------------------------------------------------------------------------------------
class TSubscriptionIndex:
    def __init__(self):
        self._subscriptions: Dict[str, List[TSubscription]] = {}
        self._all_subscriptions: List[TSubscription] = []

    def add(self, subscription: TSubscription) -> None:
        """Добавляет подписку в индекс."""
        topic = subscription.topic

        if topic not in self._subscriptions:
            self._subscriptions[topic] = []

        self._subscriptions[topic].append(subscription)
        self._all_subscriptions.append(subscription)

    def find(self, event: TEvent) -> List[TSubscription]:
        """Находит все подписки, соответствующие событию."""
        matching: List[TSubscription] = []
        topic_subs = self._subscriptions.get(event.topic, [])
        for sub in topic_subs:
            if sub.matches(event):
                matching.append(sub)
        return matching

    def remove_by_target(self, target_id: str) -> None:
        """Удаляет все подписки для указанного target_id."""
        for topic in list(self._subscriptions.keys()):
            self._subscriptions[topic] = [
                sub for sub in self._subscriptions[topic]
                if sub.target_id != target_id
            ]
            if not self._subscriptions[topic]:
                del self._subscriptions[topic]

        self._all_subscriptions = [
            sub for sub in self._all_subscriptions
            if sub.target_id != target_id
        ]

    def count(self) -> int:
        return len(self._all_subscriptions)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TwsChannelSubscriptionIndex — Индекс подписок на каналы WebSocket
# ----------------------------------------------------------------------------------------------------------------------
class TwsChannelSubscriptionIndex:
    def __init__(self):
        self._channel_subscriptions: Dict[TwsDataChannel, List[TwsChannelSubscription]] = {}
        self._all_subscriptions: List[TwsChannelSubscription] = []

    def add(self, subscription: TwsChannelSubscription) -> None:
        """Добавляет подписку на канал."""
        channel = subscription.channel

        if channel not in self._channel_subscriptions:
            self._channel_subscriptions[channel] = []

        self._channel_subscriptions[channel].append(subscription)
        self._all_subscriptions.append(subscription)

    def find(self, data_point: TwsChannelData) -> List[TwsChannelSubscription]:
        """Находит подписки, соответствующие точке данных."""
        matching: List[TwsChannelSubscription] = []
        channel_subs = self._channel_subscriptions.get(data_point.channel, [])
        for sub in channel_subs:
            if sub.matches(data_point):
                matching.append(sub)
        return matching

    def remove_by_target(self, target_id: str) -> None:
        """Удаляет все подписки канала для указанного target_id."""
        for channel in list(self._channel_subscriptions.keys()):
            self._channel_subscriptions[channel] = [
                sub for sub in self._channel_subscriptions[channel]
                if sub.target_id != target_id
            ]
            if not self._channel_subscriptions[channel]:
                del self._channel_subscriptions[channel]

        self._all_subscriptions = [
            sub for sub in self._all_subscriptions
            if sub.target_id != target_id
        ]

    def count(self) -> int:
        return len(self._all_subscriptions)


# Вспомогательные функции для создания данных
def create_tick_event(source: str, symbol: str, price: float, volume: float = 0) -> TEvent:
    return TEvent.create(
        event_type=TEventType.TICK,
        source=source,
        topic="market.ticks",
        payload={
            "exchange": source,
            "symbol": symbol,
            "price": price,
            "volume": volume,
        },
    )

def create_status_event(source: str, status: str, message: str = "") -> TEvent:
    return TEvent.create(
        event_type=TEventType.STATUS,
        source=source,
        topic="system.status",
        payload={
            "component": source,
            "status": status,
            "message": message,
            "ts": time.time(),
        },
    )

def create_ui_command(source: str, target: str, action: str, data: Dict | None = None) -> TEvent:
    return TEvent.create(
        event_type=TEventType.COMMAND,
        source=source,
        topic="ui.command",
        payload={
            "target": target,
            "action": action,
            "data": data or {},
            "user": source,
        },
    )

def create_tick_channel_data(source: str, symbol: str, price: float, volume: float = 0) -> TwsChannelData:
    return TwsChannelData.create(
        channel=TwsDataChannel.MARKET_TICKS,
        symbol=symbol,
        data={
            "exchange": source,
            "price": price,
            "volume": volume,
            "bid": price * 0.999,
            "ask": price * 1.001,
        },
    )

def create_candle_channel_data(
    symbol: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    interval: str = "1s",
) -> TwsChannelData:
    channel = TwsDataChannel.MARKET_CANDLES_1S
    if interval == "1m":
        channel = TwsDataChannel.MARKET_CANDLES_1M

    return TwsChannelData.create(
        channel=channel,
        symbol=symbol,
        data={
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "interval": interval,
        },
    )
# ======================================================================================================================
# 📁🌄 bb_events.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 316
# ======================================================================================================================
