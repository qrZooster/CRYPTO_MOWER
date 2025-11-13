# ======================================================================================================================
# 📁 file        : bb_db.py — основной рабочий файл БД (канонический шаблон)
# 🕒 created     : 18.09.2025 00:00
# 🎉 contains    : TSession (пул MySQL), TDatabase (ядро SQL/CRUD), init_log_router()
# 🌅 project     : Tradition Core 2025 🜂
# ======================================================================================================================
# 🚢 ...imports...
import hashlib
import time
import threading
import asyncio
from datetime import datetime
from typing import Union, Any, Dict, List, Tuple, Optional, Sequence
from mysql.connector import pooling  # NEW POOL LOGIC
# ---
from bb_sys import *
from bb_application import TApplication
from bb_logger import init_log_router, LOG_ROUTER
# 💎 ...database tables...
TBL_CONFIG      = 'ZZ$CONFIG'
# 💎 ...table fields...
FLD_ID          = 'FLD$ID'
FLD_HASH        = 'FLD$HASH'
FLD_TCOD        = 'FLD$TCOD'
FLD_SYMBOL      = 'FLD$SYMBOL'
FLD_TYPE        = 'FLD$TYPE'
FLD_NAME        = 'FLD$NAME'
FLD_TEXT        = 'FLD$TEXT'
# ---
FLD_DATE        = 'FLD$DATE'
FLD_DATE_TIME   = 'FLD$DATE_TIME'
# ---
FLD_PRICE       = 'FLD$PRICE'
FLD_VOLUME      = 'FLD$VOLUME'
FLD_SUM         = 'FLD$SUM'
FLD_VALUE       = 'FLD$VALUE'
# ---
FLD_SOURCE      = 'FLD$SOURCE'
FLD_URL         = 'FLD$URL'
FLD_TITLE       = 'FLD$TITLE'
FLD_TAGS        = 'FLD$TAGS'
FLD_VERSION     = 'FLD$VERSION'
# 🏵️ ... __all__ Public export ...
__all__ = [
    # --- core ---
    'TDatabase','TDbEvents', 'Application', 'CloseApplication',
    # legacy
    # --- QR facade ---
    'qr', 'qr_rw',
    'qr_add', 'qr_update', 'qr_delete',
    'qr_foi', 'qr_fou', 'qr_max', 'exec',
    # --- hash helpers ---
    'mk_hash', 'mk_row_hash', 'mk_tcod',
    # --- common fields ---
    'FLD_ID', 'FLD_TYPE', 'FLD_HASH', 'FLD_TCOD',
    'FLD_SYMBOL', 'FLD_SOURCE', 'FLD_URL', 'FLD_TITLE',
    'FLD_TAGS', 'FLD_DATE', 'FLD_DATE_TIME',
    'FLD_PRICE', 'FLD_VOLUME', 'FLD_SUM', 'FLD_VERSION',
    'FLD_NAME', 'FLD_TEXT', 'FLD_VALUE',
    # --- environment & system ---
    'MSK',
    'key', 'key_int', 'key_float', 'key_bool',
]
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TSession — Менеджер соединений (бывший bbDBManager), пул соединений MySQL
# ----------------------------------------------------------------------------------------------------------------------
class TSession(TSysComponent):
    """
    Пул соединений MySQL. Управляет connection pool, keep-alive циклом и выдаёт курсоры.
    Держит ссылку в Application как Session.
    """
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TApplication"):
        """
        Создаёт менеджер сессий. Готовит конфиг, состояние пула и keep-alive флаги.
        Регистрирует себя в Application.
        """
        super().__init__(Owner, "Session")
        # --- Конфигурация и состояние пула ---
        self.cfg = DB_CFG
        self.pool = None
        self._keep_alive = False
        self._keep_thread = None
        # --- Ссылка в Application ---
        Owner.Session = self
        # ... 🔊 ...
        self.log("__init__", "session created")
        # ⚡🛠️ TSession ▸ End of __init__
    # ..................................................................................................................
    # 🚀 Жизненный цикл / do_open
    # ..................................................................................................................
    def do_open(self, pool_size: int = 8) -> bool:
        """
        Создаёт пул соединений и запускает keep-alive.
        Если пул уже активен — просто сообщает об этом.
        Переопределяй в потомках.
        """
        if self.pool is not None:
            # ... 🔊 ...
            self.log("do_open", "pool already active")
            return True
        # x = 42 / 0
        try:
            self.pool = pooling.MySQLConnectionPool(
                pool_name="bb_pool",
                pool_size=pool_size,
                pool_reset_session=True,
                **self.cfg
            )
            # ... 🔊 ...
            self.log("do_open", f"pool started (size={pool_size})")
            self.keep_alive(60)
            return True
        except Exception as e:
            # ... 💥 ...
            self.fail("do_open", f"failed: {e}", e)
            return False
    # ..................................................................................................................
    # 🔥 Завершение / do_close
    # ..................................................................................................................
    def do_close(self) -> bool:
        """
        Останавливает keep-alive и уничтожает пул соединений.
        Переопределяй в потомках.
        """
        if not self.pool:
            # ... 🔊 ...
            self.log("do_close", "no pool to stop")
            return True
        try:
            self.stop_keep_alive()
            self.pool = None
            # ... 🔊 ...
            self.log("do_close", "pool stopped")
            return True
        except Exception as e:
            # ... 💥 ...
            self.fail("do_close", f"failed: {e}", e)
            return False
    # ..................................................................................................................
    # ⚙️ Соединения / _get_connection
    # ..................................................................................................................
    def _get_connection(self):
        """
        Возвращает connection из пула. Бросает RuntimeError, если пул не инициализирован.
        """
        if not self.pool:
            raise RuntimeError("Session pool not initialized, call open() first")
        return self.pool.get_connection()
    # ..................................................................................................................
    # ⚙️ CRUD / exec
    # ..................................................................................................................
    def exec(self, sql: str, params=None) -> int:
        """
        Выполняет произвольный SQL (обычно DML) без выборки и возвращает rowcount.
        """
        _, rowcount, _ = self._exec_cursor(sql, params, fetch=False)
        return rowcount
    # ..................................................................................................................
    # ⚙️ Курсор / _exec_cursor
    # ..................................................................................................................
    def _exec_cursor(self, sql: str, params=None, fetch=True):
        """
        Выполняет SQL и возвращает (rows, rowcount, last_id).
        """
        connection = self._get_connection()
        cursor = None
        try:
            cursor = connection.cursor(buffered=True)
            cursor.execute(sql, params or [])
            rows = cursor.fetchall() if fetch and cursor.with_rows else []
            return rows, cursor.rowcount, getattr(cursor, "lastrowid", 0)
        finally:
            try:
                if cursor:
                    cursor.close()
                connection.close()
            except Exception:
                pass
    # ..................................................................................................................
    # 🕒 Keep Alive / keep_alive
    # ..................................................................................................................
    def keep_alive(self, interval: int = 60):
        """
        Периодически пингует соединение, чтобы не было таймаута. Запускает поток,
        который каждые interval секунд берёт коннект из пула и делает ping().
        """
        if not self.pool:
            # ... 🔊 ...
            self.log("keep_alive", "no pool")
            return
        def _loop():
            while getattr(self, "_keep_alive", False):
                try:
                    connection = self.pool.get_connection()
                    connection.ping(reconnect=True, attempts=1, delay=0)
                    connection.close()
                    now = datetime.now().strftime("%H:%M:%S")
                    print(f"[Session] keep_alive ping ok ({now})")
                except Exception as e:
                    print(f"[Session] keep_alive warn: {e}")
                time.sleep(interval)
            print("[Session] keep_alive stopped")
        if getattr(self, "_keep_alive", False):
            return
        self._keep_alive = True
        self._keep_thread = threading.Thread(target=_loop, daemon=True)
        self._keep_thread.start()
        # ... 🔊 ...
        self.log("keep_alive", f"started (interval={interval}s)")
    # ..................................................................................................................
    # 🕒 Keep Alive / stop_keep_alive
    # ..................................................................................................................
    def stop_keep_alive(self):
        """
        Останавливает keep_alive-поток (если он активен) и ждёт его завершения.
        """
        if getattr(self, "_keep_alive", False):
            self._keep_alive = False
            if hasattr(self, "_keep_thread"):
                self._keep_thread.join(timeout=5)
            # ... 🔊 ...
            self.log("keep_alive", "stopped")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TDatabase — главный компонент работы с SQL и схемой (Tradition 2025)
