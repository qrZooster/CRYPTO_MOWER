# ============================== CANONICAL ==============================
# bb_db.py — основной рабочий файл БД (пустой шаблон)
# Ничего не меняю без твоей команды. Можешь вставлять свой рабочий код.
# ======================================================================

# bb_db.py
# ALIAS: BB_DB
# Created: 2025-09-18
# VERSION: QR
# Updated: 2025-10-07 08:00:00 (MSK)
# Конфигурация базы данных и универсальный класс DB с авто-переподключением

import hashlib
from datetime import datetime

from typing import Union, Any, Dict, List, Tuple, Optional, Sequence
from bb_sys import *
from mysql.connector import pooling  # NEW POOL LOGIC
import time
import threading
from bb_logger import init_log_router, LOG_ROUTER

# === Canonical field name constants (curated, common only) ===

TBL_CONFIG      = 'ZZ$CONFIG'

FLD_ID          = 'FLD$ID'
FLD_HASH        = 'FLD$HASH'
FLD_TCOD        = 'FLD$TCOD'
FLD_SYMBOL      = 'FLD$SYMBOL'
FLD_TYPE        = 'FLD$TYPE'
FLD_NAME        = 'FLD$NAME'
FLD_TEXT        = 'FLD$TEXT'

FLD_DATE        = 'FLD$DATE'
FLD_DATE_TIME   = 'FLD$DATE_TIME'

FLD_PRICE       = 'FLD$PRICE'
FLD_VOLUME      = 'FLD$VOLUME'
FLD_SUM         = 'FLD$SUM'
FLD_VALUE       = 'FLD$VALUE'

FLD_SOURCE      = 'FLD$SOURCE'
FLD_URL         = 'FLD$URL'
FLD_TITLE       = 'FLD$TITLE'
FLD_TAGS        = 'FLD$TAGS'
FLD_VERSION     = 'FLD$VERSION'


