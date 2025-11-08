# ======================================================================================================================
# 📁 file        : _sys.py — Фасад контролов: единая точка импорта UI-компонентов
# 🕒 created     : 02.11.2025 16:31
# 🎉 contains    : Реэкспорт базовых классов и контролов (custom/atom/base/pages) для удобного импорта
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
from bb_ctrl_custom import TCustomControl, TCompositeControl, TFlex_Tr, TFlex_Td
from bb_ctrl_atom import TAtomControl, TLabel, TIcon, TButton, TBadge, TAvatar
from bb_ctrl_base import TPanel, TCardPanel, TCardBody, TCard, TGrid, TGrid_Tr, TGrid_Td, TMenu
from bb_ctrl_mixin import *
# 💎 ... FACADE EXPORTS ...
__all__ = ["TCustomControl", "TCompositeControl", "TFlex_Tr", "TFlex_Td", "TAtomControl",
           "TLabel", "TIcon", "TButton", "TBadge",
           "TPanel", "TCardPanel", "TCardBody", "TCard",
           "TGrid", "TGrid_Tr", "TGrid_Td",
           "label", "icon", "button",
           "panel", "card", "grid", "menu", "badge", "avatar"]
# ......................................................................................................................
# 🍒 CONTROLS FACADE
# ......................................................................................................................
def label(owner, caption=None):
    """ Фасад: создаёт TLabel у owner с заданным caption и возвращает его."""
    lbl = TLabel(owner)
    if caption is not None:
        lbl.caption = str(caption)
    return lbl
# ---
def icon(owner, _icon="🌐"):
    """ Фасад: создаёт TIcon у owner. """
    r = TIcon(owner)
    r.icon = str(_icon)
    return r
# ---
def ico(owner, _icon="🌐"):
    return icon(owner, _icon)
# ---
def button(owner, arg=None, style=None):
    """
    Создаёт TButton. Поведение arg:
      - если arg в известных kind (semantic или social) → r.kind = arg
      - если arg выглядит как ссылка (/..., http..., #...) → r.href = arg
      - иначе → r.caption = arg
    style пробрасываем как есть.
    """
    r = TButton(owner)

    if isinstance(arg, str) and arg:
        low = arg.strip().lower()
        known = (
            {"primary","info","warning","danger","success","secondary","close"} |
            {"github","twitter","telegram","youtube","facebook","instagram","linkedin","whatsapp","discord"}
        )
        if low in known:
            r.kind = low
        elif low.startswith(("http://","https://","/","#")):
            r.href = arg
        else:
            r.caption = arg

    if style is not None:
        r.style = style
    return r
# ---
def btn(owner, caption=None):
    return button(owner, caption)
# ---
def panel(owner, name=None):
    """ Фасад: создаёт TPanel под owner и возвращает его. """
    return TPanel(owner, name)
# ---
def card(owner, title=None):
    """ Фасад: создаёт TCard под owner, выставляет .title и возвращает карточку. """
    r = TCard(owner)
    if title is not None:
        r.title = str(title)
    return r
# ---
def grid(owner, name=None):
    """ Фасад: создаёт TGrid под owner и возвращает его. """
    r = TGrid(owner)
    if name is not None:
        r.Name = str(name)
    return r
# ---
def menu(owner, name=None):
    """
    Фасад: создаёт TMenu под owner и возвращает его.
    name, если задан, записывается в .Name (чисто для читаемости логов/отладчика).
    """
    mn = TMenu(owner)
    if name is not None:
        mn.Name = str(name)
    return mn
# 🐯 ---
def badge(owner, caption=None, *, style=None):
    r = TBadge(owner)

    # --- разбор caption (как мы уже делали) ---
    parsed_caption = None
    style_from_caption = None
    icon_from_caption = None
    has_human_text = False

    if isinstance(caption, str) and caption.strip():
        parsed_caption, style_from_caption, icon_from_caption, has_human_text = \
            _badge_parse_caption_and_style(caption)

    # --- собираем итоговый style ---
    style_chunks: list[str] = []
    if style_from_caption:
        style_chunks.append(style_from_caption)
    if isinstance(style, str) and style.strip():
        style_chunks.append(style.strip())

    full_style = " ".join(style_chunks).strip()
    if full_style:
        r.style = full_style

    # --- иконка из caption, если была ---
    if icon_from_caption is not None:
        r.icon = icon_from_caption

    # --- caption-приоритеты ---
    if parsed_caption is not None:
        r.caption = parsed_caption
    elif caption is not None and not isinstance(caption, str):
        r.caption = str(caption)
    # строковый caption без parsed_caption мы специально НЕ трогаем — он был чисто стилевой

    # ⚠️ вот тут главное изменение
    style_tokens = {t.strip().lower() for t in (full_style or "").split()}

    # чистый notification: только стили, без «живого» текста → показываем точку без текста
    if "notification" in style_tokens and not has_human_text and parsed_caption is None:
        # не трогаем caption, ставим флаг на самом объекте
        r.silent = True

    return r
