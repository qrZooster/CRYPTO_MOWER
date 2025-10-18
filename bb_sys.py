# bb_sys.py
# ALIAS: BB_SYS
# Created: 2025-10-11 12:23
# Updated: 2025-10-17 07:20 — Tradition Core 2025:
#  - Архитектурные поля: PascalCase (Owner/Components/Modules/Pages/Name/Parent/Controls/Forms)
#  - id() — всегда с маленькой (родословная)
#  - Глобальный реестр компонентов (feature-flag)
#  - Инварианты дерева и согласованности реестра
#  - Совместимость со старыми именами через @property

import os
import re
import datetime as dt
import traceback
import threading
import asyncio
import json
import logging
import subprocess

from typing import MutableMapping
from pathlib import Path
from datetime import datetime
from typing import MutableMapping, List, Dict, Any, Optional

from bb_logger import LoggableComponent, TLogRouterMixin, LOG_ROUTER

# В начало bb_sys.py добавляем импорты
from bb_events import (
    TEvent, TEventType, TSubscription, TSubscriptionIndex,
    TwsDataChannel, TwsChannelSubscription, TwsChannelData, TwsChannelSubscriptionIndex,
    create_tick_event, create_status_event, create_ui_command,
    create_tick_channel_data, create_candle_channel_data
)


# --- Переназначаемая ENV-мапа ---
_ENV: MutableMapping[str, str] = os.environ

def set_env_mapping(mapping: MutableMapping[str, str] | None) -> None:
    global _ENV
    _ENV = os.environ if mapping is None else mapping

def get_env_mapping() -> MutableMapping[str, str]:
    return _ENV

def _s(v):
    return '' if v is None else str(v)

def _set_key(name: str, value: str) -> bool:
    if not name:
        return False
    _ENV[name] = '' if value is None else _s(value)
    return True

def _key(name: str | None, default: str = '') -> str | None:
    if not name:
        return None
    v = _ENV.get(name)
    if v is not None and v != '':
        return v
    _ENV[name] = str(default)
    return str(default)

def explode(delimiter: str, src: str) -> list[str]:
    if not src:
        return []
    parts = [x.strip() for x in src.replace(";", delimiter).replace(",", delimiter).split(delimiter)]
    return [x for x in parts if x]


# --- Конфигурация / константы ---
BYBIT_API_KEY = _key('BYBIT_API_KEY', '')
BYBIT_API_SECRET = _key('BYBIT_API_SECRET', '')
BYBIT_MODE = _key('BYBIT_MODE', 'prod')  # prod | test

if BYBIT_MODE == 'test':
    BYBIT_WS_PUBLIC_LINEAR = 'wss://stream-testnet.bybit.com/v5/public/linear'
    BYBIT_REST = 'https://api-testnet.bybit.com'
else:
    BYBIT_WS_PUBLIC_LINEAR = 'wss://stream.bybit.com/v5/public/linear'
    BYBIT_REST = 'https://api.bybit.com'

MSK = dt.timezone(dt.timedelta(hours=3), name='MSK')

DB_CFG = {
    'host': _key('DB_HOST', '127.0.0.1'),
    'port': int(_key('DB_PORT', '3307')),
    'user': _key('DB_USER', 'u267510'),
    'password': _key('DB_PASSWORD', '_n2FeRUP.6'),
    'database': _key('DB_NAME', 'u267510_tg'),
    'autocommit': True,
    'charset': _key('DB_CHARSET', 'utf8mb4'),
}

ANN_URL = 'https://api.bybit.com/v5/announcements/index'
ANN_LOCALE = 'en-US'

USDT_PAIR_RE = re.compile(r'([A-Z0-9]{1,20})USDT')
USDT_SLASH_RE = re.compile(r'([A-Z0-9]{1,20})/USDT')

BYBIT, PERP, USDT, BUY, SELL = 'BYBIT', 'PERP', 'USDT', 'BUY', 'SELL'
TRACEBACK_ENABLED = True
BB_ENABLE_GLOBAL_REGISTRY = int(_key('BB_ENABLE_GLOBAL_REGISTRY', '0') or '0')  # feature-flag

