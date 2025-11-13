# ======================================================================================================================
# 📁 file        : bb_application.py
# 🕒 created     : 20.10.2025 14:02
# 🎉 contains    : TApplication - Приложение
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
from typing import MutableMapping, List, Dict, Any, Optional
from bb_sys import *
from bb_logger import LoggableComponent, TLogRouterMixin, LOG_ROUTER
from bb_events import *
from urllib.parse import urlparse, parse_qs, unquote_plus
from html import escape
from bb_ws_extended import TLocalWebSocketServer
import argparse
import time
import secrets
# 💎 ... Path ...
BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = Path(os.getenv("PUBLIC_DIR", "/var/www/sys_control/public"))
ASSETS_DIR = BASE_DIR / "assets" # файловая папка новое, только для наших css/js
ASSETS_URL  = "/assets"                        # веб-путь (то, что видит браузер)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def asset_url(name: str) -> str:
    """Строим URL вида /assets/name?v=<mtime> с кэш-бастингом."""
    p = ASSETS_DIR / name
    try:
        v = int(p.stat().st_mtime)
    except FileNotFoundError:
        v = int(time.time())  # fallback, чтобы не умереть
    return f"{ASSETS_URL}/{name}?v={v}"
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TRequest — Безопасный контейнер для GET/POST/headers — с авто-экранированием.
# ----------------------------------------------------------------------------------------------------------------------
class TRequest:
    def __init__(self, url: str | None = None):
        self.get: dict[str, str] = {}
        self.post: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}
        self.path: str = "/"

        if url:
            self.parse_url(url)

    def parse_url(self, url: str):
        parsed = urlparse(url)
        self.path = parsed.path or "/"

        params = parse_qs(parsed.query)
        self.get = {
            k: escape(unquote_plus(v[0])) if v else ""
            for k, v in params.items()
        }

        # 🧠 Дополнительно разбираем "чистый путь" — /file.html/page или /page
        parts = parsed.path.strip("/").split("/")

        # 💡 Добавляем только если "page" ещё не задан из query
        if "page" not in self.get:
            if len(parts) >= 2 and parts[-2].endswith(".html"):
                self.get["page"] = parts[-1]
            elif len(parts) == 1 and parts[0] and not parts[0].endswith(".html"):
                self.get["page"] = parts[0]

    def __getitem__(self, key: str) -> str:
        """Позволяет обращаться как к словарю: request['symbol']"""
        return self.get.get(key, "")

    def __repr__(self):
        return f"<TRequest path={self.path} get={self.get}>"
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TActionBus — мини-шина действий
# ----------------------------------------------------------------------------------------------------------------------
class TActionBus:
    def __init__(self):
        self._map: dict[str, dict] = {}

    def register(
        self,
        owner,
        fn,
        ttl: int = 300,
        redirect: str | None = None,
        oneshot: bool = False,
    ) -> str:
        """
        Регистрирует действие и возвращает aid.

        fn      — callable без аргументов.
        ttl     — время жизни действия в секундах.
        redirect — URL для редиректа после выполнения.
        oneshot — True → действие одноразовое (удаляется после первого вызова).
                  False → можно вызывать многократно, пока не истёк ttl.
        """
        aid = secrets.token_urlsafe(8)
        self._map[aid] = {
            "owner": owner,
            "fn": fn,
            "ts": time.time(),
            "ttl": ttl,
            "redirect": redirect,
            "oneshot": bool(oneshot),
        }
        return aid

    def dispatch(self, aid: str):
        """
        Выполняет действие по aid.
        Для oneshot-действий удаляет запись после первого успешного вызова.
        Возвращает redirect (если задан).
        """
        rec = self._map.get(aid)
        if not rec:
            return None

        # TTL-проверка: если протухло — выкидываем и ничего не делаем
        if time.time() - rec["ts"] > rec["ttl"]:
            self._map.pop(aid, None)
            return None

        try:
            rec["fn"]()  # без аргументов — замкни нужный контекст при регистрации
        except Exception as e:
            try:
                self.log("ActionBus", f"action error: {e}")  # если есть app.log
            except Exception:
                pass

        # одноразовые действия удаляем сразу после вызова
        if rec.get("oneshot"):
            self._map.pop(aid, None)

        return rec.get("redirect")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TApplication — управляющий объект
