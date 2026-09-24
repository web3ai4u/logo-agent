#!/usr/bin/env python3
"""Small, deterministic design layer for the LogoForge bot."""

BASE_NEG = (
    "3d, metallic, chrome, emboss, bevel, shadow, gradient, texture, mockup, "
    "badge, coin, medal, ring, frame, studio lighting, grey background, "
    "text, words, letters, watermark, photo, blur, clutter, multiple logos, "
    "presentation board, product shot"
)

STYLE_FLAT = (
    "flat 2d vector logo symbol, simple geometric silhouette, solid black shape, "
    "clean sharp edges, isolated on pure white background, centered, no decoration"
)

CRAFT_RULES = (
    "one compact shape, one visual idea, optically centered, balanced negative space, "
    "recognizable at 32 pixels, suitable for favicon, stamp and embroidery"
)

NEGSPACE_DIRECTIVE = "use meaningful negative space, not ornamental detail"

SHAPE_SEMANTICS = {
    "скорость": "forward motion, one diagonal cut, compact dynamic geometry",
    "speed": "forward motion, one diagonal cut, compact dynamic geometry",
    "надёжность": "stable base, strong horizontal axis, compact solid geometry",
    "надежность": "stable base, strong horizontal axis, compact solid geometry",
    "доверие": "balanced interlocking forms, calm closed geometry",
    "trust": "balanced interlocking forms, calm closed geometry",
    "статус": "precise vertical symmetry, restrained proportions",
    "забота": "soft controlled curves, protective enclosing gesture",
    "инновации": "modular geometry with one deliberate angle break",
    "innovation": "modular geometry with one deliberate angle break",
}

CLICHES = {
    "финтех": "coins, dollar signs, charts, padlocks, generic shields",
    "fintech": "coins, dollar signs, charts, padlocks, generic shields",
    "медицина": "red crosses, heartbeat lines, caduceus, pills",
    "medicine": "red crosses, heartbeat lines, caduceus, pills",
    "кофе": "coffee cups, beans, steam, barista portraits",
    "coffee": "coffee cups, beans, steam, barista portraits",
    "логист": "delivery trucks, globes, cardboard boxes, generic arrows",
    "logistic": "delivery trucks, globes, cardboard boxes, generic arrows",
    "строит": "house roofs, cranes, bricks, keys",
    "build": "house roofs, cranes, bricks, keys",
    "construct": "house roofs, cranes, bricks, keys",
    "недвижим": "house roofs, keys, skyline silhouettes",
    "real estate": "house roofs, keys, skyline silhouettes",
    "эко": "leaves, sprouts, recycling arrows",
    "eco": "leaves, sprouts, recycling arrows",
}

PALETTES = {
    "luxury": {"primary": (11, 11, 12), "secondary": (201, 162, 39), "names": "black and warm gold", "hex": "#0B0B0C / #C9A227"},
    "премиум": {"primary": (11, 11, 12), "secondary": (201, 162, 39), "names": "black and warm gold", "hex": "#0B0B0C / #C9A227"},
    "minimal": {"primary": (17, 17, 17), "secondary": (138, 138, 138), "names": "black and grey", "hex": "#111111 / #8A8A8A"},
    "tech": {"primary": (14, 27, 44), "secondary": (45, 212, 191), "names": "deep navy and electric teal", "hex": "#0E1B2C / #2DD4BF"},
    "friendly": {"primary": (31, 41, 55), "secondary": (245, 158, 11), "names": "charcoal and warm amber", "hex": "#1F2937 / #F59E0B"},
    "bold": {"primary": (0, 0, 0), "secondary": (230, 57, 70), "names": "black and signal red", "hex": "#000000 / #E63946"},
}

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


def translit(text: str) -> str:
    return (text or "brand").lower().translate(TRANSLIT).strip() or "brand"


def shape_for(value: str) -> str:
    value = (value or "").lower()
    for key, result in SHAPE_SEMANTICS.items():
        if key in value:
            return result
    return "balanced geometric composition with a distinctive silhouette"


def cliches_for(industry: str) -> str:
    industry = (industry or "").lower()
    for key, result in CLICHES.items():
        if key in industry:
            return result
    return "generic clipart, obvious industry symbols"


def palette_for(tone: str) -> dict:
    tone = (tone or "").lower()
    for key, palette in PALETTES.items():
        if key in tone:
            return palette
    return PALETTES["minimal"]


def negative_for(industry: str) -> str:
    return BASE_NEG + ", " + cliches_for(industry)