__all__ = [
    'TObject', 'TApplication', 'TComponent', 'TLiveComponent',
    'TSysComponent', 'TModule',
    'set_env_mapping', 'get_current_app', 'set_current_app',
    '_s', '_set_key', '_key', 'explode',
    'DB_CFG', 'BYBIT_API_KEY', 'BYBIT_API_SECRET',
    'BYBIT_MODE', 'BYBIT_WS_PUBLIC_LINEAR', 'BYBIT_REST',
    'MSK', 'ANN_URL', 'ANN_LOCALE',
    'BYBIT', 'PERP', 'USDT', 'BUY', 'SELL',
    'USDT_PAIR_RE', 'USDT_SLASH_RE'
]
# ---------------------------------------------------------------------
# TObject — базовый класс
# ---------------------------------------------------------------------
class TObject:
    def __init__(self, name: str = None):
        cname = self.__class__.__name__
        if cname[:1].lower() == 't':
            cname = cname[1:]
        self.Name = name if name else cname
        # В TObject нет Owner — он появляется в TComponent

    # --- Совместимость старого доступа name ---
    @property
    def name(self) -> str:
        return self.Name
    @name.setter
    def name(self, v: str):
        self.Name = v

    def log(self, function: str, *parts, window: int = 1):
        project_symbol = _key('PROJECT_SYMBOL', 'BB')
        project_version = _key('PROJECT_VERSION', '3')
        now = datetime.now().strftime('%H:%M:%S')
        msg = ' '.join(str(p) for p in parts)
        text = f'[{project_symbol}_{project_version}][{now}][{self.Name}]{function}(): {msg}'
        try:
            if LOG_ROUTER:
                LOG_ROUTER.write(text, window=window)
            else:
                print(text, flush=True)
        except Exception:
            print(text, flush=True)

    def fail(self, function: str, msg: str, exc_type: type = Exception):
        from bb_db import key_int
        try:
            trace_limit = key_int("TRACE_LIMIT", 12)
        except Exception:
            trace_limit = 12

        stack = "".join(traceback.format_stack(limit=trace_limit))
        cls_name = self.__class__.__name__
        owner_name = getattr(getattr(self, "Owner", None), "Name", None)
        owner_part = f"\n📦 owner: {owner_name}" if owner_name else ""
        text = (f"\n💥 {cls_name}.{function}() FAILED{owner_part}\n⚙️ message: {msg}"
                f"\n\n🧩 Traceback (most recent calls):\n{stack}")
        try:
            self.log("fail", msg)
        except Exception:
            print(f"[{cls_name}] fail(): {msg}")
        try:
            os.makedirs("log", exist_ok=True)
            with open("log/fail.log", "a", encoding="utf-8") as f:
                f.write(f"{text}\n{'-'*80}\n")
        except Exception:
            pass
        print(text, flush=True)
        raise exc_type(f"{cls_name}.{function}(): {msg}")
# ---------------------------------------------------------------------
# Потоковый контекст приложения
# ---------------------------------------------------------------------
_app_context = threading.local()

def set_current_app(app: "TApplication"):
    _app_context.current = app

def get_current_app() -> "TApplication | None":
    return getattr(_app_context, "current", None)
