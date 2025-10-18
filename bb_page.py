# bb_page.py

class TxPage:
    def __init__(self):
        self.src = ""  # холст
        self.style = ""

    def set_style(self, style: str = ""):
        """Устанавливает CSS-стиль страницы."""
        self.style = style

    # базовые кирпичи
    def tg(self, name, cls=None, attr=None):
        """Открывающий тег: tg('div', 'panel', 'id=\"main\"') -> <div class=\"panel\" id=\"main\">"""
        attrs = []
        if cls:
            attrs.append(f'class="{cls}"')
        if attr:
            # допускаем и строку, и dict
            if isinstance(attr, dict):
                attrs.extend(f'{k}="{v}"' for k, v in attr.items())
            else:
                attrs.append(str(attr))
        s = " ".join(attrs)
        self.src += f"<{name}{(' ' + s) if s else ''}>"

    def etg(self, name):
        """Закрывающий тег: etg('div') -> </div>"""
        self.src += f"</{name}>\n"

    def h(self, count=1, s=None, cls=None, attr=None):
        """Заголовок <h1..h6>: h(2, 'Title', 'class', 'id="x"')"""
        try:
            n = max(1, min(6, int(count)))
        except Exception:
            n = 1
        self.tg(f"h{n}", cls, attr)
        if s is not None:
            self.text(s)
        self.etg(f"h{n}")

    def text(self, s):
        self.src += str(s)

    def br(self, count=1):
        """Вставляет <br/> count раз (с переводом строки в конце)."""
        try:
            n = max(0, int(count))
        except Exception:
            n = 1
        if n:
            self.src += ("<br/>" * n) + "\n"

    # фасады (сахар)
    def div(self, cls=None, attr=None): self.tg("div", cls, attr)
    def ediv(self): self.etg("div")

    def table(self, cls=None, attr=None): self.tg("table", cls, attr)
    def etable(self): self.etg("table")

    def tr(self, cls=None, attr=None): self.tg("tr", cls, attr)
    def etr(self): self.etg("tr")

    def td(self, cls=None, attr=None): self.tg("td", cls, attr)
    def etd(self): self.etg("td")

    def _tg(self, tg: str, src: str):
        """Оборачивает текст src в тег tg."""
        self.tg(tg)
        self.text(src)
        self.etg(tg)

    def html(self):
        """Возвращает собранный HTML-код страницы, обёрнутый в базовый скелет."""
        src = self.html()  # собираем контент через базовый html()
        self.src = []  # начинаем новый холст
        self.text("<!DOCTYPE html>\n")
        self.tg("html", None, 'lang="en"')
        self.tg("head")
        self.text('<meta charset="UTF-8">\n')
        self._tg("title", self.Title)
        if getattr(self, "style", ""):
            self._tg("style", self.style)
        self.etg("head")
        self._tg("body", src)
        self.etg("html")
        return "".join(self.src)

    # bb_monitor.py

class TxMonitor:
    def __init__(self, port=8081, element_id="log"):
        self.port = int(port)
        self.element_id = element_id

    def render(self, p):
        # панель статуса + кнопка
        p.div(None, 'id="ws-panel" style="display:flex;align-items:center;gap:12px;'
                    'margin-bottom:10px;font-family:monospace;color:#00ff88;"')
        p.div(None, 'id="ws-status"'); p.text("🔴 offline"); p.ediv()
        p.tg("button", None, (
            'id="restart-btn" '
            'style="background:#1a1d29;color:#00ff88;border:1px solid #00ff88;'
            'border-radius:6px;padding:6px 12px;cursor:pointer;'
            'font-family:monospace;font-size:0.9em;"'
        ))
        p.text("⟳ Restart service")
        p.etg("button")
        p.ediv()

        # лог-панель
        p.div(None, f'id="{self.element_id}"')
        p.text("Connecting...")
        p.ediv()

        # JS
        p.tg("script"); p.text(f"""
const statusEl = document.getElementById('ws-status');
const logEl = document.getElementById('{self.element_id}');
const btn = document.getElementById('restart-btn');
const proto = (location.protocol === 'https:') ? 'wss' : 'ws';
const ws = new WebSocket(proto + '://' + location.hostname + ':{self.port}');

function setOnline(on) {{
  statusEl.textContent = on ? '🟢 online' : '🔴 offline';
}}

ws.onopen = () => {{
  setOnline(true);
  logEl.textContent = '✅ Connected to WS...\\n';
}};

ws.onmessage = (e) => {{
  try {{
    const msg = JSON.parse(e.data);
    if (msg.type === 'log') logEl.textContent += msg.text + '\\n';
    if (msg.type === 'ping') logEl.textContent += '💓 heartbeat ' + msg.time + '\\n';
  }} catch(err) {{
    logEl.textContent += '[parse error]\\n';
  }}
  logEl.scrollTop = logEl.scrollHeight;
}};

ws.onclose = () => setOnline(false);
ws.onerror = () => setOnline(false);

btn.onclick = () => {{
  fetch('/restart', {{ method: 'POST' }})
    .then(r => logEl.textContent += '\\n🔁 Restart command sent...\\n')
    .catch(e => logEl.textContent += '\\n⚠️ Restart failed: ' + e + '\\n');
}};
"""); p.etg("script")
# =====================================================================
# bb_page.py 🜂 The End — See You Next Session 2025 ⚙️
# =====================================================================






