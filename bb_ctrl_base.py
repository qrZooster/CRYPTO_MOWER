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
__all__ = ["TGrid", "TPanel", "TCard", "TMenu", "TMonitor", "TCardMonitor"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TGrid — каркас страницы / секции (flex-column из строк)
# ----------------------------------------------------------------------------------------------------------------------
class TGrid(TCompositeControl):
    prefix = "grid"
    MARK_FAMILY = "grid"
    MARK_LEVEL = 0
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        """
        Контейнер строк грида (flex-каркас страницы / панели).
        Базовая инициализация:
        - flex-column
        - список Rows
        - первая строка grid.tr(0) с хотя бы одной ячейкой
        """
        super().do_init()
        # направление основного flex-потока
        self.direction: str = "column"
        # упорядоченный набор строк (TGrid_Tr)
        self.Rows: list["TGrid_Tr"] = []
        # делаем сам грид flex-контейнером (колонка строк)
        self.flex_box(
            direction=self.direction,
            gap="1rem",
            width="100%",
            height="100%",
        )
        # если снаружи поставили grid.border = "2px dashed lime"
        if getattr(self, "border", None):
            self.add_style(f"border:{self.border};")

        # создаём первую строку по умолчанию
        self.tr()  # row 0 с уже готовой td(0) внутри
    # ..........................................................
    # 🔹 active_control: последняя строка / её активная ячейка
    # ..........................................................
    def get_active_control(self) -> "TCustomControl":
        """
        Контейнер по умолчанию для контента TGrid:

        - если строк ещё нет → создаём первую строку TGrid_Tr + её первую ячейку TGrid_Td,
        - если строки уже есть → берём последнюю строку и её active_control
          (для TGrid_Tr это последняя ячейка).

        Любой контрол, созданный с Owner=TGrid (btn = TButton(grid)),
        будет пересажен именно в этот target-ctrl.
        """
        rows = getattr(self, "Rows", None)

        # Грид ещё пуст → лениво создаём первую строку
        if not rows:
            row = self.tr()  # создаст TGrid_Tr(self) и положит в self.Rows
        else:
            row = rows[-1]

        # строка сама знает, кто у неё активная ячейка (TFlex_Tr.get_active_control)
        if isinstance(row, TCompositeControl):
            return row.get_active_control()

        # запасной вариант, на случай странного Owner
        return super().get_active_control()

    def is_structural_child(self, ctrl: "TCustomControl") -> bool:
        """
        Для грида любые TGrid_Tr — всегда структурные дети (layout-only).
        Их нельзя считать контентом и роутить через active_control.
        """
        return isinstance(ctrl, TGrid_Tr) or super().is_structural_child(ctrl)
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

    def td(self, row_index: int | None = None, cell_index: int | None = None) -> "TGrid_Td | None":
        """
        Удобный доступ к ячейке.
        grid.td()            → работает с первой строкой (row_index = 0).
                               При необходимости строка 0 создаётся.
        grid.td(r)           → создаёт/возвращает первую свободную ячейку строки r.
        grid.td(r, c)        → вернуть конкретную ячейку c строки r.

        Реализация делегирована строке:
            row = grid.tr(r)
            row.td(c)
        """
        # по умолчанию работаем с первой строкой
        if row_index is None:
            row_index = 0
        # гарантируем наличие строки row_index
        while len(self.Rows) <= row_index:
            # tr() без аргументов добавляет новую строку в конец
            self.tr()
        # ---
        row = self.Rows[row_index]
        return row.td(cell_index)
    # ..................................................................................................................
    # 🎨 Рендеринг грида
    # ..................................................................................................................
    def render(self):
        """
        Рендерим строки грида по порядку.
        В debug-режиме перед рендером проставляем place_holder
        и пунктирную рамку для пустых ячеек:

            • если строка одна  → Grid1.td(c)
            • если строк > 1    → Grid1.tr(r).td(c)
        """
        app = None
        try:
            app = self.app()
        except Exception:
            app = None

        dbg = bool(app and getattr(app, "debug_mode", False))
        rows_count = len(self.Rows)

        if dbg and rows_count:
            #base_name = self.Name
            for r, row in enumerate(self.Rows):
                cells = getattr(row, "Tds", [])
                for c, cell in enumerate(cells):
                    # debug-класс для каждой ячейки
                    if hasattr(cell, "add_class"):
                        cell.add_class(tc_dbg_class("cell"))
                    # содержимое ячейки
                    flow = getattr(cell, "Flow", [])
                    # если в ячейке уже есть контент — плейсхолдер и скелет не нужны
                    if flow:
                        # на всякий случай уберём старый плейсхолдер, если он был
                        if hasattr(cell, "place_holder"):
                            cell.place_holder = None
                        continue
                    # пустая ячейка: включаем "скелет" — рамка + подпись
                    if hasattr(cell, "add_style"):
                        cell.add_style("border:1px dashed rgba(160,160,160,0.6);")
                    # подпись по протоколу
                    label = self._placeholder_label(r, c, rows_count)
                    cell.place_holder = label
        # обычный рендер строк
        for row in self.Rows:
            row._render()
            self.Canvas.extend(row.Canvas)

    def _placeholder_label(self, r: int, c: int, rows_count: int) -> str:
        """
        Текст плейсхолдера для пустой ячейки в debug-режиме.
        Базовая реализация: имя самого грида.
        """
        base_name = getattr(self, "Name", "") or self.__class__.__name__
        if rows_count == 1:
            return f"{base_name}.td({c})"
        return f"{base_name}.tr({r}).td({c})"
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
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        """
        Строка грида. Наследует механику TFlex_Tr:
        - Tds + td(0)
        - flex-row, width:100%, height:auto
        Оставляем грид-специфику: высота и строгую политику владения.
        """
        super().do_init()

        # --- Геометрия строки ---
        self.height: str = "auto"
        if self.height and self.height != "auto":
            self.add_style(f"height:{self.height};")
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
    def do_init(self):
        """
        Ячейка строки грида. Наследует механику TFlex_Td (flex-item, flow, рендер).
        Оставляем грид-специфику: width и строгую политику владения.
        """
        super().do_init()
        # --- Основные параметры td ---
        self.width: str = "auto"
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
# 🧩 TPanel — универсальная панель (однострочный grid)
# ----------------------------------------------------------------------------------------------------------------------
class TPanel(TGrid):
    prefix = "pnl"
    MARK_FAMILY = "panel"
    # 🔒 ЯВНЫЙ ЗАПРЕТ попыток работать со строками, как в гриде
    def tr(self, index: int | None = None) -> "TGrid_Tr":
        """
        Панель — это одна строка.
        Единственный допустимый вызов:
        - tr() при отсутствии строк (первый вызов из TGrid.do_init)

        Всё остальное — ошибка дизайна: использовать TGrid.
        """
        rows = getattr(self, "Rows", [])
        # TGrid.do_init() первый раз вызывает tr() без индекса — создаём единственную строку
        if index is None and not rows:
            return super().tr(None)  # type: ignore[return-value]
        # любые другие сценарии считаем нарушением контракта панели
        self.fail(
            "tr",
            "TPanel is single-row layout. Use TGrid for multiple rows."
        )
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCardPanel — панель внутри карточки (header / footer / status)
# ----------------------------------------------------------------------------------------------------------------------
class TCardPanel(TFlex_Tr, TIconMixin, TCaptionMixin):
    prefix = "cpnl"
    MARK_FAMILY = "card"
    MARK_LEVEL = 1
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        """
        Панель карточки. Живёт ТОЛЬКО внутри TCard и заменяет старый TPanel.
        Структура:
          left_td  — слева
          mid_td   — середина (растягивается)
          right_td — справа
        """
        # базовая flex-строка: создаёт Tds и первую td(0)
        super().do_init()
        # --- Роль панели ---
        self.type: str = "ptNone"
        # --- Колонки панели ---
        # первая td, созданная TFlex_Tr.do_init(), становится left_td
        self.left_td = self.Tds[0]
        # добавляем ещё две колонки: mid и right
        self.mid_td = self.td()
        self.right_td = self.td()
        # левая колонка — контент слева (иконка + заголовок)
        self.left_td.add_class("d-flex", "align-items-start", "gap-2", "flex-wrap")
        # средняя колонка — растягиваемая зона
        self.mid_td.add_class("d-flex", "align-items-center", "flex-grow-1", "gap-2", "flex-wrap")
        # правая колонка — actions справа
        self.right_td.add_class("d-flex", "align-items-center", "gap-2", "flex-wrap", "ms-auto")
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
class TCardBody(TGrid):
    prefix = "card_body"
    MARK_FAMILY = "card"
    MARK_LEVEL = 1

    def do_init(self):
        """
        Тело карточки.
        Ведёт себя как grid:
        - flex-column контейнер с Rows/Tds
        - добавляет класс 'card-body'
        """
        TGrid.do_init(self)
        self.add_class("card-body")

    def get_active_control(self) -> "TCustomControl":
        """ Активная ячейка тела карточки. """
        return self.Rows[-1].Tds[-1]

    def _placeholder_label(self, r: int, c: int, rows_count: int) -> str:
        """
        Для тела карточки плейсхолдер должен ссылаться на карточку:
        Card3.td(0) / Card3.tr(r).td(c)
        """
        owner = getattr(self, "Owner", None)
        base_name = getattr(owner, "Name", None) or getattr(self, "Name", "") or self.__class__.__name__
        if rows_count == 1:
            return f"{base_name}.td({c})"
        return f"{base_name}.tr({r}).td({c})"
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCard — карточка с header / body / footer (базовый каркас Tradition Core)
# ----------------------------------------------------------------------------------------------------------------------
class TCard(TIconMixin, TCompositeControl):
    prefix = "card"
    MARK_FAMILY = "card"
    MARK_LEVEL = 0
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        self.add_class("shadow-sm")
        # --- Структурные дети карточки ---
        self.header_enabled: bool = True
        self.footer_enabled: bool = False
        # header
        self.header = TCardPanel(self, "Header")
        self.header.type = "ptHeader"
        self.header.add_class("card-header")  # Tabler-совместимый класс
        # body
        self.body = TCardBody(self, "Body")  # внутри уже card-body и отключённый panel-placeholder
        # footer
        self.footer = TCardPanel(self, "Footer")
        self.footer.add_class("card-footer")
        self.footer.add_class("text-muted")
        self.footer.add_class("small")
        # --- Дефолтные логические значения ---
        # ⚠ пока сохраняем body_text_default как есть, уберём отдельным шагом
        self.icon = "🔷"
        # служебный флаг: "заголовок ещё не задавали"
        self.f_title = "<none>"
        self.sub_title = ""
        # 🔹 текст плейсхолдера для body
        #self.place_holder = f"body:{self.Name}"

    def get_active_control(self) -> "TCustomControl":
        """
        Любой визуальный ребёнок карточки по умолчанию идёт в её body.
        Дальше body (как панель/строка) сам решает, в какую td его положить.
        """
        body = getattr(self, "body", None)
        if isinstance(body, TCompositeControl):
            return body.active_control
        # запасной вариант — базовое поведение
        return super().get_active_control()
    # ..........................................................
    # 🔹 Фасад: title → нeader.caption
    # ..........................................................
    @property
    def title(self) -> str:
        """
        Логика:
        - f_title == "<none>"  → title:{Name}
        - f_title == ""        → пустая строка (осознанный выбор)
        - любое другое значение → возвращаем как есть
        """
        raw = getattr(self, "f_title", "<none>")
        if raw == "<none>":
            return f"{self.Name}.title"
        return raw or ""

    @title.setter
    def title(self, value: str | None):
        if value is None:
            # сброс к режиму "дефолт: title:Name"
            raw = "<none>"
        else:
            raw = str(value)

        self.f_title = raw

        header = getattr(self, "header", None)
        if header is not None and hasattr(header, "caption"):
            if raw == "<none>":
                header.caption = f"title:{self.Name}"
            else:
                header.caption = raw
    # ..........................................................
    # 🔹 Фасад: icon → header.icon
    # ..........................................................
    @property
    def icon(self) -> str | None:
        header = getattr(self, "header", None)
        return getattr(header, "icon", None) if header is not None else None

    @icon.setter
    def icon(self, value: str | None):
        header = getattr(self, "header", None)
        if header is not None and hasattr(header, "icon"):
            header.icon = value
    # ..................................................................................................................
    # 🎨 Рендер
    # ..................................................................................................................
    def render(self):
        # HEADER
        if self.header and self.header_enabled:
            self.header._render()
            self.Canvas.extend(self.header.Canvas)
        # BODY
        self.body._render()
        self.Canvas.extend(self.body.Canvas)
        # FOOTER
        if self.footer and self.footer_enabled:
            self.footer._render()
            self.Canvas.extend(self.footer.Canvas)
    # ..................................................................................................................
    # 🔹 Фасад: доступ к ячейкам тела карточки
    # ..................................................................................................................
    def td(self, index: int | None = None):
        return self.body.td(index)
    # ..................................................................................................................
    # 🛡️ PHASE 2: политика владения. Перехват регистрации детей: всё не header/body/footer → в body
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
    # ---
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
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        self.items: list["TMenuItem"] = []
        self.orientation: str = "horizontal"  # "horizontal" | "vertical"
        self.variant: str = "pills"           # "pills" | "tabs" | "plain"
        self.auto_active: bool = True
        # контейнер можно стилизовать снаружи
        self.flex_box(direction="row", gap="0.5rem", width="100%")
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
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
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
    def do_init(self):
        # WS-подписка по умолчанию
        self.channel = "log"
        self.type = "log_line"

        # режим работы монитора (для фронта)
        self.mode: str = "append"   # "append" | "replace" (сейчас используем append)
        self.max_lines: int = 20   # лимит строк в <pre>, фронт сам обрежет

        # базовые классы оформления (без навязывания цветов)
        self.add_class("tc-monitor")
        self.add_class("p-2")
        self.add_class("font-monospace")
        # 🔹 НОВОЕ: дополнительные css-классы темы
        # только имена классов, без inline-стилей
        self.screen_class: str = ""  # фон / рамка “экрана”
        self.font_class: str = ""  # цвет / стиль текста

    def render(self):
        # базовые классы <pre>
        cls = ["tc-monitor-body"]          # 🔹 ключевой класс для JS
        cls.extend(self.classes)           # tc-monitor, p-2, font-monospace и т.п.

        # темы
        if getattr(self, "screen_class", ""):
            cls.append(self.screen_class)
        if getattr(self, "font_class", ""):
            cls.append(self.font_class)

        # атрибуты для ws-скрипта
        attrs = [
            f"data-tws-channel='{self.channel}'",
            f"data-tws-type='{self.type}'",
            f"data-tws-mode='{self.mode}'",
            f"data-tws-max='{self.max_lines}'",
        ]

        # если хочешь — можно добавить ещё get_tws_attrs() из TwsSubscriberMixin
        # attrs.append(self.get_tws_attrs())

        self.tg(
            "pre",
            cls=" ".join(cls),
            attr=" ".join(attrs),
        )
        # контент оставляем пустым — его заполнит JS
        self.etg("pre")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TCardMonitor
# ----------------------------------------------------------------------------------------------------------------------
class TCardMonitor(TCard):
    prefix = "card_mon"
    MARK_FAMILY = "card"
    MARK_LEVEL = 0
    """
    Карточка-монитор:
      • header: иконка, title, sub_title, статус-бейдж, кнопка "Send event"
      • body: TMonitor (ws: channel/type)
    """
    def do_init(self):
        super().do_init()
        self.f_channel: str = ""
        self.f_type: str = ""
        self.f_mode: str = ""
        self.f_max_lines: int = 0
        self.f_screen_class: str = ""
        self.f_font_class: str = ""
        # --- шапка карточки ---
        self.header.type = "ptHeader"          # чтобы _auto_header_compose отработал
        self.icon = "📡"                       # прокидывается в Header.icon
        self.sub_title = f"{self.channel}:{self.type}"

        # небольшая метка для css
        self.add_class("tc-card-monitor")

        # --- тело: сам текстовый монитор ---
        td = self.body.active_control                   # первая колонка body
        self.monitor = TMonitor(td, "Monitor")
        # 🔹 дефолтные классы темы монитора
        self.channel = "log"
        self.type = "log_line"
        self.mode = "append"
        self.max_lines = 20
        self.screen_class = "tc-monitor-screen-dark"
        self.font_class = "tc-monitor-font-default"
        # чтобы body не подсовывал default-текст
        # (если у тебя в TCard уже есть _body_has_content, этого может быть достаточно)
        # здесь мы явно гарантируем, что в Flow что-то есть — сам monitor

        # --- header.right_td: статус + кнопка ---
        from bb_ctrl_atom import TBadge, TButton

        # статус-бейдж (пока статично ONLINE)
        self.status_badge = TBadge(self.header.right_td, "StatusBadge")
        self.status_badge.caption = "ONLINE"
        self.status_badge.kind = "green"      # bg-green / text-green-fg
        self.status_badge.style = "lt sm"     # лёгкий вариант + маленький
        self.status_badge.add_class("tc-monitor-status")
        self.status_badge.add_attr("data-tws-status")
        # кнопка "Send event"
        self.send_button = TButton(self.header.right_td, "SendEvent")
        self.send_button.caption = "Send event"
        self.send_button.kind = "primary"
        self.send_button.style = "sm"
        self.send_button.href = "#"           # клики будет перехватывать JS
        self.send_button.add_class("ms-2")    # небольшой отступ слева

        # payload для WebSocket: положим в data-tws-send
        # (см. патч TButton ниже)
        self.send_button.extra_attr = "data-tws-send='{\"cmd\":\"ping\"}'"
    # 🔹 channel
    @property
    def channel(self) -> str:
        return self.f_channel

    @channel.setter
    def channel(self, value: str):
        self.f_channel = str(value or "")
        # обновляем подзаголовок
        self.sub_title = f"{self.f_channel}/{self.f_type}"
        if getattr(self, "monitor", None):
            self.monitor.channel = self.f_channel

    # 🔹 type
    @property
    def type(self) -> str:
        return self.f_type

    @type.setter
    def type(self, value: str):
        self.f_type = str(value or "")
        self.sub_title = f"{self.f_channel}/{self.f_type}"
        if getattr(self, "monitor", None):
            self.monitor.type = self.f_type
    # 🔹 mode
    @property
    def mode(self) -> str:
        return self.f_mode

    @mode.setter
    def mode(self, value: str):
        self.f_mode = str(value or "")
        if getattr(self, "monitor", None):
            self.monitor.mode = self.f_mode

    # 🔹 max_lines
    @property
    def max_lines(self) -> int:
        return self.f_max_lines

    @max_lines.setter
    def max_lines(self, value: int):
        try:
            self.f_max_lines = int(value)
        except Exception:
            self.f_max_lines = 0
        if getattr(self, "monitor", None):
            self.monitor.max_lines = self.f_max_lines
    # 🔹 Внешнее API: цвет/стиль экрана и шрифта
    @property
    def screen_class(self) -> str:
        """CSS-класс, задающий фон/рамку экрана монитора."""
        return self.f_screen_class

    @screen_class.setter
    def screen_class(self, value: str):
        self.f_screen_class = str(value or "")
        if getattr(self, "monitor", None):
            self.monitor.screen_class = self.f_screen_class

    @property
    def font_class(self) -> str:
        """CSS-класс, задающий цвет/стиль текста в мониторе."""
        return self.f_font_class

    @font_class.setter
    def font_class(self, value: str):
        self.f_font_class = str(value or "")
        if getattr(self, "monitor", None):
            self.monitor.font_class = self.f_font_class
# ======================================================================================================================
# 📁🌄 bb_ctrl_base.py 🜂 The End — See You Next Session 2025 💹 188 -> 1755 -> 2088 -> 775 -> 979 -> 851 -> 1002
# ======================================================================================================================









