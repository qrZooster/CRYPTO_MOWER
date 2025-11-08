# =====================================================================
# qr_watcher_v3.py — Smart START Generator
# created: 2025-10-19
# short description: Умное создание START файлов только при изменениях
# =====================================================================

import os, json, time, hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple

# --- Конфигурация ---
PROJECT = "CRYPTO_MOWER"
REPO_URL = "https://raw.githubusercontent.com/qrZooster/CRYPTO_MOWER/main"
START_DIR = Path("start")
MAX_CHUNK_SIZE = 120 * 1024  # 120KB

# --- Управляющие массивы ---
IGNORE_DIRS = {
    'venv', '.venv', 'env', '__pycache__', '.git', '.idea',
    'log', 'start', 'backups', 'docs', 'build', 'dist'
}
IGNORE_FILES = {'qr_watcher_v3.py'}  # Исключения из авто-обнаружения

CORE_FILES = [
    "bb_sys.py", "bb_application.py", "bb_db.py", "bb_controls.py", "bb_events.py",
    "bb_logger.py", "bb_utils.py", "bb_tg.py", "bb_ws.py",
    "_bb_ws.py", "bb_page.py"
]

WORK_FILES = [
    "qr_watcher_v3.py", "bb_scan_9.py", "bb_app_sys_control.py",
    "del_tst_controls.py"
]

# Хэш конфигурации списков файлов
CONFIG_HASH = hashlib.md5(json.dumps({"core": CORE_FILES, "work": WORK_FILES}).encode()).hexdigest()


def discover_python_files() -> List[Path]:
    """Автоматически находит все .py файлы в проекте"""
    python_files = []

    # Ищем в корне проекта и в поддиректориях
    for py_file in Path('.').rglob('*.py'):
        # Пропускаем игнорируемые директории
        if any(ignore_dir in py_file.parts for ignore_dir in IGNORE_DIRS):
            continue
        # Пропускаем игнорируемые файлы
        if py_file.name in IGNORE_FILES:
            continue
        # Пропускаем файлы уже в CORE_FILES или WORK_FILES
        if py_file.name in CORE_FILES or py_file.name in WORK_FILES:
            continue

        python_files.append(py_file)

    return python_files


last_state_file = START_DIR / "last_state.hash"


# --- Утилиты ---
def get_file_hash(filepath: Path) -> str:
    return hashlib.md5(filepath.read_bytes()).hexdigest()


def get_project_state_hash() -> Tuple[str, Dict[str, str]]:
    """Вычисляет хэш состояния проекта по отслеживаемым файлам"""
    hashes = []
    file_hashes = {}

    # Добавляем хэш конфигурации списков
    current_config_hash = hashlib.md5(json.dumps({"core": CORE_FILES, "work": WORK_FILES}).encode()).hexdigest()
    hashes.append(f"config:{current_config_hash}")

    # Документация
    for md_file in Path("docs").glob("*.md"):
        file_hash = get_file_hash(md_file)
        hashes.append(f"docs:{md_file.name}:{file_hash}")
        file_hashes[str(md_file)] = file_hash

    # Ядро
    for core_file in CORE_FILES:
        path = Path(core_file)
        if path.exists():
            file_hash = get_file_hash(path)
            hashes.append(f"core:{core_file}:{file_hash}")
            file_hashes[str(path)] = file_hash

    # Рабочие файлы
    for work_file in WORK_FILES:
        path = Path(work_file)
        if path.exists():
            file_hash = get_file_hash(path)
            hashes.append(f"work:{work_file}:{file_hash}")
            file_hashes[str(path)] = file_hash

    # Автоматически обнаруженные файлы
    for py_file in discover_python_files():
        file_hash = get_file_hash(py_file)
        hashes.append(f"auto:{py_file.name}:{file_hash}")
        file_hashes[str(py_file)] = file_hash

    project_hash = hashlib.md5("|".join(sorted(hashes)).encode()).hexdigest()
    return project_hash, file_hashes


def cleanup_start_files():
    """Полная очистка директории start"""
    if START_DIR.exists():
        for file in START_DIR.glob("START*.json"):
            file.unlink()
        print(f"🧹 Очищено {len(list(START_DIR.glob('START*.json')))} старых START файлов")
    else:
        START_DIR.mkdir()


def get_file_data(filepath: Path) -> Dict[str, Any]:
    """Собирает данные файла для включения в START"""
    content = filepath.read_text(encoding="utf-8")
    return {
        "name": filepath.name,
        "dir": f"/{filepath.parent.name}" if filepath.parent.name else "/",
        "lines": content.count("\n") + 1,
        "bytes": filepath.stat().st_size,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(filepath.stat().st_mtime)),
        "content": content
    }


