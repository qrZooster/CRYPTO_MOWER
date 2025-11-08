# ======================================================================================================================
# 📁 file        : bb_ctrl_atom.py — Атомарные визуальные контролы (Label/Icon/Button/Badge)
# 🕒 created     : 02.11.2025 15:20
# 🎉 contains    : TAtomControl, TLabel, TIcon, TButton, TStatusBadge (перенесёшь сюда)
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
from typing import Any

from bb_sys import *
from bb_ctrl_mixin import *
from bb_ctrl_custom import TCustomControl
from _sys import *
# 💎🧩⚙️ ... __ALL__ ...
__all__ = ["TLabel", "TIcon", "TButton", "TBadge", "TAvatar",
           "BTN_KINDS", "BTN_SOCIAL", "BTN_STYLES", "BTN_STYLE_ALIAS"]
# 💎 ... FACADE CONSTS ...
ATOM_SIZES = ["xs", "sm", "md", "lg", "xl"]

BTN_SOCIAL = {
    "facebook","twitter","x","linkedin","google","youtube","vimeo","dribbble",
    "github","instagram","pinterest","vk","rss","flickr","bitbucket","tabler"
}
BTN_KINDS = {
    "primary","secondary","success","warning","danger","info","dark","light",
    "blue","azure","indigo","purple","pink","red","orange","yellow","lime","green","teal","cyan",
    *BTN_SOCIAL,
    "close",
}
BTN_STYLES = {"standard","outline","ghost","square","pill","icon","social","action","iconed"}
BTN_STYLE_ALIAS = {"standart": "standard"}
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TAtomControl — атомарный визуальный контрол (детей не имеет)
# ----------------------------------------------------------------------------------------------------------------------
class TAtomControl(TStyleMixin, TCustomControl):
    prefix = "atom"
    """
    Атом.
    Пример: Label, Icon, Button, Badge...
    Он живёт внутри ячейки/панели, но сам никого не содержит.
    """
    def __init__(self, Owner=None, Name: str | None = None):
        super().__init__(Owner, Name)
        self.f_size = "md"             # 'xs'|'sm'|'md'|'lg'|'xl'
        self.f_kind = None             # внутренняя форма kind
        self.f_caption = None          # сразу под caption, см. TCaptionMixin
        self.f_style = ""              # сырое значение style ("pill ghost" и т.п.)

    def add_control(self, ctrl: "TCustomControl"):
        """
        Если кто-то попытается впихнуть детей в атом — это ошибка дизайна.
        """
        self.fail("add_control",
                  f"{self.__class__.__name__} cannot own children",
                  TypeError)

    def get_base_class(self) -> list[str]:
        """
        Базовые классы атома.
        Например, для кнопки: ['btn', 'tc-btn'].
        Для иконки: ['tc-icon'] и т.п.
        Здесь уже можно использовать self.prefix.
        """
        base = []
        if getattr(self, "prefix", None):
            base.append(self.prefix)
            base.append(f"tc-{self.prefix}")
        return base

    def get_debug_class(self) -> list[str]:
        app = self.app()
        dbg = bool(app and getattr(app, "debug_mode", False))
        mark_info = self._resolve_mark_info() if dbg else None

        if not (dbg and mark_info):
            return []

        pal = str(mark_info.get("palette_name"))
        shade = str(mark_info.get("shade_idx"))

        return [
            tc_dbg_class("frame"),
            tc_dbg_class("f", pal, shade),
        ]

    def get_size_class(self) -> str:
        """
        Преобразуем атомарный size в css-класс вида '<prefix>-<size>'.
        Работает для любых атомов, у которых есть prefix и size из ATOM_SIZES.
        """
        prefix = getattr(self, "prefix", None)
        sz = getattr(self, "size", None)

        if not prefix or not sz or sz == "md":
            return ""

        return f"{prefix}-{sz}"

    def get_class(self) -> str:
        parts: list[str] = []

        # 1) базовые классы от prefix
        parts.extend(self.get_base_class())

        # 2) атомарные модификаторы (kind/size/style)
        k = self.get_kind_class()
        if k:
            parts.append(k)

        sz = self.get_size_class()
        if sz:
            parts.append(sz)

        st = self.get_style_class()
        if st:
            parts.append(st)

        # 3) пользовательские классы (add_class и т.п.)
        parts.extend(getattr(self, "classes", []) or [])

        # 4) debug-классы mark() — в самом конце
        parts.extend(self.get_debug_class())

        # 5) уникализация в порядке приоритета
        seen = set()
        out: list[str] = []

        for chunk in parts:
            if not chunk:
                continue
            for tok in str(chunk).split():
                if tok and tok not in seen:
                    seen.add(tok)
                    out.append(tok)

        return " ".join(out)

    # ..................................................................................................................
    # 🎨 Рендеринг TAtomControl
    # ..................................................................................................................
    def _render(self):
        # инъекция классов/атрибутов в ПЕРВЫЙ тег атома
        self._root_inject_pending = True
        self._root_class_inject = self.get_class() or None
        self._root_attr_inject = None

        try:
            self.render()
        except Exception as e:
            self.log("_render", f"⚠ render() failed: {e}")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TLabel — текстовая метка (заголовок или обычный текст)
