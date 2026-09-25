#!/usr/bin/env python3
"""
logo_builder.py — детерминированный SVG-конструктор логотипов.
8 шаблонов: orbit, cut, stack, leaf, peak, path, frame, initial.
Возвращает SVG + PNG + favicon. Геометрия предсказуема, текст читается.
"""

from __future__ import annotations

import io
import math
import re

import cairosvg
from PIL import Image

# 8 SVG-конструкторов: каждый принимает brand, primary, secondary, возвращает SVG
# Важно: круг = геометрический элемент, НЕ внешний ободок (иначе медаль)


def _orbit(brand: str, primary: str, secondary: str) -> str:
    """Orbit: круг с внутренней геометрией, НЕ замкнутый ободок."""
    letter = brand[0].upper() if brand else "A"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <circle cx="200" cy="200" r="150" fill="none" stroke="{primary}" stroke-width="8"/>
  <path d="M 120 280 L 200 120 L 280 280" fill="none" stroke="{primary}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="200" cy="200" r="30" fill="{secondary}"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


def _cut(brand: str, primary: str, secondary: str) -> str:
    """Cut: буква/форма с диагональным срезом."""
    letter = brand[0].upper() if brand else "A"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <path d="M 100 300 L 100 100 L 300 100 L 300 300 L 200 300 L 200 200 Z" fill="{primary}"/>
  <path d="M 220 100 L 300 180 L 220 180 Z" fill="{secondary}"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


def _stack(brand: str, primary: str, secondary: str) -> str:
    """Stack: геометрические блоки."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <rect x="80" y="80" width="120" height="120" fill="{primary}"/>
  <rect x="220" y="80" width="100" height="100" fill="{secondary}"/>
  <rect x="80" y="220" width="240" height="80" fill="{primary}"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


def _leaf(brand: str, primary: str, secondary: str) -> str:
    """Leaf: мягкая органическая форма."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <path d="M 200 80 Q 320 200 200 320 Q 80 200 200 80 Z" fill="{primary}"/>
  <path d="M 200 120 Q 280 200 200 280" fill="none" stroke="{secondary}" stroke-width="6"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


def _peak(brand: str, primary: str, secondary: str) -> str:
    """Peak: динамичная угловая форма (горы, рост)."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <path d="M 80 320 L 200 80 L 320 320 L 260 320 L 200 160 L 140 320 Z" fill="{primary}"/>
  <path d="M 200 80 L 240 160 L 200 160 Z" fill="{secondary}"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


def _path(brand: str, primary: str, secondary: str) -> str:
    """Path: движение/маршрут (стрелка, поток)."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <path d="M 80 200 Q 200 80 320 200 Q 200 320 80 200" fill="none" stroke="{primary}" stroke-width="12" stroke-linecap="round"/>
  <path d="M 280 180 L 320 200 L 280 220 Z" fill="{secondary}"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


