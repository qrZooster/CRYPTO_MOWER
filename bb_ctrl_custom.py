# ======================================================================================================================
# 📁 file        : bb_ctrl_custom.py — Базовый визуальный компонент и фундамент UI (заготовка)
# 🕒 created     : 02.11.2025 15:02
# 🎉 contains    : TCustomControl (перенесёшь сюда), helpers рендера/подсветки/uid/id (перенесёшь сам)
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
import hashlib
import base64
import re
from typing import Optional, Dict, Any
from datetime import datetime
from bb_sys import *
from bb_ctrl_sizes import TSizeMixin, ATOM_SIZES
# 💎🧩⚙️ ... __ALL__ ...
__all__ = ["TCustomControl", "TCompositeControl", "TFlex_Tr", "TFlex_Td", "ATOM_SIZES"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCustomControl — базовый визуальный компонент
# ----------------------------------------------------------------------------------------------------------------------
class TCustomControl(TSizeMixin, TComponent):
    prefix = "ctrl"  # базовый префикс для uid
    # 💎 теги которые получают uid
    TAGS_WITH_ID = {
        "div", "section", "nav", "table", "tr", "td", "form",
        "button", "input", "span",
        "h1", "h2", "h3", "h4", "h5", "h6"
    }
    # 💎 теги которые помечаются BEGIN - END плашками в коде html во время отладки
    DEBUG_TAGS = {
        "header", "footer",
        "div", "section", "nav", "table", "form",
        "ul"
    }
    # 💎🔰 Palette library: каждый элемент — [light, mid, bright, extra]
    _MARK_PALETTES = {
        "red": ["rgba(255,0,0,0.15)", "rgba(255,0,0,0.30)", "rgba(255,0,0,0.60)", "rgba(255,0,0,0.90)"],
        "maroon": ["rgba(128,0,32,0.15)", "rgba(128,0,32,0.30)", "rgba(128,0,32,0.60)", "rgba(128,0,32,0.90)"],
        "fuchsia": ["rgba(255,0,255,0.15)", "rgba(255,0,255,0.30)", "rgba(255,0,255,0.60)", "rgba(255,0,255,0.90)"],
        "purple": ["rgba(180,0,255,0.15)", "rgba(180,0,255,0.30)", "rgba(180,0,255,0.60)", "rgba(180,0,255,0.90)"],
        "olive": ["rgba(128,128,0,0.15)", "rgba(128,128,0,0.30)", "rgba(128,128,0,0.60)", "rgba(128,128,0,0.90)"],
        "green": ["rgba(0,200,0,0.15)", "rgba(0,200,0,0.30)", "rgba(0,200,0,0.60)", "rgba(0,200,0,0.90)"],
        "teal": ["rgba(0,128,128,0.15)", "rgba(0,128,128,0.30)", "rgba(0,128,128,0.60)", "rgba(0,128,128,0.90)"],
        "blue": ["rgba(0,100,255,0.15)", "rgba(0,100,255,0.30)", "rgba(0,100,255,0.60)", "rgba(0,100,255,0.90)"],
        "aqua": ["rgba(0,170,255,0.15)", "rgba(0,170,255,0.30)", "rgba(0,170,255,0.60)", "rgba(0,170,255,0.90)"],
        "gray": ["rgba(80,80,80,0.15)", "rgba(80,80,80,0.30)", "rgba(80,80,80,0.60)", "rgba(80,80,80,0.90)"],
    }
    # 💎 системные цвета → руками только
    _MARK_RESERVED = ["red", "gray"]
    # 💎 кольцевая ротация для mark() без аргументов
    _MARK_PALETTE_ROTATION = ["green", "maroon", "blue", "olive","purple", "teal",  "fuchsia", "aqua"]
    # 💎 таблица для _LEVEL_TO_SHADE остаётся как есть
    _LEVEL_TO_SHADE = {
        "grid": {0: "light", 1: "mid", 2: "bright"},
        "table": {0: "light", 1: "mid", 2: "bright"},
        "form": {0: "light", 1: "mid", 2: "bright"},
        "card": {0: "light", 1: "mid", 2: "bright"},
        "panel": {0: "light", 1: "bright"},  # panel: 0 (root), 1 (td)
        "menu": {0: "light", 1: "bright"},
        "_SINGLE_": {0: "bright"},
    }
    # 💎🔰 насыщенность цвета палитры
    _SHADE_INDEX = {"light": 0, "mid": 1, "bright": 2}
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner=None, Name: str | None = None):
        super().__init__(Owner, Name)
        # --- Дерево UI ---
        self.last_render_id: int = -1
        self.Canvas: list[str | "TCustomControl"] = []
        # --- Корневой тег этого контрола ---
        # единый источник правды для классов/стилей/атрибутов
        self.classes: list[str] = []  # add_class() пишет сюда
        self.styles: list[str] = []   # add_style() пишет сюда
        self.attrs: list[str] = []    # add_attr() пишет сюда (сырой "data-x='1'")
        # --- debug / mark() (ленивая подсветка)
        self._mark_enabled: bool = False
        self._mark_palette: list[str] | None = None
        self._mark_root: "TCustomControl" | None = None
        # uid
        if self.app().debug_mode:
            self.uid = f"{self.prefix}-{self.short_hash(self.id())}"
        else:
            self.uid = self.short_hash(self.id())
        # автоподключение к родителю
        if Owner and hasattr(Owner, "add_control"):
            Owner.add_control(self)
        # ⬇️ короткие под-id
        self._id_seq: int = 0  # глобальный счётчик внутренних тегов (per-render)
        self._id_map: dict[str, str] = {}  # стабильные ключи → под-id (например 'b' для бейджа)
        self._root_id_pending: bool = False  # следующий tg() — корневой
        self._root_inject_pending: bool = False
        self._root_class_inject: str | None = None
        self._root_attr_inject: str | None = None
        self._root_after_open_html: str | None = None
        # ---
        self.add_class(self.prefix)
        self.do_init()

        # ... 🔊 ...
        #self.log("__init__", f"{self.__class__.__name__} {self.Name} created uid={self.uid}")
        self.log("__init__", f"{self.__class__.__name__}[{self.prefix}] [{self.Name}] created")
        # ⚡🛠️ TCustomControl ▸ End of __init__

    def __init_subclass__(cls, **kwargs):
        # 1) html() запрещён - Запрещаем потомкам переопределять html(). Это защита единой точки вывода HTML.
        super().__init_subclass__(**kwargs)
        if "html" in cls.__dict__:
            raise TypeError(f"❌ {cls.__name__} пытается переопределить html(), это запрещено!")
        # 2) __init__() запрещён для всех, кроме базовых контейнеров
        base_init_whitelist = {"TCustomControl", "TCompositeControl", "TFlex_Tr", "TFlex_Td"}
        if "__init__" in cls.__dict__ and cls.__name__ not in base_init_whitelist:
            raise TypeError(
                f"❌ {cls.__name__} не должен переопределять __init__(). "
                f"Используй do_init() для дополнительной инициализации."
            )

    def do_init(self):
        pass

    def _add_control_basic(self, ctrl: "TCustomControl"):
        """Обычное добавление ребёнка в этот контрол."""
        if ctrl.Name in self.Controls:
            self.fail("add_control", f"duplicate control {ctrl.Name}", ValueError)
        self.Controls[ctrl.Name] = ctrl
        return ctrl

    def add_control(self, ctrl: "TCustomControl"):
        """
        Базовая реализация: просто регистрирует ребёнка.
        Контейнеры (TCompositeControl и потомки) переопределяют add_control().
        """
        return self._add_control_basic(ctrl)

    def text(self, html: str):
        self.Canvas.append(str(html))

    def tg(self, tag: str, cls: str | None = None, attr: str | None = None):
        app = self.app()
        nr = None
        if app:
            if not hasattr(self, "_tag_stack"):
                self._tag_stack = []
            nr = app.register_tag({
                "id": getattr(self, "uid", "-"),
                "tag": tag,
                "class": self.__class__.__name__,
                "owner_name": getattr(self.Owner, "Name", None),
                "owner_id": getattr(self.Owner, "id", lambda: None)() if hasattr(self.Owner, "id") else None,
                "timestamp": datetime.now(),
                "open": True,
                "close": False,
                "children": [],
            })
            self._tag_stack.append(nr)

        if getattr(app, "debug_mode", False) and tag in self.DEBUG_TAGS:
            self.text(f"<!-- __TAG_BEGIN__:{tag}:{self.Name}:{self.uid}:{nr} -->")

        # инъекция классов/атрибутов для ПЕРВОГО тега (из _render атома)
        if getattr(self, "_root_inject_pending", False):
            cls = " ".join(filter(None, [cls, getattr(self, "_root_class_inject", None)])) or None
            attr = " ".join(filter(None, [attr, getattr(self, "_root_attr_inject", None)])) or None
            self._root_inject_pending = False
            self._root_class_inject = None
            self._root_attr_inject = None

        cls_part = f" class='{cls}'" if cls else ""
        attr_part = f" {attr}" if attr else ""

        # единая схема id: первый тег — uid, дальше uid-1, uid-2, ...
        id_part = ""
        if tag.lower() in self.TAGS_WITH_ID:
            # если id уже передан через attr, авто-id не ставим
            provided_id = (attr or "").find(" id=") >= 0 or (attr or "").startswith("id=")
            if not provided_id:
                if getattr(self, "_id_seq", None) is None:
                    self._id_seq = 0
                if self._id_seq == 0:
                    tag_id = self.uid
                else:
                    tag_id = f"{self.uid}-{self._id_seq}"
                id_part = f" id='{tag_id}'"
                self._id_seq += 1

        self.text(f"<{tag}{id_part}{cls_part}{attr_part}>")

    def etg(self, tag: str):
        app = self.app()
        nr = None
        if hasattr(self, "_tag_stack") and self._tag_stack:
            nr = self._tag_stack.pop()
            if app:
                app.close_tag(nr)
        self.text(f"</{tag}>")
        if getattr(app, "debug_mode", False) and nr is not None and tag in self.DEBUG_TAGS:
            self.text(f"<!-- __TAG_END__:{tag}:{self.Name}:{self.uid}:{nr} -->")

    def br(self, count: int = 1):
        try:
            n = max(0, int(count))
        except Exception:
            n = 1
        if n > 0:
            self.Canvas.append("<br/>" * n + "\n")

    def h(self, count: int = 1, s: str | None = None, cls: str | None = None, attr: str | None = None):
        try:
            n = max(1, min(6, int(count)))
        except Exception:
            n = 1
        self.tg(f"h{n}", cls, attr)
        if s is not None:
            self.text(s)
        self.etg(f"h{n}")

    # фасады (сахар)
    def div(self, cls=None, attr=None):
        self.tg("div", cls, attr)

    def ediv(self):
        self.etg("div")

    def table(self, cls=None, attr=None):
        self.tg("table", cls, attr)

    def etable(self):
        self.etg("table")

    def tr(self, cls=None, attr=None):
        self.tg("tr", cls, attr)

    def etr(self):
        self.etg("tr")

    def td(self, cls=None, attr=None):
        self.tg("td", cls, attr)

    def etd(self):
        self.etg("td")

    def _tg(self, tg: str, src: str):
        """Оборачивает текст src в тег tg."""
        self.tg(tg)
        self.text(src)
        self.etg(tg)
    # 🌱 ...Параметры корневого тега...
    def root_tag(self) -> str:
        """
        Возвращает HTML-тег, которым оборачивается корень этого контрола. По умолчанию это <div>, но потомки могут переопределить.
        """
        return "div"
    # 🌱🧲 ...Публичные билд-хелперы корневого тега...
    def add_class(self, *tokens):
        """
        Идемпотентное добавление css-классов.
        - сохраняет исходный порядок,
        - не добавляет дубликаты,
        - принимает как отдельные токены, так и строки с пробелами.
        """
        if not hasattr(self, "classes"):
            self.classes = []

        for tok in tokens:
            if not tok:
                continue
            for t in str(tok).split():
                if t and t not in self.classes:
                    self.classes.append(t)

    def remove_class(self, *tokens):
        """Удаляет css-классы, если они были навешены ранее."""
        if not hasattr(self, "classes") or not self.classes:
            return

        for tok in tokens:
            if not tok:
                continue
            for t in str(tok).split():
                if t and t in self.classes:
                    self.classes.remove(t)

    def add_style(self, style_fragment: str | None):
        """
        Добавляет кусок inline-style. Не затирает предыдущее состояние. Если фрагмент не заканчивается ; — добавляем его.
        """
        if not style_fragment:
            return
        frag = style_fragment.strip()
        if not frag.endswith(";"):
            frag += ";"
        self.styles.append(frag)

    def add_attr(self, raw: str | None):
        """
        Добавляет сырой атрибут в корневой тег. Пример: "data-role='main'" или "aria-live='polite'". Храним готовую строку.
        """
        if not raw:
            return
        self.attrs.append(str(raw).strip())
    # 💠 ...Flex helpers...
    def flex_box(
        self,
        direction: str = "row",   # "row" | "column" | "row-reverse" | "column-reverse"
        gap: str | None = None,   # "1rem", "0.5rem", "7px"
        width: str | None = None, # "100%", "50%", "320px"
        height: str | None = None,# "100%", "auto", "calc(100vh-80px)"
        wrap: str | None = None,  # "wrap", "nowrap", "wrap-reverse"
        justify: str | None = None,  # "start","end","center","between","around","evenly"
        align: str | None = None     # "start","end","center","baseline","stretch"
    ):
        """
        Делает этот контрол flex-контейнером. Сначала пытаемся выразить настройку готовыми utility-классами (d-flex, flex-row, w-100...). Если подходящего класса нет — уходим в inline-style через add_style().
        """
        # 1. display:flex
        # Bootstrap / Tabler: d-flex
        self.add_class("d-flex")
        # 2. flex-direction
        dir_map = {
            "row": "flex-row",
            "row-reverse": "flex-row-reverse",
            "column": "flex-column",
            "column-reverse": "flex-column-reverse",
        }
        if direction in dir_map:
            self.add_class(dir_map[direction])
        else:
            self.add_style(f"flex-direction:{direction};")
        # 3. gap
        gap_class_map = {
            "0": "gap-0",
            "0.25rem": "gap-1",
            "0.5rem": "gap-2",
            "1rem": "gap-3",
            "1.5rem": "gap-4",
            "3rem": "gap-5",
        }
        if gap:
            if gap in gap_class_map:
                self.add_class(gap_class_map[gap])
            else:
                self.add_style(f"gap:{gap};")
        # 4. width / height
        if width:
            if width == "100%":
                self.add_class("w-100")
            else:
                self.add_style(f"width:{width};")
        if height:
            if height == "100%":
                self.add_class("h-100")
            else:
                self.add_style(f"height:{height};")
        # 5. flex-wrap
        wrap_map = {
            "wrap": "flex-wrap",
            "nowrap": "flex-nowrap",
            "wrap-reverse": "flex-wrap-reverse",
        }
        if wrap:
            if wrap in wrap_map:
                self.add_class(wrap_map[wrap])
            else:
                self.add_style(f"flex-wrap:{wrap};")
        # 6. justify-content
        justify_map = {
            "start": "justify-content-start",
            "end": "justify-content-end",
            "center": "justify-content-center",
            "between": "justify-content-between",
            "around": "justify-content-around",
            "evenly": "justify-content-evenly",
        }
        if justify:
            if justify in justify_map:
                self.add_class(justify_map[justify])
            else:
                self.add_style(f"justify-content:{justify};")
        # 7. align-items
        align_map = {
            "start": "align-items-start",
            "end": "align-items-end",
            "center": "align-items-center",
            "baseline": "align-items-baseline",
            "stretch": "align-items-stretch",
        }
        if align:
            if align in align_map:
                self.add_class(align_map[align])
            else:
                self.add_style(f"align-items:{align};")

    def flex_cell(
        self,
        grow: int | None = None,     # насколько ячейка тянется (обычно 1)
        padding: str | None = None,  # "4px", "0.5rem"
        border: str | None = None    # "2px dashed red"
    ):
        """
        Делает этот контрол flex-элементом (ячейкой в строке). Сначала пробуем известный utility-класс (flex-grow-1 и т.п.), иначе задаём inline-style.
        """
        # 1. flex-grow / flex
        if grow is not None:
            if grow == 1:
                self.add_class("flex-grow-1")
            else:
                self.add_style(f"flex:{grow};")
        # 2. padding
        padding_class_map = {
            "0": "p-0",
            "0.25rem": "p-1",
            "0.5rem": "p-2",
            "1rem": "p-3",
            "1.5rem": "p-4",
            "3rem": "p-5",
        }
        if padding:
            if padding in padding_class_map:
                self.add_class(padding_class_map[padding])
            else:
                self.add_style(f"padding:{padding};")
        # 3. border
        if border:
            self.add_style(f"border:{border};")

    def _dbg_attrs(self) -> str:
        app = self.app()
        if not (app and getattr(app, "debug_mode", False)):
            return ""

        try:
            fam = (self._mark_family() or "").strip()
        except Exception:
            fam = ""

        owner_uid = getattr(getattr(self, "Owner", None), "uid", "")
        # «старые» короткие имена
        a_root = tc_attr_name("root")
        a_class = tc_attr_name("class")
        a_name = tc_attr_name("name")
        a_family = tc_attr_name("family")
        a_owner = tc_attr_name("owner")

        # ВОЗВРАЩАЕМ: и старые tc-*, и новые data-*
        return (
            f'{a_root}="1" '
            f'{a_class}="{self.__class__.__name__}" '
            f'{a_name}="{self.Name}" '
            f'{a_family}="{fam}" '
            f'{a_owner}="{owner_uid}" '
            f'data-tc-class="{self.__class__.__name__}" '
            f'data-tc-name="{self.Name}" '
            f'data-tc-family="{fam}" '
            f'data-tc-owner="{owner_uid}"'
        )
    # ..................................................................................................................
    # 🎨 Рендеринг страницы
    # ..................................................................................................................
    def _render(self):
        tag = self.root_tag()
        mark_info = self._resolve_mark_info()
        # ⬇️ важный момент: предсказуемость коротких id на каждый рендер
        self._id_seq = 0
        self._root_id_pending = True
        class_list = list(self.classes)

        app = self.app()
        # --- проверка на дубликаты
        cur_id = getattr(app, "render_id", 0)
        if self.last_render_id == cur_id:
            # уже рендерились в этом цикле — просто выходим
            return
        self.last_render_id = cur_id
        # ---
        dbg = bool(app and getattr(app, "debug_mode", False))
        if dbg and mark_info:
            palette = mark_info.get("palette_name")
            shade = mark_info.get("shade_idx")
            class_list.append(tc_dbg_class("frame"))  # было tcmp-frame
            if palette is not None and shade is not None:
                class_list.append(tc_dbg_class("f", str(palette), str(shade)))  # было tcmp-f-...

        class_txt = " ".join(c for c in class_list if c) or None

        style_entries = list(self.styles)
        geometry_box = None
        if hasattr(type(self), "box_style"):
            try:
                geometry_box = getattr(self, "box_style", None)
            except Exception:
                geometry_box = None
        if isinstance(geometry_box, dict) and geometry_box:
            for prop, value in geometry_box.items():
                if not value:
                    continue
                prefix = f"{prop}:"
                style_entries = [s for s in style_entries if not s.strip().startswith(prefix)]
                style_entries.append(f"{prop}:{value};")

        style_txt = " ".join(s for s in style_entries if s)

        # meta-атрибуты остаются под `tc-*`
        attr_parts = []
        if style_txt:
            attr_parts.append(f"style='{style_txt}'")
        attr_parts.extend(str(a) for a in self.attrs)
        if dbg:
            dbg_attrs = getattr(self, "_dbg_attrs", lambda: "")()
            if dbg_attrs:
                attr_parts.append(dbg_attrs)
        attr_str = " ".join(attr_parts) if attr_parts else None

        self.tg(tag, cls=class_txt, attr=attr_str)
        try:
            self.render()
        except Exception as e:
            self.log("_render", f"⚠ render() failed: {e}")

        if dbg:
            try:
                self._render_badge(mark_info)  # внутри используйте tc_badge_classes()
            except Exception as e:
                self.log("_render", f"⚠ badge render failed: {e}")

        self.etg(tag)

    def render(self):
        """
        Базовый рендер для атомарных контролов — ничего не рисует.
        Контейнеры (TCompositeControl) переопределяют этот метод.
        """
        pass

    # --- внутри TCustomControl._render_badge (не удаляя остальное) ---
    def _render_badge(self, mark_info: dict[str, str] | None):
        if not mark_info or not mark_info.get("show_badge", True):
            return
        pal = mark_info["palette_name"]
        label = mark_info["badge_label"]
        badge_cls = tc_badge_classes(pal)  # "tc-dbg-badge tc-dbg-b-<pal>"
        # Простой стабильный бейдж-сосед: без спец-позиций для атомов
        self.tg("div", cls=badge_cls, attr=f"id='{self.sub_id('badge')}'")
        self.text(label)
        self.etg("div")

    @staticmethod
    def _to_b36(n: int) -> str:
        n = max(0, int(n))
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        s = ""
        while True:
            n, r = divmod(n, 36)
            s = digits[r] + s
            if n == 0:
                break
        return s

    def _next_sub_id(self) -> str:
        """Короткий авто-id для внутренних тегов: {uid}-{base36}."""
        self._id_seq += 1
        return f"{self.uid}-{self._to_b36(self._id_seq)}"

    def sub_id(self, key: str) -> str:
        """
        Стабильный под-id по ключу: {uid}-{token}.
        НИКОГДА не трогает _id_seq и не генерит порядковые id.
        Примеры: 'badge' -> '<uid>-b'
        """
        token = str(key).strip().lower()
        aliases = {"badge": "b"}
        token = aliases.get(token, token[:2] if len(token) > 2 else token or "x")

        if token not in self._id_map:
            self._id_map[token] = f"{self.uid}-{token}"
        return self._id_map[token]

    @staticmethod
    def short_hash(value: str, length: int = 5) -> str:
        """Возвращает короткий base32-хеш (только буквы и цифры, без спецсимволов)."""
        h = hashlib.sha1(value.encode("utf-8")).digest()
        b32 = base64.b32encode(h).decode("ascii").lower().strip("=")
        return b32[:length]

    def clear(self):
        """Полностью очищает содержимое страницы перед перерисовкой. Уничтожает дочерние контролы и Canvas."""
        self.release_children()
        setattr(self, "_auto_counters", {})
        # ... 🔊 ...
        self.log("clear", f"🧩 {self.__class__.__name__} '{self.Name}' fully cleared")

    def release_children(self):
        """
        Базовая версия: работает только с Components.
        Не знает ни про Controls, ни про Canvas.
        Композитные контролы расширяют эту логику в TCompositeControl.
        """
        for c in list(self.Components.values()):
            if hasattr(c, "release_children"):
                c.release_children()
            self.release_global(c)
            c.Owner = None

        self.Components.clear()
        # ... 🔊 ...
        self.log("release_children", f"{self.Name} children released (base)")
    # ..................................................................................................................
    # 🔰 mark* methods
    # ..................................................................................................................
    def _mark_family(self) -> str | None:
        """
        Возвращает имя семейства подсветки, к которому принадлежит контрол (grid/card/...).
        Базовый класс ничего не гадает. Потомки объявляют себя через атрибут класса MARK_FAMILY.
        """
        return getattr(self, "MARK_FAMILY", None)

    def _mark_level(self) -> int:
        """
        Возвращает уровень внутри семейства (0,1,2,...). Потомки объявляют себя через MARK_LEVEL.
        Если не указано — считаем 0.
        """
        return getattr(self, "MARK_LEVEL", 0)

    def mark(self, palette_name: str | None = None):
        """
        Включает debug-подсветку для этого узла как "корневого" узла семейства.
        НИКАКИХ inline-стилей тут больше нет.
        Мы просто сохраняем метаданные, которые потом дочерние контролы смогут прочитать.
        palette_name:
            "gray","red","purple","olive","green","teal","blue","aqua","maroon","fuchsia"
            или None → выберем эвристику.
        """

        app = self.app()
        if not (app and getattr(app, "debug_mode", False)):
            # вне debug режима вообще ничего не делаем
            return self

        fam = self._mark_family() or "_SINGLE_"

        # какой цвет брать по умолчанию
        if palette_name is None:
            # простая эвристика-чтоб красиво:
            if fam == "grid":
                palette_name = "gray"
            elif fam == "panel":
                palette_name = "fuchsia"
            elif fam == "card":
                palette_name = "olive"
            else:
                palette_name = "blue"

        # запоминаем, что этот узел — корень mark() для своего семейства
        self._mark_enabled = True  # сам факт "я помечен"
        self._mark_root = self  # чтобы дети знали чей бейдж рисовать
        self._mark_family_cached = fam  # чтобы не считать лишний раз
        self._mark_palette_name = palette_name  # имя палитры (gray/purple/...)

        # ВАЖНО: не трогаем self.styles, не пихаем border
        # ВАЖНО: не создаём бейдж тут, он нарисуется в _render_badge()
        return self

    def _resolve_mark_info(self) -> dict[str, object] | None:
        """
        Возвращает словарь с параметрами подсветки или None,
        если подсветки для этого узла нет.

        Формат:
        {
            "palette_name": "purple",
            "shade_idx":    1,           # => tcmp-f-purple-1
            "show_badge":   True/False,  # рисовать бейдж (только корень семейства уровня0)
            "badge_label":  "Panel1",    # текст бейджа
        }
        """

        app = self.app()
        if not (app and getattr(app, "debug_mode", False)):
            return None

        # 1. определяем семейство текущего контрола
        my_family = self._mark_family()
        if not my_family:
            my_family = getattr(self, "_mark_family_cached", None)
        if not my_family:
            my_family = "_SINGLE_"

        # 2. идём вверх по Owner, чтобы найти mark_root для этого семейства
        chain = []
        cur = self
        while cur is not None:
            chain.append(cur)
            cur = getattr(cur, "Owner", None)

        mark_root = None
        palette_name = None

        for node in chain:
            if getattr(node, "_mark_enabled", False):
                root_family = (
                        getattr(node, "_mark_family_cached", None)
                        or node._mark_family()
                        or "_SINGLE_"
                )
                if root_family == my_family:
                    mark_root = getattr(node, "_mark_root", node)
                    palette_name = getattr(node, "_mark_palette_name", None)
                    break

        if mark_root is None or palette_name is None:
            return None

        # 3. узнаём "яркость" по уровню
        level = self._mark_level()
        fam_map = self._LEVEL_TO_SHADE.get(my_family, {})
        shade_key = fam_map.get(level)
        if not shade_key:
            return None  # у семьи нет маппинга для этого уровня

        shade_idx = self._SHADE_INDEX.get(shade_key, 0)

        # 4. бейдж рисуем ТОЛЬКО если это сам корень и это уровень 0
        is_root_node = (self is mark_root) and (level == 0)

        return {
            "palette_name": palette_name,
            "shade_idx": shade_idx,
            "show_badge": is_root_node,
            "badge_label": mark_root.Name if is_root_node else "",
        }
    # 722 ->
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCompositeControl — базовый визуальный контейнерный контрол (старое имя сохранено для совместимости)
# ----------------------------------------------------------------------------------------------------------------------
class TCompositeControl(TCustomControl):
    prefix = "ctrl"
    """
    Базовый визуальный КОМПОЗИТНЫЙ блок.
    Может иметь детей и управлять раскладкой через active_control.
    Большинство сложных контролов (Grid, Panel, Td, Card и т.д.) унаследованы отсюда.
    """
    # ⚡🛠️ ▸ __init__()
    def __init__(self, Owner=None, Name: str | None = None):
        # контейнерное состояние — до super(), чтобы быть готовым к детям
        self._constructing: bool = True
        self.Controls: dict[str, TCustomControl] = {}
        self.f_active_control: "TCustomControl | None" = self
        # ---
        super().__init__(Owner, Name)
        # после do_init() больше не строимся
        self._constructing = False
        # ---
        self.log("__init__", f"TCompositeControl[{self.prefix}] {self.Name} created")

    @property
    def active_control(self) -> "TCustomControl":
        return self.get_active_control()

    @active_control.setter
    def active_control(self, value: "TCustomControl | None"):
        self.f_active_control = value

    def get_active_control(self) -> "TCustomControl":
        """
        Базовое поведение: либо явный f_active_control,
        либо сам контрол, если override не задан.
        Наследники могут переопределить этот метод и вообще не трогать f_active_control.
        """
        ac = getattr(self, "f_active_control", None)
        return ac or self

    # 🔹 Хук: какие дети считаются "структурными" (header/body/footer/слоты и т.п.)
    # По умолчанию — никого, контейнеры переопределяют.
    def structural_children(self) -> tuple["TCustomControl", ...]:
        return ()

    # 🔹 Удобная проверка: этот ctrl — один из структурных?
    def is_structural_child(self, ctrl: "TCustomControl") -> bool:
        return ctrl in self.structural_children()

    def add_control(self, ctrl: "TCustomControl"):

        # 1) Во время конструирования и для служебных детей
        if getattr(self, "_constructing", False) or self.is_structural_child(ctrl):
            return self._add_control_basic(ctrl)

        # 2) Определяем цель: куда реально должен попасть ребёнок
        target = self.active_control
        self.log(
            "add_control",
            f"[add_control] self={self.prefix}:{self.Name}, "
            f"target={target.prefix}:{target.Name}, "
            f"ctrl={ctrl.prefix}:{ctrl.Name}, "
            f"constructing={self._constructing}, "
            f"structural={self.is_structural_child(ctrl)}"
        )
        # 2a) Если target == self — просто добавляем как обычно
        if target is self:
            return self._add_control_basic(ctrl)

        # 3) Роутим в другой контейнер (layout.header/body и т.п.)
        if hasattr(self, "Components") and ctrl.Name in self.Components:
            del self.Components[ctrl.Name]
        if hasattr(self, "Controls") and ctrl.Name in self.Controls:
            del self.Controls[ctrl.Name]

        ctrl.Owner = target
        if hasattr(target, "Components"):
            target.Components[ctrl.Name] = ctrl

        # 4) На target больше НЕ роутим, просто кладём внутрь
        return target.add_control(ctrl)
        #return target._add_control_basic(ctrl)

    def control(self, ctrl: "TCustomControl"):
        if ctrl.Name in self.Controls:
            self.fail("control", f"duplicate control {ctrl.Name}", ValueError)
        self.Controls[ctrl.Name] = ctrl
        self.Canvas.append(ctrl)
        return ctrl
    # ..................................................................................................................
    # 🎨 Рендеринг для композитных контролов
    # ..................................................................................................................
    def render_children(self):
        """Отрисовывает всех дочерних контролов и вносит их Canvas в текущий Canvas."""
        #seen = set()
        for child in self.Controls.values():
            if hasattr(child, "_render"):
                child._render()
            else:
                child.render()
            self.Canvas.extend(child.Canvas)

    def render(self):
        """
        Создаёт DOM-дерево для композита: по умолчанию просто оборачивает детей.
        Потомки могут переопределять, но чаще достаточно переопределять только render(),
        а внутри вызывать super().render() или render_children().
        """
        self.render_children()
    # ..................................................................................................................
    # 🧹 Управление визуальными детьми
    # ..................................................................................................................
    def release_children(self):
        """
        Расширенная версия для композитных контролов:
        - сначала базовая логика (Components),
        - затем чистим визуальные структуры Controls и Canvas.
        """
        # 1) системные/логические компоненты
        super().release_children()

        # 2) визуальные дети
        self.Controls.clear()
        self.Canvas.clear()

        self.log("release_children", f"{self.Name} children released (composite)")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TFlex_Tr — гибкая "строка панели" (flex-row контейнер для TFlex_Td)
