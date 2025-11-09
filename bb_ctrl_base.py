# ======================================================================================================================
# 📁 file        : bb_ctrl_base.py — визуальная ветвь Tradition Core 2025 (UI-контролы и рендер)
# 🕒 created     : 17.10.2025 12:31
# 🎉 contains    : TCustomControl, TCompositeControl, TForm, TPage
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
import hashlib
import base64
import re
from typing import Optional, Dict, Any
from bb_sys import *
from bb_ctrl_custom import *
from bb_ctrl_mixin import *
from datetime import datetime
# 💎🧩⚙️ ... __ALL__ ...
__all__ = ["TGrid", "TPanel", "TCard", "TMenu", "TMonitor"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TGrid — каркас страницы / секции (flex-column из строк)
# ----------------------------------------------------------------------------------------------------------------------
class TGrid(TCompositeControl):
    prefix = "grid"
    MARK_FAMILY = "grid"
    MARK_LEVEL = 0

    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Контейнер строк грида (flex-каркас страницы / панели).

        Дочерние элементы — это TGrid_Tr (строки).
        Каждая строка сама является flex-контейнером по горизонтали и хранит TGrid_Td.

        По умолчанию грид — это вертикальный столбец строк:
            flex-direction: column;
            gap: 1rem;
            width: 100%;
            height: 100%;

        После создания можно править:
            .direction ('row'/'column')
            .border (если надо отдебажить рамкой)
        """
        super().__init__(Owner, Name)

        # --- Геометрия грида ---
        self.direction: str = "column"          # направление основного flex-потока
        self.Rows: list["TGrid_Tr"] = []        # упорядоченный набор строк (TGrid_Tr)

        # Делаем сам грид flex-контейнером (колонка строк)
        self.flex_box(
            direction=self.direction,
            gap="1rem",
            width="100%",
            height="100%",
        )

        # если снаружи кто-то поставил grid.border = "2px dashed lime"
        if getattr(self, "border", None):
            self.add_style(f"border:{self.border};")

        self.log("__init__", f"⚙️ grid {self.Name} created dir={self.direction}")
    # ..................................................................................................................
    # 🧱 Строки и ячейки грида
    # ..................................................................................................................
    def tr(self, index: int | None = None) -> "TGrid_Tr | None":
        """
        Доступ к строке грида.

        grid.tr()            → создаёт новую TGrid_Tr(Owner=self), пушит в Rows и возвращает её.
        grid.tr(-1) / tr(i)  → вернуть последнюю или i-ую строку без создания.

        ВНИМАНИЕ:
        - Каждая новая строка сразу подвешена к этому гриду (Owner=self), то есть проходит валидацию владения.
        - Логика авто-создания первой ячейки у строки (td0) живёт уже внутри самой строки TGrid_Tr (фаза позже).
        """
        if index is None:
            row = TGrid_Tr(self)
            self.Rows.append(row)
            return row
        try:
            if index == -1:
                return self.Rows[-1]
            return self.Rows[index]
        except IndexError:
            return None

    def td(self, row_index: int, cell_index: int | None = None) -> "TGrid_Td | None":
        """
        Удобный доступ к ячейке.

        grid.td(r)        → создаёт/возвращает первую свободную ячейку строки r.
        grid.td(r, c)     → вернуть конкретную ячейку c строки r.

        Реализация делегирована строке:
            row = grid.tr(r)
            row.td(c)
        """
        row = self.tr(row_index)
        if not row:
            return None
        return row.td(cell_index)
    # ..................................................................................................................
    # 🎨 Рендеринг грида
    # ..................................................................................................................
    def render(self):
        """
        Рендерим строки грида по порядку.
        Каждая строка сама:
            - откроет свой контейнер через _render()
            - отрендерит свои TGrid_Td
        Здесь мы просто вливаем результат строк в Canvas грида.
        """
        for row in self.Rows:
            row._render()
            self.Canvas.extend(row.Canvas)
    # ..................................................................................................................
    # 🔰 mark* (подсветка debug-семейства)
    # ..................................................................................................................
    def _mark_family(self) -> str | None:
        return "grid"

    def _mark_level(self) -> int:
        return 0
    # ..................................................................................................................
    # 🛡️ PHASE 2: политика владения
    # ..................................................................................................................
    def _owner_required(self) -> bool:
        """
        Грид не должен жить в вакууме.
        TGrid всегда часть чего-то большего:
        - страницы
        - карточки
        - td панели
        - td грида
        и т.д.
        """
        return True

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        """
        Кто имеет право быть Owner для TGrid?

        Идея: грид — это визуальный контейнер верхнего уровня разметки.
        Он может висеть на любом нормальном визуальном контейнере,
        то есть на любом наследнике TCustomControl.

        Это покрывает случаи:
          - Page1 (TPage)        → Grid1
          - Grid_Td3 (TGrid_Td)  → Grid2
          - Panel1 (TPanel)      → Grid3
          - CardBody (внутри TCard) → Grid4
        """
        return (TCustomControl,)

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        """
        Кого мы считаем законными детьми грида?

        Базово — строки грида (TGrid_Tr).
        Но:
        - на ранних стадиях прототипирования девелопер может сделать
              lbl = TLabel(grid)
          (crazy mode),
          и мы потом "пересадим" этот lbl в нужную td внутри последней строки.
          Чтобы не падать раньше времени, разрешаем временно и визуальные контролы.

        Поэтому пока:
          • TGrid_Tr   — структурные строки
          • TCustomControl — визуальные контролы, которые могут быть временно
                              повешены напрямую на грид и затем будут пересажены
                              в grid.tr(-1).td(-1) (эта логика придёт на PHASE 3/4).
        """
        return (TGrid_Tr, TCustomControl)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TGrid_Tr — строка грида (тонкий наследник TFlex_Tr)
# ----------------------------------------------------------------------------------------------------------------------
class TGrid_Tr(TFlex_Tr):
    prefix = "grid_tr"
    MARK_FAMILY = "grid"
    MARK_LEVEL = 1
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Строка грида. Наследует механику TFlex_Tr (flex-row, width:100%, height:auto).
        Оставляем грид-специфику: высота и строгая политика владения.
        Переопределяй в потомках.
        """
        super().__init__(Owner, Name)
        # --- Геометрия строки ---
        self.height: str = "auto"
        if self.height and self.height != "auto":
            self.add_style(f"height:{self.height};")
        # ... 🔊 ...
        self.log("__init__", f"⚙️ grid row {self.Name} created height={self.height}")
        # ⚡🛠️ TGrid_Tr ▸ End of __init__

    # ..................................................................................................................
    # 🔳 Работа с ячейками (совместимость c API грида)
    # ..................................................................................................................
    @property
    def Cells(self) -> list["TGrid_Td"]:
        return self.Tds  # type: ignore[return-value]

    @Cells.setter
    def Cells(self, value: list["TGrid_Td"]) -> None:
        self.Tds = value  # type: ignore[assignment]

    def td(self, index: int | None = None) -> "TGrid_Td | None":
        """
        Возвращает/создаёт ячейку строки.
        row.td()      → создаёт TGrid_Td(self), пушит в Tds и возвращает.
        row.td(-1)/i  → вернуть последнюю/конкретную ячейку или None.
        """
        if index is None:
            cell = TGrid_Td(self)
            self.Tds.append(cell)
            return cell
        try:
            if index == -1:
                return self.Tds[-1]
            return self.Tds[index]
        except IndexError:
            return None

    # ..................................................................................................................
    # 🛡️ Политика владения
    # ..................................................................................................................
    def _owner_required(self) -> bool:
        return True

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        return (TGrid,)

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        return (TGrid_Td,)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TGrid_Td — ячейка грида (тонкий наследник TFlex_Td)
# ----------------------------------------------------------------------------------------------------------------------
class TGrid_Td(TFlex_Td):
    prefix = "grid_td"
    MARK_FAMILY = "grid"
    MARK_LEVEL = 2
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        """
        Ячейка строки грида. Наследует механику TFlex_Td (flex-item, flow, рендер).
        Оставляем грид-специфику: width и строгую политику владения.
        Переопределяй в потомках.
        """
        super().__init__(Owner, Name)
        # --- Основные параметры td ---
        self.width: str = "auto"
        # ... 🔊 ...
        self.log("__init__", f"⚙️ grid cell {self.Name} created width={self.width}")
        # ⚡🛠️ TGrid_Td ▸ End of __init__

    # ..................................................................................................................
    # 🛡️ Политика владения
    # ..................................................................................................................
    def _owner_required(self) -> bool:
        return True

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        return (TGrid_Tr,)

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        return (TCustomControl,)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TPanel — универсальная панель (flex-row)
# ----------------------------------------------------------------------------------------------------------------------
class TPanel(TPlaceholderMixin, TFlex_Tr):
    prefix = "pnl"
    MARK_FAMILY = "panel"
    MARK_LEVEL = 0

    def __init__(self, Owner=None, Name=None):
        super().__init__(Owner, Name)

        # состояние автоколонки
        self._auto_td0: "TFlex_Td | None" = super().td(None)  # первая колонка
        self._td0_claimed: bool = False                       # True -> td0 явно занята контентом

        # по умолчанию всё летит в первую колонку
        if self._auto_td0 is not None:
            self.active_control = self._auto_td0

        app = self.app()
        if app and getattr(app, "debug_mode", False):
            # ✅ здесь _auto_td0 уже гарантированно есть
            border_frag = "border:1px dashed rgba(160,160,160,0.6);"

            # Текст плейсхолдера — имя панели
            self.place_holder = getattr(self, "Name", "") or ""

            # вся логика отрисовки/снятия плейсхолдера — в миксине
            self._init_placeholder(
                container=self._auto_td0,
                text=self.place_holder,
                border_style=border_frag,
            )

        self.log("__init__", f"panel {self.Name} created")

    # ..................................................................
    # 🧱 td() с "первой ячейкой по умолчанию"
    # ..................................................................
    def td(self, index: int | None = None) -> "TFlex_Td | None":
        """
        pnl.td() первый раз → возвращает уже созданную td0 (не снимая плейсхолдер сам по себе).
        pnl.td() второй раз → создаёт новую колонку (td1, td2, ...).
        td(n)/td(-1)        → обычная логика базового класса.
        """
        if index is None:
            if self._auto_td0 is not None and not self._td0_claimed:
                self._td0_claimed = True
                return self._auto_td0
            return super().td(None)

        return super().td(index)

    # ..................................................................
    # 🔁 Child registration hooks
    # ..................................................................
    def _notify_child_content(self, td: "TFlex_Td"):
        if td is self._auto_td0:
            self._td0_claimed = True
        self._disable_placeholder_if_needed()

    def add_control(self, ctrl: "TCustomControl"):
        # структурные колонки — как обычно
        if isinstance(ctrl, TFlex_Td):
            return super().add_control(ctrl)

        # по умолчанию кидаем в ПОСЛЕДНЮЮ ячейку (td(-1))
        cell = self.td(-1) or super().td(None)

        # убрать с панели (пересадка во внутренний td)
        if ctrl.Name in self.Components:
            del self.Components[ctrl.Name]
        if hasattr(self, "Controls") and ctrl.Name in self.Controls:
            del self.Controls[ctrl.Name]

        ctrl.Owner = cell
        cell.Components[ctrl.Name] = ctrl
        cell.add_control(ctrl)

        # панель «ожила»: снимаем плейсхолдер/рамку, если были
        self._disable_placeholder_if_needed()
        return ctrl

    # ..................................................................
    # 🔰 mark* methods
    # ..................................................................
    def _mark_family(self) -> str | None:
        return "panel"

    def _mark_level(self) -> int:
        return 0

    def _child_mark_level(self) -> int:
        return 1

    # ..................................................................
    # 🛡️ PHASE 2: политика владения
    # ..................................................................
    def _owner_required(self) -> bool:
        return True

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        return (TCustomControl,)

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        return (TFlex_Td, TCustomControl)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCardPanel — панель внутри карточки (header / footer / status)
# ----------------------------------------------------------------------------------------------------------------------
class TCardPanel(TFlex_Tr):
    prefix = "cpnl"
    MARK_FAMILY = "card"
    MARK_LEVEL = 1
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner=None, Name: str | None = None):
        """
        Панель карточки. Живёт ТОЛЬКО внутри TCard и заменяет старый TPanel.
        Назначение задаётся self.type:
          • "ptHeader" → верх карточки (иконка + title + sub_title + действия справа)
          • "ptFooter" → нижняя панель статуса
          • "ptStatus" → компактный статус-бар (мелкий шрифт)
          • "ptNone"   → универсальная гибкая строка
        Внутри всегда есть три колонки (td):
          left_td  — слева,
          mid_td   — середина (растягивается),
          right_td — справа.
        """
        super().__init__(Owner, Name)

        # --- Роль панели ---
        self.type: str = "ptNone"

        # --- Колонки панели ---
        # каждая колонка — это TFlex_Td, создаётся сразу и живёт постоянно
        self.left_td = self.td()
        self.mid_td = self.td()
        self.right_td = self.td()

        # левая колонка — контент слева (иконка+заголовок в header)
        self.left_td.add_class("d-flex")
        self.left_td.add_class("align-items-start")
        self.left_td.add_class("gap-2")
        self.left_td.add_class("flex-wrap")

        # средняя колонка — растягиваемая зона
        self.mid_td.add_class("d-flex")
        self.mid_td.add_class("align-items-center")
        self.mid_td.add_class("flex-grow-1")
        self.mid_td.add_class("gap-2")
        self.mid_td.add_class("flex-wrap")

        # правая колонка — actions справа
        self.right_td.add_class("d-flex")
        self.right_td.add_class("align-items-center")
        self.right_td.add_class("gap-2")
        self.right_td.add_class("flex-wrap")
        self.right_td.add_class("ms-auto")

        # ... 🔊 ...
        self.log("__init__", f"⚙️ card-panel {self.Name} created type={self.type}")
        # ⚡🛠️ TCardPanel ▸ End of __init__
    # ..................................................................................................................
    # 🔧 Внутренний автосборщик заголовка карточки
    # ..................................................................................................................
    def _auto_header_compose(self):
        """
        Автоматически наполняет шапку карточки (тип ptHeader), если левый td пустой.
        Строим:
            [ TIcon(icon) ][
                TLabel(h2, title)
                TLabel(span, sub_title) (если есть)
            ]
        Данные берутся у self.Owner (это TCard): .icon / .title / .sub_title.
        Если разработчик уже сам что-то положил в left_td, мы не трогаем.
        """
        from bb_ctrl_atom import TLabel, TIcon
        if self.type != "ptHeader":
            return

        # уже есть контент? не лезем
        if getattr(self.left_td, "Flow", []):
            return

        card = getattr(self, "Owner", None)
        if not card:
            return

        icon_txt = getattr(card, "icon", "")
        title_txt = getattr(card, "title", "")
        sub_txt = getattr(card, "sub_title", "")

        # --- ICON ---
        if icon_txt:
            ico = TIcon(self.left_td)
            ico.icon = icon_txt
            ico.size = 20
            ico.h = 0
            self.left_td.add(ico)

        # --- BLOCK: title + sub_title (вертикально)
        block = TCompositeControl(self.left_td, "AutoTitleBlock")
        block.add_class("d-flex")
        block.add_class("flex-column")

        # Заголовок (h2)
        lbl_title = TLabel(block, "AutoTitle")
        lbl_title.h = 2
        lbl_title.add_class("card-title")
        lbl_title.add_class("m-0")
        lbl_title.add_style("line-height:1.2; font-size:16px; font-weight:bold; color:#0056b3;")
        if title_txt:
            lbl_title.caption = title_txt
        # если title пустой → TLabel сам подставит своё Name

        # Подзаголовок (мелкий серый) — только если есть
        if sub_txt:
            lbl_sub = TLabel(block, "AutoSub")
            lbl_sub.h = 0
            lbl_sub.caption = sub_txt
            lbl_sub.add_style("color:#666; font-size:13px; line-height:1.2;")

        # положить блок целиком в левую колонку
        self.left_td.add(block)
    # ..................................................................................................................
    # 🎨 Render
    # ..................................................................................................................
    def render(self):
        """
        Рендерит панель карточки.
        1) если это ptHeader → вызываем _auto_header_compose() для левой колонки
        2) настраиваем типографику ptStatus (мелкий серый текст)
        3) дальше вызываем стандартный рендер TFlex_Tr (каждый td сам дорендерит детей)
        """
        # автоконтент для header
        self._auto_header_compose()

        # мелкий текст для статус-панелей
        if self.type == "ptStatus":
            self.add_class("text-muted")
            self.add_class("small")

        # теперь обычный рендер flex-строки
        super().render()
    # ..................................................................................................................
    # 🔌 Хелперы-совместимость с прежним API панели
    # ..................................................................................................................
    def add_left(self, item: any):
        """
        Добавляет узел в левую колонку (как раньше left_items.append()).
        item может быть str (сырой html) или TCompositeControl.
        """
        self.left_td.add(item)
        return self

    def add_middle(self, item: any):
        """
        Добавляет узел в среднюю колонку.
        """
        self.mid_td.add(item)
        return self

    def add_right(self, item: any):
        """
        Добавляет узел в правую колонку (обычно кнопки действий).
        """
        self.right_td.add(item)
        return self
    # ..................................................................................................................
    # 🔰 mark* methods
    # ..................................................................................................................
    def _mark_family(self) -> str | None:
        return "card"

    def _mark_level(self) -> int:
        return 1
    # ..................................................................................................................
    # 🛡️ PHASE 2: политика владения
    # ..................................................................................................................
    def _owner_required(self) -> bool:
        return True  # header/footer без карточки вообще не существуют

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        # card.header.Owner -> card
        # card.footer.Owner -> card
        return (TCard,)

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        # header/footer состоят из колонок (left_td, mid_td, right_td),
        # которые являются TFlex_Td.
        return (TFlex_Td,)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCardBody — панель тела карточки (без плейсхолдера)