# ----------------------------------------------------------------------------------------------------------------------
class TDatabase(TSysComponent):
    """
    Главный компонент работы с SQL. Держит ссылки на Session (пул соединений), Schema и cfg.
    Отвечает за подключение к БД, CRUD-операции, выборки и хеш-утилиты.
    """
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TApplication"):
        """
        Инициализирует TDatabase и привязывает его к приложению.
        Проверяет тип владельца, сохраняет ссылку на Session и Schema, фиксирует cfg.
        Переопределяй в потомках.
        """
        if not isinstance(Owner, TApplication):
            raise TypeError("TDatabase owner must be TApplication")
        super().__init__(Owner, "Database")
        # --- Конфигурация и ссылки ---
        self.cfg = DB_CFG
        self.Session = Owner.Session
        self.Schema = Owner.Schema  # ← просто ссылка
        # ... 🔊 ...
        self.log("__init__", "database initialized (linked to Schema)")
        # ⚡🛠️ TDatabase ▸ End of __init__
    # ..................................................................................................................
    # 🚀 Жизненный цикл / do_open
    # ..................................................................................................................
    def do_open(self) -> bool:
        """
        Активирует пул соединений и выполняет тест-запрос.
        Гарантирует, что Session.open() вызван и соединение рабочее.
        Переопределяй в потомках.
        """
        if not self.Session:
            # ... 💥 ...
            self.fail("do_open", "no Session assigned", ValueError)
            return False
        # Сессия обязана быть активна
        if not self.Session.pool:
            self.Session.open()
        try:
            conn = self.Session._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
            cur.close()
            conn.close()
            # ... 🔊 ...
            self.log("do_open", "connection test passed")
            return True
        except Exception as e:
            # ... 💥 ...
            self.fail("do_open", f"connection failed: {e}", type(e))
            return False
    # ..................................................................................................................
    # 🔥 Завершение / do_close
    # ..................................................................................................................
    def do_close(self) -> bool:
        """
        Закрывает пул соединений Session. Используется при остановке приложения.
        Переопределяй в потомках.
        """
        if self.Session:
            try:
                self.Session.close()
                # ... 🔊 ...
                self.log("do_close", "database connection closed")
                return True
            except Exception as e:
                # ... 💥 ...
                self.fail("do_close", f"failed: {e}", type(e))
                return False
        return True
    # ..................................................................................................................
    # ⚙️ Соединения / _get_connection
    # ..................................................................................................................
    def _get_connection(self):
        """
        Возвращает connection из пула Session.
        """
        return self.Session._get_connection()
    # ..................................................................................................................
    # ⚙️ Курсор / _exec_cursor
    # ..................................................................................................................
    def _exec_cursor(self, sql: str, params=None, fetch: bool = True):
        """
        Выполняет SQL и возвращает (rows, rowcount, last_id).
        """
        link = self._get_connection()
        query = None
        try:
            query = link.cursor(buffered=True)
            query.execute(sql, params or [])
            rows = query.fetchall() if fetch and query.with_rows else []
            return rows, query.rowcount, getattr(query, "lastrowid", 0)
        finally:
            try:
                if query:
                    query.close()
                link.close()
            except Exception:
                pass
    # ..................................................................................................................
    # ⚙️ Курсор (dict) / _exec_cursor_dict
    # ..................................................................................................................
    def _exec_cursor_dict(self, sql: str, params=None, fetch: bool = True):
        """
        То же самое, но возвращает dict-строки.
        """
        link = self._get_connection()
        query = None
        try:
            query = link.cursor(buffered=True, dictionary=True)
            query.execute(sql, params or [])
            rows = query.fetchall() if fetch and query.with_rows else []
            return rows, query.rowcount, getattr(query, "lastrowid", 0)
        finally:
            try:
                if query:
                    query.close()
                link.close()
            except Exception:
                pass
    # ..................................................................................................................
    # 🔍 WHERE builder / _where_sql
    # ..................................................................................................................
    @staticmethod
    def _where_sql(where: Any) -> Tuple[str, Tuple]:
        """
        Строит SQL-условие и tuple параметров из разных форматов where:
        int → equals по FLD_ID; str → raw WHERE; dict → равенства/IN/IS NULL.
        """
        if where is None:
            return "", ()
        if isinstance(where, int):
            return f"`{FLD_ID}`=%s", (int(where),)
        if isinstance(where, str):
            w = where.strip()
            return (w[6:].strip(), ()) if w.upper().startswith("WHERE ") else (w, ())
        if isinstance(where, dict):
            parts, vals = [], []
            for k, v in where.items():
                col = f"`{k}`"
                if v is None:
                    parts.append(f"{col} IS NULL")
                elif isinstance(v, (list, tuple, set)):
                    vv = list(v)
                    if not vv:
                        parts.append("1=0")
                    else:
                        placeholders = ", ".join(["%s"] * len(vv))
                        parts.append(f"{col} IN ({placeholders})")
                        vals.extend(vv)
                else:
                    parts.append(f"{col}=%s")
                    vals.append(v)
            return " AND ".join(parts), tuple(vals)
        raise TypeError(f"Unsupported where type: {type(where)}")
    # ..................................................................................................................
    # ⚙️ CRUD / exec
    # ..................................................................................................................
    def exec(self, sql: str, params: Optional[Tuple] = None) -> int:
        """
        Выполняет произвольный SQL (обычно DML) и возвращает rowcount.
        """
        _, rowcount, _ = self._exec_cursor(sql, params)
        return rowcount
    # ..................................................................................................................
    # ⚙️👑 CRUD / qr
    # ..................................................................................................................
    def qr(self, table_or_sql: str | None = None, where=None, data: dict | None = None):
        """
        Универсальный селект. Если передана raw SQL-строка ('SELECT', 'SHOW', ...), выполняет её и возвращает dict-строки.
        Если передано имя таблицы: собирает SELECT с where/order/limit.
        Если table_or_sql=None: возвращает SHOW TABLES.
        """
        if table_or_sql is None:
            rows, _, _ = self._exec_cursor_dict("SHOW TABLES", None, True)
            return rows
        s = table_or_sql.strip()
        if (" " in s) or s.upper().startswith(("SELECT", "SHOW", "DESC", "EXPLAIN")):
            rows, _, _ = self._exec_cursor_dict(s, tuple(where or ()), True)
            return rows
        fields = (data or {}).get("fields", "*")
        order_by = (data or {}).get("order_by")
        limit = (data or {}).get("limit")
        wsql, wparams = self._where_sql(where)
        sql = f"SELECT {fields} FROM `{table_or_sql}`"
        if wsql:
            sql += f" WHERE {wsql}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if isinstance(limit, int) and limit > 0:
            sql += f" LIMIT {limit}"
        rows, _, _ = self._exec_cursor_dict(sql, wparams, True)
        return rows
    # ..................................................................................................................
    # ⚙️ CRUD / qr_rw
    # ..................................................................................................................
    def qr_rw(self, table_or_sql: str | None = None, where=None, data: dict | None = None):
        """
        Возвращает первую строку результата qr(...) или None.
        Поддерживает явный список полей через data['fields'].
        """
        fields = data.pop("fields") if data and "fields" in data else "*"
        rows = self.qr(table_or_sql, where, {"fields": fields})
        return rows[0] if rows else None
    # ..................................................................................................................
    # ⚙️ CRUD / qr_add
    # ..................................................................................................................
    def qr_add(self, table_name: str, data: Dict[str, Any]) -> dict:
        """
        INSERT в table_name и возврат записи по lastrowid.
        """
        if not isinstance(data, dict) or not data:
            raise ValueError("qr_add: data must be non-empty dict")
        cols = list(data.keys())
        vals = [data[k] for k in cols]
        cols_sql = ", ".join(f"`{c}`" for c in cols)
        placeholders = ", ".join(["%s"] * len(vals))
        sql = f"INSERT INTO `{table_name}` ({cols_sql}) VALUES ({placeholders})"
        _, _, lastrowid = self._exec_cursor(sql, tuple(vals), fetch=False)
        if not lastrowid:
            return {}
        return self.qr_rw(table_name, {FLD_ID: int(lastrowid)}) or {}
    # ..................................................................................................................
    # ⚙️ CRUD / qr_update
    # ..................................................................................................................
    def qr_update(self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]) -> dict:
        """
        UPDATE table_name по where, затем возвращает обновлённую запись.
        """
        if not where or not data:
            raise ValueError("qr_update: both WHERE and DATA required")
        set_sql = ", ".join(f"`{k}`=%s" for k in data.keys())
        wsql, wparams = self._where_sql(where)
        sql = f"UPDATE `{table_name}` SET {set_sql} WHERE {wsql}"
        params = list(data.values()) + list(wparams)
        self._exec_cursor(sql, tuple(params), fetch=False)
        return self.qr_rw(table_name, where) or {}
    # ..................................................................................................................
    # ⚙️ CRUD / qr_delete
    # ..................................................................................................................
    def qr_delete(self, table_name: str, where: Dict[str, Any]) -> dict:
        """
        DELETE по where с возвратом удалённой строки.
        """
        row = self.qr_rw(table_name, where)
        if not row:
            return {}
        wsql, wparams = self._where_sql(where)
        sql = f"DELETE FROM `{table_name}` WHERE {wsql}"
        self._exec_cursor(sql, tuple(wparams), fetch=False)
        return row
    # ..................................................................................................................
    # ⚙️ CRUD / qr_foi
    # ..................................................................................................................
    def qr_foi(self, table_name: str, where: dict, data: dict) -> dict:
        """
        Find Or Insert. Если запись есть → вернуть её, иначе INSERT(where ∪ data).
        """
        row = self.qr_rw(table_name, where)
        return row if row else self.qr_add(table_name, {**where, **data})
    # ..................................................................................................................
    # ⚙️ CRUD / qr_fou
    # ..................................................................................................................
    def qr_fou(self, table_name: str, where: dict, data: dict) -> dict:
        """
        Find Or Update. Если запись есть → UPDATE, иначе INSERT.
        """
        row = self.qr_rw(table_name, where)
        if row:
            result = self.qr_update(table_name, where, data)
            return result or self.qr_rw(table_name, where) or {}
        return self.qr_add(table_name, {**where, **data})
    # ......................................................................................................................
    # ⚙️ Агрегаты / qr_max
    # ......................................................................................................................
    def qr_max(self, table_name: str, field_name: str, where=None):
        """
        Возвращает MAX(field_name) из таблицы с учётом where или None.
        """
        row = self.qr_rw(table_name, where, {"fields": f"MAX(`{field_name}`) AS m", "limit": 1})
        return row.get("m") if row and row.get("m") is not None else None
    # ..................................................................................................................
    # 🔐 HASH / mk_hash
    # ..................................................................................................................
    def mk_hash(self, *parts: Any) -> str:
        """
        MD5 от конкатенации значений parts через '|', None превращается в ''.
        """
        base = "|".join([(str(p if p is not None else "").strip()) for p in parts])
        return hashlib.md5(base.encode("utf-8")).hexdigest()
    # ..................................................................................................................
    # 🔐 HASH / mk_row_hash
    # ..................................................................................................................
    def mk_row_hash(self, row: Dict[str, Any], fields: Sequence[str]) -> str:
        """
        MD5 от выбранных полей row, приводимых к строке и склеиваемых через '|'.
        """
        values = [str(row.get(f, "") if row.get(f, "") is not None else "").strip() for f in fields]
        return hashlib.md5("|".join(values).encode("utf-8")).hexdigest()
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TConfig — компонент конфигурации проекта (ENV + ZZ$CONFIG)
# ----------------------------------------------------------------------------------------------------------------------
class TConfig(TSysComponent):
    """
    Компонент конфигурации проекта — управляет ENV и таблицей ZZ$CONFIG.
    Хранит значения параметров в памяти (self.env) и синхронизирует их с БД.
    """
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TApplication"):
        """
        Инициализирует конфигурационный компонент. Проверяет владельца, задаёт таблицу конфигурации,
        выделяет локальный ENV-словарь и прокидывает ссылку в Application.
        Переопределяй в потомках.
        """
        if not isinstance(Owner, TApplication):
            raise TypeError("TConfig owner must be TApplication")
        super().__init__(Owner, "Config")
        # --- Таблица и ENV-кэш ---
        self.table = TBL_CONFIG
        self.env: dict[str, str] = {}
        # --- Ссылка в Application ---
        Owner.Config = self
        # ... 🔊 ...
        self.log("__init__", "config initialized")
        # ⚡🛠️ TConfig ▸ End of __init__
    # ......................................................................................................................
    # 🔮 Конфигурация / запись значений
    # ......................................................................................................................
    def do_set(self, name: str, value: str, text: str = "", type_: str = "AUTO") -> dict:
        """
        Базовая функция записи значения в ENV и таблицу конфигурации.
        Используется как единая точка истины для установки параметров.
        """
        if not name:
            # ... 💥 ...
            self.fail("do_set", "name required", ValueError)
            return {}
        self.env[name] = str(value)
        record = {
            FLD_NAME: name,
            FLD_VALUE: str(value),
            FLD_TYPE: type_,
            FLD_TEXT: text or "",
        }
        try:
            from bb_db import qr_fou
            r = qr_fou(self.table, {FLD_NAME: name}, record)
            # ... 🔊 ...
            self.log("do_set", f"{name}={value}")
            return r
        except Exception as e:
            # ... 💥 ...
            self.fail("do_set", f"error: {e}", e)
            return {}
    # ......................................................................................................................
    # 🧭 Основные методы доступа
    # ......................................................................................................................
    def get(self, name: str, default: str = "") -> str:
        """
        Возвращает значение параметра.
        Сначала ищет в self.env. Если нет — создаёт параметр с default через do_set() и возвращает default.
        """
        if not name:
            return ""
        val = self.env.get(name)
        if val is not None:
            return val
        # значение отсутствует — создаём его и сохраняем через do_set()
        self.do_set(name, default, text="auto-created by get()")
        return str(default)

    def set(self, name: str, value: str, text: str = None, type_: str = None) -> dict:
        """
        Публичный метод обновления значения конфигурации. Обновляет ENV и БД.
        """
        return self.do_set(name, value, text=text or "", type_=type_ or "MANUAL")
    # ......................................................................................................................
    # 📊 Типизированные геттеры
    # ......................................................................................................................
    def get_int(self, name: str, default: int = 0) -> int:
        """
        Возвращает параметр как int. Если не получается привести, фиксирует default через do_set() и возвращает его.
        """
        try:
            return int(self.get(name, default))
        except Exception:
            self.do_set(name, default)
            return int(default)

    def get_float(self, name: str, default: float = 0.0) -> float:
        """
        Возвращает параметр как float. Если не получается привести, фиксирует default через do_set() и возвращает его.
        """
        try:
            return float(self.get(name, default))
        except Exception:
            self.do_set(name, default)
            return float(default)

    def get_bool(self, name: str, default: bool = False) -> bool:
        """
        Возвращает параметр как bool. Интерпретирует '0','false','off','none','null' как False.
        Любое иное ненулевое значение трактуется как True.
        """
        v = str(self.get(name, str(int(default)))).strip().lower()
        if v in ("", "0", "false", "off", "none", "null"):
            return False
        try:
            return bool(int(v))
        except Exception:
            return True
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TSchema — подсистема описания структуры БД (Stage 1 / PPS Doctrine)
# ----------------------------------------------------------------------------------------------------------------------
class TSchema(TSysComponent):
    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TApplication"):
        """
        Системный компонент описания структуры БД. Держит список таблиц, полей, индексов и констант, загружает метаданные
        и даёт приложению доступ к introspection. Owner обязан быть TApplication.
        Поля:
        - tables      — обнаруженные таблицы (фильтрованные по allow/deny);
        - fields      — описание полей по таблицам;
        - indices     — индексы;
        - constants   — константы схемы;
        - initialized — флаг готовности;
        - last_loaded — timestamp последней загрузки структуры.
        """
        if not isinstance(Owner, TApplication):
            raise TypeError("TSchema owner must be TApplication")
        super().__init__(Owner, "Schema")
        # --- Основные структуры схемы ---
        self.tables: dict[str, dict] = {}
        self.fields: dict[str, dict] = {}
        self.indices: dict[str, dict] = {}
        self.constants: dict[str, Any] = {}
        self.initialized: bool = False
        self.last_loaded: Optional[datetime] = None
        # --- Линк в приложение (обратная ссылка) ---
        Owner.Schema = self
        # ... 🔊 ...
        self.log("__init__", "schema component created")
        # ⚡🛠️ TSchema ▸ End of __init__
    # ......................................................................................................................
    # 🚀 Жизненный цикл / Открытие и закрытие
    # ......................................................................................................................
    def do_open(self) -> bool:
        """
        Инициализирует схему. Читает правила allow*/deny* из конфигурации (ENV/ZZ$CONFIG),
        затем вызывает _load_tables() чтобы просканировать БД и построить self.tables.
        Возвращает True при успешной инициализации.
        """
        self.allow_prefixes = explode(';', key("SCHEMA_ALLOW_PREFIXES", "TBL$,DOC$,REF$,SYS$"))
        self.allow_names    = explode(';', key("SCHEMA_ALLOW_NAMES", ""))
        self.deny_prefixes  = explode(';', key("SCHEMA_DENY_PREFIXES", "TMP$,ARCH$,DEV$"))
        self.deny_names     = explode(';', key("SCHEMA_DENY_NAMES", ""))
        # загружаем структуру таблиц
        self._load_tables()
        # ... 🔊 ...
        self.log("do_open", f"schema loaded: {len(self.tables)} tables")
        return True

    def do_close(self) -> bool:
        """
        Очищает внутренние структуры introspection. Сбрасывает кеш таблиц, полей, индексов, констант
        и метаданные состояния (initialized / last_loaded). Вызывается при остановке приложения.
        """
        self.tables.clear()
        self.fields.clear()
        self.indices.clear()
        self.constants.clear()
        self.initialized = False
        self.last_loaded = None
        # ... 🔊 ...
        self.log("do_close", "schema cleared")
        return True
    # ......................................................................................................................
    # 📚 Сканирование структуры БД
    # ......................................................................................................................
    def _load_tables(self) -> dict[str, dict]:
        """
        Загружает список таблиц из базы (через qr('SHOW TABLES')), фильтрует по allow/deny правилам
        и сохраняет результат в self.tables. Возвращает собранный dict вида {table_name: {}}.
        """
        from bb_db import qr
        # Получаем все таблицы
        rows = qr("SHOW TABLES")
        all_tables = [list(row.values())[0] for row in rows]
        # ... 🔊 ...
        self.log("_load_tables", f"scanned {len(all_tables)} tables")
        # Фильтруем по allow/deny
        filtered = []
        for t in all_tables:
            tn = t.upper()
            if any(tn.startswith(p) for p in self.deny_prefixes):
                continue
            if tn in self.deny_names:
                continue
            if self.allow_prefixes and not any(tn.startswith(p) for p in self.allow_prefixes):
                continue
            if self.allow_names and tn not in self.allow_names:
                continue
            filtered.append(t)
        # Сохраняем результат
        self.tables = {name: {} for name in filtered}
        # ... 🔊 ...
        self.log("_load_tables", f"allowed {len(filtered)} of {len(all_tables)}")
        return self.tables
    # ......................................................................................................................
    # 💎 Регистрация констант схемы
    # ......................................................................................................................
    def _register_constants(self):
        """
        Формирует и регистрирует глобальные константы схемы (Stage 2). План: публиковать важные поля в пространство имён,
        чтобы можно было использовать как CONST. Пока заглушка.
        """
        # ... 🔊 ...
        self.log("_register_constants", "stage 1 stub (const builder)")