# ---------------------------------------------------------------------
# TApplication — управляющий объект
# ---------------------------------------------------------------------
class TApplication(TObject, TLogRouterMixin):
    _instance = None

    def __init__(self):
        if TApplication._instance is not None:
            raise RuntimeError("TApplication is a singleton. Use Application() instead.")
        super().__init__('Application')
        set_current_app(self)

        # Системные объекты
        self.Session = None
        self.Database = None
        self.Config = None
        self.Schema = None

        # Архитектурные контейнеры
        self.Components: dict[str, "TComponent"] = {}  # верхнеуровневые компоненты без Owner
        self.Modules: dict[str, "TModule"] = {}
        self.Pages: dict[str, Path] = {}
        self.ActiveModule: "TModule | None" = None

        # Файловые пути / статус
        self.root_dir = Path(__file__).parent
        self.public_dir = self.root_dir / "public"
        self.public_dir.mkdir(exist_ok=True)
        self.start_time = datetime.now()

        # Глобальный реестр компонентов (id -> instance)
        self._all_components: dict[str, "TComponent"] = {}

        self._init_log_center()
        self.log('__init__', 'application created')
        # +++ СИСТЕМА СОБЫТИЙ И КАНАЛОВ +++
        # Подписки на события
        self._subscriptions = TSubscriptionIndex()
        self._event_buffer: List[TEvent] = []
        self._max_event_buffer_size = 10000

        # Подписки на WebSocket каналы
        self._channel_subscriptions = TwsChannelSubscriptionIndex()
        self._channel_sequences: Dict[TwsDataChannel, int] = {}
        self._channel_buffer: Dict[TwsDataChannel, List[TwsChannelData]] = {}
        self._max_channel_buffer_size = 1000

        # WebSocket клиенты
        self._ws_clients: Dict[str, "TWebSocketClient"] = {}

        # Метрики
        self._events_processed = 0
        self._events_dropped = 0
        self._channel_data_processed = 0
        self._channel_data_dropped = 0
        # --- КОНЕЦ ДОБАВЛЕНИЯ ---

        self._init_log_center()
        self.log('__init__', 'application created')
        TApplication._instance = self

    # --- Совместимость: modules/pages/components ---
    @property
    def modules(self): return self.Modules
    @modules.setter
    def modules(self, v): self.Modules = v
    @property
    def pages(self): return self.Pages
    @pages.setter
    def pages(self, v): self.Pages = v
    @property
    def components(self): return self.Components
    @components.setter
    def components(self, v): self.Components = v
    @property
    def active_module(self): return self.ActiveModule
    @active_module.setter
    def active_module(self, v): self.ActiveModule = v

    # --- Singleton access ---
    @staticmethod
    def app() -> "TApplication":
        if TApplication._instance is None:
            TApplication()
        return TApplication._instance

    # --- Реестр компонентов (feature-flagged) ---
    def _registry_enabled(self) -> bool:
        return bool(BB_ENABLE_GLOBAL_REGISTRY)

    def register_global(self, comp: "TComponent") -> None:
        if not self._registry_enabled():
            return
        cid = comp.id()
        if cid in self._all_components and self._all_components[cid] is not comp:
            comp.fail('register_global', f'duplicate id(): {cid}', ValueError)
        self._all_components[cid] = comp
        self.log('register_global', f'{cid}')

    def unregister_global(self, comp: "TComponent") -> None:
        if not self._registry_enabled():
            return
        cid = comp.id()
        if self._all_components.get(cid) is comp:
            del self._all_components[cid]
            self.log('unregister_global', f'{cid}')

    def find_by_id(self, cid: str) -> "TComponent | None":
        if not self._registry_enabled():
            return None
        return self._all_components.get(cid)

    def iter_components(self, root: "TComponent | None" = None):
        stack = [root] if root else list(self.Components.values())
        while stack:
            node = stack.pop()
            if not node:
                continue
            yield node
            for child in node.Components.values():
                stack.append(child)

    def check_invariants(self) -> list[str]:
        errors: list[str] = []
        seen_ids: set[str] = set()
        for comp in self.iter_components():
            # 1) уникальность Name в Owner
            if comp.Owner:
                siblings = comp.Owner.Components
                if sum(1 for n, c in siblings.items() if n == comp.Name and c is comp) != 1:
                    errors.append(f"[name-unique] {comp.Owner.Name} -> '{comp.Name}' not unique")
            # 2) корректность id()
            try:
                cid = comp.id()
            except Exception as e:
                errors.append(f"[id()] error in {comp.Name}: {e}")
                continue
            if cid in seen_ids:
                errors.append(f"[id-collision] {cid}")
            else:
                seen_ids.add(cid)
            # 3) согласованность с реестром
            if self._registry_enabled():
                if self._all_components.get(cid) is not comp:
                    errors.append(f"[registry-miss] {cid}")
        return errors

    # --- Прочее стандартное API ---
    def register_module(self, mod: "TModule"):
        self.Modules[mod.tag] = mod
        self.ActiveModule = mod
        self.log('register_module', f'{mod.tag} registered')

    def unregister_module(self, mod: "TModule"):
        if mod.tag in self.Modules:
            del self.Modules[mod.tag]
            self.log('unregister_module', f'{mod.tag} unregistered')
        if self.ActiveModule == mod:
            self.ActiveModule = None

    def close(self):
        self.log('close', 'closing all modules...')
        for mod in list(self.Modules.values()):
            try:
                mod.stop()
            except Exception as e:
                self.log('close', f'error stopping {mod.tag}: {e}')
        self.Modules.clear()
        self.ActiveModule = None
        print("🎬 The End — Application closed gracefully.")

    def __repr__(self):
        return f"<TApplication {self.project_tag}, modules={len(self.Modules)}>"

    def _init_log_center(self):
        try:
            from bb_logger import init_log_router, LOG_ROUTER
            init_log_router()
            if LOG_ROUTER:
                self.log("Application", "log center initialized", window=1)
            else:
                print("🪶 [Fallback] Plain console logger active", flush=True)
        except Exception as e:
            print(f"⚠️ [LoggerInit] failed: {e}", flush=True)

    # --- Свойства проекта ---
    @property
    def project(self) -> str:
        return _key('PROJECT', 'CRYPTO_MOWER')
    @property
    def project_version(self) -> str:
        return _key('PROJECT_VERSION', '3')
    @property
    def project_tag(self) -> str:
        return f'{self.project}{self.project_version}'

    # --- Точка регистрации верхнеуровневых компонентов ---
    def register(self, comp: "TComponent"):
        name = getattr(comp, "Name", comp.__class__.__name__)
        if name in self.Components and self.Components[name] is not comp:
            # Жёсткая защита: не допускаем дубликаты на верхнем уровне
            comp.fail('register', f"Duplicate top-level component Name: {name}", ValueError)
        self.Components[name] = comp
        self.log("register", f"component {name}")
        try:
            self.register_global(comp)
        except Exception as e:
            self.log("register", f"⚠️ registry skipped: {e}")
        return True

    # --- Визуальное (базовый стиль, оставлено как было) ---
    def base_style(self) -> str:
        return """
        body {font-family:monospace;background:#0f1117;color:#00ff88;margin:0;padding:10px;}
        h1 {color:#00ff88;}
        #log {white-space:pre-wrap;background:#1a1d29;padding:10px;border-radius:8px;overflow-y:auto;height:80vh;}
        button {background:#1a1d29;color:#00ff88;border:1px solid #00ff88;border-radius:6px;padding:6px 12px;cursor:pointer;}
        button:hover {background:#00ff8840;}
        """

    # --- Совместимость: старые вспомогательные методы ---
    def echo(self, msg: str):
        print(msg)

    # -------------------------------------------------------------
    # Page Auto-generation Interface (для переопределения потомками)
    # -------------------------------------------------------------
    def ensure_page_auto(self, force: bool = False):
        """
        Универсальный механизм автогенерации страниц.
        Делегирует реализацию потомкам через generate_page() и generate_name().
        Перезаписывает файл, если контент изменился.
        """
        try:
            content = self.generate_page()
            name = self.generate_name()

            if not content:
                self.log("ensure_page_auto", f"⚠️ no content generated for {name}")
                return None

            path = self.root_dir / name
            write_needed = force or not path.exists()

            # проверяем, изменился ли контент
            if not write_needed:
                try:
                    existing = path.read_text(encoding="utf-8")
                    if existing != content:
                        write_needed = True
                except Exception:
                    write_needed = True

            if write_needed:
                path.write_text(content, encoding="utf-8")
                self.log("ensure_page_auto", f"✅ updated {path}")
            else:
                self.log("ensure_page_auto", f"ℹ️ no changes in {path}")

            self.pages[name] = path
            return path

        except Exception as e:
            self.log("ensure_page_auto", f"❌ failed: {e}")
            return None

    def generate_page(self) -> str:
        """
        Интерфейс — потомок должен вернуть HTML-содержимое.
        """
        self.log("generate_page", "no implementation in base class")
        return ""

    def generate_name(self) -> str:
        """
        Интерфейс — потомок должен вернуть имя HTML-файла.
        По умолчанию генерирует из имени .py-файла класса.
        """
        try:
            import inspect
            path = Path(inspect.getfile(self.__class__))
            return f"{path.stem}.html"
        except Exception:
            return f"{self.__class__.__name__}.html"

    # -------------------------------------------------------------
    # Compatibility
    # ------------------------------------------------------------

    def register(self, comp):
        name = getattr(comp, "name", comp.__class__.__name__)
        self.log("register", f"component {name} (stub)")
        return True

    ##00e0ff
    def base_style(self) -> str:
        """Глобальный CSS для всех страниц приложения."""
        return """
        body {
          font-family: monospace;
          background: #0f1117;
          color: #00ff88;
          margin: 0;
          padding: 10px;
        }
        h1 { color: #00ff88; } 
        #log {
          white-space: pre-wrap;
          background: #1a1d29;
          padding: 10px;
          border-radius: 8px;
          overflow-y: auto;
          height: 80vh;
        }
        button {
          background:#1a1d29;
          color:#00ff88;
          border:1px solid #00ff88;
          border-radius:6px;
          padding:6px 12px;
          cursor:pointer;
          font-family:monospace;
        }
        button:hover {
          background:#00ff8840;
        }
        """

    # +++ МЕТОДЫ ДЛЯ РАБОТЫ С СОБЫТИЯМИ +++

    def subscribe(self, target_id: str, topic: str, **filters) -> bool:
        """Подписывает компонент на события по теме с фильтрами"""
        try:
            subscription = TSubscription(
                target_id=target_id,
                topic=topic,
                filters=filters
            )
            self._subscriptions.add(subscription)
            self.log('subscribe', f'{target_id} -> {topic} {filters}')
            return True
        except Exception as e:
            self.log('subscribe', f'ERROR: {e}')
            return False

    def unsubscribe(self, target_id: str, topic: str = None) -> bool:
        """Отписывает компонент от событий"""
        try:
            if topic:
                # Удаляем подписки только для указанной темы
                subs_to_remove = [
                    sub for sub in self._subscriptions._all_subscriptions
                    if sub.target_id == target_id and sub.topic == topic
                ]
                for sub in subs_to_remove:
                    self._subscriptions._all_subscriptions.remove(sub)
                    self._subscriptions._subscriptions[topic].remove(sub)
            else:
                # Удаляем все подписки для target_id
                self._subscriptions.remove_by_target(target_id)

            self.log('unsubscribe', f'{target_id} from {topic or "all topics"}')
            return True
        except Exception as e:
            self.log('unsubscribe', f'ERROR: {e}')
            return False

    def handle_event(self, event: TEvent) -> bool:
        """Обрабатывает событие - находит подписчиков и уведомляет их"""
        try:
            # Добавляем в буфер
            self._event_buffer.append(event)
            if len(self._event_buffer) > self._max_event_buffer_size:
                self._event_buffer.pop(0)
                self._events_dropped += 1

            # Находим подписчиков
            matching_subs = self._subscriptions.find(event)
            if not matching_subs:
                return False

            # Уведомляем подписчиков
            notified_count = 0
            for sub in matching_subs:
                comp = self.find_by_id(sub.target_id)
                if comp and hasattr(comp, 'on_event'):
                    try:
                        comp.on_event(event)
                        notified_count += 1
                    except Exception as e:
                        self.log('handle_event', f'ERROR in {comp.Name}.on_event(): {e}')

            self._events_processed += 1
            if self._events_processed % 1000 == 0:
                self.log('handle_event',
                         f'processed {self._events_processed} events, dropped {self._events_dropped}')

            return notified_count > 0

        except Exception as e:
            self.log('handle_event', f'CRITICAL ERROR: {e}')
            return False

    # +++ МЕТОДЫ ДЛЯ РАБОТЫ С WS КАНАЛАМИ +++

    def subscribe_channel(self, target_id: str, channel: TwsDataChannel,
                          symbols: List[str] = None, **filters) -> bool:
        """Подписывает компонент на WebSocket канал данных"""
        try:
            subscription = TwsChannelSubscription(
                target_id=target_id,
                channel=channel,
                symbols=symbols or [],
                filters=filters
            )
            self._channel_subscriptions.add(subscription)
            self.log('subscribe_channel', f'{target_id} -> {channel.value} symbols={symbols}')
            return True
        except Exception as e:
            self.log('subscribe_channel', f'ERROR: {e}')
            return False

    def unsubscribe_channel(self, target_id: str, channel: TwsDataChannel = None) -> bool:
        """Отписывает от WebSocket канала(ов)"""
        try:
            if channel:
                # Удаляем подписки только для указанного канала
                subs_to_remove = [
                    sub for sub in self._channel_subscriptions._all_subscriptions
                    if sub.target_id == target_id and sub.channel == channel
                ]
                for sub in subs_to_remove:
                    self._channel_subscriptions._all_subscriptions.remove(sub)
                    self._channel_subscriptions._channel_subscriptions[channel].remove(sub)
            else:
                # Удаляем все подписки каналов для target_id
                self._channel_subscriptions.remove_by_target(target_id)

            self.log('unsubscribe_channel', f'{target_id} from {channel or "all channels"}')
            return True
        except Exception as e:
            self.log('unsubscribe_channel', f'ERROR: {e}')
            return False

    def handle_channel_data(self, data_point: TwsChannelData) -> bool:
        """Обрабатывает точку данных из WebSocket канала"""
        try:
            # Обновляем последовательность
            channel = data_point.channel
            if channel not in self._channel_sequences:
                self._channel_sequences[channel] = 0
            self._channel_sequences[channel] += 1

            data_point.sequence = self._channel_sequences[channel]

            # Сохраняем в буфер канала
            if channel not in self._channel_buffer:
                self._channel_buffer[channel] = []
            self._channel_buffer[channel].append(data_point)

            # Ограничиваем размер буфера
            buffer = self._channel_buffer[channel]
            if len(buffer) > self._max_channel_buffer_size:
                buffer.pop(0)
                self._channel_data_dropped += 1

            # Находим подписчиков
            matching_subs = self._channel_subscriptions.find(data_point)
            if not matching_subs:
                return False

            # Уведомляем подписчиков
            notified_count = 0
            for sub in matching_subs:
                comp = self.find_by_id(sub.target_id)
                if comp and hasattr(comp, 'on_channel_data'):
                    try:
                        comp.on_channel_data(data_point.channel, data_point)
                        notified_count += 1
                    except Exception as e:
                        self.log('handle_channel_data', f'ERROR in {comp.Name}.on_channel_data(): {e}')

            self._channel_data_processed += 1
            if self._channel_data_processed % 1000 == 0:
                self.log('handle_channel_data',
                         f'processed {self._channel_data_processed} channel points, dropped {self._channel_data_dropped}')

            return notified_count > 0

        except Exception as e:
            self.log('handle_channel_data', f'CRITICAL ERROR: {e}')
            return False

    # +++ МЕТОДЫ ДЛЯ УПРАВЛЕНИЯ WS КЛИЕНТАМИ +++

    def add_ws_client(self, name: str, client: "TWebSocketClient") -> bool:
        """Регистрирует WebSocket клиент в приложении"""
        if name in self._ws_clients:
            self.log('add_ws_client', f'ERROR: client {name} already exists')
            return False

        self._ws_clients[name] = client
        self.log('add_ws_client', f'registered {name}')
        return True

    def remove_ws_client(self, name: str) -> bool:
        """Удаляет WebSocket клиент"""
        if name in self._ws_clients:
            del self._ws_clients[name]
            self.log('remove_ws_client', f'removed {name}')
            return True
        return False

    # +++ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ +++

    def get_event_history(self, limit: int = 100) -> List[TEvent]:
        """Возвращает историю событий"""
        return self._event_buffer[-limit:] if limit > 0 else self._event_buffer

    def get_channel_history(self, channel: TwsDataChannel, limit: int = 100) -> List[TwsChannelData]:
        """Возвращает историю данных канала"""
        buffer = self._channel_buffer.get(channel, [])
        return buffer[-limit:] if limit > 0 else buffer

    def get_metrics(self) -> Dict[str, Any]:
        """Возвращает метрики системы событий"""
        return {
            "events_processed": self._events_processed,
            "events_dropped": self._events_dropped,
            "subscriptions_count": self._subscriptions.count(),
            "event_buffer_size": len(self._event_buffer),
            "ws_clients_count": len(self._ws_clients)
        }

    def get_channel_metrics(self) -> Dict[str, Any]:
        """Возвращает метрики системы каналов"""
        return {
            "channel_data_processed": self._channel_data_processed,
            "channel_data_dropped": self._channel_data_dropped,
            "channel_subscriptions_count": self._channel_subscriptions.count(),
            "active_channels": list(self._channel_buffer.keys()),
            "channel_buffer_sizes": {chan.value: len(buf) for chan, buf in self._channel_buffer.items()}
        }
