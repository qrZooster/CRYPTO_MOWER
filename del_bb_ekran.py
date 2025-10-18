# ==============================================================
#   TEkran — встроенный web-интерфейс (HTTP :80 + WS :81)
# ==============================================================

import os
import threading
import asyncio
import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
import websockets
from bb_sys import TSysComponent
from urllib.parse import parse_qs

ECHO_FILE = "app_echo.html"


class TEkran(TSysComponent):
    """Минимальный HTTP + WebSocket интерфейс для логов и echo()."""

    def __init__(self, owner, port: int = 80):
        super().__init__(owner, "Ekran")
        self.port = port
        self.server = None
        self._stop = False
        self.log("init", f"created TEkran (HTTP:{port}, WS:{port+1})")

    # ----------------------------------------------------------
    def start(self):
        """Запускает HTTP и WebSocket серверы в отдельных потоках."""
        open(ECHO_FILE, "w", encoding="utf-8").close()

        # HTTP-сервер
        def run_http():
            try:
                self.server = HTTPServer(("0.0.0.0", self.port), self._make_handler())
                self.log("HTTP", f"listening on http://0.0.0.0:{self.port}")
                self.server.serve_forever()
            except Exception as e:
                self.log("HTTP", f"⚠️ failed to start: {e}")

        # WebSocket-сервер
        def run_ws():
            try:
                asyncio.run(self._run_ws())
            except Exception as e:
                self.log("WS", f"⚠️ failed to start: {e}")

        threading.Thread(target=run_http, daemon=True).start()
        threading.Thread(target=run_ws, daemon=True).start()
        self.log("start", f"🌐 TEkran ready (HTTP:{self.port}, WS:{self.port + 1})")

    # ----------------------------------------------------------
    async def _ws_http_fallback(self, path, request_headers):
        """
        Если пришёл НЕ websocket-запрос на порт WS — отдадим обычный HTTP
        и НЕ будем пытаться делать WS-handshake (чтобы не было InvalidUpgrade).
        """
        try:
            conn = (request_headers.get("Connection") or "").lower()
            upg = (request_headers.get("Upgrade") or "").lower()

            # Разрешаем WS-рукопожатие только когда это реально Upgrade на /ws/logs
            if path == "/ws/logs" and "upgrade" in conn and upg == "websocket":
                return None  # продолжить стандартный WS-handshake

            # Иначе просто вернём простой HTTP-ответ (200 ОК), чтобы замолчали пробы/сканеры
            body = b"ok\n"
            headers = [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Connection", "close"),
            ]
            return (200, headers, body)

        except Exception as e:
            err = f"internal error: {e}\n".encode()
            return (500, [("Content-Type", "text/plain"), ("Content-Length", str(len(err)))], err)
    # ----------------------------------------------------------
    async def _run_ws(self):
        """Чистый WebSocket-сервер на :81 (без HTTP)."""

        async def ws_router(ws):
            # В 15.x путь можно достать так (с запасом на разные версии):
            path = getattr(ws, "path", None)
            if path is None:
                req = getattr(ws, "request", None)
                path = getattr(req, "path", "/")

            if path == "/ws/logs":
                self.log("ws", "client connected to /ws/logs (live mode)")
                await self._ws_handler(ws)
                return

            self.log("ws", f"⚠️ rejected WS path: {path}")
            await ws.close(code=1008, reason="Invalid WS path")

        async with websockets.serve(
                ws_router,
                "0.0.0.0",
                self.port + 1,
                process_request=self._ws_http_fallback,   # ← добавили
        ):
            self.log("WS", f"listening on ws://0.0.0.0:{self.port + 1}/ws/logs")
            await asyncio.Future()  # вечное ожидание
    # ----------------------------------------------------------
    async def _maybe_http(self, path, request_headers):
        """
        Возвращает HTTP-ответ для не-WS запросов (совместимо с websockets >=11).
        """
        from websockets.http import Headers

        try:
            # Не обрабатываем WebSocket upgrade — пропускаем handshake
            if "upgrade" in request_headers.get("Connection", "").lower():
                return None

            if path in ("", "/", "/index.html"):
                content = render_index()
            elif path == "/logs":
                content = render_logs()
            elif path == "/echo":
                content = render_echo()
            elif path == "/config":
                content = render_config(self.owner)
            elif path == "/tables":
                content = render_tables(self.owner)
            else:
                content = "<h3>404 Not Found</h3>"

            body = content.encode("utf-8")
            headers = Headers([
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Connection", "close"),
            ])

            # Возвращаем тройку (status, headers, body) — НО в виде headers-класса, не tuple
            return 200, headers, body

        except Exception as e:
            err = f"Internal Server Error: {e}".encode()
            headers = Headers([
                ("Content-Type", "text/plain"),
                ("Content-Length", str(len(err))),
                ("Connection", "close"),
            ])
            return 500, headers, err
    # ----------------------------------------------------------
    # в TEkran._ws_handler()
    async def _ws_handler(self, ws):
        """
        На каждом новом подключении подшиваем логи за последние 2 минуты
        и продолжаем стримить в реальном времени.
        """
        # было: cmd = ["journalctl", "-u", "bbscan.service", "-n", "50", "-f"]
        cmd = ["journalctl", "-u", "bbscan.service", "--since", "-2min", "-f"]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.log("ws", "client connected to /ws/logs (catch-up 2min + live)")

        try:
            while not self._stop:
                line = proc.stdout.readline()
                if not line:
                    await asyncio.sleep(0.2)
                    continue
                await ws.send(json.dumps({"event": "log", "data": line.rstrip("\n")}))
        except (asyncio.CancelledError, websockets.ConnectionClosedOK, websockets.ConnectionClosedError):
            pass
        finally:
            if proc.poll() is None:
                proc.terminate()
            self.log("ws", "client disconnected from /ws/logs")

    # ----------------------------------------------------------
    def stop(self):
        """Останавливает оба сервера."""
        self._stop = True
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.log("stop", "TEkran stopped")

    # ----------------------------------------------------------
    def append_echo(self, html_line: str):
        """Добавляет строку в echo-файл (для /echo)."""
        if not html_line.endswith("<br>"):
            html_line += "<br>\n"
        with open(ECHO_FILE, "a", encoding="utf-8") as f:
            f.write(html_line)

    # ----------------------------------------------------------
    def _make_handler(self):
        owner = self.owner
        admin_token = owner.Config.key("ADMIN_TOKEN", "SuperSecret123")

        class Handler(BaseHTTPRequestHandler):
            # маленький хелпер на отправку ответа
            def _send(self, code: int, body: str, ct: str = "text/html; charset=utf-8"):
                b = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _forbidden(self, msg="Forbidden"):
                self._send(403, f"<h3>{msg}</h3><p><a href='/'>Back</a></p>")

            # ==== GET роуты (+ /admin) ====
            def do_GET(self):
                path = self.path.strip("/").lower()

                if path in ("", "index.html"):
                    content = render_index()
                elif path == "logs":
                    content = render_logs()
                elif path == "echo":
                    content = render_echo()
                elif path == "config":
                    content = render_config(owner)
                elif path == "tables":
                    content = render_tables(owner)
                elif path == "admin":
                    content = render_admin()
                else:
                    content = "<h3>404 Not Found</h3>"

                self._send(200, content)

            # ==== POST /admin/restart ====
            def do_POST(self):
                if self.path == "/admin/restart":
                    # читаем форму
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        length = 0
                    raw = self.rfile.read(length).decode("utf-8", "ignore")
                    form = parse_qs(raw)
                    token = (form.get("token") or [""])[0]

                    if token != admin_token:
                        return self._forbidden("Invalid token")

                    # перезапуск сервиса как отдельный transient-юнит через systemd-run
                    try:
                        import subprocess, os, shlex
                        unit_name = f"bbscan-restart-{os.getpid()}"
                        cmd = [
                            "/bin/systemd-run",
                            f"--unit={unit_name}",
                            "--on-active=1s",
                            "--collect",
                            "/bin/systemctl", "restart", "bbscan.service"
                        ]
                        r = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)

                        out = (r.stdout or "").strip()
                        err = (r.stderr or "").strip()
                        html = f"""
                        <html><head><meta charset='utf-8'><title>Restart scheduled</title></head>
                        <body style='font-family:monospace;background:#0d1117;color:#e6edf3;padding:10px'>
                          <h3>✅ Restart scheduled (in 1s)</h3>
                          <p>Transient unit: <b>{unit_name}</b></p>
                          <pre style='border:1px solid #30363d;padding:8px'>STDOUT:
    {out}

    STDERR:
    {err}</pre>
                          <p><a href='/logs'>⬅️ Back to Logs</a></p>
                        </body></html>
                        """
                        return self._send(200, html)
                    except subprocess.CalledProcessError as e:
                        out = (e.stdout or "").strip()
                        err = (e.stderr or "").strip()
                        html = f"""
                        <html><head><meta charset='utf-8'><title>Restart FAILED</title></head>
                        <body style='font-family:monospace;background:#0d1117;color:#e6edf3;padding:10px'>
                          <h3>❌ Restart failed (exit {e.returncode})</h3>
                          <pre style='border:1px solid #30363d;padding:8px'>STDOUT:
    {out}

    STDERR:
    {err}</pre>
                          <p><a href='/admin'>⬅️ Back</a></p>
                        </body></html>
                        """
                        return self._send(500, html)
                    except Exception as e:
                        html = f"""
                        <html><head><meta charset='utf-8'><title>Restart ERROR</title></head>
                        <body style='font-family:monospace;background:#0d1117;color:#e6edf3;padding:10px'>
                          <h3>❌ Error: {type(e).__name__}</h3>
                          <pre style='border:1px solid #30363d;padding:8px'>{e}</pre>
                          <p><a href='/admin'>⬅️ Back</a></p>
                        </body></html>
                        """
                        return self._send(500, html)

                # если другой POST — 404
                self._send(404, "<h3>Not Found</h3><p><a href='/'>Back</a></p>")

        return Handler

