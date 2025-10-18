import asyncio
import json
from datetime import datetime
from pathlib import Path
import websockets  # Добавьте этот импорт
from bb_sys import *
from bb_page import *


class TappSysControl(TApplication):
    def __init__(self, service_name="bbscan.service"):
        super().__init__()
        self.service_name = service_name
        self.ws = None

        # --- Автогенерация HTML при инициализации ---
        self.ensure_page_auto()

    # -------------------------------------------------------------
    # Реализация интерфейсов из TApplication
    # -------------------------------------------------------------
    def generate_name(self) -> str:
        """Имя HTML-файла для этой подсистемы."""
        return "bb_app_sys_control.html"

    def generate_page(self) -> str:
        p = TxPage()
        p.style = self.base_style()
        p.h(1, f"System Control — {self.project_tag}")
        TxMonitor(port=8081).render(p)
        return p.html()

    # -------------------------------------------------------------
    # WebSocket subsystem
    # -------------------------------------------------------------
    async def _attach_ws(self, host, port):
        from _bb_ws import TWebSocketServer
        self.ws = TWebSocketServer(None, host, port)
        self.ws.open()
        self.log("_attach_ws", f"✅ WebSocket server started at ws://{host}:{port}")

    async def _stream_logs(self):
        """Поток логов из systemd-журнала."""
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-fu", self.service_name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in proc.stdout:
            line = raw.decode(errors="ignore").rstrip()
            if self.ws:
                await self.ws.broadcast({"type": "log", "text": line})

    async def _heartbeat(self, interval=60):
        """Поддержание активности сервера."""
        while True:
            await asyncio.sleep(interval)
            if self.ws:
                await self.ws.broadcast({"type": "ping", "time": datetime.now().isoformat()})

    async def start(self):
        """Запуск приложения и всех подсистем."""
        await self._attach_ws("0.0.0.0", 8081)
        asyncio.create_task(self._stream_logs())
        asyncio.create_task(self._heartbeat())

        self.log("start", "🛰️ System Control started and running")
        while True:
            await asyncio.sleep(1)



if __name__ == "__main__":
    print("🚀 RUN: main starting")

    async def main():
        app = TappSysControl(service_name="bbscan.service")
        await app.start()

    asyncio.run(main())
