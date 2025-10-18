# 🧭 bb_db.md — Архитектура системы QR()

**Версия:** QR (2025-10-07)  
**Файл:** `bb_db.py`  
**Назначение:** Центральный модуль базы данных Tradition QR Framework  
**Авторство:** Canonical Build System (Tradition-2025)

---

## 🏗 Общий обзор

`bb_db.py` — ядро подсистемы данных QR-архитектуры.  
Он объединяет управление соединениями, CRUD-операции, конфигурацию окружения и introspection схемы в единый унифицированный модуль.

Основные компоненты образуют «четыре затвора»:

> **Session → Database → Config → Schema**

Все управляются через объект `TApplication`, который создаёт и связывает эти компоненты в единую систему.

---

## ⚙️ Архитектурные роли компонентов

| Компонент | Класс | Назначение |
|------------|-------|------------|
| **Session** | `TSession` | Управление пулом соединений MySQL и keep-alive |
| **Database** | `TDatabase` | Универсальный SQL-интерфейс и QR API |
| **Config** | `TConfig` | Управление параметрами окружения и таблицей `ZZ$CONFIG` |
| **Schema** | `TSchema` | Introspection структуры БД, фильтры, доктринная логика |
| **Application** | `TApplication` | Контейнер и точка инициализации компонентов |
| **Facade API** | `qr_*`, `exec`, `key_*`, `mk_*` | Упрощённый интерфейс к базе и конфигурации |

---

## 🧩 Canonical constants

Единый набор имён полей, принятый во всех таблицах и системных структурах:

```
FLD_ID, FLD_HASH, FLD_TCOD, FLD_SYMBOL,
FLD_TYPE, FLD_NAME, FLD_TEXT,
FLD_DATE, FLD_DATE_TIME,
FLD_PRICE, FLD_VOLUME, FLD_SUM, FLD_VALUE,
FLD_SOURCE, FLD_URL, FLD_TITLE, FLD_TAGS, FLD_VERSION
```

---

## 🧠 Временные хелперы

### `_to_dt_msk(ts)`
Приводит время `ts` (в секундах, миллисекундах или `datetime`) к timezone-aware `datetime` в МСК.  
Используется для унификации временных меток и TCOD-генерации.

### `mk_tcod(symbol, ts, tf, venue)`
Создаёт универсальный временной код:
```
SYMBOL_YYYYMMDD_HHMMSS[_mmm]_TF_VENUE
```
Пример:  
`AIAUSDT_20250929_061600_1SEC_BYBIT`

---

## 🔩 Класс `TSession` — менеджер соединений

**Роль:** управляет пулом MySQL соединений и поддерживает их активность.

### Основные методы:
- `do_open(pool_size=8)` — создаёт пул соединений.  
- `do_close()` — завершает пул и keep-alive.  
- `_get_connection()` — выдаёт соединение из пула.  
- `exec(sql, params)` — выполняет запрос без выборки.  
- `_exec_cursor()` — универсальный cursor-executor с безопасным закрытием.  
- `keep_alive(interval)` — запускает поток-пинг соединений.  
- `stop_keep_alive()` — завершает keep-alive цикл.

**Особенность:** keep-alive обеспечивает постоянное соединение с MySQL даже при долгих простоях.

---

## 🧱 Класс `TDatabase` — SQL-фасад и QR-API

Основной интерфейс для всех SQL-операций и логики CRUD.

### Основные методы
| Метод | Назначение |
|--------|-------------|
| `do_open()` | Проверка соединения (`SELECT 1`) и активация Session |
| `do_close()` | Закрытие соединений |
| `_exec_cursor()` | Выполнение SQL и возврат данных |
| `_exec_cursor_dict()` | То же, но с `dictionary=True` |
| `_where_sql()` | Построение SQL-условий (int, str, dict, list, set) |

---

### 📦 QR API (Query Runtime)

Простые и мощные CRUD-операции в духе ORM-минимализма:

