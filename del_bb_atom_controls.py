# ======================================================================================================================
# 📁 file        : bb_atom_controls.py — Атомарные визуальные контролы (Label/Icon/Button/Badge)
# 🕒 created     : 02.11.2025 15:20
# 🎉 contains    : TAtomControl, TLabel, TIcon, TButton, TStatusBadge (перенесёшь сюда)
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
from typing import Any

from bb_sys import *
from bb_custom_control import TCustomControl
# 💎🧩⚙️ ... __ALL__ ...
__all__ = ["TLabel", "TIcon", "TButton", "TBadge"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TAtomControl — атомарный визуальный контрол (детей не имеет)
# ----------------------------------------------------------------------------------------------------------------------
class TAtomControl(TCustomControl):
    """
    Атом.
    Пример: Label, Icon, Button, Badge...
    Он живёт внутри ячейки/панели, но сам никого не содержит.
    """
    def __init__(self, Owner=None, Name: str | None = None):
        super().__init__(Owner, Name)

    def add_control(self, ctrl: "TCustomControl"):
        """
        Если кто-то попытается впихнуть детей в атом — это ошибка дизайна.
        """
        self.fail("add_control",
                  f"{self.__class__.__name__} cannot own children",
                  TypeError)
    # ..................................................................................................................
    # 🎨 Рендеринг TAtomControl
    # ..................................................................................................................
    def _render(self):
        app = self.app()
        dbg = bool(app and getattr(app, "debug_mode", False))
        mark_info = self._resolve_mark_info() if dbg else None

        # инъекция классов/атрибутов в ПЕРВЫЙ тег атома
        self._root_inject_pending = True

        # базовый css-класс атома
        cls_name = self.__class__.__name__
        base_atom_cls = {
            "TLabel": "tc-label",
            "TIcon": "tc-icon",
            "TButton": "tc-btn",
            "TStatusBadge": "tc-status",  # на будущее, без влияния сейчас
        }.get(cls_name)

        # === ВАЖНО: рамку и палитру добавляем ТОЛЬКО если mark() задействован ===
        dbg_classes = []
        if dbg and mark_info:
            pal = str(mark_info.get("palette_name"))
            shade = str(mark_info.get("shade_idx"))
            dbg_classes.append(tc_dbg_class("frame"))  # пунктирная рамка
            dbg_classes.append(tc_dbg_class("f", pal, shade))  # цвет рамки по палитре

        classes = " ".join(c for c in [base_atom_cls, *dbg_classes] if c)
        self._root_class_inject = classes or None
        self._root_attr_inject = None

        try:
            self.render()
        except Exception as e:
            self.log("_render", f"⚠ render() failed: {e}")

        # бейджи отключены
        # if dbg and mark_info:
        #     self._render_badge(mark_info)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TLabel — текстовая метка (заголовок или обычный текст)
# ----------------------------------------------------------------------------------------------------------------------
class TLabel(TAtomControl):
    prefix = "lbl"
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Текстовая метка. Может быть обычной подписью (span) или заголовком (h1..h6) через self.h.
        По умолчанию выводит собственное имя (self.Name), так что можно не задавать текст вручную.
        """
        super().__init__(Owner, Name)
        # --- Контент метки ---
        self.caption: str = self.Name
        self.h: int = 0
        # ... 🔊 ...
        self.log("__init__", f"⚙️ label {self.Name} created")
        # ⚡🛠️ TLabel ▸ End of __init__
    # ..................................................................................................................
    # 🎨 Рендеринг
    # ..................................................................................................................
    def render(self):
        """
        Выводит self.caption внутри span либо h1..h6 в зависимости от self.h.
        Если h == 0 → <span>.
        """
        tag = f"h{self.h}" if 1 <= int(self.h) <= 6 else "span"
        self.tg(tag, cls="tc-label")
        self.text(self.caption)
        self.etg(tag)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TIcon — визуальная иконка (эмодзи / favicon URL / inline SVG)
# ----------------------------------------------------------------------------------------------------------------------
class TIcon(TAtomControl):
    prefix = "ico"
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Визуальный маркер. Может быть эмодзи, inline SVG (например иконка Tabler) или URL фавиконки/картинки.
        Управляется свойствами:
        - self.icon  → строка-источник (🌐 или '<svg ...>' или 'https://site/favicon.ico')
        - self.size  → базовый размер в пикселях
        - self.h     → 0 значит <span>, 1..6 значит <h1>..<h6>
        """
        super().__init__(Owner, Name)
        # --- Свойства отображения ---
        self.icon: str = "🌐"
        self.size: int = 16
        self.h: int = 0
        # ... 🔊 ...
        self.log("__init__", f"⚙️ icon {self.Name} created")
        # ⚡🛠️ TIcon ▸ End of __init__
    # ..................................................................................................................
    # 🎨 Рендеринг
    # ..................................................................................................................
    def render(self):
        """
        Рисует контейнер <span> или <h1>.. <h6> (если self.h > 0). Внутри:
        - эмодзи/текст если self.icon обычная строка;
        - <img ...> если self.icon выглядит как URL или *.ico/*.png/*.svg/*.jpg/*.gif;
        - сырой <svg> если self.icon начинается с '<svg'.
        Масштаб задаётся через self.size (px).
        """
        tag = f"h{self.h}" if 1 <= int(self.h) <= 6 else "span"
        base_style = f"line-height:{self.size}px;display:inline-flex;align-items:center;justify-content:center;"
        self.tg(tag, cls="tc-icon", attr=f"style='{base_style}'")
        val = str(self.icon).strip()
        is_svg = val.startswith("<svg")
        is_url = val.startswith("http://") or val.startswith("https://") or val.endswith(".ico") or val.endswith(".png") or val.endswith(".jpg") or val.endswith(".jpeg") or val.endswith(".gif") or val.endswith(".svg")
        if is_svg:
            self.text(val)
        elif is_url:
            img_style = f"width:{self.size}px;height:{self.size}px;object-fit:contain;display:inline-block;"
            self.text(f"<img src='{val}' style='{img_style}'/>")
        else:
            font_style = f"font-size:{self.size}px;font-weight:bold;"
            self.tg("span", cls="tc-icon-text", attr=f"style='{font_style}'")
            self.text(val)
            self.etg("span")
        self.etg(tag)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TButton — простая Button
# ----------------------------------------------------------------------------------------------------------------------
class TButton(TAtomControl):
    prefix = "btn"
    _KINDS = {"primary", "secondary", "success", "warning", "danger", "info", "light", "dark", "link",}

    def __init__(self, Owner=None, Name: str | None = None):
        super().__init__(Owner, Name)
        self.caption: str = self.Name
        self.href: str | None = None      # прямой href
        self.page: str | None = None      # /?page=...
        self.suffix_html: str | None = None  # raw svg/иконка после текста
        self.kind: str = "secondary"
        self.size: str = "md"  # NEW: sm | md | lg

    def _link_href(self) -> str:
        return self.href or (f"/?page={self.page}" if self.page else "#")

    def _caption_for_render(self) -> str:
        name = self.Name or ""
        if (getattr(self, "caption", None) or "") == name:
            k = (getattr(self, "kind", None) or "secondary")
            return k[:1].upper() + k[1:]
        return str(getattr(self, "caption", ""))

    def _kind_class(self) -> str:
        k = getattr(self, "kind", None)
        k = str(k).strip() if k is not None else ""
        if not k:
            return "btn-secondary"
        if k.startswith("btn-"):
            return k
        return f"btn-{k}"

    def _size_class(self) -> str:
        """
        Маппит size -> bootstrap-класс:
          sm -> btn-sm
          lg -> btn-lg
        Иначе — пусто (без класса).
        """
        s = getattr(self, "size", None)
        if not s:
            return ""
        s = str(s).strip()
        if not s:
            return ""
        s = s.lower()
        if s == "sm":
            return "btn-sm"
        if s == "lg":
            return "btn-lg"
        return ""

    def render(self):
        # исходные пользовательские классы
        user_cls_list = [c for c in " ".join(self.classes).split() if c]

        has_btn_base = "btn" in user_cls_list
        has_btn_variant = any(c.startswith("btn-") for c in user_cls_list)

        base_btn = "" if has_btn_base else "btn"
        kind_cls = "" if has_btn_variant else self._kind_class()
        size_cls = self._size_class()

        # собрать классы, убрать дубли сохраняя порядок
        parts = [base_btn, kind_cls, *user_cls_list, "tc-btn", size_cls]
        seen, ordered = set(), []
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                ordered.append(p)

        cls = " ".join(ordered)
        self.tg("a", cls=cls, attr=f"href='{self._link_href()}'")
        self.text(self._caption_for_render())
        if self.suffix_html:
            self.text(self.suffix_html)
        self.etg("a")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TStatusBadge — простая StatusBadge
# ----------------------------------------------------------------------------------------------------------------------
class TBadge(TAtomControl):
    prefix = "badge"
    pass
# ======================================================================================================================
# 📁🌄 bb_atom_controls.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 241
# ======================================================================================================================