# ----------------------------------------------------------------------------------------------------------------------
# 🧩 TDbEvents — системный компонент опроса SYS$EVENTS (Stage 0: таймер + логи)
# ----------------------------------------------------------------------------------------------------------------------
class TDbEvents(TSysComponent):
    """
    Системный компонент Tradition Core, который периодически опрашивает таблицу SYS$EVENTS.
    Текущая версия (Stage 0):
      - принадлежит только TApplication (Owner = TApplication);
      - раз в poll_interval секунд пишет лог через self.log()
        о том, что собирается проверить SYS$EVENTS;
      - никакого SQL и событий пока НЕ делает (только “сердцебиение” механизма).

    Дальше на этом скелете добавим:
      - last_id и загрузку новых событий из БД;
      - генерацию внутренних TEvent;
      - отправку db-сообщений по WebSocket.
    """

    # базовый интервал опроса (секунды)
    DEFAULT_POLL_INTERVAL: int = 5

    # ⚡🛠️ ▸ __init__
    def __init__(self, Owner: "TApplication"):
        """
        Создаёт компонент TDbEvents и привязывает его к приложению.
        Предполагается, что в Application он живёт как единственный экземпляр,
        например: app.DbEvents = TDbEvents(app)
        """
        if not isinstance(Owner, TApplication):
            raise TypeError("TDbEvents owner must be TApplication")

        super().__init__(Owner, "DbEvents")

        # интервал опроса (секунды) — пока фиксированный, потом вытащим в Config
        self.poll_interval: int = self.DEFAULT_POLL_INTERVAL

        # флаг остановки и ссылка на фоновую задачу
        self._stop: bool = False
        self._task_main: asyncio.Task | None = None

        # “счётчик поколений” опросов — чисто для логов/debug
        self._tick_counter: int = 0
        # ... 🔊 ...
        self.log("__init__", f"db-events watcher created (interval={self.poll_interval}s)")
    # ..................................................................................................................
    # 🚀 Жизненный цикл / do_open
    # ..................................................................................................................
    def do_open(self) -> bool:
        """
        Запускает фоновой асинхронный цикл опроса.
        Ничего не делает с БД, только пишет логи каждые poll_interval секунд.
        """
        if self._task_main is not None and not self._task_main.done():
            # уже запущен
            self.log("do_open", "already running")
            return True

        self._stop = False
        try:
            self._task_main = asyncio.create_task(self._run_loop())
            self.log("do_open", f"started (interval={self.poll_interval}s)")
            return True
        except Exception as e:
            self.fail("do_open", f"failed to start loop: {e}", e)
            return False
    # ..................................................................................................................
    # 🔥 Завершение / do_close
    # ..................................................................................................................
    def do_close(self) -> bool:
        """
        Останавливает фоновой цикл опроса.
        Реализация мягкая: ставим _stop=True и ждём завершения задачи.
        """
        self._stop = True

        task = self._task_main
        self._task_main = None

        if task is not None and not task.done():
            try:
                # не ждём бесконечно, чтобы не зависнуть при shutdown
                # (loop сам доработает текущий tick и выйдет)
                self.log("do_close", "stop requested, waiting task to finish")
            except Exception:
                pass

        self.log("do_close", "db-events watcher stopped")
        return True
    # ..................................................................................................................
    # 🧠 Главный цикл опроса
    # ..................................................................................................................
    async def _run_loop(self):
        """
        Главный асинхронный цикл TDbEvents.

        Сейчас делает только:
          - раз в poll_interval секунд вызывает _tick();
          - ловит исключения, чтобы помпа не умирала от одной ошибки.
        """
        self.log("_run_loop", "loop started")
        try:
            while not self._stop:
                try:
                    await self._tick()
                except Exception as e:
                    # логируем, но не падаем насмерть
                    self.fail("_run_loop", f"tick failed: {e}", e)

                # пауза между тиками
                await asyncio.sleep(max(1, int(self.poll_interval)))
        finally:
            self.log("_run_loop", "loop finished")
    # ..................................................................................................................
    # ⏱️ Один “тик” опроса (Stage 0: только log())
    # ..................................................................................................................
    async def _tick(self):
        """
        Один шаг опроса SYS$EVENTS.
        Stage 0:
          - увеличиваем счётчик тиков;
          - пишем лог о том, что “пора бы проверить SYS$EVENTS”.
        Без реального SQL и без генерации событий.
        """
        self._tick_counter += 1

        # в будущих версиях здесь появится SQL и обработка новых строк
        self.log(
            "tick",
            f"poll SYS$EVENTS (tick={self._tick_counter}, interval={self.poll_interval}s)"
        )

        # на будущее — оставляем await, чтобы сигнатура была async
        await asyncio.sleep(0)