# Public export surface (for `from bb_db import *`)
__all__ = [
    # --- core ---
    'TDatabase', 'Application', 'CloseApplication',
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

# --- TCOD helper -------------------------------------------------------
# Формат: SYMBOL_YYYYMMDD_HHMMSS_TF_VENUE (в МСК)
# Пример: AIAUSDT_20250929_061600_1SEC_BYBIT

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

# --- Менеджер соединений (бывший bbDBManager) ------------------------

class TSession(TSysComponent):
    """Пул соединений MySQL."""

    def __init__(self, Owner: "TApplication"):
        super().__init__(Owner, 'Session')
        self.cfg = DB_CFG
        self.pool = None
        self._keep_alive = False
        self._keep_thread = None

        # ссылка в Application
        Owner.Session = self

        self.log('__init__', 'session created')


    # --- Lifecycle ---------------------------------------------------
    def do_open(self, pool_size: int = 8) -> bool:
        """Создаёт пул соединений и запускает keep-alive."""
        if self.pool is not None:
            self.log('do_open', 'pool already active')
            return True

        #x = 42 / 0


        try:
            self.pool = pooling.MySQLConnectionPool(
                pool_name="bb_pool",
                pool_size=pool_size,
                pool_reset_session=True,
                **self.cfg
            )
            self.log('do_open', f'pool started (size={pool_size})')
            self.keep_alive(60)
            return True
        except Exception as e:
            self.fail('do_open', f'failed: {e}', e)
            return False

    def do_close(self) -> bool:
        """Останавливает keep-alive и уничтожает пул соединений."""
        if not self.pool:
            self.log('do_close', 'no pool to stop')
            return True

        try:
            self.stop_keep_alive()
            self.pool = None
            self.log('do_close', 'pool stopped')
            return True
        except Exception as e:
            self.fail('do_close', f'failed: {e}', e)
            return False

    # --- Connection management --------------------------------------
    def _get_connection(self):
        if not self.pool:
            raise RuntimeError("Session pool not initialized, call open() first")
        return self.pool.get_connection()

    def exec(self, sql: str, params=None) -> int:
        _, rowcount, _ = self._exec_cursor(sql, params, fetch=False)
        return rowcount

    # --- Cursor execution -------------------------------------------
    def _exec_cursor(self, sql: str, params=None, fetch=True):
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

    # --- Keep Alive -------------------------------------------------
    def keep_alive(self, interval: int = 60):
        """Периодически пингует соединение, чтобы не было таймаута."""
        if not self.pool:
            self.log('keep_alive', 'no pool')
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
        self.log('keep_alive', f'started (interval={interval}s)')

    def stop_keep_alive(self):
        if getattr(self, "_keep_alive", False):
            self._keep_alive = False
            if hasattr(self, "_keep_thread"):
                self._keep_thread.join(timeout=5)
            self.log('keep_alive', 'stopped')

# ---------------------------------------------------------------------
#  TDatabase — главный компонент работы с SQL и схемой (Tradition 2025)
# ---------------------------------------------------------------------

class TDatabase(TSysComponent):
    """Главный компонент работы с SQL."""

    def __init__(self, Owner: "TApplication"):
        if not isinstance(Owner, TApplication):
            raise TypeError("TDatabase owner must be TApplication")

        super().__init__(Owner, "Database")

        self.cfg = DB_CFG
        self.Session = Owner.Session
        self.Schema = Owner.Schema   # ← просто ссылка

        self.log("__init__", "database initialized (linked to Schema)")


    # -------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------
    def do_open(self) -> bool:
        """Активирует пул соединений и выполняет тест-запрос."""
        if not self.Session:
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
            self.log("do_open", "connection test passed")
            return True
        except Exception as e:
            self.fail("do_open", f"connection failed: {e}", type(e))
            return False

    def do_close(self) -> bool:
        """Закрывает пул соединений Session."""
        if self.Session:
            try:
                self.Session.close()
                self.log("do_close", "database connection closed")
                return True
            except Exception as e:
                self.fail("do_close", f"failed: {e}", type(e))
                return False
        return True

    # -------------------------------------------------------------
    # Connections
    # -------------------------------------------------------------
    def _get_connection(self):
        """Возвращает connection из пула Session."""
        return self.Session._get_connection()

    # -------------------------------------------------------------
    # Cursor execution
    # -------------------------------------------------------------
    def _exec_cursor(self, sql: str, params=None, fetch: bool = True):
        """Выполняет SQL и возвращает (rows, rowcount, last_id)."""
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

    def _exec_cursor_dict(self, sql: str, params=None, fetch: bool = True):
        """То же самое, но возвращает dict-строки."""
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

    # -------------------------------------------------------------
    # WHERE builder
    # -------------------------------------------------------------
    @staticmethod
    def _where_sql(where: Any) -> Tuple[str, Tuple]:
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
    # -------------------------------------------------------------
    # CRUD methods
    # -------------------------------------------------------------
    def exec(self, sql: str, params: Optional[Tuple] = None) -> int:
        _, rowcount, _ = self._exec_cursor(sql, params)
        return rowcount

    def qr(self, table_or_sql: str | None = None, where=None, data: dict | None = None):
        if table_or_sql is None:
            rows, _, _ = self._exec_cursor_dict('SHOW TABLES', None, True)
            return rows

        s = table_or_sql.strip()
        if (' ' in s) or s.upper().startswith(('SELECT', 'SHOW', 'DESC', 'EXPLAIN')):
            rows, _, _ = self._exec_cursor_dict(s, tuple(where or ()), True)
            return rows

        fields = (data or {}).get('fields', '*')
        order_by = (data or {}).get('order_by')
        limit = (data or {}).get('limit')
        wsql, wparams = self._where_sql(where)
        sql = f'SELECT {fields} FROM `{table_or_sql}`'
        if wsql:
            sql += f' WHERE {wsql}'
        if order_by:
            sql += f' ORDER BY {order_by}'
        if isinstance(limit, int) and limit > 0:
            sql += f' LIMIT {limit}'
        rows, _, _ = self._exec_cursor_dict(sql, wparams, True)
        return rows

    def qr_rw(self, table_or_sql: str | None = None, where=None, data: dict | None = None):
        fields = data.pop('fields') if data and 'fields' in data else '*'
        rows = self.qr(table_or_sql, where, {'fields': fields})
        return rows[0] if rows else None

    def qr_add(self, table_name: str, data: Dict[str, Any]) -> dict:
        if not isinstance(data, dict) or not data:
            raise ValueError('qr_add: data must be non-empty dict')
        cols = list(data.keys())
        vals = [data[k] for k in cols]
        cols_sql = ', '.join(f'`{c}`' for c in cols)
        placeholders = ', '.join(['%s'] * len(vals))
        sql = f'INSERT INTO `{table_name}` ({cols_sql}) VALUES ({placeholders})'
        _, _, lastrowid = self._exec_cursor(sql, tuple(vals), fetch=False)
        if not lastrowid:
            return {}
        return self.qr_rw(table_name, {FLD_ID: int(lastrowid)}) or {}

    def qr_update(self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]) -> dict:
        if not where or not data:
            raise ValueError('qr_update: both WHERE and DATA required')
        set_sql = ', '.join(f'`{k}`=%s' for k in data.keys())
        wsql, wparams = self._where_sql(where)
        sql = f'UPDATE `{table_name}` SET {set_sql} WHERE {wsql}'
        params = list(data.values()) + list(wparams)
        self._exec_cursor(sql, tuple(params), fetch=False)
        return self.qr_rw(table_name, where) or {}

    def qr_delete(self, table_name: str, where: Dict[str, Any]) -> dict:
        row = self.qr_rw(table_name, where)
        if not row:
            return {}
        wsql, wparams = self._where_sql(where)
        sql = f'DELETE FROM `{table_name}` WHERE {wsql}'
        self._exec_cursor(sql, tuple(wparams), fetch=False)
        return row

    def qr_foi(self, table_name: str, where: dict, data: dict) -> dict:
        row = self.qr_rw(table_name, where)
        return row if row else self.qr_add(table_name, {**where, **data})

    def qr_fou(self, table_name: str, where: dict, data: dict) -> dict:
        row = self.qr_rw(table_name, where)
        if row:
            result = self.qr_update(table_name, where, data)
            return result or self.qr_rw(table_name, where) or {}
        return self.qr_add(table_name, {**where, **data})

    def qr_max(self, table_name: str, field_name: str, where=None):
        row = self.qr_rw(table_name, where, {'fields': f'MAX(`{field_name}`) AS m', 'limit': 1})
        return row.get('m') if row and row.get('m') is not None else None

    # -------------------------------------------------------------
    # HASH helpers
    # -------------------------------------------------------------
    def mk_hash(self, *parts: Any) -> str:
        base = "|".join([(str(p if p is not None else "").strip()) for p in parts])
        return hashlib.md5(base.encode("utf-8")).hexdigest()

    def mk_row_hash(self, row: Dict[str, Any], fields: Sequence[str]) -> str:
        values = [str(row.get(f, "") if row.get(f, "") is not None else "").strip() for f in fields]
        return hashlib.md5("|".join(values).encode("utf-8")).hexdigest()


