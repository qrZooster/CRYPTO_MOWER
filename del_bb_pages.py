# ======================================================================================================================
# 📁 file        : bb_pages.py — Страницы и лейауты (TPage, TLayout) — заготовка
# 🕒 created     : 02.11.2025 15:29
# 🎉 contains    : TPage, TLayout (перенесёшь сюда)
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
from __future__ import annotations
from typing import Optional, Dict, Any
from bb_sys import *
from bb_ctrl_custom import TCustomControl
# 💎🧩⚙️ ... __ALL__ ...
__all__ = ["TLayout", "TPage"]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TLayout — шаблон страницы
# ----------------------------------------------------------------------------------------------------------------------
class TLayout(TCustomControl):
    prefix = "ly"
    def __init__(self, Owner, Name="default"):
        super().__init__(Owner, Name)
        self.slot_marker = "{{ content }}"
        self.add_class("layout")  # ← корневой div layout’а
        # ... 🔊...
        self.log("__init__", f"layout {self.Name} created")
        # 💡 Авто-регистрация в приложении
        app = self.app()
        if app:
            app.Layouts[self.Name] = self
            # ... 🔊...
            app.log("register_global", f"📐 Layout registered: {self.Name}")
        # 🛠️⚡ TLayout ▸ End of __init__

    def render(self):
        # только слот — любой наследник может строить свою структуру
        self.text(self.slot_marker)
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TPage — корневая страница (HTML-уровень)
# ----------------------------------------------------------------------------------------------------------------------
class TPage(TCustomControl):
    prefix = "pg"

    def __init__(self, Owner=None, Name: str | None = None):
        super().__init__(Owner, Name)
        self.title = self.Name
        self.layout = "default"
        app = self.app()
        if app:
            app.Pages[self.Name] = self
            app.log("register_global", f"📐 Page registered: {self.Name}")
        self.log("__init__", f"⚙️ page {self.Name} created uid={self.uid}")

    # корневой тег страницы — div
    def root_tag(self) -> str:
        return "div"
# ======================================================================================================================
# 📁🌄 bb_pages.py 🜂 The End — See You Next Session 2025 💹 Tradition Core 2025.10 56 ->
# ======================================================================================================================