# ----------------------------------------------------------------------------------------------------------------------
# 🏛️👑 Application Facade — ядро и публичные хелперы (qr_*, key_*, mk_hash, ...)
# ----------------------------------------------------------------------------------------------------------------------
def Application() -> TApplication:
    """
    Создаёт/возвращает singleton приложения Tradition Core.
    Поднимает Session / Database / Config / Schema и вызывает их .open() в каноническом порядке.
    Вызывай Application() вместо ручного создания TApplication.
    """
    init_log_router()
    if LOG_ROUTER:
        print("🌈 [Rich] LogRouter initialized — multi-window console active", flush=True)
    else:
        print("🪶 [Fallback] Plain console logger active", flush=True)
    app = TApplication.app()
    if not getattr(app, "Database", None):
        # создаём основные системные сущности
        app.Session = TSession(app)
        app.Database = TDatabase(app)
        app.Config = TConfig(app)
        app.Schema = TSchema(app)  # Schema принадлежит Application
        app.DbEvents = TDbEvents(app)
        # ... 🔊 ...
        app.log("Application", "core components created (Session, Database, Config, Schema)")
        # === Закон Tradition: четыре затвора ===
        app.Session.open()
        app.Database.open()
        app.Config.open()
        app.Schema.open()
        app.DbEvents.open()
        # ... 🔊 ...
        app.log("Application", "Config & Schema loaded, database connected")
    # ... 🔊 ...
    app.log("Application", "log center initialized")
    return app
