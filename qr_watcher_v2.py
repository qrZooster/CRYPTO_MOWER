# =====================================================================
# qr_watcher_v2.py — QR Framework Context Builder
# created: 2025-10-19
# short description: Мониторинг ./docs и ./src, сборка START.json
# =====================================================================

import os, json, time
from pathlib import Path

# --- Настройки проекта ---
PROJECT = "CRYPTO_MOWER"
REPO_URL = "https://raw.githubusercontent.com/qrZooster/CRYPTO_MOWER/main"
DOCS_DIR = Path(__file__).parent / "docs"
SRC_DIR = Path(__file__).parent / "src"
OUTPUT = Path(__file__).parent / "START.json"


# --- Игнорируемые файлы и каталоги ---
IGNORE_LIST = [
    "__pycache__",
    ".venv",
    ".git",
    ".idea",
    "log",
    "START.json",
    "qr_watcher_v2.py",
    "qr_watcher_v3.py",
    "*.log",
    "*.tmp",
    "*.bak",
    "*.db",
    "*.sqlite",
]

# --- Проверка, нужно ли пропустить файл ---
def should_ignore(file: Path) -> bool:
    name = file.name.lower()
    # префиксы del_ и tst_
    if name.startswith("del_") or name.startswith("tst_"):
        return True
    # по шаблону или названию каталога
    for pat in IGNORE_LIST:
        if file.match(pat) or pat in file.parts:
            return True
    return False

# --- Утилита: статистика файла ---
def get_file_stats(file_path: Path):
    text = file_path.read_text(encoding="utf-8")
    lines = text.count("\n") + 1
    bytes_ = file_path.stat().st_size
    updated = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_path.stat().st_mtime)
    )
    return text, lines, bytes_, updated

# --- Утилита: замена относительных ссылок на абсолютные ---
def convert_links(text: str):
    text = text.replace("](./", f"]({REPO_URL}/docs/")
    text = text.replace("](../docs/", f"]({REPO_URL}/docs/")
    text = text.replace("](../src/", f"]({REPO_URL}/src/")
    return text

# --- Основная сборка ---
def build_start_json():
    docs, code = [], []
    total_lines = total_bytes = 0

    # --- Документация ---
    if DOCS_DIR.exists():
        for file in DOCS_DIR.glob("*.md"):
            if should_ignore(file):
                continue
            content, lines, bytes_, updated = get_file_stats(file)
            content = convert_links(content)
            docs.append({
                "name": file.name,
                "dir": f"/docs",
                "lines": lines,
                "bytes": bytes_,
                "updated": updated,
                "content": content
            })
            total_lines += lines
            total_bytes += bytes_

    # --- Код ---
    search_dir = SRC_DIR if SRC_DIR.exists() else Path(__file__).parent
    for file in search_dir.glob("*.py"):
        if should_ignore(file):
            continue
        content, lines, bytes_, updated = get_file_stats(file)
        code.append({
            "name": file.name,
            "dir": f"/src" if SRC_DIR.exists() else "/",
            "lines": lines,
            "bytes": bytes_,
            "updated": updated,
            "content": content
        })
        total_lines += lines
        total_bytes += bytes_

    data = {
        "meta": {
            "project": PROJECT,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files_total": len(docs) + len(code),
            "lines_total": total_lines,
            "bytes_total": total_bytes
        },
        "docs": docs,
        "code": code
    }

    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    mb = total_bytes / 1024 / 1024
    print(f"[QR_Watcher] START.json обновлён ({len(docs)+len(code)} файлов, {mb:.2f} MB, {total_lines} строк)")
    for f in sorted(docs + code, key=lambda x: x["bytes"], reverse=True)[:3]:
        print(f"  • {f['name']:<15} — {f['lines']} строк, {f['bytes']/1024:.1f} KB")
    summarize_by_dir(docs + code)


# --- Мониторинг изменений ---
def watch_dirs():
    prev_state = {}
    def snapshot():
        paths = list(DOCS_DIR.glob("*.md")) + list(SRC_DIR.glob("*.py")) if SRC_DIR.exists() else list(DOCS_DIR.glob("*.md")) + list(Path(__file__).parent.glob("*.py"))
        return {p: p.stat().st_mtime for p in paths}

    prev_state = snapshot()
    build_start_json()
    print("[QR_Watcher] Мониторинг активен...\n")

    while True:
        time.sleep(2)
        current = snapshot()
        if current != prev_state:
            build_start_json()
            prev_state = current

# --- Подсчёт статистики по директориям ---
def summarize_by_dir(filesets):
    stats = {}
    for f in filesets:
        dir_name = f.get("dir", "/")
        if dir_name not in stats:
            stats[dir_name] = {"count": 0, "lines": 0, "bytes": 0}
        stats[dir_name]["count"] += 1
        stats[dir_name]["lines"] += f["lines"]
        stats[dir_name]["bytes"] += f["bytes"]
    print("[QR_Watcher] Статистика по директориям:")
    for k, v in sorted(stats.items()):
        kb = v["bytes"] / 1024
        print(f"  {k:<15} — {v['count']} файлов, {v['lines']} строк, {kb:.1f} KB")


# --- Запуск ---
if __name__ == "__main__":
    print("[QR_Watcher] Запуск QR_Watcher v2...")
    watch_dirs()
# =====================================================================
# 🜂 The End — Tradition 2025 ⚙️
# =====================================================================