def collect_prioritized_files() -> List[Dict[str, Any]]:
    """Собирает файлы в порядке приоритета: docs -> core -> work"""
    files = []

    # 1. Документация (все .md файлы)
    for md_file in Path("docs").glob("*.md"):
        # Включаем ВСЕ .md файлы документации
        files.append(get_file_data(md_file))

    # 2. Ядро (только существующие файлы)
    for core_file in CORE_FILES:
        path = Path(core_file)
        if path.exists():
            files.append(get_file_data(path))

    # 3. Рабочие файлы
    for work_file in WORK_FILES:
        path = Path(work_file)
        if path.exists():
            files.append(get_file_data(path))

    # 4. Автоматически обнаруженные Python файлы
    for py_file in discover_python_files():
        files.append(get_file_data(py_file))

    return files


def create_chunks(files: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Разбивает файлы на чанки не более MAX_CHUNK_SIZE"""
    chunks = []
    current_chunk = []
    current_size = 0

    for file in files:
        file_size = len(json.dumps(file))  # Реальный размер в JSON

        if current_size + file_size > MAX_CHUNK_SIZE and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

        current_chunk.append(file)
        current_size += file_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def generate_start_files():
    """Основная функция генерации START файлов"""
    print("🚀 Начинаем генерацию START файлов...")

    # 1. Очистка
    cleanup_start_files()

    # 2. Сбор файлов
    all_files = collect_prioritized_files()
    print(f"📦 Собрано {len(all_files)} файлов")

    # 3. Чанкование
    chunks = create_chunks(all_files)
    print(f"📚 Создано {len(chunks)} чанков")

    # 4. Генерация файлов
    total_files = 0
    for i, chunk in enumerate(chunks):
        filename = "START.json" if i == 0 else f"START_{i}.json"

        data = {
            "meta": {
                "project": PROJECT,
                "part": filename.replace(".json", ""),
                "command": "/start chat" if i == 0 else None,
                "status": "listening" if i == 0 else "pending",
                "total_parts": len(chunks),
                "loaded_parts": i + 1,
                "files_summary": {
                    "docs": len([f for f in chunk if f["dir"] == "/docs"]),
                    "core": len([f for f in chunk if f["name"] in CORE_FILES]),
                    "work": len([f for f in chunk if f["name"] in WORK_FILES]),
                    "auto": len([f for f in chunk if
                                 f["name"] not in CORE_FILES and f["name"] not in WORK_FILES and f["dir"] != "/docs"]),
                    "total": len(chunk)
                },
                "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            },
            "files": chunk
        }

        # Сохраняем файл
        output_path = START_DIR / filename
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        total_files += len(chunk)
        print(f"✅ Создан {filename} ({len(chunk)} файлов, {output_path.stat().st_size / 1024:.1f} KB)")

    # Сохраняем хэш состояния
    current_hash, current_file_hashes = get_project_state_hash()
    state_data = {
        'project_hash': current_hash,
        'file_hashes': current_file_hashes
    }
    last_state_file.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"🎉 Генерация завершена! Всего файлов: {total_files}")


def should_regenerate() -> Tuple[bool, List[str]]:
    """Проверяет, нужно ли пересоздавать START файлы. Возвращает (need_regenerate, changed_files)"""
    current_hash, current_file_hashes = get_project_state_hash()

    if not last_state_file.exists():
        return True, list(current_file_hashes.keys())

    try:
        # Загружаем предыдущее состояние
        with open(last_state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            last_hash = data.get('project_hash', '')
            last_file_hashes = data.get('file_hashes', {})
    except:
        return True, list(current_file_hashes.keys())

    # Сравниваем хэш проекта
    if last_hash != current_hash:
        # Находим изменённые файлы
        changed_files = []
        for file_path, current_file_hash in current_file_hashes.items():
            last_file_hash = last_file_hashes.get(file_path)
            if last_file_hash != current_file_hash:
                changed_files.append(Path(file_path).name)

        # Также проверяем удалённые файлы
        for file_path in last_file_hashes:
            if file_path not in current_file_hashes:
                changed_files.append(f"{Path(file_path).name} [УДАЛЁН]")

        return True, changed_files

    return False, []


def main():
    print("🔄 QR Watcher v3 запущен...")

    while True:
        need_regenerate, changed_files = should_regenerate()
        if need_regenerate:
            if changed_files:
                print(f"🔄 Обнаружены изменения в файлах: {', '.join(changed_files)}")
            else:
                print("🔄 Обнаружены изменения - пересоздаём START файлы")
            generate_start_files()
        else:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}][qr_watcher: no change]")

        time.sleep(5)


if __name__ == "__main__":
    main()

# =====================================================================
# qr_watcher_v3.py 🜂 The End — Tradition Core 2025 ⚙️
# =====================================================================