class TConfig(TSysComponent):
    """Компонент конфигурации проекта — управляет ENV и таблицей ZZ$CONFIG."""

    def __init__(self, Owner: "TApplication"):
        if not isinstance(Owner, TApplication):
            raise TypeError("TConfig owner must be TApplication")

        super().__init__(Owner, 'Config')
        self.table = TBL_CONFIG
        self.env: dict[str, str] = {}

        # ссылка в Application
        Owner.Config = self
        self.log('__init__', 'config initialized')

    # ================================================================
    # === Универсальная установка значения (ENV + DB)
    # ================================================================
    def do_set(self, name: str, value: str, text: str = '', type_: str = 'AUTO') -> dict:
        """Базовая функция записи значения в ENV и таблицу конфигурации."""
        if not name:
            self.fail('do_set', 'name required', ValueError)
            return {}

        self.env[name] = str(value)
        record = {
            FLD_NAME: name,
            FLD_VALUE: str(value),
            FLD_TYPE: type_,
            FLD_TEXT: text or '',
        }

        try:
            from bb_db import qr_fou
            r = qr_fou(self.table, {FLD_NAME: name}, record)
            self.log('do_set', f'{name}={value}')
            return r
        except Exception as e:
            self.fail('do_set', f'error: {e}', e)
            return {}

    # ================================================================
    # === Основные методы доступа
    # ================================================================
    def get(self, name: str, default: str = '') -> str:
        """Возвращает значение параметра (ENV или default, при отсутствии — добавляет в таблицу)."""
        if not name:
            return ''

        val = self.env.get(name)
        if val is not None:
            return val

        # значение отсутствует — создаём его и сохраняем через do_set()
        self.do_set(name, default, text='auto-created by get()')
        return str(default)

    def set(self, name: str, value: str, text: str = None, type_: str = None) -> dict:
        """Публичный метод обновления значения."""
        return self.do_set(name, value, text=text or '', type_=type_ or 'MANUAL')

    # ================================================================
    # === Типизированные геттеры
    # ================================================================
    def get_int(self, name: str, default: int = 0) -> int:
        try:
            return int(self.get(name, default))
        except Exception:
            self.do_set(name, default)
            return int(default)

    def get_float(self, name: str, default: float = 0.0) -> float:
        try:
            return float(self.get(name, default))
        except Exception:
            self.do_set(name, default)
            return float(default)

    def get_bool(self, name: str, default: bool = False) -> bool:
        v = str(self.get(name, str(int(default)))).strip().lower()
        if v in ('', '0', 'false', 'off', 'none', 'null'):
            return False
        try:
            return bool(int(v))
        except Exception:
            return True