# ......................................................................................................................
# 🛑🏛️ Shutdown / CloseApplication
# ......................................................................................................................
def CloseApplication():
    """
    Аккуратно завершает приложение Tradition Core.
    Закрывает Session, выгружает Components, пишет финальные логи
    и обнуляет singleton TApplication._instance.
    Используется для мягкой остановки процесса.
    """
    app = TApplication._instance
    if app is None:
        return
    try:
        if hasattr(app, "Session"):
            app.Session.close()
        if hasattr(app, "Components"):
            for name in list(app.Components.keys()):
                # ... 🔊 ...
                app.log('CloseApplication', f'releasing {name}')
            app.Components.clear()
        # ... 🔊 ...
        app.log('CloseApplication', 'application terminated successfully')
    except Exception as e:
        print(f"[Application] close warning: {e}")
    finally:
        TApplication._instance = None
        print("\n🎬  The End — HappyEnd edition 🌅\n")
# ----------------------------------------------------------------------------------------------------------------------
# 🏦🍓 DB Facade — CRUD / HASH / CONFIG wrappers
# ----------------------------------------------------------------------------------------------------------------------
# ......................................................................................................................
# 🍓 QR FACADE: CRUD / SELECT / UTILITY
# ......................................................................................................................
def qr_add(table: str, data: Dict[str, Any]):
    """Добавляет строку в таблицу и возвращает dict вставленной записи."""
    return Application().Database.qr_add(table, data)
