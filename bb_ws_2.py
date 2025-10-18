# bb_ws.py
# ALIAS: BB_WS
# Created: 2025-09-19
# Универсальный модуль работы с Bybit WebSocket v5 для минутных свечей

import asyncio
import json
from typing import Callable, List, Dict

import requests
import websockets
import contextlib

from bb_vars import BYBIT_REST

# ------------------------
# ВСПОМОГАТЕЛЬНОЕ
# ------------------------

def _chunk(lst: List[str], size: int) -> List[List[str]]:
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def get_usdt_linear_symbols() -> List[str]:
    """Возвращает все линейные USDT-символы из Bybit REST v5.
    Обходит пагинацию (cursor).
    """
    url = f"{BYBIT_REST}/v5/market/instruments-info"
    params = {"category": "linear"}
    out: List[str] = []
    cursor = None
    while True:
        if cursor:
            params["cursor"] = cursor
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        j = r.json()
        result = j.get("result", {})
        items = result.get("list", [])
        for it in items:
            # фильтр по USDT-котировке и активным инструментам
            if it.get("quoteCoin") == "USDT":
                # можно дополнительно проверять статус: it.get("status") == "Trading"
                out.append(it.get("symbol"))
        cursor = result.get("nextPageCursor") or result.get("cursor")
        if not cursor:
            break
    return out


async def subscribe_symbols(ws, topics: List[str], batch: int = 50):
    """Подписывает WS на список topics порциями."""
    for grp in _chunk(topics, batch):
        payload = {"op": "subscribe", "args": grp}
        await ws.send(json.dumps(payload))
        await asyncio.sleep(0.05)


# ------------------------
# ОСНОВНОЙ ЦИКЛ WS
# ------------------------
async def ws_loop(ws_url: str, category: str, tf_str: str,
                  on_candle: Callable[[str, Dict, Dict[str, int]], asyncio.Future]):
    """
    Подключается к Bybit WS, подписывается на kline.<tf_str>.<symbol> для всех USDT линейных фьючерсов
    и передаёт закрытые свечи в колбэк on_candle(symbol, candle_dict, k_counter).
    """
    backoff = 1
    while True:
        try:
            symbols = get_usdt_linear_symbols()
            topics = [f"kline.{tf_str}.{s}" for s in symbols]
            k_counter: Dict[str, int] = {s: 0 for s in symbols}

            async with websockets.connect(ws_url, ping_interval=None) as ws:
                # подписка
                await subscribe_symbols(ws, topics, batch=50)
                print(f"✅ WS подключен. Подписано {len(topics)} топиков ({len(symbols)} символов)")

                # периодический ping, чтобы соединение не простаивало
                async def _pinger():
                    while True:
                        try:
                            await ws.ping()
                        except Exception:
                            return
                        await asyncio.sleep(15)

                pinger_task = asyncio.create_task(_pinger())

                try:
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue

                        # ignore service acks/ops
                        if not isinstance(msg, dict):
                            continue
                        topic = msg.get("topic")
                        data = msg.get("data")
                        if not topic or not data:
                            continue

                        # ожидаем формат kline.<tf>.<symbol>
                        parts = topic.split('.')
                        if len(parts) != 3 or parts[0] != 'kline':
                            continue
                        _tf, symbol = parts[1], parts[2]
                        if _tf != tf_str:
                            continue

                        # Bybit присылает массив свечей, берём последнюю
                        candle = data[-1] if isinstance(data, list) else data
                        # обработчик сам проверит confirm или мы можем отфильтровать здесь
                        if not candle or not candle.get("confirm"):
                            continue

                        await on_candle(symbol, candle, k_counter)
                finally:
                    pinger_task.cancel()
                    with contextlib.suppress(Exception):
                        await pinger_task

            # если вышли из with без исключения — обнуляем backoff
            backoff = 1
        except Exception as e:
            print(f"WS error: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