# ---------------------------------------------------------------------
# TComponent — базовый компонент Tradition
# ---------------------------------------------------------------------
class TComponent(TObject):
    def __init__(self, Owner: "TComponent | None" = None, name: str = None):
        # name сохраняется как Name в TObject
        super().__init__(name)
        # Архитектура
        self.Owner: "TComponent | None" = Owner
        self.Components: dict[str, "TComponent"] = {}

        # Контекст приложения
        app = None
        try:
            app = TApplication.app()
        except Exception:
            app = None

        # Регистрация в Owner или на уровне приложения
        if self.Owner is not None:
            self._register_in_owner(self.Owner)
        elif app:
            app.register(self)

        self.log('__init__', f'component {self.Name} created')

    # --- Совместимость: owner/components (алиасы) ---
    @property
    def owner(self): return self.Owner
    @owner.setter
    def owner(self, v): self.Owner = v
    @property
    def components(self): return self.Components
    @components.setter
    def components(self, v): self.Components = v

    # --- Родословная (всегда с маленькой) ---
    def id(self) -> str:
        path = [self.Name]
        p = self.Owner
        guard = 0
        while p is not None and guard < 1024:
            path.append(p.Name)
            p = getattr(p, "Owner", None)
            guard += 1
        if guard >= 1024:
            self.fail('id', 'possible ownership cycle detected', RuntimeError)
        return "-".join(reversed(path))

    # --- Внутренняя регистрация у владельца ---
    def _register_in_owner(self, owner: "TComponent"):
        if self.Name in owner.Components and owner.Components[self.Name] is not self:
            self.fail('_register_in_owner', f'Duplicate subcomponent Name: {self.Name}', ValueError)
        owner.Components[self.Name] = self
        self.log('_register_in_owner', f'registered in {owner.Name}')
        app = get_current_app()
        if app:
            try:
                app.register_global(self)
            except Exception as e:
                self.log('_register_in_owner', f'⚠️ registry skipped: {e}')

    def _unregister_from_owner(self):
        if not self.Owner:
            return
        if self.Name in self.Owner.Components and self.Owner.Components[self.Name] is self:
            del self.Owner.Components[self.Name]
            self.log('_unregister_from_owner', f'unregistered from {self.Owner.Name}')
        self.Owner = None

    # --- Управление дочерними компонентами ---
    def add(self, comp: "TComponent"):
        if comp.Name in self.Components and self.Components[comp.Name] is not comp:
            self.fail('add', f'Duplicate component Name: {comp.Name}', ValueError)
        self.Components[comp.Name] = comp
        comp.Owner = self
        self.log('add', f'{comp.Name} added')
        app = get_current_app()
        if app:
            try:
                app.register_global(comp)
            except Exception as e:
                self.log('add', f'⚠️ registry skipped: {e}')

    def remove(self, comp: "TComponent"):
        if comp.Name not in self.Components:
            self.fail('remove', f'Component not found: {comp.Name}', KeyError)
        del self.Components[comp.Name]
        self.log('remove', f'{comp.Name} removed')
        # дерегистрация из глобального — при free()

    def find(self, name: str):
        return self.Components.get(name)

    def list(self):
        return list(self.Components.keys())

    # --- Жизненный цикл ---
    def free(self):
        self.log('free', f'freeing {len(self.Components)} subcomponents...')
        for sub in list(self.Components.values()):
            if hasattr(sub, 'free'):
                sub.free()
        self.Components.clear()
        app = get_current_app()
        if app:
            try:
                app.unregister_global(self)
            except Exception as e:
                self.log('free', f'⚠️ registry skipped: {e}')
        self._unregister_from_owner()
        self.log('free', 'component destroyed')

    # +++ МЕТОДЫ ДЛЯ РАБОТЫ С СОБЫТИЯМИ И КАНАЛАМИ +++

    def subscribe_event(self, topic: str, **filters):
        """Подписывается на одиночные события"""
        app = get_current_app()
        if app and hasattr(app, 'subscribe'):
            app.subscribe(self.id(), topic, **filters)
            self.log('subscribe_event', f'subscribed to {topic} {filters}')
        else:
            self.log('subscribe_event', 'app not found or no subscription support')

    def unsubscribe_event(self, topic: str = None):
        """Отписывается от событий"""
        app = get_current_app()
        if app and hasattr(app, 'unsubscribe'):
            app.unsubscribe(self.id(), topic)
            self.log('unsubscribe_event', f'unsubscribed from {topic or "all events"}')
        else:
            self.log('unsubscribe_event', 'app not found')

    def subscribe_channel(self, channel: TwsDataChannel, symbols: List[str] = None, **filters):
        """Подписывается на WebSocket канал данных"""
        app = get_current_app()
        if app and hasattr(app, 'subscribe_channel'):
            app.subscribe_channel(self.id(), channel, symbols, **filters)
            self.log('subscribe_channel', f'subscribed to {channel.value} symbols={symbols}')
        else:
            self.log('subscribe_channel', 'app not found or no channel support')

    def unsubscribe_channel(self, channel: TwsDataChannel = None):
        """Отписывается от WebSocket канала(ов)"""
        app = get_current_app()
        if app and hasattr(app, 'unsubscribe_channel'):
            app.unsubscribe_channel(self.id(), channel)
            self.log('unsubscribe_channel', f'unsubscribed from {channel or "all channels"}')
        else:
            self.log('unsubscribe_channel', 'app not found')

    def on_event(self, event: TEvent):
        """
        Обрабатывает одиночное событие.
        Переопределите в потомках для реакции на события.
        """
        self.log('on_event', f'received {event.type} from {event.source}')

    def on_channel_data(self, channel: TwsDataChannel, data_point: TwsChannelData):
        """
        Обрабатывает точку данных из непрерывного потока.
        Переопределите в потомках для работы с потоками данных.
        """
        self.log('on_channel_data', f'received {channel.value} #{data_point.sequence} for {data_point.symbol}')
