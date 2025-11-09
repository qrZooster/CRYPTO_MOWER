# ======================================================================================================================
# 📁 file        : bb_sys.py — базовые классы Tradition Core 2025
# 🕒 created     : 11.10.2025 12:23
# 🎉 contains    : Определяет базовые классы TObject, TOwnerObject, TComponent
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
import os
import re
import datetime as dt
import traceback
from datetime import datetime
from typing import MutableMapping, List, Dict, Any, Optional
from bb_logger import LoggableComponent, TLogRouterMixin
# 💎 ... Переназначаемая ENV-мапа ...
_GLOBAL_AUTO_COUNTERS: Dict[str, int] = {}  # для объектов без Owner (или на самом верхнем уровне)
_ENV: MutableMapping[str, str] = os.environ
# 🍍 ... global utilities ...
def set_env_mapping(mapping: MutableMapping[str, str] | None) -> None:
    global _ENV
    _ENV = os.environ if mapping is None else mapping
# ---
def get_env_mapping() -> MutableMapping[str, str]:
    return _ENV
# ---
def _s(v):
    return '' if v is None else str(v)
# ---
def _set_key(name: str, value: str) -> bool:
    if not name:
        return False
    _ENV[name] = '' if value is None else _s(value)
    return True
# ---
def _key(name: str | None, default: str = '') -> str | None:
    if not name:
        return None
    v = _ENV.get(name)
    if v is not None and v != '':
        return v
    _ENV[name] = str(default)
    return str(default)
# ---
def explode(delimiter: str, src: str) -> list[str]:
    if not src:
        return []
    parts = [x.strip() for x in src.replace(";", delimiter).replace(",", delimiter).split(delimiter)]
    return [x for x in parts if x]
# 💎 UI meta & utilities (глобально)
TC_PREFIX = "tc"
TC_DBG_PREFIX = "tc-dbg"  # новый префикс для debug-классов

def tc_attr_name(name: str) -> str:
    return f"{TC_PREFIX}-{name}"

def tc_class(*parts: str) -> str:
    # tc-class('frame') -> 'tc-frame'
    # tc-class('w','100') -> 'tc-w-100'
    return "-".join((TC_PREFIX, *parts))

def tc_dbg_class(*parts: str) -> str:
    # tc_dbg-class('frame') -> 'tc_dbg-frame'
    # tc_dbg-class('f','purple','2') -> 'tc_dbg-f-purple-2'
    return "-".join((TC_DBG_PREFIX, *parts))

def tc_join_classes(*cls: str) -> str:
    return " ".join(c for c in cls if c)

def tc_badge_classes(palette: str) -> str:
    # → 'tc_dbg-badge tc_dbg-b-purple'
    return tc_join_classes(tc_dbg_class("badge"), tc_dbg_class("b", palette))
# 💎 ... CONFIG / CONSTS ...
BYBIT_API_KEY = _key('BYBIT_API_KEY', '')
BYBIT_API_SECRET = _key('BYBIT_API_SECRET', '')
BYBIT_MODE = _key('BYBIT_MODE', 'prod')  # prod | test
# ---
if BYBIT_MODE == 'test':
    BYBIT_WS_PUBLIC_LINEAR = 'wss://stream-testnet.bybit.com/v5/public/linear'
    BYBIT_REST = 'https://api-testnet.bybit.com'
else:
    BYBIT_WS_PUBLIC_LINEAR = 'wss://stream.bybit.com/v5/public/linear'
    BYBIT_REST = 'https://api.bybit.com'
