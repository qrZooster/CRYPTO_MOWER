# bb_db.py
# ALIAS: BB_DB
# Created: 2025-09-18
# Конфигурация базы данных и универсальный класс DB с авто-переподключением

import os
import mysql.connector as mysql
import json
from datetime import datetime, timedelta, timezone
from bb_tg import send_telegram

DB_CFG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 3307)),
    "user": os.getenv("DB_USER", "u267510"),
    "password": os.getenv("DB_PASS", "_n2FeRUP.6"),
    "database": os.getenv("DB_NAME", "u267510_tg"),
    "use_pure": True
}

# Часовой пояс для вывода (МСК)
MSK = timezone(timedelta(hours=3))

# Универсальный класс DB для любых модулей
class DB:
    def __init__(self):
        self.cfg = DB_CFG
        self.conn = mysql.connect(**self.cfg)
        self.conn.autocommit = True

    def _get_conn(self):
        try:
            if not self.conn.is_connected():
                self.conn.reconnect(attempts=3, delay=5)
        except Exception:
            self.conn = mysql.connect(**self.cfg)
            self.conn.autocommit = True
        return self.conn

    def exec(self, sql: str, params=None):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(sql, params or [])
        conn.commit()
        return cur

    def fetchone(self, sql: str, params=None):
        cur = self.exec(sql, params)
        return cur.fetchone()

    def fetchall(self, sql: str, params=None):
        cur = self.exec(sql, params)
        return cur.fetchall()

    def insert(self, sql: str, params=None):
        cur = self.exec(sql, params)
        return getattr(cur, "lastrowid", None)

    def add(self, table: str, data: dict):
        if not isinstance(table, str) or not table:
            raise ValueError("add(): table must be a non-empty string")
        if not isinstance(data, dict) or not data:
            raise ValueError("add(): data must be a non-empty dict")

        cols = list(data.keys())

        def q(identifier: str) -> str:
            return f"`{identifier.replace('`', '``')}`"

        col_list = ", ".join(q(c) for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO {q(table)} ({col_list}) VALUES ({placeholders})"
        params = tuple(data[c] for c in cols)

        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return getattr(cur, "lastrowid", None)

# === Глобальная инициализация соединения ===
_db = None

def init_db():
    global _db
    if _db is None:
        _db = DB()
    return _db

def close_db():
    global _db
    if _db is not None:
        try:
            _db.close()
        finally:
            _db = None

def qr_add(table_name: str, data: dict):
    db = init_db()
    return db.add(table_name, data)

# --- Специализированный для MAIN класс БД ---
class DBMain(DB):
    def __init__(self):
        super().__init__()

    def insert_signal(
        self,
        symbol: str,
        ts_ms: int,
        action: str,
        price: float,
        strength: float,
        reason: str,
        x_volume: float,
        p_price: float,
        type_sig: str,
    ):
        self.exec(
            "INSERT INTO ZZ$SIGNALS(FLD$SYMBOL, FLD$TS_MS, FLD$ACTION, FLD$PRICE, FLD$STRENGTH, "
            "FLD$REASON, FLD$X_VOLUME, FLD$P_PRICE, FLD$TYPE, FLD$DATE_OTP) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            (symbol, ts_ms, action, price, strength, reason, x_volume, p_price, type_sig),
        )
        dt_str = datetime.fromtimestamp(ts_ms/1000, tz=MSK).strftime("%H:%M:%S")
        emoji = "🟢🚀" if type_sig == "PUMP" else "🔴⚠️"
        link = f"https://www.coinglass.com/tv/Bybit_{symbol}"
        msg = (
            f"{emoji} {type_sig} [{symbol}]({link})\n"
            f"{dt_str}\n"
            f"ΔP= {p_price:.2f}%, ΔVol= x{x_volume:.1f}"
        )
        print(msg)

    def execute(self, sql: str, params=None):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(sql, params or [])
        conn.commit()
        return cur.rowcount

    def close(self):
        self.conn.close()

# --- Специализированный класс для SCAN ---
class DBScan(DB):
    def __init__(self):
        super().__init__()

    def insert_pattern(self, name: str, type_sig: str, timeframe: str, symbol: str, params: dict, image_bytes: bytes = None):
        tcod = f"{params.get('datetime').replace('-', '').replace(':', '').replace(' ', '_')}_{symbol}_{timeframe}"
        exists = self.fetchone("SELECT COUNT(*) FROM ZZ$LIB WHERE FLD$TCOD=%s", (tcod,))
        if exists and exists[0] > 0:
            print(f"⚠️ Пропуск дубликата TCOD={tcod}")
            return

        sql = (
            "INSERT INTO ZZ$LIB(FLD$TCOD, FLD$NAME, FLD$TYPE, FLD$TIME_FRAME, FLD$SYMBOL, "
            "FLD$DATE_TIME, FLD$P_PRICE, FLD$X_VOLUME, FLD$PARAMS, FLD$IMAGE, FLD$DATE_OTP) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())"
        )
        self.exec(sql, (
            tcod,
            name,
            type_sig,
            timeframe,
            symbol,
            params.get("datetime"),
            params.get("p_price"),
            params.get("x_volume"),
            json.dumps(params, ensure_ascii=False),
            image_bytes
        ))