def _frame(brand: str, primary: str, secondary: str) -> str:
    """Frame: аккуратная открытая форма без замкнутой рамки."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <path d="M 100 100 L 300 100 L 300 300" fill="none" stroke="{primary}" stroke-width="8" stroke-linecap="round"/>
  <path d="M 140 140 L 260 140 L 260 260" fill="none" stroke="{secondary}" stroke-width="6" stroke-linecap="round"/>
  <rect x="180" y="180" width="40" height="40" fill="{primary}"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


def _initial(brand: str, primary: str, secondary: str) -> str:
    """Initial: монограмма из первой буквы."""
    letter = brand[0].upper() if brand else "A"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <rect width="400" height="400" fill="#FFFFFF"/>
  <text x="200" y="280" font-family="Arial, sans-serif" font-size="240" font-weight="bold" text-anchor="middle" fill="{primary}">{letter}</text>
  <circle cx="280" cy="100" r="20" fill="{secondary}"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="{primary}">{brand}</text>
</svg>'''


TEMPLATES = {
    "orbit": _orbit,
    "cut": _cut,
    "stack": _stack,
    "leaf": _leaf,
    "peak": _peak,
    "path": _path,
    "frame": _frame,
    "initial": _initial,
}

# Семантика: ценность -> шаблон
SHAPE_MAP = {
    "скорость": "path",
    "speed": "path",
    "надёжность": "stack",
    "reliability": "stack",
    "доверие": "orbit",
    "trust": "orbit",
    "статус": "frame",
    "premium": "frame",
    "luxury": "frame",
    "забота": "leaf",
    "care": "leaf",
    "инновации": "cut",
    "innovation": "cut",
    "качество": "peak",
    "quality": "peak",
    "growth": "peak",
    "рост": "peak",
}

# Палитры: hex primary, hex secondary
PALETTES = {
    "luxury": ("#0B0B0C", "#C9A227"),
    "премиум": ("#0B0B0C", "#C9A227"),
    "minimal": ("#111111", "#8A8A8A"),
    "tech": ("#0E1B2C", "#2DD4BF"),
    "friendly": ("#1F2937", "#F59E0B"),
    "bold": ("#000000", "#E63946"),
}


def choose_template(value: str, industry: str) -> str:
    """Выбор шаблона по ценности и отрасли (детерминированно)."""
    v = (value or "").lower()
    for key, tpl in SHAPE_MAP.items():
        if key in v:
            return tpl
    # Fallback по отрасли
    i = (industry or "").lower()
    if "строй" in i or "build" in i or "construct" in i:
        return "peak"
    if "технолог" in i or "tech" in i or "it" in i:
        return "cut"
    if "фин" in i or "fin" in i:
        return "stack"
    return "orbit"


def choose_palette(tone: str) -> tuple:
    """Палитра по характеру бренда."""
    t = (tone or "").lower()
    for key, pal in PALETTES.items():
        if key in t:
            return pal
    return PALETTES["minimal"]


def build_logo(brief: dict) -> dict:
    """
    Главный вход: brief -> {svg, png, favicon, template, description}
    
    Args:
        brief: dict с полями brand, value, industry, tone, audience
    
    Returns:
        dict с svg (str), png (bytes), favicon (bytes), template (str), description (str)
    """
    brand = brief.get("brand", "Brand")
    value = brief.get("value", "")
    industry = brief.get("industry", "")
    tone = brief.get("tone", "")
    
    template = choose_template(value, industry)
    primary, secondary = choose_palette(tone)
    
    # Генерируем SVG
    svg_builder = TEMPLATES[template]
    svg = svg_builder(brand, primary, secondary)
    
    # SVG -> PNG (1024x1024)
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=1024, output_height=1024)
    
    # PNG -> favicon (16x16, 32x32, 48x48 в одном ICO)
    img = Image.open(io.BytesIO(png))
    ico_bytes = io.BytesIO()
    img.save(ico_bytes, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    favicon = ico_bytes.getvalue()
    
    # Описание для rationale
    description = (
        f"Шаблон: {template}\n"
        f"Палитра: {primary} (основной) / {secondary} (акцент)\n"
        f"Геометрия: детерминированная, масштабируемая от favicon до билборда\n"
        f"Форматы: SVG (вектор) + PNG (1024px) + favicon (ICO)"
    )
    
    return {
        "svg": svg,
        "png": png,
        "favicon": favicon,
        "template": template,
        "primary": primary,
        "secondary": secondary,
        "description": description,
    }


def build_concepts(brief: dict) -> list:
    """
    Генерирует 4 варианта на разных шаблонах (для выбора клиентом).
    Возвращает список из 4 dict с результатами build_logo().
    """
    brand = brief.get("brand", "Brand")
    value = brief.get("value", "")
    industry = brief.get("industry", "")
    tone = brief.get("tone", "")
    
    primary, secondary = choose_palette(tone)
    
    # 4 разных шаблона: основной + 3 альтернативы
    main_template = choose_template(value, industry)
    all_templates = list(TEMPLATES.keys())
    alternatives = [t for t in all_templates if t != main_template][:3]
    
    concepts = []
    for i, tpl_name in enumerate([main_template] + alternatives, 1):
        svg_builder = TEMPLATES[tpl_name]
        svg = svg_builder(brand, primary, secondary)
        png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=1024, output_height=1024)
        
        concepts.append({
            "number": i,
            "template": tpl_name,
            "svg": svg,
            "png": png,
            "primary": primary,
            "secondary": secondary,
            "description": f"Вариант {i}: шаблон {tpl_name}",
        })
    
    return concepts
