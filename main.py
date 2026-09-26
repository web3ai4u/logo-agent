#!/usr/bin/env python3
"""LogoForge v5: /logo = детерминированный SVG-конструктор,
/idea = генератор визуальных идей (Pollinations, случайный сид = разнообразие)."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import re
import time

import requests
from telegram import InputFile, Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

import logo_builder

BOT_TOKEN = os.getenv("BOT_TOKEN")
MODELS = ["flux", "sana", "turbo"]          # перебор при 429/сбое
ASK_BRIEF, ASK_FIELDS, CONFIRM = range(3)   # состояния диалога /logo

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

# 4 разных арт-направления для /idea (намеренно разные стили)
IDEA_STYLES = [
    ("Геометрия / flat",
     "minimal flat geometric vector logo icon, {brief}, clean bold shapes, "
     "single idea, isolated on pure white background"),
    ("Неон / градиент",
     "modern vibrant logo icon, {brief}, smooth gradient colors, futuristic "
     "glow, dark background"),
    ("Ретро / эмблема",
     "vintage retro badge logo, {brief}, circular composition, muted retro "
     "palette, print texture"),
    ("Абстракция / органика",
     "abstract organic logo mark, {brief}, fluid flowing shapes, bold duotone "
     "colors, white background"),
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- перевод брифа (MyMemory, без ключа) ----------

def translate_ru_en(text: str) -> str:
    """RU -> EN для image-моделей. При сбое возвращает исходный текст."""
    if not re.search(r"[а-яА-Я]", text or ""):
        return text
    try:
        r = requests.get("https://api.mymemory.translated.net/get",
                         params={"q": text[:400], "langpair": "ru|en"}, timeout=10)
        out = r.json().get("responseData", {}).get("translatedText", "")
        if out and len(out) > 2:
            return out
    except Exception as e:
        logger.warning("translate failed: %s", e)
    return text


# ---------- /idea: генерация со случайным сидом ----------

def idea_image(prompt: str, seed: int):
    """PNG из Pollinations. Случайный сид = разные картинки каждый запрос.
    2 попытки на модель, при 429 пауза и следующая модель. None = всё легло."""
    base = (f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
            f"?width=768&height=768&nologo=true&safe=true&seed={seed}")
    for model in MODELS:
        for _ in range(2):
            try:
                r = requests.get(base + f"&model={model}", timeout=90)
                if r.status_code == 429:
                    time.sleep(4)
                    break
                if r.ok and r.headers.get("content-type", "").startswith("image/"):
                    return r.content
            except requests.RequestException as e:
                logger.warning("idea fetch retry: %s", e)
                time.sleep(2)
    return None


async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/idea <ТЗ одной строкой> -> 4 РАЗНЫЕ визуальные идеи."""
    text = update.message.text.replace("/idea", "", 1).strip()
    if not text:
        await update.message.reply_text(
            "Пришли ТЗ одной строкой:\n"
            "/idea бренд=Hedex ценность=качество отрасль=строительство")
        return

    brief_en = translate_ru_en(text)
    seed_base = random.randint(1, 999999)      # ключ разнообразия
    status = await update.message.reply_text("🎨 Рисую 4 разные идеи (~1-3 мин)...")
    try:
        await status.delete()
    except Exception:
        pass

    ok = 0
    for i, (name, tpl) in enumerate(IDEA_STYLES):
        img = idea_image(tpl.format(brief=brief_en), seed_base + i * 7)
        if img:
            await update.message.reply_photo(
                photo=img,
                caption=f"**Идея {i + 1}: {name}**\nТЗ: {text[:100]}",
                parse_mode="Markdown")
            ok += 1
        else:
            await update.message.reply_text(
                f"Идея {i + 1} ({name}): модели перегружены (429). Повтори позже.")
        await asyncio.sleep(3)                 # не ловим общий лимит 300 RPM

    await update.message.reply_text(
        f"✅ Идеи: {ok}/4. Это вдохновение, не финал.\n"
        "Финальный векторный лого с файлами — команда /logo.")


# ---------- /logo: разбор ТЗ ----------

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