| Метод | Описание | Возврат |
|--------|-----------|---------|
| `qr()` | Универсальный SELECT/SHOW/EXPLAIN | Список dict-строк |
| `qr_rw()` | Получает одну запись | Dict |
| `qr_add()` | Добавляет запись | Dict вставленной строки |
| `qr_update()` | Обновляет запись по WHERE | Dict обновлённой строки |
| `qr_delete()` | Удаляет запись | Dict удалённой |
| `qr_foi()` | Find-Or-Insert | Dict |
| `qr_fou()` | Find-Or-Update | Dict |
| `qr_max()` | MAX(field) | scalar |

---

### 🔐 Hash Utilities
- `mk_hash(*parts)` — MD5 от строковых частей (универсальный идентификатор).  
- `mk_row_hash(row, fields)` — хэш от выбранных полей строки (контроль версий и целостности).

---

## ⚙️ Класс `TConfig` — управление окружением и конфигурацией

**Роль:** синхронизирует внутренний ENV и таблицу `ZZ$CONFIG`.

| Метод | Назначение |
|--------|-------------|
| `do_set(name, value, text, type_)` | Записывает значение в ENV и DB |
| `get(name, default)` | Возвращает значение или создаёт default |
| `set(name, value, text, type_)` | Публичное обновление параметра |
| `get_int`, `get_float`, `get_bool` | Типизированные геттеры |

💡 Использует `qr_fou` для гарантированной консистентности (find-or-update).

---

## 🧬 Класс `TSchema` — introspection базы

**Роль:** описывает структуру таблиц и констант.

Этап реализации: **Stage 1 (PPS Doctrine).**

### Основные методы:
- `do_open()` — инициализация фильтров (allow/deny-prefixes) и загрузка таблиц.  
- `do_close()` — очистка структуры.  
- `_load_tables()` — извлечение списка таблиц и фильтрация.  
- `_register_constants()` — (stub) автогенерация констант по схемам.

---

## 🚀 Application lifecycle

### `Application()`
Создаёт экземпляр `TApplication`, инициализирует логгер и четыре ядра:

```
TSession → TDatabase → TConfig → TSchema
```

Выводит статус подключения и готовности.

### `CloseApplication()`
Закрывает соединения, очищает компоненты и выводит:
> 🎬 The End — HappyEnd edition 🌅

---

## 🪄 Фасадные функции (Public API)

| Функция | Назначение |
|----------|-------------|
| `qr()`, `qr_rw()` | Универсальный SELECT / FetchOne |
| `qr_add()`, `qr_update()`, `qr_delete()` | CRUD-операции |
| `qr_foi()`, `qr_fou()` | Find-Or-Insert / Find-Or-Update |
| `qr_max()` | Агрегация (MAX) |
| `exec()` | Выполнение произвольного SQL |
| `mk_hash()`, `mk_row_hash()` | Хэш-помощники |
| `key()`, `set_key()` | Работа с конфигурацией |
| `key_int()`, `key_float()`, `key_bool()` | Типизированные обёртки |

---

## 🔁 Архитектурный цикл QR

```
┌────────────┐
│ Application│
└──────┬─────┘
       ▼
┌────────────┐
│  TSession  │  ← пул соединений, keep-alive
└──────┬─────┘
       ▼
┌────────────┐
│ TDatabase  │  ← CRUD / QR / hash
└──────┬─────┘
       ▼
┌────────────┐
│  TConfig   │  ← ENV + ZZ$CONFIG
└──────┬─────┘
       ▼
┌────────────┐
│  TSchema   │  ← introspection
└────────────┘
```

---

## ✨ Ключевые преимущества

✅ Автоматическая инициализация приложения  
✅ Connection Pooling + Keep-Alive  
✅ Универсальный QR API  
✅ Изоляция от SQL-инъекций  
✅ Контроль целостности через хэши  
✅ Централизованная конфигурация  
✅ Расширяемая схема (Doctrine-style)  

---

## 🧾 Резюме

`bb_db.py` — это **сердце QR-системы**, объединяющее подключение, CRUD, конфигурацию и introspection в один согласованный каркас.

> 💬 *“QR — это не просто Query Runtime. Это Quick Reality — быстрая реальность данных.”*
