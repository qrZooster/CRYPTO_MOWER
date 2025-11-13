# ======================================================================================================================
# 📁 file        : bb_ctrl_pages.py — Страницы и лейауты (TPage, TLayout) — заготовка
# 🕒 created     : 02.11.2025 15:29
# 🎉 contains    : TPage, TLayout (перенесёшь сюда)
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
from typing import Optional, Dict, Any
from bb_sys import *
from bb_ctrl_custom import TCompositeControl
from _sys import *
# 💎🧩⚙️ ... __ALL__ ...
__all__ = ["TLayout", "TPage"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TLayout — шаблон страницы
# ----------------------------------------------------------------------------------------------------------------------
class TLayout(TCompositeControl):
    prefix = "layout"
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        self.slot_marker = "{{ content }}"
        self.header = TCompositeControl(self)  # контейнер для контролов хедера
        self.footer = TCompositeControl(self)  # контейнер для контролов футера
        self.active_control = self.header
        # 💡 Авто-регистрация в приложении
        app = self.app()
        if app:
            app.Layouts[self.Name] = self
            # ... 🔊...
            app.log("register_global", f"📐 Layout registered: {self.Name}")
        # ⚡🛠️ TLayout ▸ End of do_init()
    def structural_children(self) -> tuple["TCompositeControl", ...]:
        # header/footer — служебные, всё остальное — "контент"
        return tuple(
            c for c in (
                getattr(self, "header", None),
                getattr(self, "footer", None),
            ) if c is not None
        )

    def render(self):
        self.active_control = self.header
        self.header.div("page")  # <div class="page">
        # === HEADER / NAVBAR ===
        self.header.tg("header", cls="navbar navbar-expand-lg navbar-light bg-light shadow-sm border-bottom")
        self.header.div("container-fluid")
        self.render_header()  # → шапка (наследники)
        self.header.ediv()  # container-fluid
        self.header.etg("header")  # </header>
        self.header._render()
        self.Canvas.extend(self.header.Canvas)
        # ---
        self.page_body()  # → стандартный каркас + slot_marker
        # ---
        # === FOOTER ===
        self.active_control = self.footer
        self.footer.tg("footer", "mt-auto py-3 bg-light border-top")
        self.render_footer()  # → подвал (наследники)
        self.footer.etg("footer")
        # ---
        self.footer.ediv()  # </div> page
        self.footer._render()
        self.Canvas.extend(self.footer.Canvas)
    # 🧱 дефолтная реализация "тела" — наш стандартный wrapper
    def page_body(self):
        """
        Стандартный каркас основного тела страницы (Tabler-style):
        page-wrapper / page-body / container-xl my-4 + слот страницы внутри.
        """
        self.div("page-wrapper")
        self.div("page-body")
        self.div("container-xl my-4")
        # сюда потом Application.render_body подставит page.Canvas
        self.text(self.slot_marker)
        self.ediv()  # container
        self.ediv()  # page-body
        self.ediv()  # page-wrapper
    # 🧷 хуки для наследников
    def render_header(self):
        """Переопределяется в наследниках. По умолчанию — ничего."""
        pass

    def render_footer(self):
        """Переопределяется в наследниках. По умолчанию — ничего."""
        pass

    def clear(self):
        """Полностью очищает содержимое страницы перед перерисовкой. Уничтожает дочерние контролы и Canvas."""
        self.header.clear()
        self.footer.clear()
        super().clear()
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TPage — корневая страница (HTML-уровень)
# ----------------------------------------------------------------------------------------------------------------------
class TPage(TCompositeControl):
    prefix = "pg"
    # 💎 NAME_SCOPE_ROOT - корень пронстранства имен для контролов
    NAME_SCOPE_ROOT = True
    # ⚡🛠️ ▸ do_init()
    def do_init(self):
        self.title = self.Name
        self.layout = "default"
        app = self.app()
        if app:
            app.Pages[self.Name] = self
            app.log("register_global", f"📐 Page registered: {self.Name}")
    # корневой тег страницы — div
    def root_tag(self) -> str:
        return "div"
# ======================================================================================================================
# 📁🌄 bb_ctrl_pages.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 56 -> 114
# ======================================================================================================================
