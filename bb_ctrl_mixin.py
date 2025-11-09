# ======================================================================================================================
# 📁 file        : bb_ctrl_mixin.py — Mixin library for UI controls (links, caption, icon, style, placeholder, etc.)
# 🕒 created     : 06.11.2025 13:15
# 🎉 contains    : TPlaceholderMixin, TLinkMixin, TCaptionMixin, TIconMixin, TStyleMixin
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
from typing import Any, Optional, Dict
from bb_sys import *  # если миксины используют логгер / базовые типы / утилиты
from bb_ctrl_custom import *  # если где-то в миксинах есть type hints на TCustomControl
# 💎🧩⚙️🧪 ... __ALL__ ...
__all__ = [
    "TLinkMixin",
    "TCaptionMixin",
    "TIconMixin",
    "TStyleMixin",
    "TPlaceholderMixin",
    "TwsSubscriberMixin"
    # сюда же добавишь остальные миксины, если они есть
]
# bb_ctrl_mixin.py

from typing import Optional
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TwsSubscriberMixin
# ----------------------------------------------------------------------------------------------------------------------
class TwsSubscriberMixin:
    """
    Миксин для визуальных контролов, которые хотят получать данные
    из локального WebSocket-сервера.

    channel — имя канала из JSON (например, "log")
    type    — тип сообщения внутри канала (например, "log_line")

    HTML-слой: get_tws_attrs() возвращает строку с data-атрибутами,
    которую можно передать в attr= при tg(...).
    """

    channel: Optional[str] = None
    type: Optional[str] = None

    def get_tws_attrs(self) -> str:
        """
        Собирает data-атрибуты для привязки к WebSocket-сообщениям.
        Пример:
            channel="log", type="log_line" ->
            "data-tws-channel='log' data-tws-type='log_line'"
        Если что-то не задано — атрибут опускается.
        """
        parts: list[str] = []

        ch = getattr(self, "channel", None)
        tp = getattr(self, "type", None)

        if ch:
            parts.append(f"data-tws-channel='{ch}'")
        if tp:
            parts.append(f"data-tws-type='{tp}'")

        return " ".join(parts)
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TPlaceholderMixin — PlaceHolder
# ----------------------------------------------------------------------------------------------------------------------
class TPlaceholderMixin:
    def __init__(self, *args, place_holder: str = "", **kwargs):
        # сначала даём базовым классам инициализироваться
        super().__init__(*args, **kwargs)

        # текст-заглушка по умолчанию (можно потом менять)
        self.place_holder: str = place_holder

        # внутреннее состояние плейсхолдера
        self._placeholder_visible: bool = False
        self._placeholder_container: Any | None = None  # куда положили HTML (обычно td.Flow)
        self._placeholder_node: Any | None = None       # сам HTML-узел плейсхолдера
        self._placeholder_border_style: str | None = None  # бордер, который нужно снять

        # 🔹 Легаси-поля для панелей с auto-td0:
        #    чтобы старый код, который ещё смотрит на _auto_td0/_td0_claimed,
        #    не падал с AttributeError.
        if not hasattr(self, "_auto_td0"):
            self._auto_td0 = None
        if not hasattr(self, "_td0_claimed"):
            self._td0_claimed = False

    # ..................................................................
    # Внутренние хелперы
    # ..................................................................
    def _default_placeholder_html(self, text: str | None = None) -> str:
        """
        Строит HTML плейсхолдера (серый monospace-текст).
        """
        txt = (text or self.place_holder or getattr(self, "Name", "")) or ""
        ph_style = (
            "color:#999;"
            "font-size:12px;"
            "font-family:monospace;"
            "line-height:1.2;"
            "opacity:0.6;"
        )
        return f"<div style='{ph_style}'>{txt}</div>"

    def _init_placeholder(
        self,
        container: Any | None = None,
        text: str | None = None,
        border_style: str | None = None,
    ) -> None:
        """
        Инициализирует плейсхолдер:
        - вешает бордер на сам контрол (если задан),
        - кладёт HTML в container.Flow (если есть контейнер),
        - иначе в self.Canvas.
        """
        self._placeholder_container = container
        self._placeholder_border_style = border_style

        # 1) бордер на контрол
        if border_style:
            try:
                self.add_style(border_style)
            except Exception:
                pass

        # 2) HTML плейсхолдера
        html = self._default_placeholder_html(text)
        target = container

        # пробуем положить в Flow контейнера (например, td.Flow)
        if target is not None and hasattr(target, "Flow"):
            try:
                target.Flow.append(html)
                self._placeholder_node = html
                self._placeholder_visible = True
                return
            except Exception:
                # если что-то пошло не так — падаем в Canvas
                pass

        # fallback — кладём в Canvas самого контрола
        try:
            self.Canvas.append(html)
            self._placeholder_node = html
            self._placeholder_visible = True
        except Exception:
            # вообще ничего не смогли — деактивируем
            self._placeholder_visible = False
            self._placeholder_node = None
            self._placeholder_container = None
            self._placeholder_border_style = None

    def _disable_placeholder_if_needed(self) -> None:
        """
        Убирает плейсхолдер (HTML + бордер), если он ещё активен.
        Многократные вызовы безопасны.
        """
        if not getattr(self, "_placeholder_visible", False):
            return

        node = getattr(self, "_placeholder_node", None)
        container = getattr(self, "_placeholder_container", None)

        # 1) убираем HTML из Flow контейнера
        if container is not None and node is not None and hasattr(container, "Flow"):
            try:
                flow = getattr(container, "Flow", [])
                container.Flow = [
                    n for n in flow
                    if n is not node and n != node
                ]
            except Exception:
                pass
        else:
            # возможно, плейсхолдер лежит прямо в Canvas
            if node is not None and hasattr(self, "Canvas"):
                try:
                    self.Canvas = [
                        n for n in self.Canvas
                        if n is not node and n != node
                    ]
                except Exception:
                    pass

        # 2) снимаем бордер
        border = getattr(self, "_placeholder_border_style", None)
        if border and hasattr(self, "styles"):
            try:
                self.styles.remove(border)
            except Exception:
                pass

        # 3) сбрасываем состояние
        self._placeholder_visible = False
        self._placeholder_node = None
        self._placeholder_container = None
        self._placeholder_border_style = None
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TLinkMixin — навигационный миксин (href/page для кликабельных контролов)
# ----------------------------------------------------------------------------------------------------------------------
class TLinkMixin:
    @property
    def href(self) -> str:
        """
        Финальный URL для перехода. Используется в тегах <a href="..."> или data-атрибутах.
        Пустое значение интерпретируется как "#".
        """
        return getattr(self, "f_href", "#") or "#"

    @href.setter
    def href(self, value: str | None):
        s = "" if value is None else str(value).strip()
        self.f_href = s or "#"

    @property
    def page(self) -> str:
        """
        Логическое имя страницы (echo, main, stats...), на которую ведёт контрол.
        Пустая строка означает, что навигация не настроена.
        """
        return getattr(self, "f_page", "") or ""

    @page.setter
    def page(self, value: str | None):
        """
        Настраивает переход на страницу через TActionBus, если он доступен.
        page=None / "" → сбрасываем навигацию и ставим href="#".
        """
        try:
            app = self.app()  # ожидаем, что класс-носитель миксина умеет app()
        except Exception:
            app = None

        if value is None:
            self.f_page = None
            self.href = "#"
            return

        page = str(value).strip()
        if not page:
            self.f_page = None
            self.href = "#"
            return

        self.f_page = page
        redirect = f"/?page={page}"

        if app and getattr(app, "actions", None):
            try:
                aid = app.actions.register(owner=self, fn=lambda: None, redirect=redirect)
                self.href = f"/__act?aid={aid}"
                return
            except Exception as e:
                try:
                    self.log("page", f"⚠️ action register failed: {e}")
                except Exception:
                    pass

        self.href = redirect
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TCaptionMixin — миксин заголовка (caption)
# ----------------------------------------------------------------------------------------------------------------------
class TCaptionMixin:
    @property
    def caption(self) -> str:
        """
        Человекочитаемый заголовок контрола.
        1) если f_caption задан явно — возвращаем его;
        2) если есть kind — используем его с заглавной буквы;
        3) иначе — fallback на Name.
        """
        if getattr(self, "f_caption", None) not in (None, ""):
            return self.f_caption

        k = getattr(self, "kind", None)
        if k:
            k = str(k)
            return k[:1].upper() + k[1:]

        return getattr(self, "Name", "") or ""

    @caption.setter
    def caption(self, value: str | None):
        # пустое / None → значит "используй kind/Name"
        self.f_caption = None if value is None else str(value)
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TSizeMixin — миксин логического размера (xs..xl)
# ----------------------------------------------------------------------------------------------------------------------
class TSizeMixin:
    """
    Миксин для логического размера визуального контрола.
    Работает только с токенами из ATOM_SIZES: xs/sm/md/lg/xl.
    Хранит значение в self.f_size, по умолчанию считает 'md'.
    """
    @property
    def size(self) -> str:
        """
        Логический размер ('xs'..'xl').

        Если в f_size лежит мусор или None — возвращаем 'md'.
        """
        raw = getattr(self, "f_size", None)
        if raw is None:
            return "md"
        s = str(raw).strip().lower()
        if s in ATOM_SIZES:
            return s
        return "md"

    @size.setter
    def size(self, value) -> None:
        """
        Устанавливает логический размер по токену.
        Допустимы только значения из ATOM_SIZES, иначе ValueError.
        """
        if value is None:
            s = "md"
        else:
            s = str(value).strip().lower()

        if s not in ATOM_SIZES:
            raise ValueError(f"Invalid size '{value}'. Allowed: {ATOM_SIZES}")

        self.f_size = s

    def _size_idx(self) -> int:
        """
        Текущий индекс размера в ATOM_SIZES, с fallback на 'md'.
        """
        current = self.size
        try:
            return ATOM_SIZES.index(current)
        except ValueError:
            return ATOM_SIZES.index("md")

    def inc_size(self, steps: int = 1):
        """
        Увеличивает размер на steps шагов по шкале ATOM_SIZES.
        Не выходит за границы (xs..xl).
        Возвращает self для чейнинга.
        """
        try:
            step = int(steps)
        except Exception:
            step = 0

        idx = self._size_idx()
        idx = max(0, min(idx + step, len(ATOM_SIZES) - 1))
        self.size = ATOM_SIZES[idx]
        return self

    def dec_size(self, steps: int = 1):
        """
        Уменьшает размер на steps шагов.
        Вся логика в inc_size(), здесь только разворот знака.
        """
        return self.inc_size(-steps)
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TIconMixin — миксин для строкового icon
# ----------------------------------------------------------------------------------------------------------------------
class TIconMixin:
    @property
    def icon(self) -> str:
        """
        Строковое представление иконки (эмодзи / SVG / URL).
        Пустое значение интерпретируется как "".
        """
        return getattr(self, "f_icon", "") or ""

    @icon.setter
    def icon(self, value: str | None):
        self.f_icon = "" if value is None else str(value)
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TStyleMixin — kind/size/style-DSL для визуальных контролов
# ----------------------------------------------------------------------------------------------------------------------
class TStyleMixin(TSizeMixin):
    """
    Базовый миксин стиля:
    - size: через TSizeMixin (xs/sm/md/lg/xl)
    - kind: через self.kind / self._normalize_kind()
    - style: строка-модификатор ("pill ghost", "outline", "rounded" и т.п.)
    Классы могут задавать:
      STYLE_KINDS   = {...}
      STYLE_STYLES  = {...}
      STYLE_ALIAS   = {"standart": "standard", ...}
      SIZE_TOKENS   = ("xs","sm","md","lg","xl")  # если хотим отличаться от базовых
    """
    # по умолчанию — пустые наборы, конкретные контролы (Button/Badge/Avatar) их переопределяют
    STYLE_KINDS: set[str] = set()
    STYLE_STYLES: set[str] = set()
    STYLE_ALIAS: dict[str, str] = {}
    # ..................................................................................................................
    # 🏷️ kind
    # ..................................................................................................................
    @property
    def kind(self):
        """
        Логический вид контрола (primary / warning / ...).

        Семантика как в текущем TAtomControl:
          • ""      → трактуем как "secondary" (дефолтная тема),
          • "none"  → спец-значение: выключить kind (классы не добавляем),
          • None    → «ничего не задано»,
          • остальное — как есть.
        """
        v = getattr(self, "f_kind", None)

        if v == "":
            return "secondary"

        if isinstance(v, str) and v.lower() == "none":
            return ""

        return v

    @kind.setter
    def kind(self, value):
        self.f_kind = self._normalize_kind(value)

    def _normalize_kind(self, value):
        """
        Базовая нормализация kind:
        - None     → None
        - "  x  "  → "x"
        - ""       → None
        Потомки (кнопки, бейджи) могут переопределить и добавить валидацию.
        """
        if value is None:
            return None
        s = str(value).strip()
        return s or None
    # ..................................................................................................................
    # 🏷️ style (outline / ghost / pill / ...)
    # ..................................................................................................................
    @property
    def style(self) -> str:
        """ Сырые style-модификаторы в виде строки, например: "pill ghost". """
        return getattr(self, "f_style", "") or ""

    @style.setter
    def style(self, value):
        self.apply_style_tokens(value)
    # ----------------------------------------------------------------------------------------------
    # внутренний хелпер: похоже ли это на иконку (эмодзи)?
    # ----------------------------------------------------------------------------------------------
    @staticmethod
    def _is_icon_token(tok: str) -> bool:
        """
        Очень мягкая эвристика: считаем токен иконкой, если в нём есть не-ASCII символы.
        Это покрывает эмодзи вида "⭐", "🔥", "✅" и т.п.
        Никаких px/классов/слов сюда не попадают.
        """
        if not tok:
            return False
        return any(ord(ch) > 127 for ch in tok)
    # ..................................................................................................................
    # 🔍 Разбор строкового DSL: "danger pill lg"
    # ..................................................................................................................
    def _style_kinds(self) -> set[str]:
        """
        Набор допустимых kind-токенов.
        Потомок задаёт class-атрибут STYLE_KINDS.
        """
        kinds = getattr(self, "STYLE_KINDS", None)
        if kinds is None:
            return set()
        return set(kinds)

    def _style_styles(self) -> set[str]:
        """
        Набор допустимых style-модификаторов (outline / ghost / pill / ...).
        Потомок задаёт class-атрибут STYLE_STYLES.
        """
        styles = getattr(self, "STYLE_STYLES", None)
        if styles is None:
            return set()
        return set(styles)

    def _style_aliases(self) -> dict[str, str]:
        """
        Алиасы для стилей, например "standart" -> "standard".
        Потомок задаёт class-атрибут STYLE_ALIAS.
        """
        aliases = getattr(self, "STYLE_ALIAS", None)
        if aliases is None:
            return {}
        return dict(aliases)
    # ----------------------------------------------------------------------------------------------
    # apply_style_tokens: универсальный разбор строки стиля
    # ----------------------------------------------------------------------------------------------
    def apply_style_tokens(self, value):
        """
        Разбираем строку вида "danger pill lg ⭐" на:
        - size  (SIZE_TOKENS: xs/sm/md/lg/xl или переопределённые)
        - kind  (STYLE_KINDS: primary/azure/green/...)
        - style (STYLE_STYLES: pill/ghost/outline/rounded/...)
        - icon  (эмодзи/не-ASCII токен), если у объекта есть атрибут .icon

        ВАЖНО:
        - никогда не кидаем исключения (ValueError и т.п.) из-за мусора в строке;
        - неизвестные токены просто игнорируем (можно потом залогировать в debug);
        - если несколько size/kind → берём ПОСЛЕДНИЙ;
        - модификаторы стиля накапливаем в f_style через пробел;
        - f_kind / f_size не трогаем, если в строке не было соответствующих токенов.
        """
        # сбрасываем только модификаторы стиля, а НЕ kind/size
        self.f_style = ""

        if value is None:
            return

        s = str(value).strip()
        if not s:
            return

        # --- Достаём настройки из класса (или дефолты) ---
        cls = self.__class__

        size_tokens = tuple(
            getattr(cls, "SIZE_TOKENS",
                    getattr(TSizeMixin, "SIZE_TOKENS", ("xs", "sm", "md", "lg", "xl")))
        )

        style_kinds = set(getattr(cls, "STYLE_KINDS", set()))
        style_styles = set(getattr(cls, "STYLE_STYLES", set()))
        alias_map = dict(getattr(cls, "STYLE_ALIAS", {}))

        mods: list[str] = []  # накопленные модификаторы (pill/ghost/rounded/...)
        icon_set = False  # чтобы не перетирать icon несколько раз

        for raw in s.split():
            tok = raw.strip()
            if not tok:
                continue

            low = tok.lower()
            # алиасы стиля (standart -> standard и т.п.)
            low = alias_map.get(low, low)

            # 1) размер (xs/sm/md/lg/xl или свои)
            if low in size_tokens:
                try:
                    # TSizeMixin.size — строгий, но мы подаём только валидные токены
                    self.size = low
                except Exception:
                    # на всякий пожарный — не даём упасть
                    pass
                continue

            # 2) kind (primary/azure/success/...),
            #    конкретный класс сам решает, какие из них легальны через _normalize_kind
            if style_kinds and low in style_kinds:
                try:
                    self.kind = low
                except Exception:
                    # если _normalize_kind решил ругнуться — не ломаем весь парсинг
                    pass
                continue

            # 3) модификаторы стиля (pill/ghost/outline/rounded/...)
            if style_styles and low in style_styles:
                # "standard" = "ничего не добавлять"
                if low != "standard":
                    mods.append(low)
                continue

            # 4) auto-icon: эмодзи / не-ASCII токен → в icon, если ещё не установлен
            if (not icon_set) and hasattr(self, "icon") and self._is_icon_token(tok):
                try:
                    setattr(self, "icon", tok)
                    icon_set = True
                    continue
                except Exception:
                    # ну не получилось — и ладно, поедем дальше
                    pass

            # 5) всё остальное игнорируем
            # (сюда попадает "67", "lol", "abc123" и пр.)
            # при желании можно тихо логнуть в debug_mode через self.log(...)

        # финально сохраняем модификаторы в f_style
        self.f_style = " ".join(mods)
    # ..................................................................................................................
    # 🧱 CSS-классы на базе kind/style
    # ..................................................................................................................
    def get_kind_class(self) -> str:
        """
        Возвращает CSS-класс для kind, например: "btn-warning" или "badge-success".
        Использует prefix, если он задан у контрола.
        """
        prefix = getattr(self, "prefix", None)
        k = self.kind
        if not prefix or not k:
            return ""
        return f"{prefix}-{k}"

    def get_style_class(self) -> str:
        """
        Из self.style ("pill ghost") делает:
          "btn-pill btn-ghost" / "badge-pill badge-ghost" и т.п.
        Тоже опирается на prefix.
        """
        prefix = getattr(self, "prefix", None)
        style_str = self.style
        if not prefix or not style_str:
            return ""

        parts: list[str] = []
        for raw in style_str.split():
            tok = raw.strip()
            if not tok:
                continue
            parts.append(f"{prefix}-{tok}")

        return " ".join(parts)
# ======================================================================================================================
# 📁🌄 bb_ctrl_mixin.py 🜂 The End — See You Next Session 2025 💹 568
# ======================================================================================================================