# ---------------------------------------------------------------------
# TLiveComponent — “живой” компонент
# ---------------------------------------------------------------------
class TLiveComponent(TComponent, LoggableComponent):
    def __init__(self, Owner: "TComponent | None" = None, name: str = None):
        super().__init__(Owner, name)

        self._active = False
        self._thread = None
        self._stop = False

        # Delphi-style hooks
        self.AfterCreate = None
        self.BeforeDestroy = None
        self.BeforeOpen = None
        self.AfterOpen = None
        self.BeforeClose = None
        self.AfterClose = None
        self.OnError = None

        try:
            if callable(self.AfterCreate):
                self.AfterCreate(self)
        except Exception as e:
            self.log("__init__", f"⚠️ AfterCreate error: {e}")

        self.log("__init__", "live component created")

    # Публичный API
    def open(self):
        if callable(self.BeforeOpen):
            self.BeforeOpen(self)
        result = self.do_open()
        if result:
            self._active = True
            self.log("open", "component activated")
        else:
            self.fail("open", "do_open() returned False", RuntimeError)
        if callable(self.AfterOpen):
            self.AfterOpen(self)

    def close(self):
        try:
            if callable(self.BeforeClose):
                self.BeforeClose(self)
            if self.do_close():
                self._active = False
                self.log("close", "component deactivated")
            if callable(self.AfterClose):
                self.AfterClose(self)
        except Exception as e:
            self.log("close", f"⚠️ failed: {e}")
            if callable(self.OnError):
                self.OnError(self, e)
            else:
                self.fail("close", f"failed: {e}", type(e))

    # Виртуалы
    def do_open(self) -> bool:
        return True

    def do_close(self) -> bool:
        return True

    # Расширенный free()
    def free(self):
        try:
            if callable(self.BeforeDestroy):
                self.BeforeDestroy(self)
        except Exception as e:
            self.log("free", f"⚠️ BeforeDestroy error: {e}")

        if getattr(self, "_active", False):
            try:
                self.close()
            except Exception as e:
                self.log("free", f"⚠️ auto-close failed: {e}")

        super().free()
        self.log("free", "component destroyed")

    # Удобные алиасы
    def run(self, *args, **kwargs):
        self.open()

    def stop(self, *args, **kwargs):
        self.close()

    # Свойства
    @property
    def active(self) -> bool:
        return self._active
    @active.setter
    def active(self, value: bool):
        self._active = bool(value)
