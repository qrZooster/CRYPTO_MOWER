# bb_tg.py
# ALIAS: BB_TG
# Created: 2025-09-18
# Модуль для работы с Telegram

import os
import asyncio
from telegram import Bot

# --- Конфигурация Telegram ---
TG_TOKEN = os.getenv("TG_TOKEN", "7640786990:AAHFDfJy0iqwhxaO_nCLk-RCJpETH_7Fux8")
TG_USER_ID = int(os.getenv("TG_USER_ID", 694169894))

async def _send_telegram_async(bot, chat_id, msg):
    try:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        print("Telegram error:", e)

def send_telegram(msg):
    tg_bot = init_bot()
    if not tg_bot:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # цикла нет — запускаем новый
        asyncio.run(_send_telegram_async(tg_bot, TG_USER_ID, msg))
    else:
        # цикл есть — создаём задачу и она будет корректно awaited
        loop.create_task(_send_telegram_async(tg_bot, TG_USER_ID, msg))

# Утилита для инициализации бота
def init_bot():
    return Bot(TG_TOKEN) if TG_TOKEN else None