# ==============================================================
# 🧱 Рендер-функции страниц
# ==============================================================

def render_admin() -> str:
    return """
    <html><head>
      <meta charset='utf-8'>
      <title>🛠 Admin</title>
      <style>
        body{font-family:monospace;background:#0d1117;color:#e6edf3;padding:14px}
        input,button{font-family:inherit}
        .btn{background:#238636;color:white;border:0;padding:.5rem .8rem;border-radius:8px;cursor:pointer}
        .box{border:1px solid #30363d;border-radius:8px;padding:10px;margin:10px 0}
        a{color:#58a6ff;text-decoration:none}
      </style>
    </head><body>
      <h2>🛠 Admin</h2>
      <div class="box">
        <form method="POST" action="/admin/restart">
          <label>Token:&nbsp;<input type="password" name="token" placeholder="ADMIN_TOKEN" required></label>
          &nbsp;<button class="btn" type="submit">Restart bbscan.service</button>
        </form>
        <small>Рестарт уходит через <code>systemd-run</code> с задержкой 1s — страница не оборвётся.</small>
      </div>
      <p><a href='/'>⬅️ Back</a></p>
    </body></html>
    """

def render_index() -> str:
    return """
    <html><head><meta charset='utf-8'><title>BB Ekran</title></head>
    <body style='font-family:monospace;'>
    <h2>🐍 BB Ekran</h2>
    <p><a href='/admin'>🔧 Admin</a></p>
    <p><a href='/logs'>📜 Logs (live)</a></p>
    <p><a href='/config'>⚙️ Config</a></p>
    <p><a href='/tables'>🧩 Tables</a></p>
    <p><a href='/echo'>🖥 Echo</a></p>
    </body></html>
    """