# ----------------------------------------------------------------------------------------------------------------------
class TCardBody(TPanel):
    prefix = "card_body"
    MARK_FAMILY = "card"
    MARK_LEVEL = 1

    def __init__(self, Owner=None, Name: str | None = None):
        """
        Тело карточки. Наследует поведение панели, но:
        - добавляет класс 'card-body';
        - сразу отключает placeholder/рамку панели в debug;
        - служит приёмником для детей, созданных с Owner=TCard.
        """
        super().__init__(Owner, Name)

        # семантика Bootstrap/Tabler
        self.add_class("card-body")

        # у CardBody нам панельный placeholder не нужен вообще
        try:
            self._disable_placeholder_if_needed()  # убрать auto td0-плейсхолдер и пунктир
        except AttributeError:
            # на случай, если вдруг миксина нет (страховка вперёд)
            pass

        self.log("__init__", f"⚙️ card-body {self.Name} created")

    # ЯВНО говорим debug-механизму: это не panel, а card[1]
    def _mark_family(self) -> str | None:
        return "card"

    def _mark_level(self) -> int:
        return 1
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCard — карточка с header / body / footer (базовый каркас Tradition Core)
# ----------------------------------------------------------------------------------------------------------------------
class TCard(TCompositeControl):
    prefix = "card"
    MARK_FAMILY = "card"
    MARK_LEVEL = 0

    def __init__(self, Owner=None, Name: str | None = None):
        super().__init__(Owner, Name)
        self._constructing = True                      # <— NEW
        self.add_class("card");
        self.add_class("shadow-sm")

        self.icon = "🔥";
        self.title = self.Name;
        self.sub_title = ""
        self.body_text_default = self.Name

        self.header = TCardPanel(self, "Header")
        self.header.add_class("card-header")           # <— keep Tabler role

        self.body = TCardBody(self, "Body")            # <— exists before using

        self.footer = TCardPanel(self, "Footer")
        self.footer.add_class("card-footer")
        self.footer.add_class("text-muted"); self.footer.add_class("small")

        self._constructing = False                     # <— NEW
        self.log("__init__", f"⚙️ card {self.Name} created")
    # ..........................................................
    # 🔹 Фасад: caption → Header.caption
    # ..........................................................
    @property
    def caption(self) -> str | None:
        header = getattr(self, "Header", None)
        # если Header ещё не создан или без миксина — вернём None
        return getattr(header, "caption", None) if header is not None else None

    @caption.setter
    def caption(self, value: str | None):
        header = getattr(self, "Header", None)
        if header is not None and hasattr(header, "caption"):
            header.caption = value
    # ..........................................................
    # 🔹 Фасад: icon → Header.icon
    # ..........................................................
    @property
    def icon(self) -> str | None:
        header = getattr(self, "Header", None)
        return getattr(header, "icon", None) if header is not None else None

    @icon.setter
    def icon(self, value: str | None):
        header = getattr(self, "Header", None)
        if header is not None and hasattr(header, "icon"):
            header.icon = value
    # ..................................................................................................................
    # 🎨 Рендер
    # ..................................................................................................................
    def render(self):
        """
        1) header._render()
        2) body._render()  (если пусто — кладём body_text_default)
        3) footer._render()
        """
        if self.header:
            self.header._render()
            self.Canvas.extend(self.header.Canvas)
        if not self._body_has_content():
            self.body.td().add(self.body_text_default)
        self.body._render()
        self.Canvas.extend(self.body.Canvas)
        if self.footer:
            self.footer._render()
            self.Canvas.extend(self.footer.Canvas)
    # ..................................................................................................................
    # 🔧 Перехват регистрации детей: всё не header/body/footer → в body
    # ..................................................................................................................
    def structural_children(self) -> tuple["TCustomControl", ...]:
        # header/footer — служебные, всё остальное — "контент"
        return tuple(
            c for c in (
                getattr(self, "header", None),
                getattr(self, "body", None),
                getattr(self, "footer", None),
            ) if c is not None
        )
    # ..................................................................................................................
    # 🔍 Вспомогательное
    # ..................................................................................................................
    def _body_has_content(self) -> bool:
        for td in getattr(self.body, "Tds", []):
            if getattr(td, "Flow", []):
                return True
        return False
    # ------------------------------------------------------------------------------------------------------------------
    # mark() / debug family hooks
    # ------------------------------------------------------------------------------------------------------------------
    def _mark_family(self) -> str | None:
        # семейство, которое участвует в подсветке и палитре
        return "card"

    def _mark_level(self) -> int:
        # карточка — корневой объект своего семейства
        return 0

    def _child_mark_level(self) -> int:
        # её внутренние flex-панели (header/footer панельки) помечаем уровнем 1
        return 1

    # политика владения (PHASE 2)
    def _owner_required(self) -> bool:
        # Card всегда чей-то ребёнок (страницы, td, панели и т.п.)
        return True

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        # Карточка может жить в любом визуальном контейнере
        # (ячейка грида, flex-td, панель, страница и т.д.),
        # а значит достаточно сказать "любой TCustomControl".
        return (TCustomControl,)

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        # У карточки внутри могут жить:
        #  - её служебные панели header/footer (TCardPanel)
        #  - контентные контролы (кнопки, лейблы, etc.)
        return (TCustomControl,)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TMenu — навигационный контейнер (<nav><ul class="nav ...">...</ul></nav>)