# 💎 ... DATA_BASE CONFIG ...
DB_CFG = {
    'host': _key('DB_HOST', '127.0.0.1'),
    'port': int(_key('DB_PORT', '3307')),
    'user': _key('DB_USER', 'u267510'),
    'password': _key('DB_PASSWORD', '_n2FeRUP.6'),
    'database': _key('DB_NAME', 'u267510_tg'),
    'autocommit': True,
    'charset': _key('DB_CHARSET', 'utf8mb4'),
}
# 💎 ... BYBIT NEWS ...
ANN_URL = 'https://api.bybit.com/v5/announcements/index'
ANN_LOCALE = 'en-US'
# ---
USDT_PAIR_RE = re.compile(r'([A-Z0-9]{1,20})USDT')
USDT_SLASH_RE = re.compile(r'([A-Z0-9]{1,20})/USDT')
# ---
BYBIT, PERP, USDT, BUY, SELL = 'BYBIT', 'PERP', 'USDT', 'BUY', 'SELL'
TRACEBACK_ENABLED = True
# 💎 ... TIME ZONE ...
MSK = dt.timezone(dt.timedelta(hours=3), name='MSK')
# 💎🧩⚙️ ... __ALL__ ...
__all__ = [
    'TOwnerObject', 'TComponent', 'TLiveComponent',
    'TSysComponent', 'TModule',
    'set_env_mapping',
    '_s', '_set_key', '_key', 'explode',
    'is_visual_node', 'tc_attr_name', 'tc_class', 'tc_dbg_class', 'tc_badge_classes',
    'DB_CFG', 'BYBIT_API_KEY', 'BYBIT_API_SECRET',
    'BYBIT_MODE', 'BYBIT_WS_PUBLIC_LINEAR', 'BYBIT_REST',
    'MSK', 'ANN_URL', 'ANN_LOCALE',
    'BYBIT', 'PERP', 'USDT', 'BUY', 'SELL',
    'USDT_PAIR_RE', 'USDT_SLASH_RE',
]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TOwnerObject — иерархия владения, регистрация и логика родословной
# ----------------------------------------------------------------------------------------------------------------------
class TOwnerObject:
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TOwnerObject | None" = None, Name: str | None = None):
        """
        Базовый узел дерева владения Tradition Core.
        💠 объект знает своего Owner, хранит детей в self.Components,
        получает человекопонятное имя вида Panel1 / Label2,
        и автоматически регистрируется у Owner.
        """
        self.f_name = ""
        # --- PHASE 0.1: Политика владения (валидация до присвоения полей) ---
        # 1️⃣ Owner обязателен? (например, TGrid_Tr не может существовать без грид-а)
        if Owner is None and self._owner_required():
            # тут ещё нет self.Name etc, значит текст будет чуть суше — это ок
            # ... 💥 Fatal Error ...
            raise TypeError(f"{self.__class__.__name__} requires an Owner")
        # 2️⃣ тип Owner допустим?
        allowed_owner = self._allowed_owner_types()
        if Owner is not None and allowed_owner is not None:
            if not isinstance(Owner, allowed_owner):
                # ... 💥 Fatal Error ...
                raise TypeError(f"{self.__class__.__name__} cannot have Owner {Owner.__class__.__name__}")
        # ✔️ --- если мы дошли сюда — владелец формально валиден ---
        self.Owner: "TOwnerObject | None" = Owner
        # генерим имя в Delphi-стиле: Panel1, Label2, Grid_Tr1...
        if Name:
            self.f_name = Name
        # 👨‍👩‍👧‍👧 ... Дочерние компоненты и служебные поля ...
        self.Components: Dict[str, "TOwnerObject"] = {}
        self.magic_name: str = ""  # 🧙‍♀️ потомки (TPage, TModule) объявляют себя здесь для глобальной регистрации
        # --- Регистрация в родителе ---
        self.register_in_owner()
        # ⚡🛠️ TOwnerObject ▸ End of __init__
    # ..................................................................................................................
    # 🛡️ Политики владения / допустимых связей
    # ..................................................................................................................
    def _owner_required(self) -> bool:
        """
        Должен ли этот класс ВСЕГДА иметь Owner?
        По умолчанию False.
        Пример: у TApplication это будет False (оно корень),
        у TGrid_Tr это будет True (строка не может жить без грида).
        """
        return False
    # ---
    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        """
        Какие типы могут быть нашим Owner.
        None -> без ограничений.
        Пример: у TGrid_Tr → (TGrid,), у TGrid_Td → (TGrid_Tr,)
        """
        return None
    # ---
    def _allowed_child_types(self) -> tuple[type, ...] | None:
        """
        Какие типы детей мы можем держать в self.Components.
        None -> без ограничений.
        Пример: у TGrid → (TGrid_Tr,), у TGrid_Tr → (TGrid_Td,)
        """
        return None
    # ..................................................................................................................
    # 🏷️👨‍👩‍👧‍👧 Идентичность и родословная
    # ..................................................................................................................
    @property
    def Name(self) -> str:
        if not getattr(self, "f_name", ""):
            self.f_name = self._get_unique_name()
        return self.f_name
    # ---
    @Name.setter
    def Name(self, value: str | None):
        self.f_name = "" if value is None else str(value)
    # ---
    def _get_unique_name(self) -> str:
        """
        PHASE 1:
        Имя = ИмяКласса без ведущей 'T' + порядковый номер.
        TPanel  → Panel1
        TLabel  → Label1
        TGrid_Tr → Grid_Tr1
        """

        # класс -> "Panel", "Label", "Grid_Tr"
        raw_class = self.__class__.__name__
        if raw_class.startswith("T") and len(raw_class) > 1:
            human_name = raw_class[1:]
        else:
            human_name = raw_class

        # получаем счётчик
        if self.Owner is not None:
            counters = getattr(self.Owner, "_auto_counters", None)
            if counters is None:
                counters = {}
                setattr(self.Owner, "_auto_counters", counters)
        else:
            counters = _GLOBAL_AUTO_COUNTERS  # глобальный счётчик для корневых

        n = counters.get(human_name, 0) + 1
        candidate = f"{human_name}{n}"

        # уникальность в пределах Owner
        if self.Owner is not None:
            while candidate in self.Owner.Components:
                n += 1
                candidate = f"{human_name}{n}"

        counters[human_name] = n
        return candidate
    # ---
    def id(self) -> str:
        """
        Возвращает полный путь владения (родословную) через дефис, от корня до текущего узла. Если обнаружен цикл владения глубже 1024 шагов — падаем через fail().
        """
        path = [self.Name]
        p = self.Owner
        guard = 0
        while p is not None and guard < 1024:
            path.append(p.Name)
            p = getattr(p, "Owner", None)
            guard += 1
        if guard >= 1024:
            self.fail("id", "Ownership cycle detected", RuntimeError)
        return "-".join(reversed(path))
    # ..................................................................................................................
    # ⚙️ Register & Release
    # ..................................................................................................................
    def app(self) -> "TApplication":
        """
        Возвращает ссылку на текущее приложение TApplication (singleton). Используется для глобальных регистраций и доступа к корневым каталогам.
        """
        from bb_application import TApplication
        return TApplication.app()
    # ---
    def register_global(self, component: "TOwnerObject | None" = None):
        """
        Сообщает приложению (если оно есть), что компонент существует. Используется для автокаталогизации страниц, модулей и системных узлов.
        """
        try:
            app = self.app()
        except Exception:
            app = None
        if app:
            app.register_global(component)
    # ---
    def release_global(self, component: "TOwnerObject | None" = None):
        """
        Убирает компонент из глобальной регистрации приложения, если оно активно. Безопасно вызывается даже если app() недоступно.
        """
        try:
            app = self.app()
        except Exception:
            app = None
        if app:
            app.release_global(component)
    # ---
    def register_in_owner(self):
        """
        Регистрирует self у Owner.Components и проверяет,
        что Owner вообще имеет право иметь ребёнка такого типа.
        """
        if not self.Owner:
            return

        # 🔒 Политика детей: Owner может ли владеть таким типом?
        allowed_kids = self.Owner._allowed_child_types()
        if allowed_kids is not None and not isinstance(self, allowed_kids):
            self.fail(
                "register_in_owner",
                f"{self.Owner.__class__.__name__} cannot own {self.__class__.__name__}",
                TypeError
            )

        # имя уже сгенерировано, значит тут можно fail() с нормальным self.Name
        if self.Name in self.Owner.Components:
            self.fail(
                "register_in_owner",
                f"Duplicate component: {self.Name}",
                ValueError
            )

        self.Owner.Components[self.Name] = self

        # пробуем подняться в приложение (Pages, Layouts, Modules и т.д.)
        try:
            self.Owner.register_global(self)
        except Exception:
            pass
    # ..................................................................................................................
    # 🔍 Поиск и служебные
    # ..................................................................................................................
    def find(self, name: str) -> "TOwnerObject | None":
        """
        Возвращает прямого ребёнка по имени среди self.Components или None, если такого нет.
        """
        return self.Components.get(name)
    # ---
    def list(self) -> list[str]:
        """
        Возвращает список имён дочерних компонентов (плоский уровень, без рекурсии).
        """
        return list(self.Components.keys())
    # ..................................................................................................................
    # 📡 Log / Debug / Fail
    # ..................................................................................................................
    def log(self, function: str, *parts, window: int = 1):
        """
        Базовый логгер для всех owner-компонентов:
        1) пишет в TLogRouter / консоль,
        2) параллельно пытается отправить строку в браузер через ws_push_log().
        """
        from datetime import datetime
        from bb_logger import LOG_ROUTER
        from bb_sys import _key

        project_symbol = _key('PROJECT_SYMBOL', 'BB')
        project_version = _key('PROJECT_VERSION', '3')
        now = datetime.now().strftime('%H:%M:%S')
        msg = ' '.join(str(p) for p in parts)
        text = f'[{project_symbol}_{project_version}][{now}][{self.Name}]{function}(): {msg}'

        # 1) Терминал / Rich-консоль
        try:
            if LOG_ROUTER:
                LOG_ROUTER.write(text, window=window)
            else:
                print(text, flush=True)
        except Exception:
            print(text, flush=True)

        # 2) Браузер (WebSocket) — ищем вверх по Owner того, у кого есть ws_push_log()
        try:
            app = None
            cur = self
            depth = 0

            # поднимаемся по цепочке Owner максимум 20 шагов
            while cur is not None and depth < 20:
                if hasattr(cur, "ws_push_log"):
                    app = cur
                    break
                cur = getattr(cur, "Owner", None)
                depth += 1

            if app:
                # здесь сработает твой TApplication.ws_push_log(...)
                app.ws_push_log(text)

        except Exception:
            # логгер не должен ронять систему
            pass
    # ---
    def debug(self, func: str, *parts):
        """
        Унифицированный отладочный вывод (иконка 🔍). Включается только если глобальный флаг DEBUG_MODE == '1'. Подходит для временной диагностики.
        """
        if not _key("DEBUG_MODE", "1") == "1":
            return
        now = datetime.now().strftime('%H:%M:%S')
        msg = " ".join(str(p) for p in parts)
        text = f"🔍 [DEBUG][{self.__class__.__name__}.{func}] {msg}"
        print(text, flush=True)
    # ---
    def fail(self, function: str, msg: str, exc_type: type = Exception):
        """
        Аварийный выход с логированием стека в файл log/fail.log.
        """
        from bb_db import key_int

        try:
            trace_limit = key_int("TRACE_LIMIT", 12)
        except Exception:
            trace_limit = 12

        stack = "".join(traceback.format_stack(limit=trace_limit))
        cls_name = self.__class__.__name__
        owner_name = getattr(getattr(self, "Owner", None), "Name", None)
        owner_part = f"\n📦 owner: {owner_name}" if owner_name else ""
        text = (
            f"\n💥 {cls_name}.{function}() FAILED{owner_part}\n⚙️ message: {msg}"
            f"\n\n🧩 Traceback (most recent calls):\n{stack}"
        )

        # пытаемся залогировать через общий лог
        try:
            self.log("fail", msg)
        except Exception:
            print(f"[{cls_name}] fail(): {msg}")

        # пишем в файл
        try:
            os.makedirs("log", exist_ok=True)
            with open("log/fail.log", "a", encoding="utf-8") as f:
                f.write(f"{text}\n{'-' * 80}\n")
        except Exception:
            pass

        print(text, flush=True)
        raise exc_type(f"{cls_name}.{function}(): {msg}")
    # ..................................................................................................................
    # ♻️ Уничтожение
    # ..................................................................................................................
    def iter_tree(self):
        """
        Генератор обхода вниз по иерархии от текущего узла. Даёт self, затем рекурсивно всех детей.
        """
        yield self
        for child in self.Components.values():
            yield from child.iter_tree()
    # ---
    def free(self):
        """
        Рекурсивно вызывает free() у всех дочерних компонентов, удаляет их, исключает себя из Owner и логирует факт уничтожения.
        """
        for child in list(self.Components.values()):
            if hasattr(child, "free"):
                child.free()
        self.Components.clear()
        if self.Owner:
            self.Owner.remove(self)
        self.log("free", "component destroyed")
    # ---
    def remove(self, child: "TOwnerObject"):
        """
        Удаляет дочерний компонент из self.Components по ссылке. Если такого ребёнка нет — бросает fail().
        """
        if child.Name not in self.Components:
            self.fail("remove", f"Component not found: {child.Name}", KeyError)
        del self.Components[child.Name]
        self.log("remove", f"{child.Name} removed")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TObject — базовый класс - Alias