def render_logs() -> str:
    return """
    <html><head>
    <meta charset='utf-8'>
    <title>📜 Logs — Live</title>
    <style>
        body{font-family:monospace;background:#0d1117;color:#e6edf3;padding:10px}
        h2{color:#58a6ff;margin-top:0}
        #logs{white-space:pre-wrap;line-height:1.3em;height:80vh;overflow-y:auto;
              border-top:1px solid #30363d;padding-top:8px}
        a{color:#58a6ff;text-decoration:none}
        .toolbar{display:flex;gap:12px;align-items:center;margin:6px 0 12px 0}
        .toolbar form{display:inline-flex;gap:8px;align-items:center;margin:0}
        .toolbar input{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:4px 6px}
        .toolbar button{background:#238636;border:0;color:white;padding:6px 10px;cursor:pointer}
        .toolbar button:hover{filter:brightness(1.05)}
    </style>
    </head><body>
    <h2>📜 Logs — live stream (ws://same-host:81/ws/logs)</h2>

    <div class="toolbar">
      <a href='/'>⬅️ Back</a>

      <!-- 🔧 КНОПКА РЕСТАРТА: вставь свой токен вручную при необходимости -->
      <form method="post" action="/admin/restart" onsubmit="return confirm('Перезапустить bbscan.service?');">
        <label>Token:
          <input name="token" type="password" placeholder="ADMIN_TOKEN">
        </label>
        <button type="submit">Restart bbscan.service</button>
      </form>
    </div>

    <div id="logs"></div>

    <script>
    const div = document.getElementById("logs");
    function connect(){
      const ws = new WebSocket("ws://" + location.hostname + ":81/ws/logs");
      ws.onopen   = () => { div.insertAdjacentText("beforeend","[connected]\\n"); div.scrollTop=div.scrollHeight; };
      ws.onmessage= (e) => { const m = JSON.parse(e.data); if(m.event==="log"){ div.insertAdjacentText("beforeend", m.data+"\\n"); div.scrollTop=div.scrollHeight; } };
      ws.onclose  = () => { div.insertAdjacentText("beforeend","[disconnected] reconnecting...\\n"); div.scrollTop=div.scrollHeight; setTimeout(connect, 2000); };
      ws.onerror  = () => { div.insertAdjacentText("beforeend","[error]\\n"); ws.close(); };
    }
    connect();
    </script>
    </body></html>
    """