# ----------------------------------------------------------------------------------------------------------------------
class TMenu(TCompositeControl):
    prefix = "menu"
    MARK_FAMILY = "menu"
    MARK_LEVEL = 0

    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        super().__init__(Owner, Name)
        self.items: list["TMenuItem"] = []
        self.orientation: str = "horizontal"  # "horizontal" | "vertical"
        self.variant: str = "pills"           # "pills" | "tabs" | "plain"
        self.auto_active: bool = True
        self.flex_box(direction="row", gap="0.5rem", width="100%")  # контейнер можно стилизовать снаружи

    # семантический корневой тег
    def root_tag(self) -> str:
        return "nav"

    # политика владения/детей (динамически, чтобы избежать форвард-линков)
    def _allowed_child_types(self) -> tuple[type, ...] | None:
        cls = globals().get("TMenuItem")
        return (cls,) if cls else None

    def item(self, caption: str, link: str | None = None) -> "TMenuItem":
        it = TMenuItem(self)
        it.caption = caption
        if link is not None:
            s = str(link).strip()
            if s.startswith("page="):
                it.page = s[5:]
            elif s.startswith("href="):
                it.href = s[5:]
            # иное — игнор (MVP)
        self.items.append(it)
        return it

    def _ul_class(self) -> str:
        parts = ["nav"]
        v = (self.variant or "pills").lower()
        if v == "pills":
            parts.append("nav-pills")
        elif v == "tabs":
            parts.append("nav-tabs")
        # "plain" -> только "nav"
        if (self.orientation or "horizontal").lower() == "vertical":
            parts.append("flex-column")
        parts.append("tc-menu")
        return " ".join(parts)

    def render(self):
        # актуализируем active по текущей странице (если нужно)
        if self.auto_active:
            try:
                app = self.app()
            except Exception:
                app = None
            active_page = getattr(app, "current_page", None) or _key("ACTIVE_PAGE", "main")
            for it in self.items:
                it.active = bool(it.page and str(it.page) == str(active_page))

        # <ul class="nav ..."> ... </ul>
        self.tg("ul", cls=self._ul_class())
        # если items пуст, подберём прямых детей-элементов как fallback
        items = self.items[:] or [
            c for c in getattr(self, "Controls", {}).values()
            if c.__class__.__name__ == "TMenuItem"  # без прямой ссылки на класс
        ]
        for it in items:
            it._render()
            self.Canvas.extend(it.Canvas)
        self.etg("ul")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TMenuItem — пункт меню (<li class="nav-item"><a class="nav-link">...</a></li>)
