#!/usr/bin/env python3
"""
Logo Agent - Railway + Pollinations.ai
Бот для генерации логотипов по ТЗ
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
    Генерирует URL картинки через Pollinations.ai
    
    Ponytail: одна строка, простой GET, без токенов
    """
    encoded_prompt = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&model=flux"
    return url

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и базовая инструкция"""
    await update.message.reply_text(
        "🎨 Logo Agent активен\n\n"
        "Отправь: /logo бренд=Название ценность=скорость\n\n"
        "Пример:\n"
        "/logo бренд=СеверныйПоток ценность=надёжность"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь и примеры использования"""
    await update.message.reply_text(
        "📋 Доступные команды:\n\n"
        "/start - перезапуск бота\n"
        "/logo [ТЗ] - генерация логотипа\n"
        "/help - эта справка\n\n"
        "Формат ТЗ:\n"
        "бренд=Название\n"
        "ценность=доверие|скорость|статус|забота|инновации\n"
        "аудитория=кто клиент\n"
        "отрасль=финтех|edtech|медицина|ритейл\n\n"
        "Пример:\n"
        "/logo бренд=CoffeeFlow ценность=скорость отрасль=кофейни"
    )

async def logo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /logo бренд=Название ценность=скорость
    Генерирует 4 концепции логотипа
    """
    text = update.message.text.replace("/logo", "").strip()
    
    if not text:
        await update.message.reply_text(
            "Отправь ТЗ в формате:\n"
            "/logo бренд=Название ценность=скорость\n\n"
            "Нажми /help для примеров"
        )
        return
    
    # Отправляем индикатор работы
    status_msg = await update.message.reply_text("🎨 Генерирую 4 концепции...")
    
    try:
        # 4 концепции с разными подходами
        concepts = [
            {
                "name": "Symbol-led (символ)",
                "prompt": f"minimal vector logo symbol for {text}, clean geometric shape, black and white, flat design, centered, professional brand identity"
            },
            {
                "name": "Typography-led (типографика)",
                "prompt": f"modern typography logo wordmark for {text}, custom letterforms, precise kerning, elegant spacing, minimalist design"
            },
            {
                "name": "Luxury Minimal (премиум)",
                "prompt": f"luxury minimalist logo for {text}, premium aesthetic, gold accent, sophisticated geometry, high-end brand identity"
            },
            {
                "name": "Competitive Edge (отличие)",
                "prompt": f"unique distinctive logo for {text}, abstract innovative shape, professional, memorable, stands out from competitors"
            }
        ]
        
        # Удаляем статусное сообщение
        await status_msg.delete()
        
        # Генерируем и отправляем каждую концепцию
        for i, concept in enumerate(concepts, 1):
            url = generate_logo_pollinations(concept["prompt"])
            
            caption = (
                f"**Вариант {i}: {concept['name']}**\n\n"
                f"Prompt: {concept['prompt'][:100]}...\n\n"
                f"ТЗ: {text[:50]}{'...' if len(text) > 50 else ''}"
            )
            
            await update.message.reply_photo(
                photo=url,
                caption=caption,
                parse_mode='Markdown'
            )
        
        # Финальное сообщение с философией
        await update.message.reply_text(
            "✅ 4 концепции сгенерированы\n\n"
            "📐 Философия:\n"
            "• Symbol-led: метафора бренда через знак\n"
            "• Typography: узнаваемость через шрифт\n"
            "• Luxury: премиальность через сдержанность\n"
            "• Competitive Edge: отличие от клише\n\n"
            "Выбери направление для детальной проработки"
        )
        
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await update.message.reply_text(
            "❌ Ошибка генерации. Попробуй позже или упрости ТЗ."
        )

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен в переменных окружения")
        return
    
    logger.info("Инициализация Logo Agent...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("logo", logo_command))
    
    logger.info("Бот запущен на Railway")
    
    # Запускаем polling (для Railway polling проще чем webhook)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