# ---------- /logo: диалог ----------

async def flow_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["brief"] = {}
    context.user_data.pop("concepts", None)
    await update.message.reply_text(
        "🎨 Принимаю задачу.\n\nПришли ТЗ текстом или файлом (PDF / DOCX / TXT).\n"
        "Если ТЗ нет — напиши «вопросы», и я задам 5 коротких сам.")
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


# ---------- /logo: сборка и выдача ----------

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SVG-конструктор: 4 варианта PNG, затем по номеру — SVG + favicon."""
    b = context.user_data["brief"]
    status = await update.message.reply_text("🎨 Собираю 4 варианта логотипа...")
    try:
        await status.delete()
    except Exception:
        pass

    concepts = logo_builder.build_concepts(b)
    context.user_data["concepts"] = concepts

    for c in concepts:
        await update.message.reply_photo(
            photo=c["png"],
            caption=(f"**Вариант {c['number']}: шаблон {c['template']}**\n\n"
                     f"🎨 Палитра: {c['primary']} / {c['secondary']}\n"
                     f"📐 Геометрия детерминирована: favicon → билборд без потерь\n\n"
                     f"Напиши номер (1-4) — отправлю SVG + favicon."),
            parse_mode="Markdown")
        await asyncio.sleep(1)

    await update.message.reply_text(
        "✅ 4 варианта готовы.\nНапиши номер (1-4) — пришлю вектор и favicon.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор варианта (1-4) или подсказка вне диалога."""
    if "concepts" not in context.user_data:
        await update.message.reply_text("Я по логотипам. /logo — финальный вектор, /idea — идеи.")
        return

    text = update.message.text.strip()
    if text.isdigit() and 1 <= int(text) <= 4:
        c = context.user_data["concepts"][int(text) - 1]
        brand = context.user_data.get("brief", {}).get("brand", "logo")
        safe_brand = re.sub(r"[^\w\-]", "_", brand)

        svg_file = InputFile(io.BytesIO(c["svg"].encode("utf-8")),
                             filename=f"{safe_brand}.svg")
        await update.message.reply_document(
            document=svg_file,
            caption="📄 SVG — вектор для печати, Figma, Illustrator")

        logo = logo_builder.build_logo(context.user_data["brief"])
        ico_file = InputFile(io.BytesIO(logo["favicon"]), filename="favicon.ico")
        await update.message.reply_document(
            document=ico_file,
            caption="🔷 favicon.ico — 16/32/48 px, для корня сайта")

        await update.message.reply_text(
            f"✅ Файлы отправлены.\nШаблон: {c['template']}\n"
            f"Палитра: {c['primary']} / {c['secondary']}\n\n"
            "SVG открывается в браузере/Figma без потерь качества.")
        del context.user_data["concepts"]
    else:
        await update.message.reply_text("Напиши номер варианта (1-4) или /logo — заново.")


# ---------- служебные команды ----------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("concepts", None)
    await update.message.reply_text("Диалог завершён. /logo — начать заново.")
    return ConversationHandler.END


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 LogoForge v5 — логотипы премиум-класса.\n\n"
        "/logo — финальный вектор: ТЗ → бриф → 4 варианта → SVG + favicon\n"
        "/idea — 4 разные визуальные идеи для вдохновения\n"
        "/help — справка\n/cancel — прервать диалог")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**/logo** (финал):\n"
        "1. ТЗ текстом/файлом или «вопросы»\n"
        "2. Бриф → «да»\n"
        "3. 4 варианта PNG\n"
        "4. Номер (1-4) → SVG + favicon\n\n"
        "**/idea** (вдохновение):\n"
        "/idea бренд=X ценность=Y отрасль=Z → 4 разных стиля, каждый раз новые\n\n"
        "Геометрия /logo детерминирована: предсказуемо, читаемо, масштабируемо.",
        parse_mode="Markdown")


async def nudge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я по логотипам. /logo — финальный вектор, /idea — идеи.")


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен (файл .env)")
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    logger.info("Бот запущен (VPS, SVG-конструктор + /idea)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