# ----------------------------------------------------------------------------------------------------------------------
class TFlex_Tr(TCompositeControl):
    prefix = "flex_tr"
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        """
        Горизонтальная полоса (flex-row), содержащая набор ячеек TFlex_Td.
        Поведение похоже на строку грида, но без жёсткой сетки.
        """
        # --- Контейнер ячеек строки ---
        # Список ячеек (TFlex_Td) в порядке добавления.
        self.Tds: list[TFlex_Td] = []
        # первая колонка по умолчанию — td(0)
        self.td()  # создаёт TFlex_Td(self) и кладёт в self.Tds
        # --- Геометрия строки как flex-контейнера ---
        # По умолчанию: одна строка flex-row, тянется на 100% ширины, высота авто.
        self.flex_box(
            direction="row",
            width="100%",
            height="auto",
        )

    def td(self, index: int | None = None) -> "TFlex_Td | None":
        """
        Возвращает/создаёт ячейку строки.
        td()           → создаёт новый TFlex_Td, пушит в self.Tds и возвращает его.
        td(n)/td(-1)   → вернуть существующую ячейку по индексу (или None если нет).
        """
        if index is None:
            td = TFlex_Td(self)
            self.Tds.append(td)
            return td
        try:
            if index == -1:
                return self.Tds[-1]
            return self.Tds[index]
        except IndexError:
            return None

    def get_active_control(self) -> "TCustomControl":
        return self.Tds[-1]

    def is_structural_child(self, ctrl: "TCustomControl") -> bool:
        # Ячейки строки — всегда структурные (включая наследников TFlex_Td, например TGrid_Td)
        return isinstance(ctrl, TFlex_Td) or super().is_structural_child(ctrl)
    # ..................................................................................................................
    # 🎨 Render
    # ..................................................................................................................
    def render(self):
        """
        _render() уже открыл мой корневой <div id='flex_tr-*' ...>. Здесь мы просто по очереди рендерим все td (TFlex_Td) и вливаем их Canvas внутрь текущего контейнера без дополнительных обёрток.
        """
        for td in self.Tds:
            td._render()
            self.Canvas.extend(td.Canvas)
    # ..................................................................................................................
    # 🔰 mark* methods
    # ..................................................................................................................
    def _mark_family(self) -> str | None:
        """
        Базовая flex-строка сама по себе семейство не задаёт.
        Наследники (например панель/карточка) могут переопределить MARK_FAMILY.
        """
        return getattr(self, "MARK_FAMILY", None)
    # ---
    def _mark_level(self) -> int:
        """
        Уровень самой строки.
        По умолчанию считаем строку уровнем 1.
        Переопределяй в потомках.
        """
        return 1
    # ---
    def mark_level_for_cell(self) -> int:
        """
        Возвращает уровень подсветки (MARK_LEVEL) для дочерних TFlex_Td.
        По умолчанию ячейка считаем глубже строки, уровень 2.
        Переопределяй в потомках.
        """
        return 2
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TFlex_Td — ячейка flex-строки (flex-item)
# ----------------------------------------------------------------------------------------------------------------------
class TFlex_Td(TCompositeControl):
    prefix = "flex_td"
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        """
        Ячейка внутри TFlex_Tr. Ведёт себя как flex-item.
        Держит упорядоченный поток контента в self.Flow.
        """
        # --- Внутренний поток контента ---
        self.Flow: list[Any] = []
        # ⛳ Текст плейсхолдера (показывается, когда Flow пуст)
        # Если None или "" → плейсхолдер не рисуем.
        self.place_holder: str | None = None
        # --- Базовая геометрия flex-ячейки ---
        # Ячейка должна уметь тянуться. Даём ей flex-grow-1 и базовый padding.
        self.add_class("flex-grow-1")
        self.add_style("padding:4px;")
    # ..................................................................................................................
    # 🔔 внутренний хук уведомления панели
    # ..................................................................................................................
    def _notify_owner_has_content(self):
        """
        Сообщает владельцу-строке (а это может быть TPanel, TCardPanel и т.п.,
        то есть наследник TFlex_Tr), что в этой колонке появилось живое содержимое.
        Панель на это реагирует:
        - снимает placeholder
        - убирает серую пунктирную рамку "скелета"
        """
        parent_row = getattr(self, "Owner", None)
        if parent_row and hasattr(parent_row, "_notify_child_content"):
            parent_row._notify_child_content(self)
    # ..................................................................................................................
    # ➕ Наполнение вручную (текстом или уже готовым контролом)
    # ..................................................................................................................
    def add(self, item: Any) -> "TFlex_Td":
        """
        Добавляет элемент (контрол или текст) в td, сохраняя порядок.
        Если item — контрол, он уже должен быть создан с Owner=self
        (это гарантирует автописание его в дерево).
        """
        if item is None:
            return self

        if isinstance(item, TCompositeControl):
            if item not in self.Flow:
                self.Flow.append(item)
            self.log("add", f"control {item.Name} added to Flow")
        else:
            text_val = str(item)
            self.Flow.append(text_val)
            self.log("add", f"text added to Flow: {text_val[:30]}")

        # как только что-то реально попало в колонку — панель должна ожить
        self._notify_owner_has_content()
        return self

    def set(self, item: Any) -> "TFlex_Td":
        """
        Полностью очищает td и кладёт item как единственный первый элемент.
        Удобно для простых ячеек типа 'только кнопка', 'только иконка', 'только текст'.
        """
        self.Flow = []
        return self.add(item)

    def add_control(self, ctrl: "TCustomControl"):
        """
        Хук автоподключения. Вызывается автоматически в __init__ дочернего контрола.
        1) регистрируем дочерний контрол (базовая логика),
        2) добавляем тот же контрол в Flow (визуальный порядок),
        3) уведомляем владельца-строку/панель, что контент реально появился.
        """
        super().add_control(ctrl)

        if ctrl not in self.Flow:
            self.Flow.append(ctrl)
            self.log("add_control", f"{ctrl.Name} registered into Flow")

        # сигнал наверх панели/строке
        self._notify_owner_has_content()
    # ..................................................................................................................
    # 🎨 Render
    # ..................................................................................................................
    def _render(self):
        """
        Переопределённый рендер-обёртка:
        сначала подстраиваем flex под фиксированную ширину, потом используем
        стандартный механизм TCustomControl._render().
        """
        self._apply_fixed_width_flex()
        super()._render()

    def render(self):
        """
        _render() уже открыл мой корневой <div id='flex_td-*' ...> и после возврата из render() сам его закроет.
        Здесь просто заливаем содержимое Flow по порядку без доп. обёрток.
        Если Flow пуст и задан place_holder — рисуем только плейсхолдер.
        """
        # ⛳ Placeholder: показываем только если в ячейке нет реального содержимого
        if (not self.Flow) and self.place_holder:
            text = str(self.place_holder)
            # простой нейтральный debug-стиль (как в миксине)
            ph_style = (
                "color:#999;"
                "font-size:12px;"
                "font-family:monospace;"
                "line-height:1.2;"
                "opacity:0.6;"
            )
            # отдельный div, чтобы можно было переопределить в css по .tc-placeholder
            self.tg("div", cls="tc-placeholder", attr=f"style='{ph_style}'")
            self.text(text)
            self.etg("div")
            return
        # ---
        for node in self.Flow:
            if is_visual_node(node):
                node._render()
                self.Canvas.extend(node.Canvas)
            else:
                self.text(str(node))

    def _apply_fixed_width_flex(self) -> None:
        """
        Если для ячейки явно задана ширина (width) или min-width (width_min),
        то:
          - снимаем flex-grow-1, чтобы колонка не растягивалась,
          - при наличии width задаём flex: 0 0 <width>.
        """
        width = getattr(self, "f_width", None)
        min_width = getattr(self, "f_min_width", None)

        # если ни width, ни width_min не заданы — ничего не делаем
        if width is None and min_width is None:
            return

        # 1) убираем авто-растяжение
        if hasattr(self, "classes") and "flex-grow-1" in self.classes:
            self.classes.remove("flex-grow-1")

        # 2) если есть явный width — задаём flex:0 0 <width>
        if width is not None:
            current_styles = list(getattr(self, "styles", []))
            # убираем предыдущие flex: ...
            filtered = [
                s for s in current_styles
                if not s.strip().startswith("flex:")
            ]
            filtered.append(f"flex:0 0 {width};")
            self.styles = filtered
    # ..................................................................................................................
    # 🔰 mark* methods
    # ..................................................................................................................
    def _mark_family(self) -> str | None:
        """Ячейка берёт семейство у владельца (строки/панели)."""
        return getattr(self.Owner, "_mark_family", lambda: None)()

    def _mark_level(self) -> int:
        """
        Уровень подсветки ячейки.

        Если Owner (строка, напр. TPanel) умеет сообщать свой child-level
        через _child_mark_level(), то берём его — это даёт, например,
        panel.level=0 → td.leveуками открывал/закрывал через tg/etg.l=1 (фиолетовые рамки отдельно от grid).

        Иначе по умолчанию считаем себя уровнем 2.
        """
        owner_row = getattr(self, "Owner", None)
        if owner_row and hasattr(owner_row, "_child_mark_level"):
            return owner_row._child_mark_level()
        return 2
    # ..................................................................................................................
    # 🛡️ PHASE 2: политика владения
    # ..................................................................................................................
    def _owner_required(self) -> bool:
        # Колонка не может существовать без строки панели / flex-ряда.
        return True

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        """
        Мой хозяин обязан быть flex-строкой (TFlex_Tr и его потомки):
        - TPanel (самостоятельная панель)
        - TCardPanel (хедер/футер карточки)
        - любые будущие наследники.
        """
        return (TFlex_Tr,)

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        """
        В колонку можно бросать любые визуальные контролы UI:
        кнопки, лейблы, иконки, вложенные карточки и т.д.
        (всё это наследует TCustomControl)
        """
        return (TCustomControl,)
# ======================================================================================================================
# 📁🌄 bb_ctrl_custom.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 671 -> 1400 -> 984
# ======================================================================================================================
