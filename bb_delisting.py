# bb_delisting.py — оповещения о делистингах Bybit → таблица ZZ$DELISTING
# CHANGELOG (append-only):
# 2025-10-07 13:45 MSK  — -> —   (инициализация учёта правок)
# 2025-10-07 14:25 MSK  — QR refactor: local DB() → qr_foi/tcod/mk_hash; imports упрощены; учёт добавлений через pre-check HASH
# 2025-10-07 15:05 MSK  — Fix: TCOD=UNIQUE, HASH=index; вставка по каждому символу; pre-check по TCOD, проверка существования по HASH (для инфо)

#
# ✔ Получаем анонсы через REST v5 /v5/announcements/index
# ✔ Фильтруем по тегу «Delistings» и/или по слову «Delisting» в заголовке
# ✔ Парсим символы из заголовка (XXXUSDT, XXX/USDT) и тип рынка (PERP/SPOT)
# ✔ Пишем по одной строке на каждый символ в ZZ$DELISTING (upsert по HASH)
# ✔ Совместимо с Python 3.9, без внешних зависимостей

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from bb_db import *  # импорт по белому списку (__all__) — короче и чище
from bb_vars import *

def _detect_market(title: str, tags: List[str]) -> str:
    t = title.lower()
    tagset = {str(x).lower() for x in (tags or [])}
    if "perpetual" in t or "contract" in t:
        return PERP
    if "spot" in t or "spot" in tagset:
        return "SPOT"
    return "UNKNOWN"


def _symbols_from_title(title: str) -> List[str]:
    out = set()
    for m in USDT_PAIR_RE.findall(title):
        out.add(f"{m}USDT")
    for m in USDT_SLASH_RE.findall(title):
        out.add(f"{m}USDT")
    # иногда в заголовке просто перечисление тикеров без "/USDT",
    # такие случаи пропустим на первом этапе (иначе высокий риск ложных срабатываний)
    return sorted(out)


def _http_get(url: str, params: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    req = urllib.request.Request(full, headers={
        "User-Agent": "Mozilla/5.0 (compatible; BBScanner/1.0)"
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))



# --- основная логика ---

def _max_date_str() -> Optional[str]:
    """
    MAX(FLD$DATE) как 'YYYY-MM-DD' или None, если таблица пуста.
    """
    v = qr_max('ZZ$DELISTING', FLD_DATE, {FLD_SOURCE: BYBIT})
    return str(v) if v else None



def get_delistings_since_date(limit: int = 50, max_pages: int = 100) -> List[Dict[str, Any]]:
    """
    Если таблица пуста -> грузим всё (до max_pages).
    Если есть last_date -> берём все элементы, у кого дата(MSK) >= last_date (включительно).
    """
    last_date = _max_date_str()  # 'YYYY-MM-DD' или None
    out: List[Dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        batch, raw_len = get_delistings(page=page, limit=limit)
        print(f"[delisting] page={page} raw={raw_len} kept={len(batch)}")
        if not batch:
            break

        if last_date is None:
            out.extend(batch)
            if raw_len < limit:
                break
            continue

        older_seen = False
        for it in batch:
            pms = int(it.get("publishTime") or it.get("dateTimestamp") or 0)
            dt_msk = datetime.fromtimestamp(pms/1000, tz=MSK).strftime("%Y-%m-%d")
            if dt_msk >= last_date:        # ВКЛЮЧИТЕЛЬНО по дате!
                out.append(it)
            else:
                older_seen = True          # дальше по страницам только старее

        if older_seen or raw_len < limit:
            break
    out.sort(key=lambda it: int(it.get("publishTime") or it.get("dateTimestamp") or 0))
    return out



def get_delistings(page: int = 1, limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
    params = {
        "locale": ANN_LOCALE,
        "page": page,
        "limit": limit,
    }
    data = _http_get(ANN_URL, params)

    res = data.get("result") or {}
    # Бывают разные контейнеры со списком:
    items = (
            res.get("list")
            or res.get("items")
            or res.get("rows")
            or res.get("data")
            or []
    )
    raw_len = len(items)

    rx = re.compile(r"\b(delist\w*|remov\w*|terminat\w*)", re.I)
    out: List[Dict[str, Any]] = []

    for it in items:
        title = str(it.get("title") or "")
        raw_tags = it.get("tags") or []

        # Теги бывают строками или словарями — нормализуем в строки
        tags: List[str] = []
        for t in raw_tags:
            if isinstance(t, dict):
                tags.append(str(t.get("title") or t.get("name") or t.get("tag") or ""))
            else:
                tags.append(str(t))

        tag_text = " ".join(tags)
        if rx.search(title) or rx.search(tag_text):
            out.append(it)

    return out, raw_len


def store_delistings(items: List[Dict[str, Any]]) -> int:
    """Парсит объявления и складывает их в ZZ$DELISTING. Возвращает кол-во добавленных строк."""
    added = 0
    for it in items:
        title = str(it.get("title") or "").strip()
        url = str(it.get("url") or "").strip()
        tags = it.get("tags") or []
        publish_ms = int(it.get("publishTime") or it.get("dateTimestamp") or 0)

        if publish_ms <= 0:
            publish_ms = int(time.time() * 1000)
        h = mk_hash(title, url, publish_ms)
        pub_dt_msk = datetime.fromtimestamp(publish_ms / 1000.0, tz=MSK).strftime("%Y-%m-%d %H:%M:%S")
        pub_date = pub_dt_msk[:10]  # 'YYYY-MM-DD'
        market = _detect_market(title, tags)
        symbols = _symbols_from_title(title)

        # info-only: есть ли уже такая новость в системе (по HASH, не влияет на вставку по символам)
        rw = qr_rw('ZZ$DELISTING', where={FLD_HASH: h})
        _hash_seen = bool(rw)

        def _upsert_one(sym: str) -> bool:
            tc = mk_tcod(sym, publish_ms, 'ANN', BYBIT)
            # pre-check по TCOD (UNIQUE) — чтобы корректно посчитать added и не ловить дубликаты
            rw = qr_rw('ZZ$DELISTING', where={FLD_TCOD: tc})
            if bool(rw):
                return False
            rw = {
                FLD_SYMBOL: '' if sym == 'ALL' else sym,
                'FLD$MARKET': market,
                FLD_TITLE: title[:250],
                FLD_URL: url[:250],
                FLD_TAGS: ",".join(tags)[:250],
                'FLD$RAW_JSON': json.dumps(it, ensure_ascii=False),
                FLD_TCOD: tc,
                FLD_HASH: h,
                FLD_SOURCE: BYBIT,
                FLD_DATE_TIME: pub_dt_msk,  # ← новое имя поля
                FLD_DATE: pub_date,  # ← новая дата-дневка
            }
            # вставка по уникальному TCOD; HASH — просто индекс (не уникальный)
            qr_foi('ZZ$DELISTING', {FLD_TCOD: tc}, rw)
            return True

        if not symbols:
            if _upsert_one('ALL'):
                added += 1
            continue

        for sym in symbols:
            if _upsert_one(sym):
                added += 1

    return added

def run_once(limit: int = 50, max_pages: int = 50) -> int:
    items = get_delistings_since_date(limit=limit, max_pages=max_pages)
    log(f"[delisting] loaded={len(items)}")
    return store_delistings(items)

if __name__ == "__main__":
    n = run_once(limit=50)
    log(f"[delisting] inserted: {n}")

