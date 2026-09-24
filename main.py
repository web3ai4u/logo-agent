#!/usr/bin/env python3
"""LogoForge: generate simple logo directions and flatten the model output."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time
from functools import lru_cache

import requests
from PIL import Image, ImageFilter, ImageOps
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

import design_skills as ds

BOT_TOKEN = os.getenv("BOT_TOKEN")
MODELS = ["flux", "sana", "turbo"]
ASK_BRIEF, ASK_FIELDS, CONFIRM = range(3)
FIELDS = ["brand", "value", "audience", "industry", "tone"]
LABELS = {"brand": "Бренд", "value": "Ценность", "audience": "Аудитория", "industry": "Отрасль", "tone": "Характер"}
QUESTIONS = {
    "brand": "Название бренда?",
    "value": "Главная ценность бренда? Например: надёжность, скорость, статус, забота, инновации.",
    "audience": "Кто клиент? Например: владельцы домов, курьеры мегаполисов.",
    "industry": "Отрасль или ниша?",
    "tone": "Характер: luxury, minimal, tech, friendly или bold?",
}
VALUE_MAP = {"скорость": "speed and motion", "надёжность": "reliability and trust", "надежность": "reliability and trust", "доверие": "trust and confidence", "статус": "restrained premium quality", "забота": "care and warmth", "инновации": "innovation and technology"}
_PATTERNS = {
    "brand": r"(?:бренд|brand|название)\s*[:=]\s*([^,\n]+)",
    "value": r"(?:ценность|value)\s*[:=]\s*([^,\n]+)",
    "audience": r"(?:аудитория|audience|клиент)\s*[:=]\s*([^,\n]+)",
    "industry": r"(?:отрасль|industry|ниша|сфера)\s*[:=]\s*([^,\n]+)",
    "tone": r"(?:тон|tone|стиль|style|характер)\s*[:=]\s*([^,\n]+)",
}
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@lru_cache(maxsize=128)
def translate_ru_en(text: str) -> str:
    """Translate descriptive text once; retain the original on any failure."""
    text = (text or "").strip()[:400]
    if not text or not re.search(r"[а-яА-Я]", text):
        return text
    try:
        response = requests.get("https://api.mymemory.translated.net/get", params={"q": text, "langpair": "ru|en"}, timeout=8)
        response.raise_for_status()
        result = response.json().get("responseData", {}).get("translatedText", "").strip()
        if result and len(result) > 2:
            return result
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("translation failed: %s", exc)
    return text


def flatten_logo(data: bytes, fg=(17, 17, 17), size=1024) -> bytes | None:
    """Convert a generated image into a safe, single-colour mark on white.

    The source is never returned unchanged: if extraction fails, return None so
    the caller can retry another model instead of showing a 3D mockup.
    """
    try:
        source = Image.open(io.BytesIO(data)).convert("RGB")
        source.thumbnail((768, 768), Image.Resampling.LANCZOS)
        gray = ImageOps.grayscale(source)
        gray = gray.filter(ImageFilter.MedianFilter(3))
        w, h = gray.size
        border = [gray.getpixel((x, y)) for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]]
        border.sort()
        bg = sum(border[2:-2]) / len(border[2:-2])
        best = None
        for threshold in (35, 50, 65, 80):
            mask = gray.point(lambda p: 255 if abs(p - bg) >= threshold else 0)
            mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
            bbox = mask.getbbox()
            if not bbox:
                continue
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            ratio = area / (w * h)
            if 0.02 <= ratio <= 0.92:
                score = abs(ratio - 0.32)
                if best is None or score < best[0]:
                    best = (score, mask, bbox)
        if best is None:
            return None
        _, mask, bbox = best
        # Remove isolated watermark/noise by keeping only the central crop area.
        crop = mask.crop(bbox)
        crop = crop.filter(ImageFilter.MedianFilter(3))
        cw, ch = crop.size
        side = max(cw, ch)
        pad = max(12, int(side * 0.14))
        canvas = Image.new("L", (side + 2 * pad, side + 2 * pad), 0)
        canvas.paste(crop, ((side - cw) // 2 + pad, (side - ch) // 2 + pad))
        canvas = canvas.resize((size, size), Image.Resampling.LANCZOS).point(lambda p: 255 if p >= 128 else 0)
        output = Image.new("RGB", (size, size), (255, 255, 255))
        output.paste(Image.new("RGB", (size, size), fg), mask=canvas)
        result = io.BytesIO()
        output.save(result, "PNG", optimize=True)
        return result.getvalue()
    except (OSError, ValueError) as exc:
        logger.warning("logo flattening failed: %s", exc)
        return None


def build_image_url(prompt: str, model: str, negative: str) -> str:
    return (f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt, safe='')}"
            f"?width=768&height=768&nologo=true&safe=true&model={model}"
            f"&negative_prompt={requests.utils.quote(negative, safe='')}")


def fetch_image_bytes(prompt: str, negative: str) -> bytes | None:
    for model in MODELS:
        for attempt in range(2):
            try:
                response = requests.get(build_image_url(prompt, model, negative), timeout=90)
                if response.status_code == 429:
                    time.sleep(4 + attempt * 2)
                    continue
                if response.ok and response.headers.get("content-type", "").startswith("image/"):
                    return response.content
            except requests.RequestException as exc:
                logger.warning("image request failed (%s): %s", model, exc)
    return None


def parse_brief(text: str) -> dict:
    text = (text or "").strip()
    found = {}
    for field, pattern in _PATTERNS.items():
        match = re.search(pattern, text, re.I)
        if match:
            found[field] = match.group(1).strip()[:120]
    if not found and text:
        found["description"] = text[:400]
    return found


def extract_doc(data: bytes, name: str):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    try:
        if ext in ("txt", "md"):
            return data.decode("utf-8", errors="ignore")
        if ext == "pdf":
            from PyPDF2 import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        if ext == "docx":
            from docx import Document
            return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(data)).paragraphs)
    except Exception as exc:
        logger.warning("document parse failed: %s", exc)
    return None


def build_concepts(brief: dict) -> list[tuple]:
    brand = brief.get("brand", "brand")
    brand_en = ds.translit(brand)
    value = brief.get("value", "professionalism")
    value_en = VALUE_MAP.get(value.lower(), translate_ru_en(value))
    industry = translate_ru_en(brief.get("industry", ""))
    audience = translate_ru_en(brief.get("audience", ""))
    description = translate_ru_en(brief.get("description", ""))
    shape = ds.shape_for(value)
    palette = ds.palette_for(brief.get("tone"))
    context = f"brand concept inspired by {value_en}"
    if industry:
        context += f", for {industry}"
    if audience:
        context += f", designed for {audience}"
    if description:
        context += f"; brief context: {description[:220]}"
    common = f"{ds.STYLE_FLAT}, {ds.CRAFT_RULES}, {ds.NEGSPACE_DIRECTIVE}, {context}"
    return [
        ("1. Symbol — смысл", f"{common}, one abstract symbol, {shape}, no letters, no border", "Смысловая геометрическая форма.", palette),
        ("2. Monogram — литера", f"{common}, one simple geometric monogram based on the single initial {brand_en[0].upper()}, no readable words, no border", "Одна литера вместо ненадёжного текста.", palette),
        ("3. Minimal — точность", f"{common}, restrained compact symbol, precise proportions, calm geometry, no letters, no border", "Сдержанный знак для малого размера.", palette),
        ("4. Distinctive — отличие", f"{common}, bold asymmetric abstract symbol with one deliberate cut, no letters, no border", "Более отличимый вариант без отраслевого клише.", palette),
    ]


async def flow_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["brief"] = {}
    await update.message.reply_text("🎨 Пришли ТЗ текстом или PDF/DOCX/TXT. Если ТЗ нет — напиши «вопросы».")
    return ASK_BRIEF


async def ask_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    missing = context.user_data.get("missing", [])
    if not missing:
        return await show_brief(update, context)
    await update.message.reply_text(f"❓ {QUESTIONS[missing[0]]}")
    return ASK_FIELDS


async def on_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brief = context.user_data["brief"]
    if update.message.document:
        document = update.message.document
        telegram_file = await document.get_file()
        buffer = io.BytesIO()
        await telegram_file.download_to_memory(out=buffer)
        text = extract_doc(buffer.getvalue(), document.file_name or "file.txt")
        if text is None:
            await update.message.reply_text("Не читаю этот формат. Пришли текст, TXT, PDF или DOCX.")
            return ASK_BRIEF
        brief.update(parse_brief(text))
    else:
        text = update.message.text or ""
        if text.strip().lower() in ("вопросы", "нет тз", "спроси", "questions"):
            context.user_data["missing"] = list(FIELDS)
            return await ask_next(update, context)
        brief.update(parse_brief(text))
    missing = [field for field in FIELDS if not brief.get(field)]
    context.user_data["missing"] = missing
    return await ask_next(update, context) if missing else await show_brief(update, context)


async def on_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data["missing"].pop(0)
    context.user_data["brief"][field] = (update.message.text or "").strip()[:120]
    return await ask_next(update, context)


async def show_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brief = context.user_data["brief"]
    lines = [f"• {LABELS[field]}: {brief[field]}" for field in FIELDS]
    if brief.get("description"):
        lines.append(f"• Описание: {brief['description'][:180]}")
    await update.message.reply_text("📋 Бриф:\n" + "\n".join(lines) + "\n\nОтветь «да», чтобы получить 4 плоских варианта, или «нет» для перезапуска.")
    return CONFIRM


async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = (update.message.text or "").strip().lower()
    if answer in ("да", "+", "ок", "ok", "погнали", "подтверждаю"):
        await generate(update, context)
        return ConversationHandler.END
    if answer in ("нет", "заново", "отмена"):
        return await flow_start(update, context)
    await update.message.reply_text("Ответь «да» или «нет».")
    return CONFIRM


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brief = context.user_data["brief"]
    negative = ds.negative_for(brief.get("industry"))
    await update.message.reply_text("🎨 Генерирую и очищаю 4 варианта. Это может занять несколько минут.")
    successful = 0
    first_flat = None
    for name, prompt, rationale, palette in build_concepts(brief):
        raw = await asyncio.to_thread(fetch_image_bytes, prompt, negative)
        flat = await asyncio.to_thread(flatten_logo, raw, palette["primary"]) if raw else None
        if flat:
            if first_flat is None:
                first_flat = flat
            await update.message.reply_photo(photo=flat, caption=f"{name}\n\n💡 {rationale}\n🎨 {palette['hex']} ({palette['names']})")
            successful += 1
        else:
            await update.message.reply_text(f"{name}: не удалось получить чистый силуэт, вариант пропущен.")
        await asyncio.sleep(2)
    if first_flat:
        await update.message.reply_photo(photo=first_flat, caption="🧪 Монохромный контроль: чёрный силуэт на белом фоне.")
    await update.message.reply_text(f"✅ Готово: {successful}/4. Выбери номер понравившегося направления для следующего шага.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог завершён. /logo — начать заново.")
    return ConversationHandler.END


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎨 LogoForge\n/logo — создать логотип\n/help — справка\n/cancel — отмена")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("1. /logo → ТЗ или вопросы\n2. Подтверждение брифа\n3. Четыре плоских варианта\n4. Монохромная проверка")


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен")
        return
    conversation = ConversationHandler(
        entry_points=[CommandHandler("logo", flow_start)],
        states={ASK_BRIEF: [MessageHandler(filters.TEXT | filters.Document.ALL, on_brief)], ASK_FIELDS: [MessageHandler(filters.TEXT, on_field)], CONFIRM: [MessageHandler(filters.TEXT, on_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(conversation)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: update.message.reply_text("Я создаю логотипы. Напиши /logo.")))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