# ---------------------------------------------------------------------
#  TSchema — подсистема описания структуры БД (Stage 1 / PPS Doctrine)
# ---------------------------------------------------------------------

class TSchema(TSysComponent):
    """Системный компонент: структура таблиц, introspection, constants."""

    def __init__(self, Owner: "TApplication"):
        if not isinstance(Owner, TApplication):
            raise TypeError("TSchema owner must be TApplication")
        super().__init__(Owner, "Schema")
        self.tables: dict[str, dict] = {}
        # добавлено для корректного закрытия и стейтов:
        self.fields: dict[str, dict] = {}
        self.indices: dict[str, dict] = {}
        self.constants: dict[str, Any] = {}
        self.initialized: bool = False
        self.last_loaded: Optional[datetime] = None
        Owner.Schema = self

        self.log("__init__", "schema component created")


    # -------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------
    def do_open(self) -> bool:

        self.allow_prefixes = explode(';', key("SCHEMA_ALLOW_PREFIXES", "TBL$,DOC$,REF$,SYS$"))
        self.allow_names    = explode(';', key("SCHEMA_ALLOW_NAMES", ""))
        self.deny_prefixes  = explode(';', key("SCHEMA_DENY_PREFIXES", "TMP$,ARCH$,DEV$"))
        self.deny_names     = explode(';', key("SCHEMA_DENY_NAMES", ""))

        # === 2. Загружаем структуру таблиц ===
        self._load_tables()
        self.log('do_open', f'schema loaded: {len(self.tables)} tables')

        return True

    def do_close(self) -> bool:
        """Очищает внутренние структуры и состояние."""
        self.tables.clear()
        self.fields.clear()
        self.indices.clear()
        self.constants.clear()
        self.initialized = False
        self.last_loaded = None
        self.log("do_close", "schema cleared")
        return True

    # -------------------------------------------------------------
    # Заглушки под будущую реализацию (Stage 2)
    # -------------------------------------------------------------
    # ==========================================================
    def _load_tables(self) -> dict[str, dict]:
        """Загружает список таблиц из базы, фильтрует и сохраняет результат в self.tables."""
        from bb_db import qr

        # --- Получаем все таблицы ---
        rows = qr("SHOW TABLES")
        all_tables = [list(row.values())[0] for row in rows]
        self.log('_load_tables', f'scanned {len(all_tables)} tables')

        # --- Фильтруем по allow/deny ---
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

        # --- Сохраняем результат ---
        self.tables = {name: {} for name in filtered}
        self.log('_load_tables', f'allowed {len(filtered)} of {len(all_tables)}')
        return self.tables

    def _register_constants(self):
        """Формирует и регистрирует глобальные константы."""
        # placeholder — позже добавится builtins.setattr()
        self.log("_register_constants", "stage 1 stub (const builder)")

# --- Application ---

def Application() -> TApplication:
    """Создаёт и инициализирует приложение Tradition Framework."""
    init_log_router()
    if LOG_ROUTER:
        print("🌈 [Rich] LogRouter initialized — multi-window console active", flush=True)
    else:
        print("🪶 [Fallback] Plain console logger active", flush=True)

    app = TApplication.app()

    if not getattr(app, "Database", None):
        # --- создаём основные системные сущности ---
        app.Session = TSession(app)
        app.Database = TDatabase(app)
        app.Config = TConfig(app)
        app.Schema = TSchema(app)       # ← теперь Schema принадлежит Application

        app.log("Application", "core components created (Session, Database, Config, Schema)")

        #try:
            # === Закон Tradition: четыре затвора ===
        app.Session.open()
        app.Database.open()
        app.Config.open()
        app.Schema.open()

        app.log("Application", "Config & Schema loaded, database connected")
        #except Exception as e:
            #app.fail("Application", f"init error: {e}")

    app.log("Application", "log center initialized", window=1)
    return app

