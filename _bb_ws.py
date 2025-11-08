import asyncio
import json
import logging
import websockets

from bb_sys import *

# ==============================================================
#  TWebSocketServer
# ==============================================================

class TWebSocketServer(TLiveComponent):
    """
    Асинхронный WebSocket-сервер.
    Принимает клиентов, рассылает им сообщения и принимает команды.
    """

    def __init__(self, owner, host="0.0.0.0", port=8081):
        super().__init__(owner, "WebSocketServer")
        self.host = host
        self.port = port
        self.clients: set = set()
        self._server = None
        self._task_heartbeat = None
        self.log("__init__", f"initialized on ws://{host}:{port}")

    # ----------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------
    def do_open(self) -> bool:
        asyncio.create_task(self._amain())
        self.log("do_open", f"server task started ({self.host}:{self.port})")
        return True

    def do_close(self) -> bool:
        self.log("do_close", "closing...")
        for ws in list(self.clients):
            asyncio.create_task(ws.close(code=1001, reason="server shutdown"))
        return True

    # ----------------------------------------------------------
    # Main loop
    # ----------------------------------------------------------
    async def _amain(self):
        self._server = await websockets.serve(self._handler, self.host, self.port)
        self.log("_amain", f"listening on ws://{self.host}:{self.port}")

        self._task_heartbeat = asyncio.create_task(self._heartbeat())

        await self._server.wait_closed()
        self.log("_amain", "server stopped")

    async def _handler(self, ws):
        self.clients.add(ws)
        addr = getattr(ws, "remote_address", None)
        self.log("_handler", f"client connected: {addr}")
        try:
            await ws.send(json.dumps({"type": "hello", "msg": "welcome"}))
            async for msg in ws:
                await self._on_message(ws, msg)
        except Exception as e:
            self.log("_handler", f"⚠️ {e}")
        finally:
            self.clients.discard(ws)
            self.log("_handler", f"client disconnected: {addr}")

    # ----------------------------------------------------------
    # Event handling
    # ----------------------------------------------------------
    async def _on_message(self, ws, msg: str):
        """Обработка входящих сообщений."""
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "echo", "msg": msg}))
            return

        cmd = data.get("cmd")
        if cmd == "ping":
            await ws.send(json.dumps({"type": "pong"}))
        elif cmd == "broadcast":
            text = data.get("text", "")
            await self.broadcast({"type": "broadcast", "text": text})
        else:
            await ws.send(json.dumps({"type": "unknown", "data": data}))

    async def broadcast(self, payload: dict):
        """Рассылает JSON всем активным клиентам."""
        if not self.clients:
            return
        msg = json.dumps(payload)
        await asyncio.gather(*(ws.send(msg) for ws in list(self.clients)), return_exceptions=True)

    async def _heartbeat(self):
        """Регулярно пингует всех клиентов, чтобы держать соединение."""
        while True:
            dead = []
            for ws in list(self.clients):
                try:
                    pong_waiter = await ws.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)
            await asyncio.sleep(10)

# ==============================================================
#  TWebSocketClient
# ==============================================================

class TWebSocketClient(TLiveComponent):
    """
    Универсальный WebSocket-клиент.
    Подключается к внешнему серверу, слушает сообщения, пересылает данные.
    """

    def __init__(self, owner, url, on_message=None, reconnect_delay=5):
        super().__init__(owner, "WebSocketClient")
        self.url = url
        self.on_message = on_message
        self.reconnect_delay = reconnect_delay
        self._stop = False
        self.log("__init__", f"ready for {url}")

    def do_open(self) -> bool:
        asyncio.create_task(self._amain())
        self.log("do_open", f"connecting to {self.url}")
        return True

    def do_close(self) -> bool:
        self._stop = True
        self.log("do_close", "stop requested")
        return True

    async def _amain(self):
        while not self._stop:
            try:
                async with websockets.connect(self.url, ping_interval=20) as ws:
                    self.log("_amain", f"connected to {self.url}")
                    async for msg in ws:
                        if self.on_message:
                            self.on_message(msg)
            except Exception as e:
                self.log("_amain", f"⚠️ {e}")
                await asyncio.sleep(self.reconnect_delay)