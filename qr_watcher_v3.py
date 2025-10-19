# =====================================================================
# qr_watcher_v3.py — Smart START Generator
# created: 2025-10-19
# short description: Умное создание START файлов только при изменениях
# =====================================================================

import os, json, time, hashlib
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# --- Конфигурация ---
PROJECT = "CRYPTO_MOWER"
REPO_URL = "https://raw.githubusercontent.com/qrZooster/CRYPTO_MOWER/main"
START_DIR = Path("start")
MAX_CHUNK_SIZE = 120 * 1024  # 120KB

# --- Управляющие массивы ---
CORE_FILES = [
    "bb_sys.py", "bb_db.py", "bb_controls.py", "bb_events.py",
    "bb_logger.py", "bb_utils.py", "bb_tg.py", "bb_ws.py",
    "_bb_ws.py", "bb_page.py"
]

WORK_FILES = [
    "qr_watcher_v3.py", "bb_scan_9.py", "bb_app_sys_control.py",
    "tst_controls.py"
]


# --- Утилиты ---
def get_file_hash(filepath: Path) -> str:
    return hashlib.md5(filepath.read_bytes()).hexdigest()


def get_project_state_hash() -> str:
    """Вычисляет хэш состояния проекта по отслеживаемым файлам"""
    hashes = []

    # Документация
    for md_file in Path("docs").glob("*.md"):
        hashes.append(f"docs:{md_file.name}:{get_file_hash(md_file)}")

    # Ядро
    for core_file in CORE_FILES:
        path = Path(core_file)
        if path.exists():
            hashes.append(f"core:{core_file}:{get_file_hash(path)}")

    # Рабочие файлы
    for work_file in WORK_FILES:
        path = Path(work_file)
        if path.exists():
            hashes.append(f"work:{work_file}:{get_file_hash(path)}")

    return hashlib.md5("|".join(sorted(hashes)).encode()).hexdigest()


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
        if md_file.name not in ["STRUCTURE.md", "CONTEXT.md"]:  # Исключаем временно
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
    current_hash = get_project_state_hash()
    (START_DIR / "last_state.hash").write_text(current_hash)

    print(f"🎉 Генерация завершена! Всего файлов: {total_files}")


def should_regenerate() -> bool:
    """Проверяет, нужно ли пересоздавать START файлы"""
    state_file = START_DIR / "last_state.hash"

    if not state_file.exists():
        return True

    last_hash = state_file.read_text().strip()
    current_hash = get_project_state_hash()

    return last_hash != current_hash


def main():
    print("🔄 QR Watcher v3 запущен...")

    while True:
        if should_regenerate():
            print("🔄 Обнаружены изменения - пересоздаём START файлы")
            generate_start_files()
        else:
            current_time = datetime.now().strftime("%Y-%m-%d й%H:%M:%S")
            print(f"[{current_time}][qr_watcher: no change]")

        time.sleep(5)


if __name__ == "__main__":
    main()

# =====================================================================
# qr_watcher_v3.py 🜂 The End — Tradition Core 2025 ⚙️
# =====================================================================