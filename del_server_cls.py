#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tradition Framework: System Control Server
------------------------------------------
TSysControl — основной управляющий компонент (приложение).
TWebSocketHub — универсальный WebSocket-компонент для взаимодействия с UI и другими модулями.
Оба наследуются от TLiveComponent из bb_sys.
"""

import asyncio
import json
import logging
from _bb_ws import TWebSocketServer
import subprocess
import websockets
# ==============================================================
# SYSTEM CONTROL CORE
# ==============================================================
class TSysControl:
    """
    Центральный управляющий компонент приложения.
    Управляет системным сервисом и стримом логов.
    """

    def __init__(self, service_name="bbscan.service"):
        self.service_name = service_name
        self.ws = None
        logging.info(f"[SysControl] initialized for service: {service_name}")

    async def start(self):
        """Запускает стрим логов и ждёт завершения."""
        asyncio.create_task(self._stream_logs())
        logging.info("[SysControl] log stream started")
        await asyncio.Future()  # главный цикл — ждём вечно

    async def attach_ws(self, host="0.0.0.0", port=8081):
        """Создаёт и запускает WebSocket-сервер."""
        self.ws = TWebSocketServer(None, host=host, port=port)
        self.ws.on_message = self._on_ws_message
        self.ws.open()
        logging.info(f"[SysControl] WS attached on {host}:{port}")

    async def _on_ws_message(self, ws, msg):
        """Обработка команд от клиента."""
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "error", "msg": "invalid JSON"}))
            return

        cmd = data.get("cmd")
        if cmd == "restart":
            await self._restart_service(ws)
        elif cmd == "ping":
            await ws.send(json.dumps({"type": "pong"}))
        else:
            await ws.send(json.dumps({"type": "unknown", "cmd": cmd}))

    async def _restart_service(self, ws):
        """Перезапускает системный сервис."""
        logging.info(f"[SysControl] Restarting {self.service_name}")
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "restart", self.service_name
        )
        await proc.wait()
        await ws.send(json.dumps({"type": "info", "msg": "service restarted"}))

    async def _stream_logs(self):
        """Транслирует journalctl в WebSocket."""
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-fu", self.service_name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        async for raw in proc.stdout:
            line = raw.decode(errors="ignore").rstrip()
            if self.ws:
                await self.ws.broadcast({"type": "log", "text": line})

# ==============================================================
# ENTRY POINT
# ==============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    loop = asyncio.get_event_loop()
    app = TSysControl(service_name="bbscan.service", host="0.0.0.0", port=8081)
    app.open()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
