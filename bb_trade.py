# bb_trade.py — демо-трейдинг (PAPER) + единый интерфейс
# Совместимо с Python 3.9

import os
import time
import math
from datetime import datetime
from typing import Dict, Any

import bb_db as db
from bb_db import *
from bb_vars import *

# ========= утилиты округления к шагу =========
def _floor_step(x: float, step: float) -> float:
    if step is None or step <= 0:
        return float(x)
    return math.floor(float(x) / float(step)) * float(step)

def _round_step(x: float, step: float) -> float:
    if step is None or step <= 0:
        return float(x)
    # безопасное округление к ближайшему шагу
    return round(round(float(x) / float(step)) * float(step), 12)

# ========= базовый класс интерфейса =========
class BaseTrader:
    mode = "BASE"

    def open_order_from_c(self, symbol: str, c: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

# ========= PAPER (локальный демосчёт, без API) =========
class PaperTrader(BaseTrader):
    mode = "PAPER"

    def __init__(self):
        # можно переопределить шаги через ENV
        self.qty_step = float(os.getenv("PAPER_QTY_STEP", "0.001"))
        self.price_step = float(os.getenv("PAPER_PRICE_STEP", "0.0001"))
        db.init_db()

    def _build_order(self, symbol: str, c: Dict[str, Any]) -> Dict[str, Any]:
        side = "Buy" if c.get("OPERATION") == "BUY" else "Sell"
        price = float(c.get("close", 0.0))
        lev   = int(c.get("LEVERAGE", 1) or 1)
        usdt  = float(c.get("SUM", 0.0) or 0.0)

        # Кол-во по формуле qty = (USDT * leverage) / price, приведённое к шагу
        qty_raw = (usdt * lev) / max(price, 1e-12)
        qty = _floor_step(qty_raw, self.qty_step)

        return {
            "side": side,
            "price": _round_step(price, self.price_step),
            "qty": qty,
            "usdt": usdt,
            "leverage": lev,
            "tf": str(c.get("TF", "1SEC")),
            "direction": c.get("D", "FLAT"),
            "p_oc": float(c.get("P_OC", 0.0) or 0.0),
        }

    def open_order_from_c(self, symbol: str, c: Dict[str, Any]) -> Dict[str, Any]:
        o = self._build_order(symbol, c)
        if o["qty"] <= 0:
            return {"status": "REJECT", "reason": "qty<=0", "mode": self.mode}

        ts_sec = int(time.time())
        dt_str = datetime.fromtimestamp(ts_sec, tz=MSK).strftime("%Y-%m-%d %H:%M:%S")

        # Запишем как «бумажный» ордер в отдельную таблицу
        row = {
            FLD_SYMBOL: symbol,
            FLD_DATE_TIME: dt_str,
            FLD_PRICE: float(o["price"]),
            FLD_SUM: float(o["usdt"]),
            FLD_TCOD: mk_tcod(symbol, ts_sec, "PAPER", BYBIT),
            "FLD$TF": "PAPER",
            "FLD$SIDE": o["side"],
            "FLD$QTY": float(o["qty"]),
            "FLD$LEVERAGE": int(o["leverage"]),
            "FLD$P_OC": float(o["p_oc"]),
            "FLD$DIRECTION": o["direction"],
            "FLD$MODE": self.mode,
            "FLD$VERSION": os.getenv("TRADE_VERSION", "AUDI_RS7"),
        }
        db.qr_add("ZZ$PAPER_TRADES", row)
        return {"status": "FILLED", "mode": self.mode, "qty": o["qty"], "price": o["price"]}

# ========= заглушка для TESTNET (включим по команде) =========
class TestnetTrader(BaseTrader):
    mode = "TESTNET"

    def __init__(self):
        # Заготовка — подключим REST Bybit v5 по твоей команде (ключи/сигнатуры/эндпоинты)
        raise NotImplementedError("TESTNET включим по твоей команде, PAPER уже работает.")

# ========= фабрика =========
def trader() -> BaseTrader:
    mode = os.getenv("TRADE_MODE", "PAPER").upper()
    if mode == "TESTNET":
        return TestnetTrader()  # поднимем по команде
    return PaperTrader()