# ---
def qr_update(table: str, where: Any, data: Dict[str, Any]):
    """Обновляет строки и возвращает dict обновлённой записи (если есть)."""
    return Application().Database.qr_update(table, where, data)
# ---
def qr_delete(table: str, where: Any, data: Optional[Dict[str, Any]] = None):
    """Удаляет строки и возвращает количество удалённых (int)."""
    limit = None
    if isinstance(data, dict) and isinstance(data.get("limit"), int):
        limit = data["limit"]
    return Application().Database.qr_delete(table, where)
# ---
def qr_foi(table: str, where: Any, data: Dict[str, Any]):
    """Find-Or-Insert — возвращает dict строки (всегда свежей)."""
    return Application().Database.qr_foi(table, where, data)
# ---
def qr_fou(table: str, where: dict, data: dict):
    """Find-Or-Update — возвращает dict строки."""
    return Application().Database.qr_fou(table, where, data)
# ---
def qr_max(table_name: str, field_name: str, where=None):
    """Возвращает значение MAX(field_name) — примитив, не dict."""
    return Application().Database.qr_max(table_name, field_name, where)
# ---
def qr(table_or_sql: str | None = None, where=None, data: dict | None = None):
    """Универсальный запрос SELECT / SHOW."""
    return Application().Database.qr(table_or_sql, where, data)