# ---------------------------------------------------------------------
# TSysComponent — системный компонент (singleton per class)
# ---------------------------------------------------------------------
class TSysComponent(TLiveComponent):
    _instances: dict[type, "TSysComponent"] = {}

    def __init__(self, Owner: "TApplication", name: str):
        if not isinstance(Owner, TApplication):
            raise TypeError(f"{self.__class__.__name__} Owner must be TApplication")

        cls = self.__class__
        if cls in TSysComponent._instances:
            raise RuntimeError(f"{cls.__name__} already instantiated")

        super().__init__(Owner, name)
        TSysComponent._instances[cls] = self
        self.log("__init__", "system component created")

    def do_open(self) -> bool:
        return True

    def do_close(self) -> bool:
        return True

    @classmethod
    def instance(cls) -> "TSysComponent | None":
        return TSysComponent._instances.get(cls)

    @classmethod
    def is_active(cls) -> bool:
        inst = TSysComponent._instances.get(cls)
        return bool(inst and inst._active)
# ---------------------------------------------------------------------
# TModule — модуль верхнего уровня
# ---------------------------------------------------------------------
class TModule(TLiveComponent):
    def __init__(self, Owner: "TApplication", name: str, version: str | int = "1"):
        if not isinstance(Owner, TApplication):
            raise TypeError("TModule Owner must be TApplication")

        tag = f"{name}_{version}"
        super().__init__(Owner, tag)

        self.base_name = str(name).upper()
        self.version = str(version)

        if hasattr(Owner, "register_module"):
            Owner.register_module(self)

        self.log("__init__", f"{self.base_name} v{self.version} initialized")

    @property
    def tag(self) -> str:
        return f"{self.base_name}_{self.version}"

    @property
    def full_tag(self) -> str:
        return f"{self.Owner.project_tag}/{self.tag}"

    def do_open(self) -> bool:
        self.Owner.register_module(self)
        self.log("do_open", f"{self.tag} opened")
        return True

    def do_close(self) -> bool:
        self.Owner.unregister_module(self)
        self.log("do_close", f"{self.tag} closed")
        return True
# =====================================================================
# bb_sys.py 🜂 The End — See You Next Session 2025 ⚙️ 1056
# =====================================================================