# ----------------------------------------------------------------------------------------------------------------------
class TMenuItem(TCompositeControl, TLinkMixin, TCaptionMixin, TIconMixin):
    prefix = "menu_item"
    MARK_FAMILY = "menu"
    MARK_LEVEL = 1

    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        super().__init__(Owner, Name)
        self.active: bool = False
        self.disabled: bool = False
        self.group_index: int = 0  # для стилей/логики групп
        # лёгкая базовая типографика для вертикального стека контента, если понадобится
        # (сам <a> стилизуется классами nav-link)
        self.flex_cell(grow=None, padding=None)

    def root_tag(self) -> str:
        return "li"

    # политика владения
    def _owner_required(self) -> bool:
        return True

    def _allowed_owner_types(self) -> tuple[type, ...] | None:
        cls = globals().get("TMenu")
        return (cls,) if cls else None

    def _allowed_child_types(self) -> tuple[type, ...] | None:
        # внутри <li> может жить любой визуальный контрол, но MVP сам рисует <a>
        return (TCustomControl,)

    def render(self):
        # <li ...>
        li_cls = " ".join(filter(None, [
            "nav-item",
            f"tc-menu-g-{int(self.group_index)}" if self.group_index else "",
        ]))
        li_attr = " ".join(filter(None, [
            f"data-menu-group='{int(self.group_index)}'" if self.group_index else ""
        ])) or None
        self.tg("li", cls=li_cls or None, attr=li_attr)

        # <a ...> — href: отключаем при disabled
        a_cls = " ".join(filter(None, [
            "nav-link",
            "active" if self.active else "",
            "disabled" if self.disabled else "",
        ]))
        href = "#" if self.disabled else (self.href or "#")
        a_attr_extra = []
        if self.disabled:
            a_attr_extra.append('tabindex="-1"')
            a_attr_extra.append('aria-disabled="true"')
        a_attr = f"href='{href}'"
        if a_attr_extra:
            a_attr += " " + " ".join(a_attr_extra)

        self.tg("a", cls=a_cls or None, attr=a_attr)
        self.text(self.caption or self.Name)
        self.etg("a")

        # </li>
        self.etg("li")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TMonitor