# ---
def qr_rw(table_or_sql: str | None = None, where=None, data: dict | None = None):
    """Возвращает одну строку (row) по условию WHERE."""
    return Application().Database.qr_rw(table_or_sql, where, data)
# ---
def exec(sql: str, params: Optional[Tuple] = None):
    """Выполняет SQL-запрос без выборки (INSERT/UPDATE/DELETE)."""
    return Application().Database.exec(sql, params)
# ......................................................................................................................
# 🍋 HASH Facade
# ......................................................................................................................
def mk_hash(*parts: Any) -> str:
    """Возвращает MD5-хэш строки из частей."""
    return Application().Database.mk_hash(*parts)
# ---
def mk_row_hash(row: Dict[str, Any], fields: Sequence[str]) -> str:
    """Хэширует набор полей строки (по значениям)."""
    return Application().Database.mk_row_hash(row, fields)
# ......................................................................................................................
# 🍒 CONFIG KEYS FACADE: (COMPAT LAYER)
# ......................................................................................................................
def key(name: str | None, default: str = '') -> str | None:
    """Возвращает значение параметра (ENV / ZZ$CONFIG)."""
    return Application().Config.get(name, default)
# ---
def set_key(name: str, value: Any, text: str = None, type_: str = None) -> dict:
    """Обновляет параметр конфигурации (ENV / ZZ$CONFIG)."""
    return Application().Config.set(name, value, text=text or '', type_=type_ or 'MANUAL')