def CloseApplication():
    """Завершает работу приложения: красиво, с чувством и немного иронии."""
    app = TApplication._instance
    if app is None:
        return
    try:
        if hasattr(app, "Session"):
            app.Session.close()
        if hasattr(app, "Components"):
            for name in list(app.Components.keys()):
                app.log('CloseApplication', f'releasing {name}')
            app.Components.clear()
        app.log('CloseApplication', 'application terminated successfully')
    except Exception as e:
        print(f"[Application] close warning: {e}")
    finally:
        TApplication._instance = None
        print("\n🎬  The End — HappyEnd edition 🌅\n")

# === Фасадные функции (тонкие обёртки) ===

def qr_add(table: str, data: Dict[str, Any]):
    """Добавляет строку в таблицу и возвращает dict вставленной записи."""
    return Application().Database.qr_add(table, data)

def qr_update(table: str, where: Any, data: Dict[str, Any]):
    """Обновляет строки и возвращает dict обновлённой записи (если есть)."""
    return Application().Database.qr_update(table, where, data)

def qr_delete(table: str, where: Any, data: Optional[Dict[str, Any]] = None):
    """Удаляет строки и возвращает количество удалённых (int)."""
    limit = None
    if isinstance(data, dict) and isinstance(data.get("limit"), int):
        limit = data["limit"]
    return Application().Database.qr_delete(table, where)

def qr_foi(table: str, where: Any, data: Dict[str, Any]):
    """Find-Or-Insert — возвращает dict строки (всегда свежей)."""
    return Application().Database.qr_foi(table, where, data)

def qr_fou(table: str, where: dict, data: dict):
    """Find-Or-Update — возвращает dict строки."""
    return Application().Database.qr_fou(table, where, data)

def qr_max(table_name: str, field_name: str, where=None):
    """Возвращает значение MAX(field_name) — примитив, не dict."""
    return Application().Database.qr_max(table_name, field_name, where)

def qr(table_or_sql: str | None = None, where=None, data: dict | None = None):
    """Универсальный запрос SELECT / SHOW."""
    return Application().Database.qr(table_or_sql, where, data)

def qr_rw(table_or_sql: str | None = None, where=None, data: dict | None = None):
    """Возвращает одну строку (row) по условию WHERE."""
    return Application().Database.qr_rw(table_or_sql, where, data)

def exec(sql: str, params: Optional[Tuple] = None):
    """Выполняет SQL-запрос без выборки (INSERT/UPDATE/DELETE)."""
    return Application().Database.exec(sql, params)

# --- HASH facade wrappers ---

def mk_hash(*parts: Any) -> str:
    """Возвращает MD5-хэш строки из частей."""
    return Application().Database.mk_hash(*parts)

def mk_row_hash(row: Dict[str, Any], fields: Sequence[str]) -> str:
    """Хэширует набор полей строки (по значениям)."""
    return Application().Database.mk_row_hash(row, fields)

# === CONFIG FACADE (COMPAT LAYER) ===

def key(name: str | None, default: str = '') -> str | None:
    """Возвращает значение параметра (ENV / ZZ$CONFIG)."""
    return Application().Config.get(name, default)

def set_key(name: str, value: Any, text: str = None, type_: str = None) -> dict:
    """Обновляет параметр конфигурации (ENV / ZZ$CONFIG)."""
    return Application().Config.set(name, value, text=text or '', type_=type_ or 'MANUAL')

def key_int(name: str, default: int = 0) -> int:
    """Возвращает параметр как int."""
    return Application().Config.get_int(name, default)

def key_float(name: str, default: float = 0.0) -> float:
    """Возвращает параметр как float."""
    return Application().Config.get_float(name, default)

def key_bool(name: str, default: bool = False) -> bool:
    """Возвращает параметр как bool."""
    return Application().Config.get_bool(name, default)
# =====================================================================
# bb_db.py 🜂 The End — See You Next Session 2025 ⚙️  768
# =====================================================================
