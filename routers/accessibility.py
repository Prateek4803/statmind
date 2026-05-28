"""
StatMind N20 — Accessibility & Color Blind Mode
Color palette transformations for deuteranopia/protanopia.
Keyboard shortcut definitions.
WCAG 2.1 AA compliant color system.
Returns CSS variable overrides for the frontend.
"""
from dataclasses import dataclass, field


@dataclass
class AccessibilityConfig:
    mode: str                   # "default","deuteranopia","protanopia","high_contrast","dark"
    css_variables: dict         # CSS variable overrides
    chart_colors: list          # ordered color palette for charts
    description: str
    wcag_level: str             # "AA" or "AAA"


# ── Color Palettes ────────────────────────────────────────────────────────────

PALETTES = {
    "default": {
        "description": "Standard StatMind teal theme",
        "wcag": "AA",
        "accent":  "#2dd4a0",
        "green":   "#34d980",
        "amber":   "#f0b429",
        "red":     "#f05c5c",
        "purple":  "#a78bfa",
        "blue":    "#60a5fa",
        "chart_colors": [
            "#2dd4a0","#60a5fa","#f0b429","#f05c5c",
            "#a78bfa","#34d211","#f97316","#06b6d4",
        ],
    },
    "deuteranopia": {
        "description": "Deuteranopia-safe (blue/orange/purple — avoids red-green confusion)",
        "wcag": "AA",
        "accent":  "#0077bb",   # blue replaces teal
        "green":   "#0077bb",   # blue instead of green
        "amber":   "#ee7733",   # orange instead of amber
        "red":     "#cc3311",   # high-contrast red
        "purple":  "#aa3377",   # magenta
        "blue":    "#33bbee",   # cyan
        "chart_colors": [
            "#0077bb","#ee7733","#aa3377","#33bbee",
            "#009988","#cc3311","#bbbbbb","#000000",
        ],
    },
    "protanopia": {
        "description": "Protanopia-safe (blue/yellow/purple — avoids red confusion)",
        "wcag": "AA",
        "accent":  "#005f87",
        "green":   "#005f87",
        "amber":   "#ffb000",
        "red":     "#785ef0",   # purple replaces red (distinguishable)
        "purple":  "#dc267f",
        "blue":    "#648fff",
        "chart_colors": [
            "#648fff","#ffb000","#dc267f","#785ef0",
            "#fe6100","#005f87","#b0b0b0","#000000",
        ],
    },
    "high_contrast": {
        "description": "High contrast WCAG AAA — for low vision users",
        "wcag": "AAA",
        "accent":  "#00ff88",   # bright green on dark bg
        "green":   "#00ff88",
        "amber":   "#ffdd00",
        "red":     "#ff4444",
        "purple":  "#cc88ff",
        "blue":    "#66aaff",
        "chart_colors": [
            "#00ff88","#ffdd00","#ff4444","#66aaff",
            "#cc88ff","#ffffff","#ff8800","#00ddff",
        ],
    },
    "print": {
        "description": "Print-friendly — dark on white, high contrast grayscale",
        "wcag": "AAA",
        "accent":  "#1a1a1a",
        "green":   "#1a1a1a",
        "amber":   "#555555",
        "red":     "#000000",
        "purple":  "#333333",
        "blue":    "#444444",
        "chart_colors": [
            "#000000","#444444","#888888","#bbbbbb",
            "#1a1a1a","#666666","#222222","#999999",
        ],
    },
}

KEYBOARD_SHORTCUTS = [
    {"keys": "Ctrl+N",  "mac": "⌘N",  "action": "New file",         "category": "File"},
    {"keys": "Ctrl+O",  "mac": "⌘O",  "action": "Open file",        "category": "File"},
    {"keys": "Ctrl+R",  "mac": "⌘R",  "action": "Run analysis",     "category": "Analysis"},
    {"keys": "Ctrl+E",  "mac": "⌘E",  "action": "Export PDF",       "category": "File"},
    {"keys": "Ctrl+/",  "mac": "⌘/",  "action": "AI Query",         "category": "AI"},
    {"keys": "Ctrl+1",  "mac": "⌘1",  "action": "Normality",        "category": "Navigate"},
    {"keys": "Ctrl+2",  "mac": "⌘2",  "action": "Capability",       "category": "Navigate"},
    {"keys": "Ctrl+3",  "mac": "⌘3",  "action": "SPC Charts",       "category": "Navigate"},
    {"keys": "Ctrl+4",  "mac": "⌘4",  "action": "Gauge R&R",        "category": "Navigate"},
    {"keys": "Ctrl+5",  "mac": "⌘5",  "action": "CAPA Engine",      "category": "Navigate"},
    {"keys": "Ctrl+D",  "mac": "⌘D",  "action": "Dashboard",        "category": "Navigate"},
    {"keys": "Ctrl+M",  "mac": "⌘M",  "action": "Multi-Vari",       "category": "Navigate"},
    {"keys": "Escape",  "mac": "Esc", "action": "Close modal/panel", "category": "UI"},
    {"keys": "Ctrl+?",  "mac": "⌘?",  "action": "Show shortcuts",   "category": "Help"},
]

FONT_SIZE_SCALES = {
    "small":   {"base": "13px", "chart_label": "10px", "heading": "15px"},
    "default": {"base": "14px", "chart_label": "11px", "heading": "16px"},
    "large":   {"base": "16px", "chart_label": "13px", "heading": "18px"},
    "xlarge":  {"base": "18px", "chart_label": "15px", "heading": "20px"},
}

def get_accessibility_config(
    mode: str = "default",
    font_size: str = "default",
    reduce_motion: bool = False,
) -> AccessibilityConfig:
    palette = PALETTES.get(mode, PALETTES["default"])

    css_vars = {
        "--teal":   palette["accent"],
        "--green":  palette["green"],
        "--amber":  palette["amber"],
        "--red":    palette["red"],
        "--purple": palette["purple"],
        "--blue":   palette["blue"],
        "--accent": palette["accent"],
        "--accent2": palette["accent"],
    }

    # Font size
    fs = FONT_SIZE_SCALES.get(font_size, FONT_SIZE_SCALES["default"])
    css_vars["--font-size-base"]    = fs["base"]
    css_vars["--font-size-chart"]   = fs["chart_label"]
    css_vars["--font-size-heading"] = fs["heading"]

    # Reduced motion
    if reduce_motion:
        css_vars["--animation-duration"] = "0ms"
        css_vars["--transition-duration"] = "0ms"

    return AccessibilityConfig(
        mode=mode,
        css_variables=css_vars,
        chart_colors=palette["chart_colors"],
        description=palette["description"],
        wcag_level=palette["wcag"],
    )

def get_keyboard_shortcuts(platform: str = "windows") -> list:
    key_field = "mac" if platform.lower() == "mac" else "keys"
    return [{"shortcut": s[key_field], "action": s["action"], "category": s["category"]} for s in KEYBOARD_SHORTCUTS]
