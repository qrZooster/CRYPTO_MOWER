# ======================================================================================================================
# 📁 file        : bb_ctrl_sizes.py
# 🕒 created     : 14.11.2025 10:28
# 🎉 contains    : TSizeMixin - управление общей геометрией контрола
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
import re
from bb_ctrl_custom import *
# Ожидается, что где-то снаружи определено:
# ATOM_SIZES = ("xs", "sm", "md", "lg", "xl")
# 💎🧩⚙️ ... __ALL__ ...
__all__ = ["TSizeMixin",
           "CARD_SIZE_CFG", "GRID_ROW_SIZE_CFG", "GRID_CELL_SIZE_CFG",
           "CardSizeCfg", "GridRowSizeCfg", "GridCellSizeCfg"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧪 TSizeMixin — миксин логического размера (xs..xl)
# ----------------------------------------------------------------------------------------------------------------------
class TSizeMixin:
    """
    Миксин для логического размера и базовой геометрии визуального контрола.

    1) Логический размер:
       - size: один из ATOM_SIZES ('xs', 'sm', 'md', 'lg', 'xl')
       - хранится в self.f_size
       - по умолчанию 'md', даже если f_size == None или мусор

    2) Геометрия (layout):
       - top/left/right/bottom: '10px' | '5%' | 'auto'
         хранятся в self.f_top / f_left / f_right / f_bottom
       - width/height: 'auto' | '100px' | '50%' | 'calc(...)'
         хранятся в self.f_width / self.f_height

    3) Утилиты:
       - _size_idx(): индекс текущего размера в ATOM_SIZES
       - inc_size()/dec_size(): инкремент/декремент размера по шкале
       - box_style: dict со всеми заданными top/left/right/bottom/width/height
    """

    # ---------- ЛОГИЧЕСКИЙ РАЗМЕР (как у тебя было) ----------

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

    # ---------- ГЕОМЕТРИЯ: top / left / right / bottom ----------

    @staticmethod
    def _normalize_offset(value) -> str:
        """
        Нормализация значений для top/left/right/bottom.

        Допустимо:
            - 'auto'
            - '<int>px'  (например, '10px')
            - '<int>%'   (например, '5%')
        Во всех остальных случаях — ValueError.
        """
        if value is None:
            raise ValueError("Offset cannot be None")

        s = str(value).strip()
        if not s:
            raise ValueError("Offset cannot be empty")

        # auto (без учёта регистра)
        if s.lower() == "auto":
            return "auto"

        # <int>px или <int>%
        if re.fullmatch(r"-?\d+px", s) or re.fullmatch(r"-?\d+%", s):
            return s

        raise ValueError(
            f"Invalid offset value '{value}'. "
            "Allowed: 'auto', '<int>px', '<int>%'."
        )

    @property
    def top(self) -> str | None:
        """
        '10px' | '5%' | 'auto' | None
        """
        return getattr(self, "f_top", None)

    @top.setter
    def top(self, value: str | None) -> None:
        if value is None:
            self.f_top = None
        else:
            self.f_top = self._normalize_offset(value)

    @property
    def left(self) -> str | None:
        return getattr(self, "f_left", None)

    @left.setter
    def left(self, value: str | None) -> None:
        if value is None:
            self.f_left = None
        else:
            self.f_left = self._normalize_offset(value)

    @property
    def right(self) -> str | None:
        return getattr(self, "f_right", None)

    @right.setter
    def right(self, value: str | None) -> None:
        if value is None:
            self.f_right = None
        else:
            self.f_right = self._normalize_offset(value)

    @property
    def bottom(self) -> str | None:
        return getattr(self, "f_bottom", None)

    @bottom.setter
    def bottom(self, value: str | None) -> None:
        if value is None:
            self.f_bottom = None
        else:
            self.f_bottom = self._normalize_offset(value)

    # ---------- ГЕОМЕТРИЯ: width / height ----------

    @staticmethod
    def _normalize_dimension(value) -> str:
        """
        Нормализация значений для width/height.

        Допустимо:
            - 'auto'
            - '<int>px'
            - '<int>%'
            - 'calc(...)'  (любая строка, начинающаяся на 'calc(' и заканчивающаяся ')')

        Во всех остальных случаях — ValueError.
        """
        if value is None:
            raise ValueError("Dimension cannot be None")

        s = str(value).strip()
        if not s:
            raise ValueError("Dimension cannot be empty")

        # auto
        if s.lower() == "auto":
            return "auto"

        # <int>px / <int>%
        if re.fullmatch(r"-?\d+px", s) or re.fullmatch(r"-?\d+%", s):
            return s

        # calc(...)
        if s.lower().startswith("calc(") and s.endswith(")"):
            return s

        raise ValueError(
            f"Invalid dimension value '{value}'. "
            "Allowed: 'auto', '<int>px', '<int>%', 'calc(...)'."
        )

    @property
    def width(self) -> str | None:
        """
        'auto' | '100px' | '50%' | 'calc(...)' | None
        """
        return getattr(self, "f_width", None)

    @width.setter
    def width(self, value: str | None) -> None:
        if value is None:
            self.f_width = None
        else:
            self.f_width = self._normalize_dimension(value)

    @property
    def height(self) -> str | None:
        """
        'auto' | '100px' | '50%' | 'calc(...)' | None
        """
        return getattr(self, "f_height", None)

    @height.setter
    def height(self, value: str | None) -> None:
        if value is None:
            self.f_height = None
        else:
            self.f_height = self._normalize_dimension(value)

    # ---------- helper: dict стилей ----------

    @property
    def box_style(self) -> dict[str, str]:
        """
        Собирает dict для inline-стилей по геометрии.

        Включает только те ключи, которые заданы (не None).
        Пример:
            top='10px', width='50%' → {'top': '10px', 'width': '50%'}
        """
        style: dict[str, str] = {}

        top = getattr(self, "f_top", None)
        left = getattr(self, "f_left", None)
        right = getattr(self, "f_right", None)
        bottom = getattr(self, "f_bottom", None)
        width = getattr(self, "f_width", None)
        height = getattr(self, "f_height", None)

        if top is not None:
            style["top"] = top
        if left is not None:
            style["left"] = left
        if right is not None:
            style["right"] = right
        if bottom is not None:
            style["bottom"] = bottom
        if width is not None:
            style["width"] = width
        if height is not None:
            style["height"] = height

        return style
# ---
from dataclasses import dataclass
# ----------------------------------------------------------------------------------------------------------------------
# 🔰 CARD: конфиг размеров для TCard
# ----------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CardSizeCfg:
    icon_px: int
    title_font_px: int
    sub_title_font_px: int
    header_padding_y_px: int
    header_padding_x_px: int
    body_padding_y_px: int
    body_padding_x_px: int
    margin_y_px: int
    margin_x_px: int
# 💎 ... CARD_SIZE_CFG ...
CARD_SIZE_CFG: dict[str, CardSizeCfg] = {
    "xs": CardSizeCfg(
        icon_px=12,
        title_font_px=13,
        sub_title_font_px=11,
        header_padding_y_px=6,
        header_padding_x_px=6,
        body_padding_y_px=6,
        body_padding_x_px=6,
        margin_y_px=4,
        margin_x_px=4,
    ),
    "sm": CardSizeCfg(
        icon_px=14,
        title_font_px=14,
        sub_title_font_px=12,
        header_padding_y_px=8,
        header_padding_x_px=8,
        body_padding_y_px=8,
        body_padding_x_px=8,
        margin_y_px=6,
        margin_x_px=6,
    ),
    "md": CardSizeCfg(
        icon_px=16,
        title_font_px=16,
        sub_title_font_px=13,
        header_padding_y_px=12,
        header_padding_x_px=12,
        body_padding_y_px=12,
        body_padding_x_px=12,
        margin_y_px=8,
        margin_x_px=8,
    ),
    "lg": CardSizeCfg(
        icon_px=20,
        title_font_px=18,
        sub_title_font_px=14,
        header_padding_y_px=16,
        header_padding_x_px=16,
        body_padding_y_px=16,
        body_padding_x_px=16,
        margin_y_px=12,
        margin_x_px=12,
    ),
    "xl": CardSizeCfg(
        icon_px=24,
        title_font_px=22,
        sub_title_font_px=16,
        header_padding_y_px=20,
        header_padding_x_px=20,
        body_padding_y_px=20,
        body_padding_x_px=20,
        margin_y_px=16,
        margin_x_px=16,
    ),
}
# ----------------------------------------------------------------------------------------------------------------------
# 🔰 GRID: конфиг размеров для строк (TGrid_Tr)
# ----------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class GridRowSizeCfg:
    min_height_px: int
    padding_y_px: int
    font_px: int
# 💎 ... GRID_ROW_SIZE_CFG ...
GRID_ROW_SIZE_CFG: dict[str, GridRowSizeCfg] = {
    "xs": GridRowSizeCfg(
        min_height_px=20,
        padding_y_px=2,
        font_px=11,
    ),
    "sm": GridRowSizeCfg(
        min_height_px=24,
        padding_y_px=3,
        font_px=12,
    ),
    "md": GridRowSizeCfg(
        min_height_px=28,
        padding_y_px=4,
        font_px=13,
    ),
    "lg": GridRowSizeCfg(
        min_height_px=32,
        padding_y_px=5,
        font_px=14,
    ),
    "xl": GridRowSizeCfg(
        min_height_px=36,
        padding_y_px=6,
        font_px=16,
    ),
}
# ----------------------------------------------------------------------------------------------------------------------
# 🔰 GRID: конфиг размеров для ячеек (TGrid_Td)
# ----------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class GridCellSizeCfg:
    padding_y_px: int
    padding_x_px: int
    font_px: int
# 💎 ... GRID_CELL_SIZE_CFG ...
GRID_CELL_SIZE_CFG: dict[str, GridCellSizeCfg] = {
    "xs": GridCellSizeCfg(
        padding_y_px=1,
        padding_x_px=4,
        font_px=11,
    ),
    "sm": GridCellSizeCfg(
        padding_y_px=2,
        padding_x_px=6,
        font_px=12,
    ),
    "md": GridCellSizeCfg(
        padding_y_px=3,
        padding_x_px=8,
        font_px=13,
    ),
    "lg": GridCellSizeCfg(
        padding_y_px=4,
        padding_x_px=10,
        font_px=14,
    ),
    "xl": GridCellSizeCfg(
        padding_y_px=5,
        padding_x_px=12,
        font_px=16,
    ),
}
# ======================================================================================================================
# 📁🌄 bb_ctrl_sizes.py 🜂 The End — See You Next Session 2025 💹 284 -> 431
# ======================================================================================================================