# ----------------------------------------------------------------------------------------------------------------------
TObject = TOwnerObject
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TComponent — базовый компонент Tradition Core
# ----------------------------------------------------------------------------------------------------------------------
class TComponent(TOwnerObject):
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TOwnerObject | None" = None, Name: str | None = None):
        """
        Базовый компонент Tradition Core. Живёт в дереве владения (TOwnerObject), может подписываться на события и WebSocket-каналы, участвует в управлении жизненным циклом. Name можно не передавать: если Name не задан, он генерируется автоматически на основе prefix или имени класса. Переопределяй в потомках.
        """
        super().__init__(Owner, Name)
        # --- Жизненный статус компонента ---
        # На этом этапе self уже зарегистрирован в Owner.Components (это сделал TOwnerObject.__init__).
        # ... 🔊 ...
        self.log("__init__", f"⚙️ component {self.Name} created")
        # ⚡🛠️ TComponent ▸ End of __init__
    # ..................................................................................................................
    # 🚀 Жизненный цикл
    # ..................................................................................................................
    def free(self):
        """
        Безопасно уничтожает компонент и всех дочерних. Вызывает free() у детей (если есть), снимает детей с Owner, удаляет себя у Owner и логирует уничтожение. Переопределяй в потомках, если нужно доп.очистка.
        """
        for sub in list(self.Components.values()):
            try:
                sub.free()
            except Exception as e:
                self.log("free", f"⚠️ subcomponent free error: {e}")
        self.Components.clear()
        if self.Owner:
            try:
                self.Owner.remove(self)
            except Exception as e:
                self.log("free", f"⚠️ owner remove error: {e}")
    # ..................................................................................................................
    # 📡 Подписки на события
    # ..................................................................................................................
    def subscribe_event(self, topic: str, **filters):
        """
        Подписывает компонент на логические события Tradition Core. Фактически делегирует в app().subscribe(...).
        """
        app = self.app()
        if app:
            app.subscribe(self.id(), topic, **filters)
            self.log("subscribe_event", f"→ {topic} {filters}")

    def on_event(self, event):
        """
        Колбэк события. Вызывается приложением, когда пришло TEvent, совпадающее с фильтрами подписки. Переопределяй в потомках.
        """
        self.log("on_event", f"received {event.type} from {event.source}")
    # ..................................................................................................................
    # 🌐 Каналы данных WebSocket
    # ..................................................................................................................
    def subscribe_channel(self, channel, symbols=None, **filters):
        """
        Подписывает компонент на поток данных (WebSocket канал). Делегирует в app().subscribe_channel(...).
        """
        app = self.app()
        if app:
            app.subscribe_channel(self.id(), channel, symbols or [], **filters)
            self.log("subscribe_channel", f"→ {channel.value} {symbols or []}")

    def on_channel_data(self, channel, data_point):
        """
        Колбэк точки данных канала WS. Получает TwsDataChannel и структуру данных с sequence. Переопределяй в потомках.
        """
        self.log("on_channel_data", f"{channel.value} #{data_point.sequence}")
    # ..................................................................................................................
    # 🔧 Вспомогательное
    # ..................................................................................................................
    def app(self) -> "TApplication | None":
        """
        Возвращает текущее приложение Tradition Core (singleton TApplication). Возвращает None, если импорт или инициализация TApplication недоступны. Это мягкий вариант super().app() для совместимости со старым кодом.
        """
        try:
            from bb_application import TApplication
            return TApplication.app()
        except Exception:
            return None
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TLiveComponent — “живой” компонент (умеет open()/close(), живёт в рантайме)
# ----------------------------------------------------------------------------------------------------------------------
class TLiveComponent(TComponent, LoggableComponent):
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TComponent | None" = None, Name: str | None = None):
        """
        Живой компонент Tradition Core. Имеет состояние active, умеет открываться/закрываться (open/close), хранит хуки жизненного цикла (BeforeOpen, AfterClose и т.д.), может работать в отдельном потоке. Name можно не передавать: если не задан, генерируется автоматически через TOwnerObject. Переопределяй в потомках.
        """
        super().__init__(Owner, Name)
        # --- Runtime state / threading / flags ---
        self._active: bool = False        # компонент сейчас в рабочем состоянии?
        self._thread = None               # опциональный рабочий поток
        self._stop: bool = False          # внешний флаг "надо остановиться"
        # --- Delphi-style hook callbacks ---
        # Все поля ниже — колбэки, если заданы пользователем:
        #   callable(self) → ok
        # Используются в open()/close()/free().
        self.AfterCreate = None
        self.BeforeDestroy = None
        self.BeforeOpen = None
        self.AfterOpen = None
        self.BeforeClose = None
        self.AfterClose = None
        self.OnError = None
        # --- Invoke AfterCreate hook (если задан) ---
        try:
            if callable(self.AfterCreate):
                self.AfterCreate(self)
        except Exception as e:
            self.log("__init__", f"⚠️ AfterCreate error: {e}")
        # ... 🔊 ...
        self.log("__init__", f"⚙️ live component {self.Name} created")
        # ⚡🛠️ TLiveComponent ▸ End of __init__
    # ..................................................................................................................
    # 🚀 Публичный жизненный цикл
    # ..................................................................................................................
    def open(self):
        """
        Активирует компонент. Последовательность:
        1) вызываем BeforeOpen(self), если задан;
        2) do_open() → должен вернуть True при успехе;
        3) ставим self._active = True;
        4) вызываем AfterOpen(self), если задан.
        При неуспехе вызываем fail().
        """
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
        """
        Деактивирует компонент. Последовательность:
        1) BeforeClose(self), если задан;
        2) do_close() → логика выключения;
        3) self._active = False;
        4) AfterClose(self), если задан.
        При исключении вызывает OnError(self, e) если есть, иначе fail().
        """
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
    # ..................................................................................................................
    # ▶️ Виртуальные методы do_open()/do_close()
    # ..................................................................................................................
    def do_open(self) -> bool:
        """
        Реальная логика старта компонента. По умолчанию просто возвращает True.
        Переопределяй в потомках.
        """
        return True

    def do_close(self) -> bool:
        """
        Реальная логика остановки компонента. По умолчанию просто возвращает True.
        Переопределяй в потомках.
        """
        return True
    # ..................................................................................................................
    # ♻️ Жизненный цикл уничтожения
    # ..................................................................................................................
    def free(self):
        """
        Расширенный free() для живых компонентов.
        1) дергает BeforeDestroy(self), если задан;
        2) если компонент ещё active → пытается close();
        3) зовёт super().free() чтобы убрать из дерева;
        4) логирует финал.
        """
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
    # ..................................................................................................................
    # ▶️ Удобные алиасы
    # ..................................................................................................................
    def run(self, *args, **kwargs):
        """
        Алиас для open(). Используем, когда компонент трактуется как сервис.
        """
        self.open()

    def stop(self, *args, **kwargs):
        """
        Алиас для close(). Используем, когда компонент трактуется как сервис.
        """
        self.close()
    # ..................................................................................................................
    # 🔎 Свойства состояния
    # ..................................................................................................................
    @property
    def active(self) -> bool:
        """True → компонент открыт и работает."""
        return self._active

    @active.setter
    def active(self, value: bool):
        """Принудительно пометить компонент активным/неактивным (не вызывает open/close)."""
        self._active = bool(value)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TSysComponent — системный компонент (singleton per class)
# ----------------------------------------------------------------------------------------------------------------------
class TSysComponent(TLiveComponent):
    _instances: dict[type, "TSysComponent"] = {}

    def __init__(self, Owner: "TOwnerObject", name: str):
        if not isinstance(Owner, TOwnerObject):
            raise TypeError(f"{self.__class__.__name__} Owner must be TOwnerObject")

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
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TModule — модуль верхнего уровня
# ----------------------------------------------------------------------------------------------------------------------
class TModule(TLiveComponent):
    def __init__(self, Owner: "TOwnerObject", name: str, version: str | int = "1"):
        if not isinstance(Owner, TOwnerObject):
            raise TypeError("TModule Owner must be TOwnerObject")

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
# ---
def is_visual_node(x):
    """
    Узел считается визуальным, если он умеет сам себя рендерить
    и хранит результат рендера в Canvas.
    Это наш «протокол контрола», не завязанный на наследование.
    """
    return hasattr(x, "_render") and hasattr(x, "Canvas")
# ======================================================================================================================
# 📁🌄 bb_sys.py 🜂 The End — See You Next Session 2025 💹 1056 -> 484 -> 631
# ======================================================================================================================