# ----------------------------------------------------------------------------------------------------------------------
class TLabel(TCaptionMixin, TAtomControl):
    prefix = "lbl"
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Текстовая метка. Может быть обычной подписью (span) или заголовком (h1..h6) через self.h.
        По умолчанию выводит собственное имя (self.Name), так что можно не задавать текст вручную.
        """
        super().__init__(Owner, Name)
        # --- Контент метки ---
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
        self.tg(tag)
        self.text(self.caption)
        self.etg(tag)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TIcon — визуальная иконка (эмодзи / favicon URL / inline SVG)
# ----------------------------------------------------------------------------------------------------------------------
class TIcon(TIconMixin, TAtomControl):
    prefix = "ico"
    _ICON_SIZE_TOKENS = {
        "xs": 12,
        "sm": 14,
        "md": 16,
        "lg": 20,
        "xl": 24,
    }
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
        self._size_px: int = 16
        self.h: int = 0
        # ... 🔊 ...
        self.log("__init__", f"⚙️ icon {self.Name} created")
        # ⚡🛠️ TIcon ▸ End of __init__
        # -------- size: пиксели --------

    def get_size_class(self) -> str:
        # никакого 'ico-16', размер уходим в style
        return ""

    def get_style(self) -> str | None:
        if not self._size_px:
            return None
        return f"font-size:{self._size_px}px"

    def _size_token(self) -> str:
        """ Возвращает ближайший логический токен размера ('xs'..'xl') по текущему _size_px. """
        px = self.size
        best_token = "md"
        best_diff: int | None = None
        for tok in ATOM_SIZES:
            target_px = self._ICON_SIZE_TOKENS.get(tok)
            if target_px is None:
                continue
            diff = abs(target_px - px)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_token = tok
        return best_token

    def _size_idx(self) -> int:
        """ Индекс текущего логического размера в ATOM_SIZES. """
        token = self._size_token()
        try:
            return ATOM_SIZES.index(token)
        except ValueError:
            return ATOM_SIZES.index("md")

    def inc_size(self, steps: int = 1):
        """
        Увеличивает размер иконки на steps логических шагов по шкале ATOM_SIZES.
        Если текущий размер задан в пикселях и не совпадает с токеном,
        используем ближайший токен.
        """
        try:
            step = int(steps)
        except Exception:
            step = 0

        idx = self._size_idx()
        idx = max(0, min(idx + step, len(ATOM_SIZES) - 1))
        token = ATOM_SIZES[idx]
        # выставляем через токен — setter size сам переведёт в пиксели
        self.size = token
        return self

    def dec_size(self, steps: int = 1):
        """ Уменьшает размер иконки на steps логических шагов. """
        return self.inc_size(-steps)

    @property
    def size(self) -> int:
        """Размер иконки в пикселях."""
        # если ещё не трогали – дефолт 16
        return getattr(self, "_size_px", 16)

    @size.setter
    def size(self, v):
        """Поддерживаем:
        - int / float → напрямую в пиксели,
        - 'xs'..'xl' → маппим в пиксели,
        - строку-число → тоже в пиксели.
        """
        if v is None:
            self._size_px = 16
            return

        # 1) Числа: 16, 24, 32...
        if isinstance(v, (int, float)):
            n = int(v)
            if n <= 0:
                raise ValueError("Icon size must be positive")
            self._size_px = n
            return

        s = str(v).strip().lower()
        if not s:
            self._size_px = 16
            return

        # 2) Токены xs/sm/md/lg/xl
        if s in self._ICON_SIZE_TOKENS:
            self._size_px = self._ICON_SIZE_TOKENS[s]
            return

        # 3) Попробуем строку-число: "16"
        try:
            n = int(s)
        except ValueError:
            raise ValueError(
                f"Invalid icon size '{v}'. Use int px or one of {sorted(self._ICON_SIZE_TOKENS)}"
            )
        else:
            if n <= 0:
                raise ValueError("Icon size must be positive")
            self._size_px = n
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
class TButton(TIconMixin, TCaptionMixin, TLinkMixin, TAtomControl):
    prefix = "btn"
    STYLE_KINDS = BTN_KINDS
    STYLE_STYLES = BTN_STYLES
    STYLE_ALIAS = BTN_STYLE_ALIAS
    """ Чистая версия"""
    def __init__(self, Owner=None, Name=None):
        super().__init__(Owner, Name)
        self.href = "#"           # target href
        self.suffix_html = ""     # html-хвост (иконка/бейдж справа)

    def _link_href(self) -> str:
        return self.href or "#"

    def _normalize_kind(self, value):
        if value is None:
            return None

        s = str(value).strip().lower()

        # пустая строка — отдельный смысл: "по умолчанию secondary"
        if s == "":
            return ""

        # явный "none" — выключить kind
        if s == "none":
            return "none"

        # поддержка "btn-warning" и т.п.
        if s.startswith("btn-"):
            s = s[4:]

        if s not in BTN_KINDS:
            raise ValueError(f"Invalid kind '{value}'. Allowed: {sorted(BTN_KINDS)}")

        return s
    # ---------- render ----------
    def render(self):
        self.tg("a", cls="", attr=f"href='{self._link_href()}'")
        self.text(self.caption)
        if self.suffix_html:
            self.text(self.suffix_html)
        self.etg("a")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TBadge — простой Badge
# ----------------------------------------------------------------------------------------------------------------------
class TBadge(TIconMixin, TCaptionMixin, TAtomControl):
    prefix = "badge"
    STYLE_KINDS = {
        "default",
        "blue", "azure", "indigo", "purple", "pink", "red", "orange",
        "yellow", "lime", "green", "teal", "cyan",
        "dark", "light",
    }
    STYLE_STYLES = TAtomControl.STYLE_STYLES | {
        "outline",
        "notification",
        "blink",
        "light",  # наш человекочитаемый токен
        "lt",  # алиас под bg-*-lt
    }
    STYLE_ALIAS = TAtomControl.STYLE_ALIAS
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Небольшой индикатор-состояние (лейбл) рядом с текстом или иконкой.
        По умолчанию — Tabler-совместимый бейдж 'Default' малого размера.
        Иконка (self.icon) опциональна и рисуется слева от текста.
        """
        super().__init__(Owner, Name)
        self.style = "default sm"
        self.silent: bool = False
        # ... 🔊 ...
        self.log("__init__", f"⚙️ badge {self.Name} created style={self.style}")
        # ⚡🛠️ TBadge ▸ End of __init__
    # ..................................................................................................................
    # 🎨 Рендеринг
    # ..................................................................................................................
    def render(self):
        """
        Рисует <span> с optional-иконкой слева и caption справа.
        Примеры:
            bdg = TBadge(td)
            bdg.caption = "Default"
            bdg.icon = "⭐"
            bdg.style = "blue pill sm"
        """
        style_tokens = {t.strip().lower() for t in (self.style or "").split()}
        is_notification = "notification" in style_tokens
        silent = getattr(self, "silent", False)
        # ---
        self.tg("span")
        if is_notification and silent:
            # Tabler делает просто пустой span с классами; нам текст не нужен
            # можно вообще ничего не писать внутрь
            self.etg("span")
            return
        # ---
        icon_val = (self.icon or "").strip()
        if icon_val:
            # небольшая обёртка под иконку — можно стилизовать через .badge-icon
            self.tg("span", cls="badge-icon")
            self.text(icon_val)
            self.etg("span")
            self.text(" ")
        self.text(self.caption)
        self.etg("span")
    # ..................................................................................................................
    # 🧙‍♂️ Tabler-kind → bg/text классы
    # ..................................................................................................................
    def get_kind_class(self) -> str:
        """
        Маппинг kind/style → таблеровские цветовые классы.
        """
        k = self.kind or "default"
        style_tokens = set((self.style or "").split())

        # 1) notification-dot (в приоритете над outline/light)
        if "notification" in style_tokens:
            if k == "default":
                return "bg-default badge-notification"
            return f"bg-{k} badge-notification"

        # 2) outline-badge
        if "outline" in style_tokens:
            if k == "default":
                return "badge-outline text-default"
            return f"badge-outline text-{k}"

        # 3) light / -lt вариант
        if "light" in style_tokens or "lt" in style_tokens:
            if k == "default":
                return "bg-default-lt"
            return f"bg-{k}-lt"

        # 4) по умолчанию — solid
        if k == "default":
            return "bg-default text-default-fg"
        return f"bg-{k} text-{k}-fg"
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TAvatar — атомарный аватар (фото / инициалы / иконка)
# ----------------------------------------------------------------------------------------------------------------------
class TAvatar(TIconMixin, TAtomControl):
    prefix = "avatar"
    STYLE_KINDS = {
        "default",
        "blue", "azure", "indigo", "purple", "pink", "red", "orange",
        "yellow", "lime", "green", "teal", "cyan",
        "dark", "light", "gray",
    }
    STYLE_STYLES = {"standard", "rounded", "square", "outline", "soft", "shadow"}
    STYLE_ALIAS = {"standart": "standard"}
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Аватар пользователя: фото, инициалы или иконка внутри круглого/квадратного контейнера.
        Приоритет содержимого:
        1) src      → <img src="...">
        2) initials → текстовые инициалы (PK)
        3) icon     → строковая иконка (эмодзи/SVG)
        4) автоинициалы из Name.
        По умолчанию — маленький rounded-плейсхолдер в цвете default.
        Дополнительно может показывать статусную точку/бейдж (status/status_text).
        """
        super().__init__(Owner, Name)
        # --- Основные данные аватара ---
        self.src: str | None = None
        self.initials: str | None = None
        self.alt: str | None = None
        # --- Статус: точка/бейдж в углу ---
        self.status: str | None = None  # 'online','green','red','away',...
        self.status_text: str | None = None  # None → просто точка, '5' → бейдж с цифрой
        # --- Базовый стиль ---
        self.style = "default sm rounded"
        # ... 🔊 ...
        self.log("__init__", f"⚙️ avatar {self.Name} created style={self.style}")
        # ⚡🛠️ TAvatar ▸ End of __init__
    # ..................................................................................................................
    # 🎨 Рендеринг
    # ..................................................................................................................
    def render(self):
        """
        Рисует корневой <span> с классами avatar* и внутреннее содержимое:
        либо <img>, либо инициалы/иконку. В конце рисует статусную точку/бейдж,
        если указаны status/status_text.
        """
        self.tg("span")
        if self.src:
            alt = self.alt or self._auto_initials() or (self.Name or "")
            self.text(f"<img src='{self.src}' alt='{alt}'/>")
        else:
            text = self._resolve_placeholder_text()
            self.tg("span", cls="avatar-initials")
            self.text(text)
            self.etg("span")
        self._render_status()
        self.etg("span")
    # ..................................................................................................................
    # 🧠 Внутренние хелперы содержимого
    # ..................................................................................................................
    def _resolve_placeholder_text(self) -> str:
        """
        Выбирает, что показать внутри, если нет src:
        1) явные initials;
        2) icon (эмодзи/SVG/текст);
        3) автоинициалы из Name;
        4) '?' как последний fallback.
        """
        if self.initials:
            return str(self.initials).strip() or "?"
        icon_val = (self.icon or "").strip()
        if icon_val:
            return icon_val
        auto_init = self._auto_initials()
        if auto_init:
            return auto_init
        return "?"
    # ---
    def _auto_initials(self) -> str:
        """
        Строит инициалы из Name:
        'Pawel Kuna'  → 'PK'
        'Single'      → 'S'
        Пустое Name даёт пустую строку.
        """
        name = str(getattr(self, "Name", "") or "").strip()
        if not name:
            return ""
        parts = name.split()
        letters: list[str] = []
        for p in parts:
            if p:
                letters.append(p[0].upper())
            if len(letters) == 2:
                break
        if not letters:
            return ""
        if len(letters) == 1:
            return letters[0]
        return (letters[0] + letters[1])[:2]
    # ..................................................................................................................
    # 🩺 Статус аватара (точка/бейдж)
    # ..................................................................................................................
    def _map_status(self, value: str | None) -> str | None:
        """
        Нормализует статусный цвет.
        Поддерживает как прямые токены ('green','red',...),
        так и семантические ('online','offline','busy','away').
        """
        if value is None:
            return None
        s = str(value).strip().lower()
        if not s:
            return None
        semantic = {
            "online": "green",
            "ok": "green",
            "success": "green",
            "busy": "red",
            "error": "red",
            "fail": "red",
            "away": "yellow",
            "idle": "yellow",
            "offline": "gray",
        }
        s = semantic.get(s, s)
        allowed = {
            "default",
            "blue", "azure", "indigo", "purple", "pink", "red", "orange",
            "yellow", "lime", "green", "teal", "cyan",
            "dark", "light", "gray",
        }
        if s not in allowed:
            return "gray"
        return s
    # ---
    def _render_status(self):
        """
        Рисует статусную точку/бейдж, если задан status или status_text.
        Классы в духе Tabler:
            badge avatar-status avatar-badge bg-green
        """
        kind = self._map_status(getattr(self, "status", None))
        text = getattr(self, "status_text", None)
        if not kind and not text:
            return
        cls = "badge avatar-status avatar-badge"
        if kind:
            if kind == "default":
                cls = f"{cls} bg-default"
            else:
                cls = f"{cls} bg-{kind}"
        self.tg("span", cls=cls)
        if text:
            self.text(str(text))
        self.etg("span")
    # ..................................................................................................................
    # 🔧 Tabler-kind → bg/text классы
    # ..................................................................................................................
    def get_kind_class(self) -> str:
        """
        Для аватара основной цвет контейнера задаётся так же, как для бейджа:
        default → bg-default text-default-fg
        blue    → bg-blue text-blue-fg
        ...
        """
        k = self.kind
        if not k:
            return ""
        if k == "default":
            return "bg-default text-default-fg"
        return f"bg-{k} text-{k}-fg"
# ======================================================================================================================
# 📁🌄 bb_ctrl_atom.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 241 -> 539 -> 392
# ======================================================================================================================
