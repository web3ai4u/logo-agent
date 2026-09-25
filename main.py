#!/usr/bin/env python3
"""LogoForge v4: SVG-конструктор. Детерминированная геометрия, предсказуемый результат."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re

from telegram import Update, InputFile
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

import design_skills as ds
import logo_builder

BOT_TOKEN = os.getenv("BOT_TOKEN")

ASK_BRIEF, ASK_FIELDS, CONFIRM = range(3)

FIELDS = ["brand", "value", "audience", "industry", "tone"]
LABELS = {"brand": "Бренд", "value": "Ценность", "audience": "Аудитория",
          "industry": "Отрасль", "tone": "Характер"}
QUESTIONS = {
    "brand": "Название бренда, как оно должно выглядеть на логотипе?",
    "value": "Главная ценность, которую бренд обещает клиенту? (одно слово: надёжность, скорость, статус, забота, инновации…)",
    "audience": "Кто клиент? (одна фраза: «курьеры мегаполисов», «мамы малышей»…)",
    "industry": "Отрасль / ниша? (финтех, кофейни, логистика, medtech…)",
    "tone": "Характер бренда: luxury, minimal, tech, friendly, bold? (одно слово)",
}
_PATTERNS = {
    "brand": r"(?:бренд|brand|название)\s*[:=]\s*([^,\n]+)",
    "value": r"(?:ценность|value)\s*[:=]\s*([^,\n]+)",
    "audience": r"(?:аудитория|audience|клиент)\s*[:=]\s*([^,\n]+)",
    "industry": r"(?:отрасль|industry|ниша|сфера)\s*[:=]\s*([^,\n]+)",
    "tone": r"(?:тон|tone|стиль|style|характер)\s*[:=]\s*([^,\n]+)",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- ТЗ: разбор текста и файлов ----------

def parse_brief(text: str) -> dict:
    found = {}
    for f, pat in _PATTERNS.items():
        m = re.search(pat, text, re.I)
        if m:
            found[f] = m.group(1).strip()[:120]
    if not found and text.strip():
        found["description"] = text.strip()[:400]
    return found


def extract_doc(data: bytes, name: str):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    try:
        if ext in ("txt", "md"):
            return data.decode("utf-8", errors="ignore")
        if ext == "pdf":
            from PyPDF2 import PdfReader
            return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        if ext == "docx":
            from docx import Document
            return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    except Exception as e:
        logger.warning("doc parse failed: %s", e)
    return None


# ---------- диалог ----------

async def flow_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["brief"] = {}
    await update.message.reply_text(
        "🎨 Принимаю задачу.\n\nПришли ТЗ текстом или файлом (PDF / DOCX / TXT).\n"
        "Если ТЗ нет — напиши «вопросы», и я задам 5 коротких сам.\n\n"
        "Или /idea — сгенерирую визуальные концепции через Pollinations.")
    return ASK_BRIEF


async def ask_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    missing = context.user_data.get("missing", [])
    if not missing:
        return await show_brief(update, context)
    await update.message.reply_text(f"❓ Осталось {len(missing)}. {QUESTIONS[missing[0]]}")
    return ASK_FIELDS


async def on_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brief = context.user_data["brief"]
    if update.message.document:
        doc = update.message.document
        f = await doc.get_file()
        bio = io.BytesIO()
        await f.download_to_memory(out=bio)
        text = extract_doc(bio.getvalue(), doc.file_name or "file.txt")
        if text is None:
            await update.message.reply_text("Формат не читается. Пришли TXT, PDF, DOCX или текст.")
            return ASK_BRIEF
        brief.update(parse_brief(text))
    else:
        t = update.message.text.strip().lower()
        if t in ("вопросы", "нет тз", "спроси", "questions"):
            context.user_data["missing"] = list(FIELDS)
            return await ask_next(update, context)
        brief.update(parse_brief(update.message.text))
    missing = [f for f in FIELDS if f not in brief]
    if missing:
        context.user_data["missing"] = missing
        return await ask_next(update, context)
    return await show_brief(update, context)


async def on_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data["missing"].pop(0)
    context.user_data["brief"][field] = update.message.text.strip()[:120]
    return await ask_next(update, context)


async def show_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    b = context.user_data["brief"]
    lines = [f"• {LABELS[f]}: {b[f]}" for f in FIELDS if f in b]
    if b.get("description"):
        lines.append(f"• Описание: {b['description'][:200]}")
    await update.message.reply_text(
        "📋 Бриф, который я сформулировал:\n" + "\n".join(lines) +
        "\n\nОтветь «да» — соберу 4 варианта логотипа (SVG + PNG + favicon). «нет» — заново.")
    return CONFIRM


async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip().lower()
    if t in ("да", "+", "ок", "ok", "погнали", "подтверждаю"):
        await generate(update, context)
        return ConversationHandler.END
    if t in ("нет", "заново", "отмена"):
        context.user_data["brief"] = {}
        await update.message.reply_text("Начнём заново. Пришли ТЗ или напиши «вопросы».")
        return ASK_BRIEF
    await update.message.reply_text("Ответь «да» или «нет».")
    return CONFIRM


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SVG-конструктор: 4 варианта + SVG + favicon."""
    b = context.user_data["brief"]
    status = await update.message.reply_text("🎨 Собираю 4 варианта логотипа...")
    
    try:
        await status.delete()
    except Exception:
        pass
    
    concepts = logo_builder.build_concepts(b)
    
    # Отправляем 4 PNG варианта
    for concept in concepts:
        await update.message.reply_photo(
            photo=concept["png"],
            caption=(
                f"**{concept['description']}**\n\n"
                f"🎨 Палитра: {concept['primary']} / {concept['secondary']}\n"
                f"📐 Шаблон: {concept['template']}\n\n"
                f"Напиши номер варианта (1-4) — отправлю SVG + favicon."),
            parse_mode="Markdown")
        await asyncio.sleep(1)
    
    # Сохраняем концепции в context для последующего выбора
    context.user_data["concepts"] = concepts
    
    await update.message.reply_text(
        "✅ 4 варианта готовы!\n\n"
        "Напиши номер (1-4) — отправлю:\n"
        "• SVG (вектор для печати/дизайнера)\n"
        "• favicon.ico (для сайта)\n\n"
        "Или /logo — создать новый бриф.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора варианта после generate()."""
    if "concepts" not in context.user_data:
        await update.message.reply_text("Я по логотипам. Напиши /logo — начнём.")
        return
    
    text = update.message.text.strip()
    if text.isdigit() and 1 <= int(text) <= 4:
        idx = int(text) - 1
        concept = context.user_data["concepts"][idx]
        
        # Отправляем SVG как документ
        svg_bytes = concept["svg"].encode("utf-8")
        svg_file = InputFile(io.BytesIO(svg_bytes), filename=f"{context.user_data['brief'].get('brand', 'logo')}.svg")
        await update.message.reply_document(
            document=svg_file,
            caption="📄 SVG (векторный файл для печати и дизайнера)")
        
        # Отправляем favicon
        logo = logo_builder.build_logo(context.user_data["brief"])
        favicon_file = InputFile(io.BytesIO(logo["favicon"]), filename="favicon.ico")
        await update.message.reply_document(
            document=favicon_file,
            caption="🔷 favicon.ico (для сайта)")
        
        await update.message.reply_text(
            "✅ Файлы отправлены!\n\n"
            f"Шаблон: {concept['template']}\n"
            f"Палитра: {concept['primary']} / {concept['secondary']}\n\n"
            "SVG можно открыть в Figma/Illustrator для доработки.\n"
            "favicon.ico — загрузить в корень сайта.")
        
        # Очищаем context
        del context.user_data["concepts"]
    else:
        await update.message.reply_text("Напиши номер варианта (1-4) или /logo — начать заново.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог завершён. /logo — начать заново.")
    return ConversationHandler.END


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 LogoForge v4 — детерминированные логотипы.\n\n"
        "/logo — создать логотип (SVG + PNG + favicon)\n"
        "/idea — визуальные концепции через Pollinations\n"
        "/help — справка\n/cancel — прервать")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**/logo** — основной режим:\n"
        "1. ТЗ (текст/PDF/DOCX/TXT) или «вопросы»\n"
        "2. Формулирую бриф → «да»\n"
        "3. 4 варианта логотипа (PNG)\n"
        "4. Выбираешь номер → получаешь SVG + favicon\n\n"
        "**/idea** — экспериментальный:\n"
        "Визуальные концепции через Pollinations (медленно, но креативно)\n\n"
        "Геометрия логотипов детерминирована: предсказуемый результат, читаемый текст, масштабируемость.")


async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pollinations для визуальных идей (не финальный лого)."""
    await update.message.reply_text(
        "🎨 /idea — визуальные концепции через Pollinations.\n\n"
        "Пришли ТЗ текстом (например: бренд=Hedex ценность=качество отрасль=строительство).\n"
        "Сгенерирую 4 концепции для вдохновения (~2-4 мин).")
    # TODO: интегрировать старую логику Pollinations сюда


async def nudge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я по логотипам. Напиши /logo — начнём.")


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен в Railway Variables")
        return
    conv = ConversationHandler(
        entry_points=[CommandHandler("logo", flow_start)],
        states={
            ASK_BRIEF: [MessageHandler(filters.TEXT | filters.Document.ALL, on_brief)],
            ASK_FIELDS: [MessageHandler(filters.TEXT, on_field)],
            CONFIRM: [MessageHandler(filters.TEXT, on_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("idea", idea_command))
    # Обработка выбора варианта (после generate)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    logger.info("Бот запущен на Railway (SVG-конструктор)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