# ----------------------------------------------------------------------------------------------------------------------
class TMonitor(TCustomControl, TwsSubscriberMixin):
    prefix = "monitor"
    MARK_FAMILY = "_SINGLE_"
    MARK_LEVEL = 0
    """
    Простой монитор логов:
    - корень: <div class="tc-monitor ...">
    - внутри: <pre class="tc-monitor-body" ...> — точка привязки к WS
    По умолчанию подписан на канал "log", type="log_line".
    """
    def __init__(self, Owner: TOwnerObject | None = None, Name: str | None = None):
        super().__init__(Owner, Name)

        # WS-подписка по умолчанию
        self.channel = "log"
        self.type = "log_line"

        # режим работы монитора (для фронта)
        self.mode: str = "append"   # "append" | "replace" (сейчас используем append)
        self.max_lines: int = 500   # лимит строк в <pre>, фронт сам обрежет

        # базовые классы оформления (без навязывания цветов)
        self.add_class("tc-monitor")
        self.add_class("p-2")
        self.add_class("font-monospace")

        self.log("__init__", f"monitor {self.Name} created")

    def render(self):
        """
        Рисуем внутренний <pre>, который будет получать данные по WebSocket.
        Все data-* атрибуты используются только фронтендом.
        """
        # собираем data-* атрибуты для привязки
        attr_parts: list[str] = []

        # из миксина TwsSubscriberMixin: data-tws-channel / data-tws-type
        if hasattr(self, "get_tws_attrs"):
            tws_attrs = (self.get_tws_attrs() or "").strip()
            if tws_attrs:
                attr_parts.append(tws_attrs)

        # режим работы и лимит строк — чисто фронтовые параметры
        attr_parts.append(f"data-tws-mode='{self.mode}'")
        attr_parts.append(f"data-tws-max='{int(self.max_lines)}'")

        attr_str = " ".join(attr_parts).strip() or None

        # корень уже открыт в _render() (div.monitor),
        # здесь рисуем только <pre> как тело монитора
        self.tg("pre", cls="tc-monitor-body", attr=attr_str)
        # стартовое содержимое оставляем пустым — всё придёт из WS
        self.etg("pre")
# ======================================================================================================================
# 📁🌄 bb_ctrl_base.py 🜂 The End — See You Next Session 2025 💹 188 -> 1755 -> 2088 -> 775 -> 979 -> 851
# ======================================================================================================================