# ---
# вспомогательный разбор строки caption в стиле "azure ⭐ outline sm"
def _badge_parse_caption_and_style(raw: str):
    """
    Возвращает:
      caption_text | None,
      style_string | None,
      icon_text    | None,
      has_human_text: bool  (были ли НЕ-стилевые токены)
    """
    from bb_ctrl_atom import ATOM_SIZES  # если в этом же файле – можно убрать импорт

    raw = (raw or "").strip()
    if not raw:
        return None, None, None, False

    kinds = getattr(TBadge, "STYLE_KINDS", set()) or set()
    styles = getattr(TBadge, "STYLE_STYLES", set()) or set()
    alias  = getattr(TBadge, "STYLE_ALIAS", {}) or {}
    size_tokens = set(ATOM_SIZES)

    tokens = raw.split()

    kind_token: str | None = None
    size_token: str | None = None
    style_tokens: list[str] = []
    caption_tokens: list[str] = []
    icon_token: str | None = None
    seen_text = False

    for tok in tokens:
        if not tok:
            continue

        low = tok.lower()
        low = alias.get(low, low)

        if not seen_text:
            # kind (цвет/вариант)
            if low in kinds:
                if kind_token is None:
                    kind_token = low
                continue

            # размер xs..xl
            if low in size_tokens:
                size_token = low
                continue

            # модификаторы стиля (outline, pill, notification, blink ...)
            if low in styles:
                style_tokens.append(low)
                continue

            # "иконка" — одиночный символ (в т.ч. эмодзи)
            if len(tok) == 1 and not tok.isalnum():
                if icon_token is None:
                    icon_token = tok
                continue

        # всё остальное считаем обычным текстом
        seen_text = True
        caption_tokens.append(tok)

    has_human_text = bool(caption_tokens)
    caption_text: str | None = " ".join(caption_tokens) if caption_tokens else None

    # есть kind, НЕТ notification и нет явного текста → caption = Kind
    has_notification = "notification" in (t.lower() for t in style_tokens)
    if caption_text is None and kind_token and not has_notification:
        caption_text = kind_token.capitalize()

    # собираем style-строку из kind/size/mod'ов
    style_parts: list[str] = []
    if kind_token:
        style_parts.append(kind_token)
    if size_token:
        style_parts.append(size_token)
    style_parts.extend(style_tokens)

    style_text = " ".join(style_parts) if style_parts else None
    return caption_text, style_text, icon_token, has_human_text
# ---
def avatar(owner, src=None, *, style=None):
    """
    Фасад: создаёт TAvatar у owner.

    Сигнатура сохраняет «правило трёх»:
        avatar(owner, src=None, *, style=None)

    Примеры:
        # фото по URL/пути
        av = avatar(td, "/assets/Igor.jpg", style="lg rounded")

        # авто-инициалы по имени
        av = avatar(td, "Igor Kuzmichev", style="blue lg rounded")

        # явные инициалы
        av = avatar(td, "IK", style="green sm rounded")

        # эмодзи-иконка
        av = avatar(td, "👤", style="teal sm square")

        # статус через style (если TAvatar.status есть):
        av = avatar(td, "/assets/Igor.jpg", style="lg rounded online")
    """
    # TAvatar уже объявлен выше в этом же модуле, так что import не нужен
    r = TAvatar(owner)

    # --- разбор src ---
    if isinstance(src, str):
        s = src.strip()
        if s:
            low = s.lower()

            # 1) Похоже на URL/путь/картинку → src
            is_url = (
                low.startswith(("http://", "https://"))
                or s.startswith("/")
                or low.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"))
            )
            if is_url and hasattr(r, "src"):
                r.src = s

            else:
                # 2) Явные инициалы: "IK", "JD", "A"
                if (
                    len(s) <= 3
                    and " " not in s
                    and s.isalpha()
                    and s.upper() == s
                    and hasattr(r, "initials")
                ):
                    r.initials = s

                # 3) Эмодзи/символ → icon
                elif len(s) <= 3 and " " not in s and hasattr(r, "icon") and not s.isalnum():
                    r.icon = s

                # 4) Всё остальное считаем человекочитаемым именем
                elif hasattr(r, "caption"):
                    r.caption = s
        # пустая строка → просто игнорируем
    elif src is not None:
        # нестроковое значение: просто в caption, если он есть
        if hasattr(r, "caption"):
            r.caption = str(src)

    # --- разбор style ---
    if style is not None:
        s = str(style).strip()
        if s:
            tokens = s.split()
            rest_tokens = []
            status_token = None

            for t in tokens:
                tl = t.lower()
                if tl in {"online", "offline", "busy", "away"} and hasattr(r, "status"):
                    status_token = tl
                else:
                    rest_tokens.append(t)

            if status_token is not None and hasattr(r, "status"):
                r.status = status_token

            if rest_tokens:
                r.style = " ".join(rest_tokens)

    return r
# ======================================================================================================================
# 📁🌄 _sys.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 72 -> 312
# ======================================================================================================================
