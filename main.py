#!/usr/bin/env python3
"""
Logo Agent - Railway + Pollinations.ai
"""

import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_logo_pollinations(prompt: str) -> str:
    """
    Генерирует картинку через Pollinations.ai
    
    Ponytail: одна строка, простой GET, без токенов
    """
    # URL-кодируем промпт
    encoded_prompt = requests.utils.quote(prompt)
    
    # Pollinations.ai URL
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&model=flux"
    
    return url  # Возвращаем URL, не скачиваем картинку сразу

async def logo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /logo бренд=Название ценность=скорость
    """
    text = update.message.text.replace("/logo", "").strip()
    
    if not text:
        await update.message.reply_text(
            "Отправь ТЗ: /logo бренд=Название ценность=скорость"
        )
        return
    
    # 4 концепции с разными промптами
    concepts = [
        ("Symbol-led", "minimal vector logo, mountain symbol, black and white, flat design"),
        ("Typography-led", "modern typography logo, custom letterforms, clean geometry"),
        ("Luxury Minimal", "premium minimalist logo, gold accent, elegant spacing"),
        ("Competitive Edge", "unique abstract logo, distinctive shape, professional")
    ]
    
    # Отправляем 4 картинки через URL (Railway не хранит файлы)
    for name, prompt in concepts:
        url = generate_logo_pollinations(prompt)
        await update.message.reply_photo(
            photo=url,
            caption=f"Концепция: {name}\n{prompt}"
        )

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("logo", logo_command))
    
    logger.info("Бот запущен на Railway")
    app.run_polling()

if __name__ == "__main__":
    main()
