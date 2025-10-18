# bb_vars.py
# ALIAS: BB_VARS
# Created: 2025-09-18

import os
import re
import datetime as dt

def _s(v):
    return '' if v is None else str(v)

def _set_key(name: str, value: str) -> bool:
    if not name:
        return False
    os.environ[name] = '' if value is None else _s(value)
    return True

def _key(name: str | None, default: str = '') -> str | None:
    if not name:
        return None
    v = os.environ.get(name)
    if v is not None and v != '':
        return v
    os.environ[name] = str(default)
    return str(default)

# версия проекта/модуля берём через bb_db.v_project/v_module

BYBIT_API_KEY = _key('BYBIT_API_KEY', '')
BYBIT_API_SECRET = _key('BYBIT_API_SECRET', '')

# --- Переключение между боевым и тестовым режимом ---
BYBIT_MODE = _key('BYBIT_MODE', 'prod')  # prod | test

if BYBIT_MODE == 'test':
    BYBIT_WS_PUBLIC_LINEAR = 'wss://stream-testnet.bybit.com/v5/public/linear'
    BYBIT_REST = 'https://api-testnet.bybit.com'
else:
    BYBIT_WS_PUBLIC_LINEAR = 'wss://stream.bybit.com/v5/public/linear'
    BYBIT_REST = 'https://api.bybit.com'

# Часовой пояс Москва (UTC+3)
MSK = dt.timezone(dt.timedelta(hours=3), name='MSK')

DB_CFG = {
    'host'      : _key('DB_HOST', '127.0.0.1'),
    'port'      : int(_key('DB_PORT', '3307')),
    'user'      : _key('DB_USER', 'u267510'),
    'password'  : _key('DB_PASSWORD', '_n2FeRUP.6'),
    'database'  : _key('DB_NAME', 'u267510_tg'),
    'autocommit': True,
    'charset'   : _key('DB_CHARSET', 'utf8mb4'),
}

ANN_URL = 'https://api.bybit.com/v5/announcements/index'
ANN_LOCALE = 'en-US'

# --- утилиты ---
USDT_PAIR_RE = re.compile(r'([A-Z0-9]{1,20})USDT')
USDT_SLASH_RE = re.compile(r'([A-Z0-9]{1,20})/USDT')

BYBIT = 'BYBIT'
PERP = 'PERP'
USDT = 'USDT'
BUY = 'BUY'
SELL = 'SELL'

__all__ = [
    'BBBase', 'get_module',
    '_s', '_set_key', '_key',
    'BYBIT_API_KEY', 'BYBIT_API_SECRET',
    'BYBIT_MODE', 'BYBIT_WS_PUBLIC_LINEAR', 'BYBIT_REST',
    'MSK',
    'DB_CFG',
    'ANN_URL', 'ANN_LOCALE',
    'BYBIT', 'PERP', 'USDT',
    'BUY', 'SELL',
    'USDT_PAIR_RE', 'USDT_SLASH_RE',
]

# ---------------------------------------------------------------------
# BASE CLASS — общий логгер и точка для наследования
# ---------------------------------------------------------------------

from datetime import datetime

class BBBase:
    def __init__(self, name: str = None):
        cname = self.__class__.__name__
        if cname[:2].lower() == 'bb':     # ← ключевой момент
            cname = cname[2:]
        self.name = name if (name is not None and name != '') else cname

    def log(self, function: str, *parts):
        project_symbol = _key('PROJECT_SYMBOL', 'BB')
        project_version = _key('PROJECT_VERSION', '3')
        now = datetime.now().strftime('%H:%M:%S')
        msg = ' '.join(str(p) for p in parts)
        print(f'[{project_symbol}_{project_version}][{now}][{self.name}]{function}(): {msg}', flush=True)

# ---------------------------------------------------------------------
# Модуль верхнего уровня (создаётся в каждом __main__)
# ---------------------------------------------------------------------

class bbModule(BBBase):
    """Контейнер модуля запуска (например, SCAN_8, DELISTING_1, WS_3 и т.п.)."""

    def __init__(self, name: str, version: str = '1'):
        # Формируем имя модуля сразу с версией
        full_name = f'{name}_{version}'
        super().__init__(full_name)
        self.name = full_name
        self.version = version
        self.log('__init__', f'module {name} v{version} started')

    def run(self, *args):
        """Переопределяется потомками или внешним кодом."""
        self.log('run', 'executing main loop...')


def get_module(name: str, version: str | int = 1) -> bbModule:
    """Фабрика для создания модуля верхнего уровня."""
    return bbModule(str(name), str(version))