def render_echo(refresh: int = 3) -> str:
    if not os.path.exists(ECHO_FILE):
        content = "<i>No echo output yet...</i>"
    else:
        with open(ECHO_FILE, "r", encoding="utf-8") as f:
            content = f.read()

    return f"""
    <html><head>
      <meta charset='utf-8'>      
      <title>🖥 Echo</title>
    </head>
    <body style='font-family:monospace;'>
      <h2>🖥 Echo (manual refresh)</h2>
      <hr>
      <div style='white-space:pre-wrap;'>{content}</div>
      <p><a href='/'>⬅️ Back</a></p>
    </body></html>
    """

def render_config(owner) -> str:
    env = getattr(owner.Config, "env", {})
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in env.items())
    return f"""
    <html><head><meta charset='utf-8'><title>⚙️ Config</title></head>
    <body style='font-family:monospace;'>
      <h2>⚙️ Config ENV</h2>
      <table border=1 cellspacing=0 cellpadding=4>
      <tr><th>Name</th><th>Value</th></tr>{rows}</table>
      <p><a href='/'>⬅️ Back</a></p>
    </body></html>
    """

def render_tables(owner) -> str:
    schema = getattr(owner, "Schema", None)
    tables = getattr(schema, "tables", [])
    text = "<br>".join(tables) or "— нет таблиц —"
    return f"""
    <html><head><meta charset='utf-8'><title>🧩 Tables</title></head>
    <body style='font-family:monospace;'>
      <h2>🧩 Tables</h2>
      <pre>{text}</pre>
      <p><a href='/'>⬅️ Back</a></p>
    </body></html>
    """