# ---
def key_int(name: str, default: int = 0) -> int:
    """Возвращает параметр как int."""
    return Application().Config.get_int(name, default)
# ---
def key_float(name: str, default: float = 0.0) -> float:
    """Возвращает параметр как float."""
    return Application().Config.get_float(name, default)
# ---
def key_bool(name: str, default: bool = False) -> bool:
    """Возвращает параметр как bool."""
    return Application().Config.get_bool(name, default)
# ......................................................................................................................
# 🍇 TCOD
# ......................................................................................................................
def mk_tcod(symbol: str, ts: Union[int, float], tf: str, venue: str = "BYBIT") -> str:
    """
    Формат:
      SYMBOL_YYYYMMDD_HHMMSS[_mmm]_TF_VENUE

    - ts: UNIX-время в секундах ИЛИ миллисекундах (определяется автоматически).
    - Если в ts есть миллисекунды, добавляем *_mmm* для ЛЮБОГО TF (универсально).
    """
    tfu = str(tf).upper()
    vu  = str(venue).upper()

    t_int = int(ts)
    # эвристика: >= 1e12 → миллисекунды
    is_ms = t_int >= 1_000_000_000_000
    if is_ms:
        sec = t_int // 1000
        ms  = t_int % 1000
    else:
        sec = t_int
        ms  = 0

    dt_msk = datetime.fromtimestamp(sec, tz=MSK)
    base = f"{symbol}_{dt_msk.strftime('%Y%m%d_%H%M%S')}"
    if ms:
        base += f"_{ms:03d}"
    return f"{base}_{tfu}_{vu}"
# ---
def _to_dt_msk(ts) -> datetime:
    """
    Приводит ts к timezone-aware datetime в МСК.
    Допускает: epoch seconds/ms (int/float) или datetime (naive/aware).
    Naive datetime трактуем как уже-МСК.
    """
    if isinstance(ts, (int, float)):
        # поддержка миллисекунд (грубая эвристика)
        if ts > 10**12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=MSK)
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=MSK)
        return ts.astimezone(MSK)
    raise TypeError(f"Unsupported ts type for mk_tcod(): {type(ts)}")
# ======================================================================================================================
# 📁🌄 bb_db.py 🜂 The End — See You Next Session 2025 ⚙️ 768 -> 929
# ======================================================================================================================