# ----------------------------------------------------------------------------------------------------------------------
class TApplication(TOwnerObject, TLogRouterMixin):
    _instance = None

    def __init__(self):
        if TApplication._instance is not None:
            raise RuntimeError("TApplication is a singleton. Use TApplication.app() instead.")

        super().__init__(Owner=None, Name="Application")
        TApplication._instance = self
        # 📡 LOG_ROUTER subscribing
        from bb_logger import LOG_ROUTER
        if LOG_ROUTER:
            LOG_ROUTER.add_subscriber(lambda msg, wnd: self.ws_push_log(msg))
        # --------------------------------------------------------------------------------------------------------------
        # Системные поля
        # --------------------------------------------------------------------------------------------------------------
        self.debug_mode = True
        self.render_id = 0
        #self._debug_css_ready = False
        #self._debug_css_cache = ""
        # ---
        self.request = TRequest()   # безопасный контейнер запроса
        self.actions = TActionBus()
        self.root = None  # общий корневой контейнер для HTML-рендеров

        self.loaded = False
        self.loading = False
        self.start_time = datetime.now()
        self.Echo: list[str] = []
        self._tag_counter = 0 # счетчик тегов для генерации комментов в html
        self._tag_stack: list[dict[str, str]] = [] # стек тегов
        # DOM Registry (живой журнал тегов TraditionDOM)
        self._dom_registry: dict[int, dict[str, Any]] = {}
        self._dom_counter: int = 0
        # 🔍 палитра подсветки mark()
        self._mark_palette_index = 0
        # Пути и окружение
        self.root_dir = Path(__file__).parent


        # Каталоги Tradition
        self.Layouts: Dict[str, TOwnerObject] = {}
        self.Pages: Dict[str, TOwnerObject] = {}
        self.Modules: Dict[str, TOwnerObject] = {}
        self._ws_clients: Dict[str, Any] = {}
        # Системные компоненты
        self.Session = None
        self.Database = None
        self.Config = None
        self.Schema = None
        self.DbEvents = None
        self.LocalWebSocketServer = None

        # События и каналы
        self._subscriptions = TSubscriptionIndex()
        self._channel_subscriptions = TwsChannelSubscriptionIndex()
        self._event_buffer: List[TEvent] = []
        self._channel_buffer: Dict[TwsDataChannel, List[TwsChannelData]] = {}

        self._events_processed = 0
        self._channel_data_processed = 0
        self.header = {
            "title": "Tradition Core",
            "meta": [],
            "links": [],
            "scripts": [],
            "styles": [],
        }
        self.log("__init__", "application created")
    # ------------------------------------------------------------------------------------------------------------------
    # 🚀 Start Application
    # ------------------------------------------------------------------------------------------------------------------
    async def start(self):
        """
        🌐 Главная точка входа Tradition Core 2025.
        Определяет режим работы (CLI или WebServer) и запускает соответствующий процесс.
        """
        if getattr(self, "loaded", False):
            self.log("start", "already started")
            return True

        # 👉 сохраняем текущий asyncio loop
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        self.log("start", "🔹 Base Application starting...")
        self.loading = True
        # --- Определяем режим и запускаем ---
        mode = getattr(self, "mode", None) or self.detect_mode()
        self.start_links()
        await self.do_start()
        if not self.Pages:
            self.do_pages()
        self.loading = False
        self.loaded = True
        self.log("start", f"✅ Application fully started in {mode.upper()} mode")
        #if not self.Pages:
        await self.run_web_server()
        return True

    def start_links(self):
        self.echo(str(ASSETS_DIR))
        # базовые стили всегда
        if not getattr(self, "_base_css_linked", False):
            self.add_link(asset_url("bb_tc.css"))
            self._base_css_linked = True

        # debug-стили только когда debug_mode=True
        if self.debug_mode and not getattr(self, "_dbg_css_linked", False):
            self.add_link(asset_url("bb_tc_dbg.css"))
            self._dbg_css_linked = True

    async def do_start(self):
        """Переопределяй в потомках. База — ничего не делает."""
        pass

    def do_pages(self):
        pass

    def add_page(self, page: "TPage"):
        """Регистрирует страницу в приложении."""
        self.Pages[page.Name] = page
        self.log("add_page", f"🧭 Page '{page.Name}' added")
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
    # ------------------------------------------------------------------------------------------------------------------
    # ⚙️ Главный механизм регистрации (Книга учета Жизни)
    # ------------------------------------------------------------------------------------------------------------------
    def register_global(self, comp: TOwnerObject):
        """
        Корневая регистрация компонентов Tradition Core.
        Раскладывает элементы по тематическим каталогам.
        """
        key = comp.magic_name.lower()

        if "page" in key:
            self.Pages[comp.Name] = comp
            self.log("register_global", f"📄 Page registered: {comp.Name}")
        elif "module" in key:
            self.Modules[comp.Name] = comp
            self.log("register_global", f"🧩 Module registered: {comp.Name}")
        else:
            # остальные просто считаем активными компонентами
            self.Components[comp.Name] = comp
            self.log("register_global", f"⚙️ Component registered: {comp.Name}")
    # ------------------------------------------------------------------------------------------------------------------
    def render(self, page: "TPage"):
        self.render_id += 1
        # перед тем как что-то рисовать — убедись что css вставлен
        self.add_meta("charset", "utf-8")
        self.add_meta("viewport", "width=device-width, initial-scale=1.0")
        #self.add_link("/assets/bb_tc_dbg.css?v=4")
        #self.add_link("/assets/bb_tc.css?v=4")
        #self.add_head_raw("<link rel='stylesheet' href='/assets/bb_tc_dbg.css?v=2'>")
        #self.add_head_raw("<link rel='stylesheet' href='/assets/bb_tc.css?v=2'>")
        #self.add_script("/main.js", defer=True)
        page.clear()
        page._render()
        # --- Очистка старого рендера ---
        if self.root:
            self.root.Canvas.clear()
        from bb_ctrl_custom import TCustomControl
        self.root = TCustomControl(None, "BigFather")
        self.root.text("<!DOCTYPE html>\n")
        self.root.tg("html", None, 'lang="en"')
        self.render_head(self.root)
        self.root.tg("body")
        self.render_body(self.root, page)
        self.root.etg("body")
        self.root.etg("html")
        self.renumber_dom()
        return self.root.Canvas

    def render_body(self, root: "TCustomControl", page: "TPage"):
        layout_canvas = None
        #self.log("render_body", f"STEP_01")
        if getattr(page, "layout", None):
            layout = self.Layouts.get(page.layout)
            if layout:
                layout.clear()
                layout._render()
                self.log("render_body", f"📘 Layouts available: {list(self.Layouts.keys())}")
                self.log("render_body", f"🔍 Page '{page.Name}' requests layout '{page.layout}'")
                layout_canvas = layout.Canvas
            else:
                self.log("render_body", f"⚠️ layout '{page.layout}' not found — fallback to bare page")
        # ---
        if layout_canvas:
            for item in layout_canvas:
                if isinstance(item, str) and item == layout.slot_marker:
                    root.Canvas.extend(page.Canvas)
                else:
                    root.Canvas.append(item)
        else:
            root.Canvas.extend(page.Canvas)
    # ---
    def render_head(self, root: "TCustomControl"):
        root.tg("head")
        root._tg("title", self.header["title"])

        # metas
        for name, content in self.header.get("meta", []):
            if str(name).lower() == "charset":
                root.Canvas.append(f'<meta charset="{content}">')
            else:
                root.Canvas.append(f'<meta name="{name}" content="{content}">')

        # ---- CSS: форсированный порядок ---------------------------------------
        links = list(self.header.get("links", []))  # [(rel, href), ...]

        def weight(href: str) -> int:
            h = (href or "").lower()
            if "bb_tc-dbg.css" in h or "bb_tc_dbg.css" in h:  # debug — самый последний
                return 500
            if "bb_tc.css" in h:  # базовый tc — перед debug
                return 400
            if h.endswith("style.css") or "/style.css" in h:  # твой кастом — перед tc
                return 350
            if "tabler" in h:  # внешние — первыми
                return 100
            return 300  # прочее

        links_sorted = sorted(enumerate(links), key=lambda ih: (weight(ih[1][1]), ih[0]))
        for _, (rel, href) in links_sorted:
            root.Canvas.append(f"<link rel='{rel}' href='{href}'>")

        # inline <style> и сырье — после <link>
        for css in self.header.get("styles", []):
            root._tg("style", css)
        for raw in self.header.get("styles_raw", []):
            root.text(raw)
        # scripts
        for src, defer in self.header.get("scripts", []):
            d = " defer" if defer else ""
            root.Canvas.append(f"<script src='{src}'{d}></script>")

        root.etg("head")
    # ---
    def reset_header(self):
        """
        Готовит шапку <head> к свежему рендеру.
        title оставляем, а накопленный мусор чистим.
        """
        self.header["meta"] = []
        self.header["links"] = []
        self.header["scripts"] = []
        self.header["styles"] = []
    # ---
    def add_head_raw(self, raw_html: str):
        """
        Кладёт кусок сырых head-тегов (обычно <style>...</style>)
        в self.header["styles"] без экранирования.
        Вызывается один раз для debug css.
        """
        if "styles_raw" not in self.header:
            self.header["styles_raw"] = []
        self.header["styles_raw"].append(raw_html)
    # ------------------------------------------------------------------------------------------------------------------
    # ⚙️ Producing html text
    # ------------------------------------------------------------------------------------------------------------------
    def get_page(self) -> Optional["TPage"]:
        """
        Определяет и сохраняет активную страницу Tradition Core.
        Использует переменную окружения ACTIVE_PAGE для сохранения состояния.
        """
        self.log("get_page", f"DEBUG req('page')={req('page', None)} self.request.get={self.request.get}")
        self.echo(req('page', None))
        # 1️⃣ Получаем параметр запроса (если есть)
        page_name = req("page", None)

        # 2️⃣ Если параметра нет — читаем из ENV (_key)
        if not page_name:
            page_name = _key("ACTIVE_PAGE", "main")

        # 3️⃣ Проверяем, что такая страница есть
        if page_name not in self.Pages:
            self.debug("get_page", f"⚠️ page '{page_name}' not found, fallback to main")
            page_name = "main"

        # 4️⃣ Сохраняем активную страницу в ENV
        _set_key("ACTIVE_PAGE", page_name)
        self.current_page = page_name

        # 5️⃣ Логируем результат
        self.debug("get_page", f"🧭 current_page={self.current_page}")

        return self.Pages.get(page_name)

    def get_page_html(self, request) -> str:
        """
        🧩 Генерирует HTML-страницу Tradition Core 2025
        на основе данных из request.
        Только подготавливает структуру — без запуска ядра.
        """
        # 1️⃣ Создаём безопасный контейнер запроса
        self.request = TRequest(str(request.rel_url))
        page = self.get_page()
        self.debug("save_website", f"Saving page: {page.Name if page else 'None'}")
        if not page:
            self.log("save_website", "⚠️ no active page to render")
            return
        # 2️⃣ render всех элементов документа 💡
        items = self.render(page)
        # 3️⃣ создание html-кода и передача web-серверу для вывода в браузер
        return self.html(items)# 🎁➡️🌍 Hello World!
    # ⛳ ... HTML ...
    def html(self, items: list[str]) -> str:
        """
        Собирает финальный HTML из Canvas, красиво форматируя:
        - блочные теги → с отступами;
        - inline-теги → в одну строку;
        - void-теги (meta, link, br, img, hr, input, area, base, col, embed, param, source, track, wbr) → без изменения отступа.
        """
        self._tag_counter = 0
        self._tag_stack = []
        BLOCK_TAGS = {
            "html", "head", "body",
            "div", "form", "table", "tr",
            "ul", "ol",
            "header", "footer", "section", "nav"
        }

        INLINE_TAGS = {
            "title", "span", "a", "b", "i", "small",
            "button", "h1", "h2", "h3", "h4", "h5", "h6"
        }

        VOID_TAGS = {
            "area", "base", "br", "col", "embed", "hr",
            "img", "input", "link", "meta", "param",
            "source", "track", "wbr"
        }
        LIST_ITEM_TAGS = {"li"}  # 🜂 спец-режим TraditionDOM
        INDENT = "    "
        indent = 0
        lines: list[str] = []
        inline_open = False
        div_counter = 0
        for raw in items:
            line = str(raw).strip()
            if not line:
                continue
            # 🔹 ... Маркер BEGIN ...
            if line.startswith("<!-- __TAG_BEGIN__:"):
                body = line[len("<!-- __TAG_BEGIN__:"):-3].strip()
                parts = body.split(":")
                tag = parts[0] if len(parts) > 0 else "div"
                cls = parts[1] if len(parts) > 1 else "?"
                uid = parts[2] if len(parts) > 2 else "-"
                nr = parts[3] if len(parts) > 3 else "?"
                pad = INDENT * indent
                lines.append(f"{pad}<!-- BEGIN {tag}#{nr} {uid} ({cls}) -->")
                continue
            # 🔹 ... Маркер END ...
            if line.startswith("<!-- __TAG_END__:"):
                body = line[len("<!-- __TAG_END__:"):-3].strip()
                parts = body.split(":")
                tag = parts[0] if len(parts) > 0 else "div"
                cls = parts[1] if len(parts) > 1 else "?"
                uid = parts[2] if len(parts) > 2 else "-"
                nr = parts[3] if len(parts) > 3 else "?"
                pad = INDENT * indent
                lines.append(f"{pad}<!-- END {tag}#{nr} {uid} ({cls}) -->")
                continue
            # 🔹 ... Закрывающий тег ...
            if line.startswith("</"):
                tag_name = line[2:].split(">")[0].split()[0].lower()

                # 🜂 Закрываем <li>: просто доклеиваем </li> в ту же строку
                if tag_name in LIST_ITEM_TAGS:
                    if lines:
                        lines[-1] += line
                    inline_open = False
                    continue

                # 🜂 Закрываем inline (<a>, <span> и т.д.)
                if tag_name in INLINE_TAGS:
                    if lines:
                        lines[-1] += line
                    inline_open = False
                    continue

                # 🜂 Закрываем блочный (<div>, <ul>, <header>...)
                indent = max(indent - 1, 0)
                lines.append(f"{INDENT * indent}{line}")
                inline_open = False
                continue
            # 🔹 ... Открывающий или одиночный тег ...
            if line.startswith("<") and not line.startswith("</"):
                tn = line[1:].split(">")[0].split()[0].rstrip("/").lower()
                self_closing = line.endswith("/>") or tn in VOID_TAGS

                # 🜂 1) список элементов <li>
                if tn in LIST_ITEM_TAGS:
                    # каждый <li> всегда с новой строки, на текущем indent
                    lines.append(f"{INDENT * indent}{line}")
                    # считаем, что дальше может идти текст / <a> на той же строке
                    inline_open = not self_closing
                    continue

                # 🜂 2) обычные inline (a, span, ...)
                if tn in INLINE_TAGS:
                    # если перед нами только что открылся <li> — приклеиваем <a> к нему
                    if lines and lines[-1].lstrip().startswith("<li"):
                        lines[-1] += line
                    else:
                        # иначе — новый визуальный элемент внутри блока:
                        # новая строка, но без дополнительного уровня вложенности
                        base_indent = indent if indent >= 0 else 0
                        lines.append(f"{INDENT * base_indent}{line}")
                    inline_open = not self_closing
                    continue

                # 🜂 3) блочные
                lines.append(f"{INDENT * indent}{line}")
                if (tn in BLOCK_TAGS) and (not self_closing):
                    indent += 1
                inline_open = False
                continue
            # 🔹 ... текст ...
            if inline_open and lines:
                lines[-1] += line
            else:
                lines.append(f"{INDENT * indent}{line}")
        lines.append("")
        lines.append("<!-- Tradition Core 2025 | Rendered by TApplication -->")
        return "\n".join(lines)
    # ------------------------------------------------------------------------------------------------------------------
    # 🌐 DOM Registry API — TraditionDOM Tracker
    # ------------------------------------------------------------------------------------------------------------------
    def renumber_dom(self):
        """Сквозная нумерация тегов по фактическому порядку в Canvas, начиная с 1."""
        if not (self.root and getattr(self.root, "Canvas", None)):
            return

        mapping: dict[int, int] = {}
        new_nr = 1
        out: list[str] = []

        for line in self.root.Canvas:
            s = str(line)

            # BEGIN
            if s.startswith("<!-- __TAG_BEGIN__:"):
                # формат: <!-- __TAG_BEGIN__:{tag}:{Name}:{uid}:{nr} -->
                try:
                    old_nr = int(s.rsplit(":", 1)[1].strip(" -->"))
                    mapping.setdefault(old_nr, new_nr)
                    s = s[:s.rfind(":")] + f":{mapping[old_nr]} -->"
                    new_nr += 1
                except Exception:
                    pass
                out.append(s)
                continue

            # END
            if s.startswith("<!-- __TAG_END__:"):
                try:
                    old_nr = int(s.rsplit(":", 1)[1].strip(" -->"))
                    if old_nr in mapping:
                        s = s[:s.rfind(":")] + f":{mapping[old_nr]} -->"
                except Exception:
                    pass
                out.append(s)
                continue

            out.append(s)

        self.root.Canvas = out

        # синхронизируем реестр (если он вёлся)
        if getattr(self, "_dom_registry", None):
            new_registry = {}
            for old_nr, info in list(self._dom_registry.items()):
                new = mapping.get(old_nr)
                if new is not None:
                    info["nr"] = new
                    new_registry[new] = info
            # возможны теги без DEBUG-комментариев — просто перенесём что смогли
            self._dom_registry = dict(sorted(new_registry.items(), key=lambda kv: kv[0]))

    def register_tag(self, tag_info: dict[str, Any]) -> int:
        """Добавляет тег в глобальный реестр TraditionDOM."""
        self._dom_counter += 1
        tag_info["nr"] = self._dom_counter
        self._dom_registry[self._dom_counter] = tag_info
        return self._dom_counter

    def close_tag(self, nr: int):
        """Помечает тег как закрытый."""
        tag = self._dom_registry.get(nr)
        if tag:
            tag["close"] = True
            tag["open"] = False

    def get_dom_tree(self) -> dict[int, dict[str, Any]]:
        """Возвращает текущую карту DOM."""
        return self._dom_registry
    # ------------------------------------------------------------------------------------------------------------------
    # ⚙️ Close TApplication
    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        for mod in list(self.Modules.values()):
            try:
                if hasattr(mod, "close"):
                    mod.close()
            except Exception as e:
                self.log("close", f"⚠️ error closing {mod.Name}: {e}")
        self.Modules.clear()
        self.log("close", "🎬 Application stopped")

    def __repr__(self):
        return f"<TApplication loaded={self.loaded} pages={len(self.Pages)} modules={len(self.Modules)}>"

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
    def find(self, name: str):
        """
        Ищет компонент по имени в пределах приложения.
        Поиск идёт:
          1. среди верхнеуровневых Components,
          2. в глубину (через дочерние Components),
          3. в Pages (если применимо).
        Возвращает первый найденный компонент или None.
        """
        # 1. Прямой поиск на верхнем уровне
        if name in self.Components:
            return self.Components[name]

        # 2. Глубокий поиск по дереву компонентов
        stack = list(self.Components.values())
        while stack:
            node = stack.pop()
            if getattr(node, "Name", None) == name:
                return node
            for child in getattr(node, "Components", {}).values():
                stack.append(child)

        # 3. Поиск по страницам, если они зарегистрированы
        if name in self.Pages:
            return self.Pages[name]

        return None

    def find_by_id(self, target_id: str) -> Optional[TOwnerObject]:
        """Находит компонент по его ID (родословной)"""
        for component in self.iter_tree():
            if hasattr(component, 'id') and component.id() == target_id:
                return component
        return None
    # ------------------------------------------------------------------------------------------------------------------
    # ⚙️ ECHO
    # ------------------------------------------------------------------------------------------------------------------
    def echo(self, msg: str):
        """Добавляет строку в буфер Echo для вывода на страницу."""
        try:
            self.Echo.append(str(msg))
        except Exception as e:
            self.log("echo", f"❌ echo failed: {e}")

    def debug_on(self):
        """Включает подробные DEBUG-комментарии в HTML (BEGIN/END и mark())."""
        self.debug_mode = True

    def debug_off(self):
        """Выключает все DEBUG-комментарии в HTML выводе."""
        self.debug_mode = False

    def set_title(self, title: str):
        """Устанавливает <title> сайта."""
        self.header["title"] = str(title)

    def add_meta(self, name: str, content: str):
        """Добавляет <meta name="..." content="...">"""
        self.header["meta"].append((name, content))

    def add_link(self, href: str, rel: str = "stylesheet"):
        """Добавляет <link rel="..." href="...">"""
        self.header["links"].append((rel, href))

    def add_script(self, src: str, defer: bool = True):
        """Добавляет <script src="...">"""
        self.header["scripts"].append((src, defer))

    def add_style(self, css: str):
        """Добавляет встроенный <style>...</style>"""
        if "styles" not in self.header:
            self.header["styles"] = []
        self.header["styles"].append(css)
    # ------------------------------------------------------------------------------------------------------------------
    # Page Auto-generation Interface (для переопределения потомками)
    # ------------------------------------------------------------------------------------------------------------------
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

    # +++ МЕТОДЫ ДЛЯ РАБОТЫ С СОБЫТИЯМИ +++
    def ws_push_log(self, line: str):
        """
        Отправляет строку лога во все подключённые WebSocket-мониторы, если сервер поднят.
        Вызывается из log()/echo() и из TLogRouter (как subscriber).
        """
        # 🔍 DEBUG: фиксируем сам факт вызова ws_push_log
        print(f"[ws_push_log] GOT: {line}", flush=True)

        try:
            ws = getattr(self, "LocalWebSocketServer", None)
            if not isinstance(ws, TLocalWebSocketServer):
                return

            # используем сохранённый главный event loop
            loop = getattr(self, "_loop", None)
            if loop is None:
                # приложение ещё не в async-контексте или loop не сохранён —
                # просто молча выходим (логи хотя бы в консоль уже ушли)
                return

            def _send():
                asyncio.create_task(ws.send_log_to_monitors(line))

            # безопасно вызываем из любого потока (в т.ч. из потока TLogRouter)
            loop.call_soon_threadsafe(_send)

        except Exception as e:
            # UI не должен ломать ядро логгера
            print(f"[ws_push_log] ERROR: {e}")

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
    def subscribe_channel(self, target_id: str, channel: TwsDataChannel, symbols: List[str] = None, **filters) -> bool:
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

    def run_web(self, host="0.0.0.0", port=8081):
        """Создаёт и запускает системный WebSocket-сервер."""
        if not getattr(self, "LocalWebSocketServer", None):
            from bb_ws_extended import TLocalWebSocketServer
            self.LocalWebSocketServer = TLocalWebSocketServer(self, host, port)
            self.log("run_web", f"🌐 LocalWebSocketServer created on {host}:{port}")

        if not self.LocalWebSocketServer.active:
            self.LocalWebSocketServer.open()
            self.log("run_web", "🟢 LocalWebSocketServer started")

        return self.LocalWebSocketServer

    def run_db(self):
        """
        Запускает системный стек Tradition Database Core:
        Session → Database → Config → Schema
        """
        from bb_db import TSession, TDatabase, TConfig, TSchema, TDbEvents

        # --- Session ---
        if not getattr(self, "Session", None):
            self.Session = TSession(self)
            self.log("run_db", "🧩 Session component created")

        # --- Database ---
        if not getattr(self, "Database", None):
            self.Database = TDatabase(self)
            self.log("run_db", "💾 Database component created")

        # --- Config ---
        if not getattr(self, "Config", None):
            self.Config = TConfig(self)
            self.log("run_db", "⚙️ Config component created")

        # --- Schema ---
        if not getattr(self, "Schema", None):
            self.Schema = TSchema(self)
            self.log("run_db", "📘 Schema component created")

        # --- DbEvents ---
        if not getattr(self, "DbEvents", None):
            self.DbEvents = TDbEvents(self)
            self.log("run_db", "📘 DbEvents component created")

        # === Закон Tradition: четыре затвора ===
        try:
            self.Session.open()
            self.Database.open()
            self.Config.open()
            self.Schema.open()
            self.DbEvents.open()
            self.log("run_db", "✅ Database stack fully initialized")
        except Exception as e:
            self.fail("run_db", f"❌ initialization failed: {e}", type(e))

        return self.Database
    # ------------------------------------------------------------------------------------------------------------------
    # ⚙️ run_web_server() - Запуск Web Server`а
    # ------------------------------------------------------------------------------------------------------------------
    async def run_web_server(self, host: str = "0.0.0.0", port: int = 8081):
        """HTTP-сервер: динамически рендерит страницу через get_page_html(request)."""
        from aiohttp import web
        import asyncio, traceback
        from html import escape as _esc
        import gc

        gc.collect()
        async def handle(request: "web.Request"):
            # --- Игнорируем служебные запросы браузера ---
            url = str(request.rel_url)
            if url.endswith((".css", ".js", ".ico")):
                self.debug("handle", f"⏭ Ignored static file request: {url}")
                return web.Response(status=204)  # просто "ОК", без тела

            # ⤵️ /__act?aid=... — выполняем зарегистрированное действие и выходим
            if request.rel_url.path == "/__act":
                aid = request.query.get("aid", "")
                redirect = self.actions.dispatch(aid) if aid else None
                if redirect:
                    raise web.HTTPFound(redirect)
                return web.Response(status=204)

            try:
                # зафиксировать запрос в безопасном контейнере
                self.request = TRequest(str(request.rel_url))
                self.echo(f"🌐 GET {request.rel_url}")

                # вызвать твой динамический конструктор
                if asyncio.iscoroutinefunction(self.get_page_html):
                    html = await self.get_page_html(request)
                else:
                    html = self.get_page_html(request)

            except Exception as e:
                tb = _esc(traceback.format_exc())
                html = f"<h2>🔥 Render error</h2><pre>{_esc(str(e))}</pre><hr><pre>{tb}</pre>"

            return web.Response(text=html, content_type="text/html", charset="utf-8")

        app = web.Application()
        app.router.add_get("/{tail:.*}", handle)
        app.router.add_post("/{tail:.*}", handle)  # если вдруг будет POST

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        self.log("run_web_server", f"✅ Listening on http://{host}:{port}")

        # держим сервер живым
        while True:
            await asyncio.sleep(3600)

    def detect_mode(self) -> str:
        """
        Определяет, в каком режиме должна работать система:
        - cli  → запуск с параметром --url
        - server → обычный запуск или --serve
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--url", help="CLI mode: generate static HTML by URL")
        parser.add_argument("--serve", action="store_true", help="Run internal web server")
        args, _ = parser.parse_known_args()

        # 💡 Сохраняем для дальнейшего использования
        self.args = args

        if args.url:
            self.mode = "cli"
        elif args.serve:
            self.mode = "server"
        else:
            self.mode = "server"

        self.echo(f"🔍 detect_mode(): {self.mode}")
        return self.mode
    # ------------------------------------------------------------------------------------------------------------------
    # 🗑️ Корзина - Карантин
    # ------------------------------------------------------------------------------------------------------------------
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
# ----------------------------------------------------------------------------------------------------------------------
# ⚙️ Фасады для TApplication.request
# ----------------------------------------------------------------------------------------------------------------------
def req(key: str, default: str = "") -> str:
    """Возвращает строковый параметр из текущего запроса (GET/POST и т.д.)."""
    try:
        app = TApplication.app()
        req_obj = app.request
        # поддержка словаря и метода .get()
        if isinstance(req_obj.get, dict):
            return str(req_obj.get.get(key, default))
        else:
            return str(req_obj.get(key, default))
    except Exception:
        return str(default)

def req_int(key: str, default: int = 0) -> int:
    """Возвращает параметр как int (при ошибке — default)."""
    try:
        return int(float(req(key, default)))
    except Exception:
        return int(default)

def req_float(key: str, default: float = 0.0) -> float:
    """Возвращает параметр как float (при ошибке — default)."""
    try:
        return float(req(key, default))
    except Exception:
        return float(default)

def req_bool(key: str, default: bool = False) -> bool:
    """
    Возвращает параметр как bool.
    True → 1, true, yes, on
    False → 0, false, no, off, none, ''
    """
    val = str(req(key, str(default))).strip().lower()
    if val in ("1", "true", "yes", "on", "y", "t"):
        return True
    if val in ("0", "false", "no", "off", "n", "none", ""):
        return False
    try:
        return bool(int(val))
    except Exception:
        return bool(default)
# ======================================================================================================================
# 📁🌄 bb_application.py 🜂 The End — See You Next Session 2025 💹 493 -> 818 -> 931 -> 1035
# ======================================================================================================================