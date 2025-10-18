# ============================================================
# bb_controls.py — визуальная ветвь Tradition Core 2025
# created: 17.10.2025 12:31
# Определяет TCustomControl, TControl, TForm, TPage
# ============================================================
from __future__ import annotations
from typing import Optional, Dict
from bb_sys import *
# ---------------------------------------------------------------------
# TCustomControl — базовый визуальный компонент
# ---------------------------------------------------------------------
class TCustomControl(TComponent):
    def __init__(self, Owner=None, Name=None, Parent=None):
        super().__init__(Owner, Name)
        self.Parent = Parent
        self.Controls: dict[str, "TCustomControl"] = {}
        self.src: list[str | "TCustomControl"] = []
        if Parent:
            Parent.add_control(self)
        self.log("__init__", f"visual control {self.Name} created")

    def add_control(self, ctrl: "TCustomControl"):
        if ctrl.Name in self.Controls:
            self.fail("add_control", f"duplicate control {ctrl.Name}", ValueError)
        self.Controls[ctrl.Name] = ctrl
        ctrl.Parent = self
        self.src.append(ctrl)

    def control(self, ctrl: "TCustomControl"):
        if ctrl.Name in self.Controls:
            self.fail("control", f"duplicate control {ctrl.Name}", ValueError)
        self.Controls[ctrl.Name] = ctrl
        ctrl.Parent = self
        self.src.append(ctrl)
        return ctrl

    def text(self, html: str):
        self.src.append(str(html))

    def tg(self, tag: str, cls: str | None = None, attr: str | None = None):
        cls_part = f" class='{cls}'" if cls else ""
        attr_part = f" {attr}" if attr else ""
        self.text(f"<{tag}{cls_part}{attr_part}>")

    def etg(self, tag: str):
        self.text(f"</{tag}>")

    def br(self, count: int = 1):
        try:
            n = max(0, int(count))
        except Exception:
            n = 1
        if n > 0:
            self.src.append("<br/>" * n + "\n")

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
    def div(self, cls=None, attr=None):self.tg("div", cls, attr)
    def ediv(self):self.etg("div")
    def table(self, cls=None, attr=None):self.tg("table", cls, attr)
    def etable(self):self.etg("table")
    def tr(self, cls=None, attr=None):self.tg("tr", cls, attr)
    def etr(self):self.etg("tr")
    def td(self, cls=None, attr=None):self.tg("td", cls, attr)
    def etd(self):self.etg("td")

    def _tg(self, tg: str, src: str):
        """Оборачивает текст src в тег tg."""
        self.tg(tg)
        self.text(src)
        self.etg(tg)

    def html(self) -> str:
        out = []
        for item in self.src:
            if isinstance(item, TCustomControl):
                out.append(item.html())
            else:
                out.append(str(item))
        return "".join(out)
# ---------------------------------------------------------------------
# TControl — обычный элемент интерфейса (div, span, button и т.д.)
# ---------------------------------------------------------------------
class TControl(TCustomControl):
    def __init__(self, Owner=None, Name=None, Parent=None, tag="div", text=""):
        super().__init__(Owner, Name, Parent)
        self.log("__init__", f"control {self.Name}  created")
# ---------------------------------------------------------------------
# TPage — корневая страница (HTML-уровень)
# ---------------------------------------------------------------------
class TPage(TCustomControl):
    def __init__(self, Owner, Name="page", title="New Page"):
        super().__init__(Owner, Name)
        self.title = title
        self.Parent = None
        self.style = ""
        self.log("__init__", f"page {self.Name} created")

    def html(self):
        """Возвращает полный HTML-документ Tradition Core."""
        body = super().html()
        self.src = []
        self.text("<!DOCTYPE html>\n")
        self.tg("html", None, 'lang="en"')
        self.tg("head")
        self.text('<meta charset="UTF-8">\n')
        self._tg("title", self.title)
        self._tg("style", self.style)
        self.etg("head")
        self._tg("body", body)
        self.etg("html")
        return "".join(self.src)
# ---------------------------------------------------------------------
# TWSControl — приёмник WebSocket-потока (уровень связи)
# ---------------------------------------------------------------------
class TWSControl(TControl):
    def __init__(self, Owner=None, Name="wsControl", Parent=None, url="ws://localhost:8081", channel="SYS"):
        super().__init__(Owner, Name, Parent)
        self.url = url
        self.channel = channel  # ← радио-частота (канал)
        self.log("__init__", f"receiver {self.Name} tuned to channel '{self.channel}'")

    def html(self):
        eid = self.id()
        return f"""
<script>
const proto = (location.protocol === 'https:') ? 'wss' : 'ws';
const ws = new WebSocket('{self.url}');
const eid = '{eid}';
const channel = '{self.channel}';

ws.onopen = () => {{
  ws.send(JSON.stringify({{ type: "subscribe", channel }}));
  console.log(`📡 Subscribed to ${{channel}}`);
}};

ws.onmessage = (e) => {{
  try {{
    const msg = JSON.parse(e.data);
    if (msg.channel && msg.channel !== channel) return; // фильтр по каналу
    const el = document.getElementById(eid);
    if (el) {{
      el.textContent += (msg.text || e.data) + "\\n";
      el.scrollTop = el.scrollHeight;
    }}
  }} catch(err) {{
    console.error('[WS parse error]', err);
  }}
}};
</script>
"""
# ---------------------------------------------------------------------
# TMonitor — визуальный кинескоп Tradition Core
# ---------------------------------------------------------------------
class TMonitor(TWSControl):
    def __init__(self, Owner=None, Name="Monitor", Parent=None, port=8081, channel="SYS"):
        url = f"ws://localhost:{port}"
        super().__init__(Owner, Name, Parent, url=url, channel=channel)
        self.log("__init__", f"monitor {self.Name} created for {self.channel}")

    def html(self):
        eid = self.id()
        return f"""
<div id="{eid}" style="font-family:monospace;color:#00ff88;
background:#1a1d29;padding:10px;border-radius:8px;
height:70vh;overflow-y:auto;">Connecting to {self.channel}...</div>
{super().html()}
"""
# =====================================================================
# bb_controls.py 🜂 The End — See You Next Session 2025 ⚙️
# =====================================================================









