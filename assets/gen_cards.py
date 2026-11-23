#!/usr/bin/env python3
"""Generate oil-painting SVG cards (dark & light themes) and README.md.

Reads structured profile copy from assets/profile.json, computes exact text
wrapping and layout using real font glyph metrics (fontTools + subsetted WOFF),
synthesizes 3D-lit impasto oil-canvas textures (NumPy + Pillow), embeds real
company/school/project logos and portrait sprites, and writes dual-theme SVGs
into assets/cards/ plus root README.md.

Usage:
    python assets/gen_cards.py
"""

import base64
import hashlib
import io
import json
import math
import os
import pathlib
import re
import urllib.request
from collections import defaultdict

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_DIR = HERE / "cards"
CACHE = pathlib.Path(os.environ.get("FONT_CACHE_DIR", HERE / ".font-cache"))
OIL_CACHE = CACHE / "oil-v4"
PROFILE_PATH = HERE / "profile.json"

P = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
LINKS = P["links"]

# ═══════════════════════════════════════════════════════════════════════════
# COLOR SYSTEM — Sampled from Ignacio's oil-painted GitHub IB avatar & Marco Azul Impasto
# ═══════════════════════════════════════════════════════════════════════════

THEMES = {
    "dark": {
        "bg": ("#020516", "#051034", "#0a215c"),
        "frame_grad": ("#93c5fd", "#2960c4", "#08143b"),
        "gold_rim": ("#e8c888", "#9e7a3a", "#3a2a12"),
        "mat_hi": "#f8f4ed",
        "mat_hi_op": 0.22,
        "plate": "#03091f",
        "plate_op": 0.62,
        "plate_stroke": "#2e64bf",
        "plate_stroke_op": 0.55,
        "ink": "#f6f1ea",        # warm impasto alabaster-cream
        "text": "#ede5da",
        "body": "#c8daf4",
        "muted": "#8fa9d8",
        "accent": "#68abff",
        "accent_strong": "#3b82f6",
        "hand": "#ebc88a",       # warm museum gallery ochre-gold
        "hand_alt": "#8ec5ff",
        "gold": "#e2bd79",
        "gold_ink": "#2d1e07",
        "pill_bg": "#06143a",
        "pill_fg": "#ede5da",
        "pill_stroke": "#2f64bd",
        "btn_bg": "#ede5da",
        "btn_fg": "#03091f",
        "shadow_c": "#01030d",
        "shadow_op": 0.52,
        "key_used_bg": ("#0d2459", "#07163b"),
        "key_used_sh": "#03091d",
        "key_used_stroke": "#2e60b5",
        "key_used_fg": "#e6eefc",
        "key_exp_stroke": "#6490d6",
        # RGB palettes for NumPy oil impasto engine
        "oil_base_top": (2, 7, 25),
        "oil_base_bot": (10, 31, 90),
        "oil_swatches": [
            (2, 6, 22),     # deepest Prussian crease
            (5, 16, 52),    # Prussian dark
            (10, 32, 94),   # ultramarine shadow
            (17, 53, 146),  # deep ultramarine
            (28, 79, 194),  # rich cobalt
            (46, 114, 226), # cobalt-cerulean body
            (84, 152, 244), # sky cerulean highlight
        ],
        "oil_flecks": [
            (226, 214, 198), # warm impasto cream
            (218, 184, 122), # antique ochre gold
        ],
        "oil_light_amt": 0.54,
        "oil_gloss": 0.34,
    },
    "light": {
        "bg": ("#d5e4fa", "#a8c7f2", "#6e9de4"),
        "frame_grad": ("#0e2e75", "#3d78d8", "#071a4a"),
        "gold_rim": ("#c59648", "#8f6524", "#e6cc98"),
        "mat_hi": "#ffffff",
        "mat_hi_op": 0.85,
        "plate": "#fcfaf5",
        "plate_op": 0.84,
        "plate_stroke": "#7ea8e6",
        "plate_stroke_op": 0.85,
        "ink": "#050f2b",        # deep Prussian ink
        "text": "#0a1b47",
        "body": "#1a3163",
        "muted": "#3f5990",
        "accent": "#1d4ed8",
        "accent_strong": "#173ea8",
        "hand": "#9a5d17",       # museum burnt umber ochre
        "hand_alt": "#133a87",
        "gold": "#c89648",
        "gold_ink": "#231604",
        "pill_bg": "#ffffff",
        "pill_fg": "#091b48",
        "pill_stroke": "#8ab2eb",
        "btn_bg": "#061438",
        "btn_fg": "#f6f1ea",
        "shadow_c": "#091b48",
        "shadow_op": 0.22,
        "key_used_bg": ("#ffffff", "#edf3fc"),
        "key_used_sh": "#8eb0e3",
        "key_used_stroke": "#adc7ee",
        "key_used_fg": "#081845",
        "key_exp_stroke": "#446cb0",
        # Primed ivory linen glazed with vibrant coastal ultramarine & cerulean oil paint
        "oil_base_top": (239, 232, 219),
        "oil_base_bot": (176, 204, 240),
        "oil_swatches": [
            (18, 56, 138),   # deep ultramarine accent ridges
            (34, 88, 188),   # strong cobalt blue
            (64, 125, 224),  # mid cerulean blue
            (116, 166, 238), # soft azure oil
            (168, 202, 244), # pale pastel blue glaze
            (226, 234, 246), # titanium white-blue blend
            (246, 241, 232), # thick warm titanium cream
        ],
        "oil_flecks": [
            (250, 246, 238), # pure cream ridge highlight
            (204, 158, 86),  # warm linen ochre
        ],
        "oil_light_amt": 0.42,
        "oil_gloss": 0.26,
    },
}

PROJECT_PALETTES = {
    "damaCrm": {"dot": "#60a5fa", "dot_light": "#1d4ed8", "tilt": -0.7, "motif": "grid", "stroke_c": "#3b82f6"},
    "commitFlow": {"dot": "#38bdf8", "dot_light": "#0284c7", "tilt": 0.7, "motif": "gitgraph", "stroke_c": "#0ea5e9"},
    "senseHue": {"dot": "#e2bd79", "dot_light": "#b07621", "tilt": 0.7, "motif": "dualsense", "stroke_c": "#4f6fd6"},
    "virtualMouse": {"dot": "#2dd4bf", "dot_light": "#0f766e", "tilt": -0.7, "motif": "cursor", "stroke_c": "#14b8a6"},
}

STACK_PALETTES = {
    "languages": ("#60a5fa", "#1c4da8", "#0b2459", "#c8defd", "#93b7ed"),
    "frontend": ("#38bdf8", "#13589c", "#082e5c", "#c5e8fc", "#87bee8"),
    "backend": ("#818cf8", "#2d3b9e", "#151d59", "#d5dbfd", "#9faaf0"),
    "infra": ("#e2bd79", "#22538f", "#0e274d", "#e4dac4", "#bba477"),
}

# ═══════════════════════════════════════════════════════════════════════════
# FONTS & TEXT MEASUREMENT
# ═══════════════════════════════════════════════════════════════════════════

FAMILIES = {
    "display": ("Bricolage Grotesque", "Bricolage+Grotesque:opsz,wght@48,800"),
    "sans": ("Plus Jakarta Sans", "Plus+Jakarta+Sans:wght@400;500;600;700;800"),
    "hand": ("Caveat", "Caveat:wght@700"),
    "mono": ("JetBrains Mono", "JetBrains+Mono:wght@600;700"),
}
FALLBACK = {"display": "sans-serif", "sans": "sans-serif", "hand": "cursive", "mono": "monospace"}

DISPLAY = ("display", 800)
HAND = ("hand", 700)


def sans(weight):
    return ("sans", weight)


def mono(weight=600):
    return ("mono", weight)


def _download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/4.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def ensure_fonts():
    """Return {(family_key, weight): path}, downloading TTFs if absent."""
    CACHE.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, (_, query) in FAMILIES.items():
        listed = sorted(CACHE.glob(f"{key}-*.ttf"))
        if not listed:
            css = _download(f"https://fonts.googleapis.com/css2?family={query}").decode()
            for weight, url in re.findall(
                r"font-weight:\s*(\d+);.*?src:\s*url\(([^)]+\.ttf)\)", css, re.S
            ):
                (CACHE / f"{key}-{weight}.ttf").write_bytes(_download(url))
            listed = sorted(CACHE.glob(f"{key}-*.ttf"))
        for p in listed:
            paths[(key, int(p.stem.split("-")[1]))] = p
    return paths


class Metrics:
    """Glyph advance widths and vertical ascent/descent metrics."""

    def __init__(self, path):
        from fontTools.ttLib import TTFont
        self.font = TTFont(path)
        self.upm = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font["hmtx"]
        hhea = self.font["hhea"]
        self.asc = hhea.ascent / self.upm
        self.desc = -hhea.descent / self.upm

    def width(self, text, size, ls=0.0):
        units = 0
        for ch in text:
            gid = self.cmap.get(ord(ch))
            if gid is None:
                gid = self.cmap.get(ord(" "), ".notdef")
            units += self.hmtx[gid][0]
        return units * size / self.upm + ls * max(0, len(text) - 1)

    def baseline(self, top, line_h, size):
        content = (self.asc + self.desc) * size
        return top + (line_h - content) / 2 + self.asc * size


FONT_PATHS = {}
METRICS = {}


def m(font):
    if font not in METRICS:
        METRICS[font] = Metrics(FONT_PATHS[font])
    return METRICS[font]


def tw(text, font, size, ls=0.0):
    return m(font).width(text, size, ls)


def wrap(text, font, size, max_w, ls=0.0):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        cand = w if not cur else f"{cur} {w}"
        if cur and tw(cand, font, size, ls) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def subset_woff(font, chars):
    from fontTools import subset
    opts = subset.Options()
    opts.flavor = "woff"
    opts.layout_features = ["kern"]
    opts.hinting = False
    opts.desubroutinize = True
    opts.name_IDs = [1, 2]
    opts.notdef_outline = True
    f = subset.load_font(str(FONT_PATHS[font]), opts)
    s = subset.Subsetter(opts)
    s.populate(text="".join(sorted(chars)) + " ")
    s.subset(f)
    buf = io.BytesIO()
    subset.save_font(f, buf, opts)
    return base64.b64encode(buf.getvalue()).decode()


# ═══════════════════════════════════════════════════════════════════════════
# SVG TOOLKIT
# ═══════════════════════════════════════════════════════════════════════════

def n(v):
    if isinstance(v, float):
        v = round(v, 2)
        return str(int(v)) if v == int(v) else f"{v}"
    return str(v)


def esc(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


MARGIN = 12
CONTENT_W = 880

ANIM_CSS = """
.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.6s ease-out infinite}
@keyframes pulse{0%{transform:scale(1);opacity:.65}100%{transform:scale(2.7);opacity:0}}
.oil-glow{animation:oilglow 4s ease-in-out infinite}
@keyframes oilglow{0%,100%{opacity:.55}50%{opacity:.95}}
@media (prefers-reduced-motion:reduce){.pulse,.oil-glow{animation:none}}
"""


class Canvas:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.defs, self.els = [], []
        self.used = defaultdict(set)
        self.cache = {}
        self.count = 0
        self.animated = False

    def uid(self, prefix):
        self.count += 1
        return f"{prefix}{self.count}"

    def add(self, *els):
        self.els.extend(els)

    def text(self, x, y, s, font, size, fill, anchor="start", ls=0.0, extra=""):
        fam, weight = font
        self.used[font].update(s)
        a = (
            f'x="{n(x)}" y="{n(y)}" font-family="{FAMILIES[fam][0]}, '
            f'{FALLBACK[fam]}" font-weight="{weight}" font-size="{n(size)}" '
            f'fill="{fill}"'
        )
        if anchor != "start":
            a += f' text-anchor="{anchor}"'
        if ls:
            a += f' letter-spacing="{n(ls)}"'
        return f"<text {a}{extra}>{esc(s)}</text>"

    def text_box(self, x, top, s, font, size, fill, line_h=None, anchor="start", ls=0.0, extra=""):
        line_h = line_h or (m(font).asc + m(font).desc) * size
        return self.text(x, m(font).baseline(top, line_h, size), s, font, size, fill, anchor, ls, extra)

    def lines(self, x, top, lines, font, size, fill, line_h, anchor="start", ls=0.0):
        return [
            self.text_box(x, top + i * line_h, ln, font, size, fill, line_h, anchor, ls)
            for i, ln in enumerate(lines)
        ]

    def linear(self, stops, angle=180):
        key = ("lin", tuple(stops), angle)
        if key not in self.cache:
            gid = self.uid("g")
            a = math.radians(angle)
            sx, sy = math.sin(a), -math.cos(a)
            st = "".join(
                f'<stop offset="{n(o)}" stop-color="{c}"'
                f'{f" stop-opacity={chr(34)}{n(op)}{chr(34)}" if op != 1 else ""}/>'
                for o, c, op in [s if len(s) == 3 else (*s, 1) for s in stops]
            )
            self.defs.append(
                f'<linearGradient id="{gid}" x1="{n(.5 - sx / 2)}" '
                f'y1="{n(.5 - sy / 2)}" x2="{n(.5 + sx / 2)}" '
                f'y2="{n(.5 + sy / 2)}">{st}</linearGradient>'
            )
            self.cache[key] = gid
        return f"url(#{self.cache[key]})"

    def radial(self, stops, cx=0.5, cy=0.5, r=0.5):
        key = ("rad", tuple(stops), cx, cy, r)
        if key not in self.cache:
            gid = self.uid("r")
            st = "".join(
                f'<stop offset="{n(o)}" stop-color="{c}"'
                f'{f" stop-opacity={chr(34)}{n(op)}{chr(34)}" if op != 1 else ""}/>'
                for o, c, op in [s if len(s) == 3 else (*s, 1) for s in stops]
            )
            self.defs.append(
                f'<radialGradient id="{gid}" cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}">{st}</radialGradient>'
            )
            self.cache[key] = gid
        return f"url(#{self.cache[key]})"

    def shadow(self, dy=5, blur=7, color="#01030d", opacity=0.32):
        key = ("sh", dy, blur, color, opacity)
        if key not in self.cache:
            fid = self.uid("f")
            self.defs.append(
                f'<filter id="{fid}" x="-25%" y="-25%" width="150%" height="165%">'
                f'<feDropShadow dx="0" dy="{n(dy)}" stdDeviation="{n(blur)}" '
                f'flood-color="{color}" flood-opacity="{n(opacity)}"/></filter>'
            )
            self.cache[key] = fid
        return f'filter="url(#{self.cache[key]})"'

    def clip_rrect(self, x, y, w, h, r):
        cid = self.uid("c")
        self.defs.append(
            f'<clipPath id="{cid}"><rect x="{n(x)}" y="{n(y)}" '
            f'width="{n(w)}" height="{n(h)}" rx="{n(r)}"/></clipPath>'
        )
        return f'clip-path="url(#{cid})"'

    def render(self):
        faces = []
        for font, chars in sorted(self.used.items()):
            fam, weight = font
            faces.append(
                f"@font-face{{font-family:'{FAMILIES[fam][0]}';"
                f"font-weight:{weight};src:url(data:font/woff;base64,"
                f"{subset_woff(font, chars)}) format('woff')}}"
            )
        css = "".join(faces) + (ANIM_CSS if self.animated else "")
        label = esc(self.label)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'text-rendering="geometricPrecision" viewBox="0 0 {n(self.w)} '
            f'{n(self.h)}" width="{n(self.w)}" height="{n(self.h)}" role="img" '
            f'aria-label="{label}"><title>{label}</title>'
            f"<style>{css}</style><defs>{''.join(self.defs)}</defs>"
            + "".join(self.els) + "</svg>\n"
        )


def rrect(x, y, w, h, r, fill, extra=""):
    return f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" rx="{n(r)}" fill="{fill}"{extra}/>'


def icon(path_d, x, y, size, stroke=None, fill="none", width=2.3):
    s = size / 24
    st = (
        f' stroke="{stroke}" stroke-width="{n(width)}" stroke-linecap="round" stroke-linejoin="round"'
        if stroke else ""
    )
    paths = "".join(f'<path d="{d}"/>' for d in path_d)
    return f'<g transform="translate({n(x)} {n(y)}) scale({n(s)})" fill="{fill}"{st}>{paths}</g>'


ICON = {
    "arrow": ["M7 17L17 7", "M9 7h8v8"],
    "mail": ["M4 6h16v12H4z", "M4 7l8 6 8-6"],
    "layers": ["M4 5h16v4H4z", "M4 11h16v4H4z", "M4 17h10v2H4z"],
    "award": ["M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12z", "M8.21 13.89 7 23l5-3 5 3-1.21-9.12"],
}


def pill(cv, x, cy, label, font, size, h, pad, bg, fg, dot=None, gap=8, dot_size=7, extra=""):
    w = pad * 2 + tw(label, font, size) + (dot_size + gap if dot else 0)
    els = [rrect(x, cy - h / 2, w, h, h / 2, bg, extra)]
    tx = x + pad
    if dot:
        els.append(f'<circle cx="{n(tx + dot_size / 2)}" cy="{n(cy)}" r="{n(dot_size / 2)}" fill="{dot}"/>')
        tx += dot_size + gap
    els.append(cv.text_box(tx, cy - h / 2, label, font, size, fg, h))
    return els, w


def flow(items, max_w, gap_x, gap_y, item_h):
    x = y = 0
    out = []
    for w, payload in items:
        if x and x + w > max_w:
            x, y = 0, y + item_h + gap_y
        out.append((x, y, payload, w))
        x += w + gap_x
    return out, y + item_h


# ═══════════════════════════════════════════════════════════════════════════
# 3D-LIT IMPASTO OIL-PAINTING CANVAS ENGINE ("Cuadro al Óleo")
# ═══════════════════════════════════════════════════════════════════════════

def _paint_spline_stroke(rgb, height_map, pts, half_w, col_rgb, bristle_freq, phase, alpha_max, accent_tint):
    """Rasterize a continuous curved bristle-brush oil stroke with 3D ridge height."""
    H_img, W_img = height_map.shape
    xs, ys = pts[:, 0], pts[:, 1]
    pad = half_w + 4.0
    x0 = max(0, int(math.floor(xs.min() - pad)))
    y0 = max(0, int(math.floor(ys.min() - pad)))
    x1 = min(W_img, int(math.ceil(xs.max() + pad)))
    y1 = min(H_img, int(math.ceil(ys.max() + pad)))
    if x1 <= x0 or y1 <= y0:
        return

    # Vectorized closest-point projection onto piecewise segments in bounding box
    gx = np.arange(x0, x1, dtype=np.float32)[None, :, None]
    gy = np.arange(y0, y1, dtype=np.float32)[:, None, None]

    ax = xs[:-1][None, None, :]
    ay = ys[:-1][None, None, :]
    bx = xs[1:][None, None, :]
    by = ys[1:][None, None, :]
    dx = bx - ax
    dy = by - ay
    seg_len2 = np.maximum(dx * dx + dy * dy, 1e-4)

    t_seg = np.clip(((gx - ax) * dx + (gy - ay) * dy) / seg_len2, 0.0, 1.0)
    px = ax + t_seg * dx
    py = ay + t_seg * dy
    vx = gx - px
    vy = gy - py
    dist2 = vx * vx + vy * vy

    idx = np.argmin(dist2, axis=2)
    iy, ix = np.ogrid[: (y1 - y0), : (x1 - x0)]
    min_d2 = dist2[iy, ix, idx]
    inv_l = 1.0 / np.sqrt(seg_len2[0, 0, idx])
    sdx = dx[0, 0, idx] * inv_l
    sdy = dy[0, 0, idx] * inv_l
    rvx = vx[iy, ix, idx]
    rvy = vy[iy, ix, idx]

    # Signed perpendicular coordinate u in [-1, 1] and normalized arc position s in [0, 1]
    perp = (rvx * (-sdy) + rvy * sdx) / half_w
    s_best = (idx.astype(np.float32) + t_seg[iy, ix, idx]) / float(len(xs) - 1)

    mask = np.abs(perp) < 1.05
    if not np.any(mask):
        return

    # Longitudinal bristle tracks & feathery irregular brush ends (zero round pills!)
    bristle_wave = np.sin(perp * bristle_freq + phase) * 0.55 + np.sin(perp * (bristle_freq * 2.13) + phase * 1.7) * 0.45
    tip_taper = np.clip((s_best - 0.03 - 0.05 * bristle_wave) * 9.0, 0.0, 1.0) * np.clip((0.97 - s_best - 0.05 * bristle_wave) * 9.0, 0.0, 1.0)
    cross_prof = np.clip(1.0 - (np.abs(perp) / 1.0) ** 2.2, 0.0, 1.0)

    # Edge ridges mimic thick paint pushed outward by stiff hog-bristle brush
    edge_ridge = 0.25 * np.exp(-((np.abs(perp) - 0.72) ** 2) / 0.04)
    grooves = 0.68 + 0.32 * bristle_wave
    alpha = np.clip(cross_prof * tip_taper * (0.72 + 0.34 * grooves) * alpha_max, 0.0, 1.0)
    h_bump = cross_prof * tip_taper * (0.48 + 0.52 * grooves + edge_ridge)

    # Multi-pigment loading across individual bristle streams
    col = np.array(col_rgb, dtype=np.float32)[None, None, :] + accent_tint * bristle_wave[:, :, None]
    col = np.clip(col, 0.0, 255.0)

    a3 = alpha[:, :, None]
    rgb[y0:y1, x0:x1] = rgb[y0:y1, x0:x1] * (1.0 - a3) + col * a3
    # Raised paint stacks naturally over lower dried layers
    h_sub = height_map[y0:y1, x0:x1]
    height_map[y0:y1, x0:x1] = h_sub * (1.0 - 0.65 * alpha) + (h_sub * 0.35 + h_bump * 1.35) * (0.65 + 0.35 * alpha)


def render_oil_canvas(w, h, theme_key, seed, preset="card", tint_rgb=None):
    """Synthesize a bespoke 3D-lit impasto oil canvas JPEG data URI with caching."""
    OIL_CACHE.mkdir(parents=True, exist_ok=True)
    key_str = f"{w}x{h}-{theme_key}-{seed}-{preset}-{tint_rgb}"
    hsh = hashlib.md5(key_str.encode()).hexdigest()[:16]
    cache_file = OIL_CACHE / f"oil_{hsh}.jpg"
    if cache_file.exists():
        return "data:image/jpeg;base64," + base64.b64encode(cache_file.read_bytes()).decode()

    T = THEMES[theme_key]
    dark = theme_key == "dark"
    rng = np.random.default_rng(seed)

    # Render at crisp working scale (1.0 for normal cards, slightly softer for giant cards keeps <60KB)
    scale = 1.0 if (w * h <= 480000) else 0.85
    pw = max(64, int(round(w * scale)))
    ph = max(48, int(round(h * scale)))

    yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
    nx_u = xx / max(1, pw - 1)
    ny_u = yy / max(1, ph - 1)

    if preset == "cream_impasto":
        # Thick carved alabaster/cream oil paint texture for IB monogram (like Marco Azul Impasto.png)
        top_c = np.array((254, 250, 244), dtype=np.float32)
        bot_c = np.array((244, 237, 226), dtype=np.float32)
        rgb = top_c[None, None, :] * (1.0 - ny_u[:, :, None]) + bot_c[None, None, :] * ny_u[:, :, None]
        height_map = 0.04 * np.sin(xx * 0.50) + 0.03 * np.sin(yy * 0.50)
        swatches = [(255, 253, 249), (250, 244, 235), (241, 232, 218), (255, 255, 252)]
        n_strokes = 68
    else:
        top_c = np.array(T["oil_base_top"], dtype=np.float32)
        bot_c = np.array(T["oil_base_bot"], dtype=np.float32)
        diag = 0.55 * nx_u + 0.45 * ny_u
        rgb = top_c[None, None, :] * (1.0 - diag[:, :, None]) + bot_c[None, None, :] * diag[:, :, None]
        if tint_rgb is not None:
            tr = np.array(tint_rgb, dtype=np.float32)[None, None, :]
            rgb = rgb * 0.78 + tr * 0.22
        # Subtle organic flax canvas tooth without periodic moire stripes
        height_map = (0.025 * rng.standard_normal((ph, pw))).astype(np.float32)
        swatches = list(T["oil_swatches"])
        if tint_rgb is not None:
            swatches.append(tuple(min(255, int(c)) for c in tint_rgb))
        if preset == "medallion":
            n_strokes = 66
        elif ph < 110:
            n_strokes = 58
        elif preset == "mini":
            n_strokes = 68
        else:
            n_strokes = 120

    # Generate organic multi-tier curved oil brushstrokes
    ts = np.linspace(0.0, 1.0, 11, dtype=np.float32)
    b0 = (1 - ts) ** 3
    b1 = 3 * ts * ((1 - ts) ** 2)
    b2 = 3 * (ts ** 2) * (1 - ts)
    b3 = ts ** 3

    for i in range(n_strokes):
        tier = i / n_strokes
        if preset == "cream_impasto":
            half_w = float(rng.uniform(3.8, 9.5))
            col = swatches[int(rng.integers(0, len(swatches)))]
            alpha = float(rng.uniform(0.62, 0.90))
            p0 = np.array([rng.uniform(-20, pw + 20), rng.uniform(-20, ph + 20)])
            ang = rng.choice([0.04, 1.54, -0.08]) + rng.uniform(-0.18, 0.18)
            L = float(rng.uniform(34, 88))
            d_end = np.array([math.cos(ang), math.sin(ang)]) * L
            perp_n = np.array([-d_end[1], d_end[0]]) * float(rng.uniform(-0.22, 0.22))
            tint_var = np.array([12.0, 10.0, 8.0], dtype=np.float32)
        elif tier < 0.28:
            # Tier 1: Broad sweeping palette-knife foundation covering canvas deeply
            half_w = float(rng.uniform(22, 42)) * min(1.0, ph / 120.0 + 0.35)
            col = swatches[int(rng.integers(0, min(4, len(swatches))))]
            alpha = float(rng.uniform(0.58, 0.84))
            p0 = np.array([rng.uniform(-30, pw + 30), rng.uniform(-30, ph + 30)])
            ang = float(rng.uniform(-0.85, 0.85)) + (math.pi if rng.random() < 0.5 else 0.0)
            L = float(rng.uniform(pw * 0.22, pw * 0.55))
            d_end = np.array([math.cos(ang), math.sin(ang)]) * L
            perp_n = np.array([-d_end[1], d_end[0]]) * float(rng.uniform(-0.42, 0.42))
            tint_var = np.array([9.0, 12.0, 18.0], dtype=np.float32)
        elif tier < 0.84:
            # Tier 2: Expressive swirling cobalt/ultramarine brushwork (concentrated along rims & eddies)
            half_w = float(rng.uniform(8.5, 22)) * min(1.0, ph / 140.0 + 0.4)
            col = swatches[int(rng.integers(1, len(swatches)))]
            alpha = float(rng.uniform(0.68, 0.92))
            if preset == "medallion" or rng.random() < 0.42:
                # Swirling vortex strokes around center or border
                cx, cy = pw * (0.72 if preset == "hero" else 0.5), ph * 0.5
                ang_r = float(rng.uniform(0, 2 * math.pi))
                rad = float(rng.uniform(0.18, 0.55)) * min(pw, ph)
                p0 = np.array([cx + math.cos(ang_r) * rad, cy + math.sin(ang_r) * rad])
                tang = ang_r + math.pi / 2 + float(rng.uniform(-0.45, 0.45))
                L = float(rng.uniform(55, min(pw, ph) * 0.72))
                d_end = np.array([math.cos(tang), math.sin(tang)]) * L
                perp_n = np.array([-d_end[1], d_end[0]]) * float(rng.uniform(0.15, 0.48) * (-1 if rng.random() < 0.3 else 1))
            else:
                # Border-hugging dramatic Marco Azul Impasto frame strokes
                edge = i % 4
                if edge == 0:
                    p0 = np.array([rng.uniform(0, pw), rng.uniform(-8, ph * 0.18)])
                elif edge == 1:
                    p0 = np.array([rng.uniform(0, pw), rng.uniform(ph * 0.82, ph + 8)])
                elif edge == 2:
                    p0 = np.array([rng.uniform(-8, pw * 0.16), rng.uniform(0, ph)])
                else:
                    p0 = np.array([rng.uniform(pw * 0.72, pw + 8), rng.uniform(0, ph)])
                ang = float(rng.uniform(-1.1, 1.1))
                L = float(rng.uniform(60, 185))
                d_end = np.array([math.cos(ang), math.sin(ang)]) * L
                perp_n = np.array([-d_end[1], d_end[0]]) * float(rng.uniform(-0.45, 0.45))
            tint_var = np.array([12.0, 16.0, 24.0], dtype=np.float32)
        else:
            # Tier 3: Thick impasto ridge highlights & occasional warm museum cream/gold flecks
            half_w = float(rng.uniform(3.8, 9.5))
            if rng.random() < 0.24:
                col = T["oil_flecks"][int(rng.integers(0, len(T["oil_flecks"])))]
                alpha = float(rng.uniform(0.32, 0.58))
            else:
                col = swatches[-1 if rng.random() < 0.65 else -2]
                alpha = float(rng.uniform(0.72, 0.94))
            p0 = np.array([rng.uniform(0, pw), rng.uniform(0, ph)])
            ang = float(rng.uniform(-1.3, 1.3))
            L = float(rng.uniform(28, 86))
            d_end = np.array([math.cos(ang), math.sin(ang)]) * L
            perp_n = np.array([-d_end[1], d_end[0]]) * float(rng.uniform(-0.42, 0.42))
            tint_var = np.array([14.0, 18.0, 24.0], dtype=np.float32)

        p3 = p0 + d_end
        p1 = p0 + d_end * 0.33 + perp_n + np.array([rng.uniform(-14, 14), rng.uniform(-14, 14)])
        p2 = p0 + d_end * 0.67 + perp_n * float(rng.uniform(0.3, 1.1))
        pts = (
            b0[:, None] * p0[None, :]
            + b1[:, None] * p1[None, :]
            + b2[:, None] * p2[None, :]
            + b3[:, None] * p3[None, :]
        ).astype(np.float32)

        freq = float(rng.uniform(7.5, 13.5))
        phase = float(rng.uniform(0.0, 2.0 * math.pi))
        _paint_spline_stroke(rgb, height_map, pts, half_w, col, freq, phase, alpha, tint_var)

    # 3D Directional Gallery Impasto Relief Lighting from top-left key light
    dy, dx = np.gradient(height_map)
    relief = 3.8 if preset != "cream_impasto" else 2.8
    nx_n = -dx * relief
    ny_n = -dy * relief
    nz_n = np.ones_like(nx_n)
    inv_len = 1.0 / np.sqrt(nx_n * nx_n + ny_n * ny_n + nz_n * nz_n)
    nx_n *= inv_len
    ny_n *= inv_len
    nz_n *= inv_len

    lx, ly, lz = -0.58, -0.72, 0.38
    norm_l = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / norm_l, ly / norm_l, lz / norm_l

    diff = np.clip(nx_n * lx + ny_n * ly + nz_n * lz, 0.0, 1.0)
    # Paint shadows use deep blue/ultramarine glazes rather than muddy black/grey
    if preset == "cream_impasto":
        shade = 1.01 + (diff - 0.42) * 0.28
        rgb = rgb * shade[:, :, None]
    elif dark:
        shade = 1.0 + (diff - 0.34) * T["oil_light_amt"]
        rgb = rgb * shade[:, :, None]
    else:
        sh_tint = np.array((24, 66, 156), dtype=np.float32)[None, None, :]
        sh_mix = np.clip((0.36 - diff) * 0.42, 0.0, 0.24)[:, :, None]
        hi_mul = (1.0 + np.clip(diff - 0.36, 0.0, 1.0) * 0.42)[:, :, None]
        rgb = rgb * (1.0 - sh_mix) + sh_tint * sh_mix
        rgb = rgb * hi_mul

    # Glossy linseed-oil Blinn-Phong specular glint on thick impasto ridges
    hx, hy, hz = lx, ly, lz + 1.0
    norm_h = math.sqrt(hx * hx + hy * hy + hz * hz)
    spec = np.clip(nx_n * (hx / norm_h) + ny_n * (hy / norm_h) + nz_n * (hz / norm_h), 0.0, 1.0) ** 20
    gloss_col = np.array((250, 246, 238) if preset == "cream_impasto" else (196, 224, 255) if dark else (255, 252, 246), dtype=np.float32)
    gloss_amt = 0.20 if preset == "cream_impasto" else T["oil_gloss"]

    rgb = rgb + (spec * gloss_amt * 255.0)[:, :, None] * (gloss_col[None, None, :] / 255.0)

    # Gentle gallery vignette around frame perimeter (ultramarine-tinted on light mode)
    if preset != "cream_impasto":
        vig = np.clip(1.0 - 0.22 * (((nx_u - 0.5) * 1.9) ** 2 + ((ny_u - 0.5) * 1.9) ** 2) ** 1.4, 0.74, 1.0)
        if dark:
            rgb *= vig[:, :, None]
        else:
            rim_blue = np.array((32, 80, 178), dtype=np.float32)[None, None, :]
            rm = (1.0 - vig)[:, :, None] * 0.72
            rgb = rgb * (1.0 - rm) + rim_blue * rm

    out_im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    if (pw, ph) != (w, h):
        out_im = out_im.resize((w, h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    out_im.save(buf, format="JPEG", quality=86 if preset != "cream_impasto" else 90, optimize=True, subsampling=1)
    data = buf.getvalue()
    cache_file.write_bytes(data)
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def oil_box(cv, x, y, w, h, r, theme_key, seed=7, preset="card", tint_rgb=None, frame=True):
    """Render a real 3D-lit impasto oil-painting canvas box with double gallery frame."""
    T = THEMES[theme_key]
    iw, ih = int(round(w)), int(round(h))
    uri = render_oil_canvas(iw, ih, theme_key, seed=seed, preset=preset, tint_rgb=tint_rgb)
    clip = cv.clip_rrect(x, y, w, h, r)
    out = []
    if frame:
        sh = cv.shadow(6, 9, T["shadow_c"], T["shadow_op"])
        out.append(rrect(x, y, w, h, r, T["bg"][0], " " + sh))
    out.append(
        f'<g {clip}>'
        f'<image x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" href="{uri}" preserveAspectRatio="none"/>'
        f'</g>'
    )
    if frame:
        # Museum gallery double rim: cobalt bezel + fine antique gold inner fillet
        fg = cv.linear([(0, T["frame_grad"][0]), (0.5, T["frame_grad"][1]), (1, T["frame_grad"][2])], 140)
        gold_g = cv.linear([(0, T["gold_rim"][0]), (0.5, T["gold_rim"][1]), (1, T["gold_rim"][2])], 135)
        out.append(rrect(x + 0.9, y + 0.9, w - 1.8, h - 1.8, r - 0.6, "none", f' stroke="{fg}" stroke-width="2.0"'))
        out.append(
            rrect(
                x + 3.8, y + 3.8, w - 7.6, h - 7.6, max(4, r - 3), "none",
                f' stroke="{gold_g}" stroke-opacity="{0.52 if theme_key == "dark" else 0.45}" stroke-width="1.0"'
            )
        )
    return out


# ═══════════════════════════════════════════════════════════════════════════
# LOGO, SPRITE & MONOGRAM HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def encode_png_fit(rel_path, max_w, max_h):
    """Aspect-preserving RGBA PNG resize and base64 URI."""
    p = HERE / rel_path
    im = Image.open(p).convert("RGBA")
    ow, oh = im.size
    sc = min(max_w / ow, max_h / oh)
    rw, rh = max(1, int(round(ow * sc))), max(1, int(round(oh * sc)))
    im = im.resize((rw, rh), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), rw, rh


def encode_badge_png(rel_path, size=92):
    p = HERE / rel_path
    im = Image.open(p).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def embed_sprite(cv, sprite_name, x, y, target_h, clip_attr="", shadow=True, flip_x=False):
    """Inline one of Ignacio's portfolio vector sprites crisply inside card bounds."""
    raw = (HERE / "sprites" / f"{sprite_name}.svg").read_text(encoding="utf-8")
    m_vb = re.search(r'viewBox="0\s+0\s+(\d+)\s+(\d+)"', raw)
    vw, vh = (int(m_vb.group(1)), int(m_vb.group(2))) if m_vb else (250, 390)
    inner = re.sub(r"<\?xml[^>]*\?>", "", raw)
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.S)
    inner = re.sub(r"</?svg[^>]*>", "", inner).strip()
    sc = target_h / vh
    rw = vw * sc
    sh_attr = f" {cv.shadow(6, 7, '#01030d', 0.42)}" if shadow else ""
    if flip_x:
        xf = f"translate({n(x + rw)} {n(y)}) scale({n(-sc)} {n(sc)})"
    else:
        xf = f"translate({n(x)} {n(y)}) scale({n(sc)})"
    g = f'<g transform="{xf}"{sh_attr}>{inner}</g>'
    if clip_attr:
        return f'<g {clip_attr}>{g}</g>', rw
    return g, rw


def modern_ib_logo(cv, x, y, size, theme_key="dark", medallion=True):
    """Ignacio's modern IB monogram in sculpted impasto oil paint."""
    BRACKETS = (
        "M1.92,33.53L1.92,98.78L66.09,98.78L66.09,91.30L9.60,91.30L9.47,91.17L9.47,33.53Z "
        "M34.55,0.90L34.55,8.38L91.04,8.38L91.17,8.51L91.17,66.15L98.72,66.15L98.72,0.90Z"
    )
    MONO = (
        "M38.39,16.06L38.39,84.64L67.18,84.58L69.80,84.26L73.45,83.37L76.07,82.34L78.57,81.00"
        "L81.51,78.76L83.17,77.03L84.84,74.73L85.86,72.74L86.69,70.51L87.20,68.33L87.46,66.15"
        "L87.40,63.08L86.95,60.59L85.73,57.20L84.58,55.09L83.05,52.91L81.32,51.06L78.63,49.01"
        "L76.46,47.92L78.76,46.32L80.17,44.91L81.13,43.70L82.79,40.75L83.81,37.49L84.07,35.51"
        "L84.07,33.21L83.75,30.58L82.85,27.38L81.57,24.82L80.42,23.22L79.21,21.88L77.80,20.67"
        "L76.14,19.51L73.70,18.23L72.10,17.59L69.23,16.76L66.28,16.25L64.11,16.06Z "
        "M50.61,54.32L65.71,54.25L68.39,54.70L70.12,55.34L71.27,55.98L72.36,56.81L73.77,58.35"
        "L74.66,59.88L75.18,61.42L75.37,62.57L75.30,65.26L74.98,66.86L74.15,68.84L73.38,69.93"
        "L71.98,71.21L70.44,72.04L68.39,72.68L66.35,72.94L50.67,72.94Z "
        "M50.61,27.19L50.74,27.06L63.98,27.13L66.67,27.64L67.95,28.09L69.42,28.85L70.19,29.43"
        "L71.47,30.77L72.23,32.12L72.68,33.53L72.81,34.42L72.68,37.24L72.30,38.71L71.66,40.05"
        "L70.89,41.07L69.42,42.29L67.75,43.06L66.28,43.44L63.72,43.70L50.74,43.70L50.61,43.57Z "
        "M16.76,16.06L16.76,84.64L29.05,84.64L29.05,16.06Z"
    )
    els = []
    if medallion:
        ms = int(round(size))
        med_uri = render_oil_canvas(ms, ms, "dark", seed=991, preset="medallion")
        clip = cv.clip_rrect(x, y, size, size, size * 0.16)
        sh = cv.shadow(8, 11, "#01030d", 0.48 if theme_key == "dark" else 0.28)
        els.append(rrect(x, y, size, size, size * 0.16, "#020619", " " + sh))
        els.append(
            f'<g {clip}>'
            f'<image x="{n(x)}" y="{n(y)}" width="{n(size)}" height="{n(size)}" href="{med_uri}" preserveAspectRatio="none"/>'
            f'</g>'
        )
        fg = cv.linear([(0, "#e2c48c"), (0.5, "#6095de"), (1, "#183e85")], 135)
        els.append(
            rrect(x + 1, y + 1, size - 2, size - 2, size * 0.16 - 1, "none", f' stroke="{fg}" stroke-width="2.4"')
        )
        pad = size * 0.13
        sc = (size - 2 * pad) / 100.0
        tx, ty = x + pad, y + pad
    else:
        sc = size / 100.0
        tx, ty = x, y

    # Cream impasto texture clipped directly onto IB paths (no <g> inside <clipPath>, valid across all SVG renderers)
    cream_uri = render_oil_canvas(200, 200, "dark", seed=406, preset="cream_impasto")
    ib_cid = cv.uid("ib")
    cv.defs.append(
        f'<clipPath id="{ib_cid}" clipPathUnits="userSpaceOnUse">'
        f'<path transform="translate({n(tx)} {n(ty)}) scale({n(sc)})" d="{BRACKETS}" clip-rule="evenodd"/>'
        f'<path transform="translate({n(tx)} {n(ty)}) scale({n(sc)})" d="{MONO}" clip-rule="evenodd"/></clipPath>'
    )
    bx0 = tx - 2
    by0 = ty - 2
    bw = 100 * sc + 4
    impasto = [
        f'<g transform="translate({n(tx + 2.6)} {n(ty + 3.2)}) scale({n(sc)})" opacity="0.78">'
        f'<path d="{BRACKETS}" fill="#01030f" fill-rule="evenodd"/>'
        f'<path d="{MONO}" fill="#01030f" fill-rule="evenodd"/></g>',
        f'<g transform="translate({n(tx + 0.9)} {n(ty + 1.2)}) scale({n(sc)})">'
        f'<path d="{BRACKETS}" fill="#706659" fill-rule="evenodd"/>'
        f'<path d="{MONO}" fill="#706659" fill-rule="evenodd"/></g>',
        f'<g clip-path="url(#{ib_cid})">'
        f'<image x="{n(bx0)}" y="{n(by0)}" width="{n(bw)}" height="{n(bw)}" href="{cream_uri}" preserveAspectRatio="none"/>'
        f'</g>',
        f'<g transform="translate({n(tx - 0.35)} {n(ty - 0.45)}) scale({n(sc)})" opacity="0.58">'
        f'<path d="{BRACKETS}" fill="none" stroke="#fffdf9" stroke-width="1.25" fill-rule="evenodd"/>'
        f'<path d="{MONO}" fill="none" stroke="#fffdf9" stroke-width="1.15" fill-rule="evenodd"/></g>',
    ]
    els.extend(impasto)
    return "".join(els)


def painted_motif(cv, x, y, size, kind, accent, theme_key):
    """Compact oil-canvas mini-illustration badge for project cards."""
    dark = theme_key == "dark"
    bg = "#07173f" if dark else "#ffffff"
    stroke = accent
    els = [
        rrect(x, y, size, size, size * 0.28, bg, f' fill-opacity="{0.86 if dark else 0.92}" stroke="{stroke}" stroke-opacity="0.48" stroke-width="1.4"'),
    ]
    cx, cy = x + size / 2, y + size / 2
    s = size * 0.3
    T = THEMES[theme_key]
    if kind == "grid":
        els += [
            rrect(cx - s, cy - s, s * 0.85, s * 1.15, 2.5, stroke, ' fill-opacity="0.85"'),
            rrect(cx + s * 0.15, cy - s, s * 0.85, s * 0.75, 2.5, T["gold"], ' fill-opacity="0.9"'),
            rrect(cx + s * 0.15, cy + s * 0.05, s * 0.85, s * 0.95, 2.5, stroke, ' fill-opacity="0.45"'),
            rrect(cx - s, cy + s * 0.35, s * 0.85, s * 0.65, 2.5, stroke, ' fill-opacity="0.45"'),
        ]
    elif kind == "nodes":
        els += [
            f'<path d="M{n(cx - s)} {n(cy)} L{n(cx)} {n(cy - s * 0.75)} L{n(cx + s)} {n(cy)} L{n(cx)} {n(cy + s * 0.75)} Z" fill="none" stroke="{stroke}" stroke-width="1.8"/>',
            f'<circle cx="{n(cx - s)}" cy="{n(cy)}" r="3.5" fill="{T["gold"]}"/>',
            f'<circle cx="{n(cx + s)}" cy="{n(cy)}" r="3.5" fill="{stroke}"/>',
            f'<circle cx="{n(cx)}" cy="{n(cy - s * 0.75)}" r="3" fill="{stroke}"/>',
            f'<circle cx="{n(cx)}" cy="{n(cy + s * 0.75)}" r="3" fill="{stroke}"/>',
        ]
    elif kind == "radar":
        els += [
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(s * 0.95)}" fill="none" stroke="{stroke}" stroke-opacity="0.35" stroke-width="1.4"/>',
            f'<path d="M{n(cx - s)} {n(cy + 2)} L{n(cx - s * .35)} {n(cy + 2)} L{n(cx - s * .1)} {n(cy - s * .7)} L{n(cx + s * .25)} {n(cy + s * .65)} L{n(cx + s * .5)} {n(cy - 2)} L{n(cx + s)} {n(cy - 2)}" fill="none" stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
        ]
    elif kind == "pin":
        els += [
            f'<path d="M{n(cx)} {n(cy + s)} C{n(cx - s * .9)} {n(cy + 2)} {n(cx - s * .8)} {n(cy - s * .95)} {n(cx)} {n(cy - s * .95)} C{n(cx + s * .8)} {n(cy - s * .95)} {n(cx + s * .9)} {n(cy + 2)} {n(cx)} {n(cy + s)}Z" fill="{stroke}" fill-opacity="0.28" stroke="{stroke}" stroke-width="1.8"/>',
            f'<circle cx="{n(cx)}" cy="{n(cy - s * .22)}" r="3.2" fill="{T["gold"]}"/>',
        ]
    elif kind == "eye":
        els += [
            f'<path d="M{n(cx - s * 1.05)} {n(cy)} Q{n(cx)} {n(cy - s * 0.9)} {n(cx + s * 1.05)} {n(cy)} Q{n(cx)} {n(cy + s * 0.9)} {n(cx - s * 1.05)} {n(cy)}Z" fill="none" stroke="{stroke}" stroke-width="1.8"/>',
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(s * 0.42)}" fill="{stroke}"/>',
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(s * 0.16)}" fill="{T["gold"]}"/>',
        ]
    elif kind == "gitgraph":
        els += [
            f'<line x1="{n(cx - s * 0.55)}" y1="{n(cy - s * 0.8)}" x2="{n(cx - s * 0.55)}" y2="{n(cy + s * 0.8)}" stroke="{stroke}" stroke-width="2" stroke-linecap="round"/>',
            f'<path d="M{n(cx - s * 0.55)} {n(cy + s * 0.25)} Q{n(cx - s * 0.55)} {n(cy - s * 0.25)} {n(cx + s * 0.5)} {n(cy - s * 0.25)} L{n(cx + s * 0.5)} {n(cy - s * 0.65)}" fill="none" stroke="{T["gold"]}" stroke-width="2" stroke-linecap="round"/>',
            f'<circle cx="{n(cx - s * 0.55)}" cy="{n(cy - s * 0.72)}" r="3.4" fill="{stroke}"/>',
            f'<circle cx="{n(cx - s * 0.55)}" cy="{n(cy + s * 0.5)}" r="3.4" fill="{stroke}"/>',
            f'<circle cx="{n(cx + s * 0.5)}" cy="{n(cy - s * 0.55)}" r="3.4" fill="{T["gold"]}"/>',
        ]
    elif kind == "dualsense":
        els += [
            f'<path d="M{n(cx - s * 0.9)} {n(cy + s * 0.45)} C{n(cx - s * 0.85)} {n(cy - s * 0.4)} {n(cx - s * 0.25)} {n(cy - s * 0.55)} {n(cx)} {n(cy - s * 0.35)} C{n(cx + s * 0.25)} {n(cy - s * 0.55)} {n(cx + s * 0.85)} {n(cy - s * 0.4)} {n(cx + s * 0.9)} {n(cy + s * 0.45)} Q{n(cx + s * 0.65)} {n(cy + s * 0.65)} {n(cx + s * 0.35)} {n(cy + s * 0.25)} H{n(cx - s * 0.35)} Q{n(cx - s * 0.65)} {n(cy + s * 0.65)} {n(cx - s * 0.9)} {n(cy + s * 0.45)} Z" fill="{stroke}" fill-opacity="0.22" stroke="{stroke}" stroke-width="1.7" stroke-linejoin="round"/>',
            f'<path d="M{n(cx - s * 0.35)} {n(cy - s * 0.15)} L{n(cx + s * 0.35)} {n(cy - s * 0.15)}" stroke="{T["gold"]}" stroke-width="2.2" stroke-linecap="round"/>',
        ]
    elif kind == "cursor":
        els += [
            f'<polygon points="{n(cx - s * 0.45)},{n(cy - s * 0.75)} {n(cx + s * 0.72)},{n(cy - s * 0.05)} {n(cx + s * 0.12)},{n(cy + s * 0.12)} {n(cx - s * 0.05)},{n(cy + s * 0.72)}" fill="{stroke}" fill-opacity="0.32" stroke="{stroke}" stroke-width="1.8" stroke-linejoin="round"/>',
            f'<circle cx="{n(cx + s * 0.55)}" cy="{n(cy + s * 0.55)}" r="3" fill="{T["gold"]}"/>',
            f'<circle cx="{n(cx + s * 0.72)}" cy="{n(cy - s * 0.65)}" r="2.2" fill="{stroke}"/>',
        ]
    elif kind == "prompt":
        els += [
            f'<path d="M{n(cx - s * .75)} {n(cy - s * .5)} L{n(cx - s * .1)} {n(cy)} L{n(cx - s * .75)} {n(cy + s * .5)}" fill="none" stroke="{stroke}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
            f'<line x1="{n(cx + s * .1)}" y1="{n(cy + s * .48)}" x2="{n(cx + s * .8)}" y2="{n(cy + s * .48)}" stroke="{T["gold"]}" stroke-width="2.4" stroke-linecap="round"/>',
        ]
    return "".join(els)


# ═══════════════════════════════════════════════════════════════════════════
# CARD BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def build_hero(theme_key):
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    hero = P["hero"]
    H = 500
    cv = Canvas(CONTENT_W + 2 * MARGIN, H, hero_alt())
    X = MARGIN
    cv.add(*oil_box(cv, X, 0, CONTENT_W, H, 28, theme_key, seed=11, preset="hero"))

    # Glazed reading panel on left so brushstrokes swirl cleanly all around
    if dark:
        cv.add(
            rrect(
                X + 20, 20, 464, H - 40, 22,
                cv.linear([(0, "#02071a", 0.64), (1, "#051238", 0.42)], 110),
                f' stroke="{T["plate_stroke"]}" stroke-opacity="0.48" stroke-width="1.1"',
            )
        )
    else:
        cv.add(
            rrect(
                X + 20, 20, 464, H - 40, 22,
                cv.linear([(0, "#fcfaf5", 0.86), (1, "#f2f6fd", 0.72)], 110),
                f' stroke="{T["plate_stroke"]}" stroke-opacity="0.72" stroke-width="1.2"',
            )
        )

    # Left typography
    hx, hy = X + 42, 40
    hello = cv.text_box(hx, hy, hero["hello"], HAND, 31, T["hand"], 34)
    hw = tw(hero["hello"], HAND, 31)
    cv.add(f'<g transform="rotate(-3 {n(hx + hw / 2)} {n(hy + 17)})">{hello}</g>')

    name_top, name_lh, name_size = hy + 38, 56, 52
    name_ls = -0.035 * name_size
    name_lines = wrap(hero["name"], DISPLAY, name_size, 424, name_ls)
    cv.add(*cv.lines(X + 40, name_top, name_lines, DISPLAY, name_size, T["ink"], name_lh, ls=name_ls))

    # Oil-brush swash
    sq_top = name_top + name_lh * len(name_lines) + 2
    swash_grad = cv.linear([(0, T["accent_strong"]), (0.6, T["accent"]), (1, T["gold"])], 90)
    cv.add(
        f'<path transform="translate({X + 42} {n(sq_top)})" '
        f'd="M3 10 C 32 3, 56 15, 88 8 S 144 3, 180 9 S 212 14, 240 8" '
        f'fill="none" stroke="{swash_grad}" stroke-width="5.2" stroke-linecap="round"/>'
    )

    lead_top = sq_top + 22
    lead = wrap(hero["lead"], sans(400), 15.8, 424)
    cv.add(*cv.lines(X + 40, lead_top, lead, sans(400), 15.8, T["body"], 23.5))

    pills_top = lead_top + 23.5 * len(lead) + 18
    items = []
    for i, label in enumerate(hero["chips"]):
        live = i == 0
        w = 24 + tw(label, sans(600), 13) + (16 if live else 0)
        items.append((w, (label, live)))
    placed, _ = flow(items, 434, 8, 9, 32)
    sh = cv.shadow(3, 5, T["shadow_c"], 0.25 if dark else 0.12)
    for px, py, (label, live), w in placed:
        x0, cy = X + 40 + px, pills_top + py + 16
        cv.add(rrect(x0, cy - 16, w, 32, 16, T["pill_bg"], f' stroke="{T["pill_stroke"]}" stroke-width="1.2" {sh}'))
        tx = x0 + 12
        if live:
            cv.animated = True
            dot_c = "#60a5fa" if dark else "#1d4ed8"
            cv.add(
                f'<circle class="pulse" cx="{n(tx + 4)}" cy="{n(cy)}" r="4" fill="{dot_c}" fill-opacity=".55"/>',
                f'<circle cx="{n(tx + 4)}" cy="{n(cy)}" r="7.5" fill="{dot_c}" fill-opacity=".2"/>',
                f'<circle cx="{n(tx + 4)}" cy="{n(cy)}" r="4" fill="{dot_c}"/>',
            )
            tx += 16
        cv.add(cv.text_box(tx, cy - 16, label, sans(600), 13, T["pill_fg"], 32))

    # Right composition: Oil IB Medallion top-right, Waving Ignacio sprite bottom-left, studio note + pills bottom-right
    mx, my, msize = X + 622, 42, 198
    aura = cv.radial([(0, T["accent_strong"], 0.36 if dark else 0.24), (1, T["accent_strong"], 0)], 0.5, 0.5, 0.5)
    cv.add(f'<circle class="oil-glow" cx="{n(mx + msize / 2)}" cy="{n(my + msize / 2)}" r="146" fill="{aura}"/>')
    cv.animated = True
    cv.add(
        f'<g transform="rotate(2.2 {n(mx + msize / 2)} {n(my + msize / 2)})">'
        + modern_ib_logo(cv, mx, my, msize, theme_key, medallion=True)
        + "</g>"
    )

    st = hero["stickers"]

    # Waving Ignacio Sprite docked smoothly onto bottom-right gallery frame
    card_inner_clip = cv.clip_rrect(X + 4, 4, CONTENT_W - 8, H - 8, 24)
    sprite_aura = cv.radial([(0, "#1d4ed8", 0.28), (1, "#1d4ed8", 0)], 0.5, 0.5, 0.5)
    cv.add(f'<circle cx="{X + 576}" cy="{H - 110}" r="118" fill="{sprite_aura}"/>')
    sp_g, _ = embed_sprite(cv, "ignacio_wave", X + 498, H - 220, 224, clip_attr=card_inner_clip)
    cv.add(sp_g)

    # "¡hola!" speech bubble next to Ignacio waving
    bw = tw(st["bubble"], HAND, 25) + 26
    bx, by, bh = X + 496, 206, 38
    bub_bg = "#faf6ef" if dark else "#ffffff"
    bub_fg = "#06102f"
    bub = [
        f'<rect x="{n(bx + 18)}" y="{n(by + bh - 8)}" width="12" height="12" fill="{bub_bg}" transform="rotate(45 {n(bx + 24)} {n(by + bh - 2)})"/>',
        rrect(bx, by, bw, bh, 17, bub_bg),
        cv.text_box(bx + 13, by + 5, st["bubble"], HAND, 25, bub_fg, 28),
    ]
    cv.add(f'<g transform="rotate(-4 {n(bx + bw / 2)} {n(by + bh / 2)})" {cv.shadow(5, 6, T["shadow_c"], 0.25)}>' + "".join(bub) + "</g>")

    # Handwritten studio note + upward arrow pointing directly to IB medallion
    nw = tw(st["note"], HAND, 23) + 24
    nx_note = X + 670
    ny_note = 262
    cv.add(
        f'<g transform="translate({nx_note - 26} {ny_note - 16})" fill="none" stroke="{T["hand"]}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M10 28 C 6 16, 10 8, 22 2"/><path d="M22 2 L 13 4"/><path d="M22 2 L 24 11"/></g>'
    )
    note_bg = rrect(nx_note, ny_note, nw, 30, 15, T["plate"], f' fill-opacity="{0.76 if dark else 0.90}" stroke="{T["plate_stroke"]}" stroke-opacity="0.55" stroke-width="1"')
    note = cv.text_box(nx_note + 12, ny_note + 1, st["note"], HAND, 23, T["hand"], 28)
    cv.add(f'<g transform="rotate(-2.5 {n(nx_note + nw / 2)} {ny_note + 15})">{note_bg}{note}</g>')

    # Enamel pills on bottom-right below IB medallion
    pw1 = 14 + 14 + tw(st["pillTop"], sans(700), 12) + 12
    px1, py1 = X + 676, 326
    p1_bg = "#081a4a" if dark else "#ffffff"
    p1_fg = "#ede5da" if dark else "#081744"
    p1 = [
        rrect(px1, py1, pw1, 34, 17, "#f5f0e8" if dark else "#0a1f56"),
        rrect(px1 + 2.5, py1 + 2.5, pw1 - 5, 29, 14.5, p1_bg),
        f'<circle cx="{n(px1 + 15)}" cy="{n(py1 + 17)}" r="4" fill="{T["gold"]}"/>',
        cv.text_box(px1 + 24, py1 + 2.5, st["pillTop"], sans(700), 12, p1_fg, 29),
    ]
    cv.add(f'<g transform="rotate(-3.5 {n(px1 + pw1 / 2)} {n(py1 + 17)})" {cv.shadow(5, 6, T["shadow_c"], 0.28)}>' + "".join(p1) + "</g>")

    pw2 = 14 + 14 + tw(st["pillBot"], sans(700), 12) + 12
    px2, py2 = X + 662, 384
    p2_bg = "#133a82" if dark else "#e7effb"
    p2_fg = "#f6f1ea" if dark else "#091845"
    p2 = [
        rrect(px2, py2, pw2, 34, 17, "#f5f0e8" if dark else "#1d4ed8"),
        rrect(px2 + 2.5, py2 + 2.5, pw2 - 5, 29, 14.5, p2_bg),
        f'<circle cx="{n(px2 + 15)}" cy="{n(py2 + 17)}" r="4" fill="#60a5fa"/>',
        cv.text_box(px2 + 24, py2 + 2.5, st["pillBot"], sans(700), 12, p2_fg, 29),
    ]
    cv.add(f'<g transform="rotate(3.5 {n(px2 + pw2 / 2)} {n(py2 + 17)})" {cv.shadow(5, 6, T["shadow_c"], 0.28)}>' + "".join(p2) + "</g>")
    return cv


def build_section(num, title, aside, theme_key):
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    H = 74
    cv = Canvas(CONTENT_W + 2 * MARGIN, H, f"{num} · {title} — {aside}")
    X = MARGIN + 4
    cy = 37

    # Subtle painted accent brushstroke rule behind section header
    rule_grad = cv.linear([(0, T["accent_strong"], 0.65), (0.5, T["gold"], 0.45), (1, T["accent"], 0)], 90)
    cv.add(
        f'<path d="M{X + 52} 62 Q{X + 340} 59 {MARGIN + CONTENT_W - 6} 62" fill="none" stroke="{rule_grad}" stroke-width="2.2" stroke-linecap="round"/>'
    )

    # Miniature oil-painted tilted number plaque
    cx = X + 22
    badge_bg = cv.linear([(0, "#143c8c"), (1, "#071847")], 135) if dark else cv.linear([(0, "#1d4ed8"), (1, "#0b2259")], 135)
    sticker = [
        rrect(cx - 22, cy - 22, 44, 44, 13, "#e8e0d8" if dark else "#f7f9fd"),
        rrect(cx - 19, cy - 19, 38, 38, 10, badge_bg),
        cv.text(cx, m(DISPLAY).baseline(cy - 22, 44, 16), num, DISPLAY, 16, "#f6f1ea", "middle"),
    ]
    cv.add(f'<g transform="rotate(-7 {cx} {cy})" {cv.shadow(4, 5, T["shadow_c"], 0.28)}>' + "".join(sticker) + "</g>")

    title_c = "#f3ede6" if dark else "#06102f"
    cv.add(cv.text_box(X + 58, cy - 21, title, DISPLAY, 29, title_c, 40, ls=-0.7))

    right = MARGIN + CONTENT_W - 6
    aw = tw(aside, HAND, 25)
    cv.add(
        f'<g transform="rotate(-2 {n(right - aw / 2)} {cy})">'
        + cv.text_box(right, cy - 17, aside, HAND, 25, T["hand"], 32, "end")
        + "</g>"
    )
    return cv


def build_project(p, theme_key):
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    pal = PROJECT_PALETTES[p["key"]]
    CW, CH, HEAD, SIDE, BOTTOM = 430, 358, 22, 18, 22
    cv = Canvas(CW + 2 * SIDE, HEAD + CH + BOTTOM, project_alt(p))
    x, y = SIDE, HEAD
    dot_c = pal["dot"] if dark else pal["dot_light"]

    cx, cy = x + CW / 2, y + CH / 2
    card_els = oil_box(cv, x, y, CW, CH, 24, theme_key, seed=50 + hash(p["key"]) % 40, preset="mini")

    # Inner oil-glazed plate so brushwork still glows around border & quietly behind text
    card_els.append(
        rrect(
            x + 13, y + 13, CW - 26, CH - 26, 18,
            T["plate"], f' fill-opacity="{0.60 if dark else 0.84}" stroke="{pal["stroke_c"]}" stroke-opacity="0.45" stroke-width="1.1"'
        )
    )

    ix, iy = x + 28, y + 28
    e, _ = pill(
        cv, ix, iy + 12, p["kicker"], sans(700), 11, 24, 10,
        T["pill_bg"], T["pill_fg"], dot=dot_c, gap=7, dot_size=6.5,
        extra=f' stroke="{T["pill_stroke"]}" stroke-opacity="0.7" stroke-width="1"'
    )
    card_els += e
    if p["key"] == "damaCrm":
        d_uri, dw, dh = encode_png_fit("logos/dama-logo.png" if dark else "logos/dama-logo-dark.png", 86, 26)
        px_l = x + CW - 26 - 96
        py_l = y + 26
        card_els += [
            rrect(px_l, py_l, 96, 40, 12, "#07173f" if dark else "#ffffff", f' stroke="{dot_c}" stroke-opacity="0.48" stroke-width="1.2"'),
            f'<image x="{n(px_l + (96 - dw) / 2)}" y="{n(py_l + (40 - dh) / 2)}" width="{dw}" height="{dh}" href="{d_uri}" preserveAspectRatio="xMidYMid meet"/>',
        ]
    else:
        card_els.append(painted_motif(cv, x + CW - 28 - 52, y + 25, 52, pal["motif"], dot_c, theme_key))

    card_els.append(cv.text_box(ix, iy + 38, p["name"], sans(700), 19.5, T["ink"], 24))
    card_els.append(cv.text_box(ix, iy + 67, p["big"], DISPLAY, 38, T["ink"], 40, ls=-1.1))

    sub = wrap(p["sub"], sans(600), 13.5, 290)
    card_els += cv.lines(ix, iy + 112, sub, sans(600), 13.5, T["accent"], 18)

    dtop = iy + 112 + 18 * len(sub) + 11
    desc = wrap(p["text"], sans(400), 13.2, CW - 56)
    card_els += cv.lines(ix, dtop, desc, sans(400), 13.2, T["body"], 19.5)

    row_cy = y + CH - 34
    qx = ix
    for s in p["tags"]:
        pe, pw = pill(
            cv, qx, row_cy, s, mono(600), 10.5, 24, 8.5,
            T["pill_bg"], T["pill_fg"],
            extra=f' stroke="{T["pill_stroke"]}" stroke-opacity="0.65" stroke-width="1"'
        )
        card_els += pe
        qx += pw + 5

    label = "GitHub"
    lw = 22 + tw(label, sans(700), 12) + 16
    lx = x + CW - 28 - lw
    card_els += [
        rrect(lx, row_cy - 14, lw, 28, 14, T["btn_bg"]),
        cv.text_box(lx + 11, row_cy - 14, label, sans(700), 12, T["btn_fg"], 28),
        icon(ICON["arrow"], lx + lw - 21, row_cy - 5, 10, T["btn_fg"], width=3.0),
    ]

    cv.add(f'<g transform="rotate({pal["tilt"]} {n(cx)} {n(cy)})">' + "".join(card_els) + "</g>")
    return cv


def build_more_work(theme_key):
    """Oil-canvas card highlighting additional full-stack engineering builds."""
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    cl = P["work"]["more"]
    items = cl["items"]
    X, PAD = MARGIN, 22
    inner_w = CONTENT_W - 2 * PAD
    col_w = (inner_w - 28) / 3

    col_layouts = []
    max_body_h = 0
    for item in items:
        tl = wrap(item["text"], sans(400), 12.6, col_w - 30)
        tag_items = [(18 + tw(s, mono(600), 9.6), s) for s in item["tags"]]
        placed_t, tags_h = flow(tag_items, col_w - 28, 5, 5, 22)
        bh = 22 + 12 + 26 + 18 * len(tl) + 12 + tags_h + 14
        max_body_h = max(max_body_h, bh)
        col_layouts.append((item, tl, placed_t))

    card_h = max(176, max_body_h)
    foot_h = 28
    H = PAD + 40 + card_h + 14 + foot_h + PAD
    cv = Canvas(CONTENT_W + 2 * MARGIN, H + MARGIN, more_work_alt())
    cv.add(*oil_box(cv, X, 0, CONTENT_W, H, 26, theme_key, seed=67))

    # Top frosted header strip
    cv.add(
        rrect(X + PAD, PAD - 3, inner_w, 34, 13, T["plate"], f' fill-opacity="{0.74 if dark else 0.90}" stroke="{T["plate_stroke"]}" stroke-opacity="0.58" stroke-width="1.1"'),
        icon(ICON["layers"], X + PAD + 14, PAD + 5, 17, T["accent"]),
        cv.text_box(X + PAD + 38, PAD + 4, cl["label"], mono(700), 11.5, T["ink"], 20, ls=0.8),
    )
    right = X + CONTENT_W - PAD - 14
    aw = tw(cl["aside"], HAND, 22)
    cv.add(
        f'<g transform="rotate(-1.8 {n(right - aw / 2)} {PAD + 14})">'
        + cv.text_box(right, PAD + 1, cl["aside"], HAND, 22, T["hand"], 26, "end")
        + "</g>",
    )

    cy = PAD + 40
    for i, (item, tl, placed_t) in enumerate(col_layouts):
        cx = X + PAD + i * (col_w + 14)
        cv.add(
            rrect(cx, cy, col_w, card_h, 18, T["plate"], f' fill-opacity="{0.66 if dark else 0.88}" stroke="{T["plate_stroke"]}" stroke-opacity="0.62" stroke-width="1.2"'),
        )
        pe, _ = pill(cv, cx + 14, cy + 22, item["badge"], mono(700), 9.4, 21, 8, "#143885" if dark else "#dbeafe", "#f6f1ea" if dark else "#1e3a8a")
        cv.add(*pe)
        cv.add(cv.text_box(cx + 14, cy + 39, item["name"], sans(800), 15.8, T["ink"], 22))
        cv.add(*cv.lines(cx + 14, cy + 65, tl, sans(400), 12.6, T["body"], 18))
        ty_base = cy + card_h - 36
        # Measure how many tag rows so bottom alignment stays crisp
        max_ty = max((qy for _, qy, _, _ in placed_t), default=0)
        ty_start = cy + card_h - 14 - (max_ty + 22)
        for qx, qy, s, _w in placed_t:
            te, _ = pill(
                cv, cx + 14 + qx, ty_start + qy + 11, s, mono(600), 9.6, 22, 7.5,
                T["pill_bg"], T["pill_fg"], extra=f' stroke="{T["pill_stroke"]}" stroke-opacity="0.6" stroke-width="0.9"'
            )
            cv.add(*te)

    # Bottom frosted footnote strip
    fy = cy + card_h + 14
    fw = tw(cl["footnote"], mono(600), 10.6) + 28
    cv.add(
        rrect(X + (CONTENT_W - fw) / 2, fy, fw, foot_h, 14, T["plate"], f' fill-opacity="{0.74 if dark else 0.90}" stroke="{T["plate_stroke"]}" stroke-opacity="0.58" stroke-width="1"'),
        cv.text_box(X + CONTENT_W / 2, fy + 6, cl["footnote"], mono(600), 10.6, T["ink"] if not dark else T["muted"], 16, "middle"),
    )
    return cv


def build_certifications(theme_key):
    """Oil-canvas card showcasing verified Credly certifications (Cisco & IBM)."""
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    cr = P["certifications"]
    X, PAD = MARGIN, 22
    inner_w = CONTENT_W - 2 * PAD
    cert_h = 98
    H = PAD + 44 + cert_h * 2 + 12 + 14 + 26 + PAD
    cv = Canvas(CONTENT_W + 2 * MARGIN, H + MARGIN, certifications_alt())
    cv.add(*oil_box(cv, X, 0, CONTENT_W, H, 28, theme_key, seed=111))

    # Top header inside crisp frosted gallery strip
    cv.add(
        rrect(X + PAD, PAD - 3, inner_w, 34, 13, T["plate"], f' fill-opacity="{0.72 if dark else 0.90}" stroke="{T["plate_stroke"]}" stroke-opacity="0.58" stroke-width="1.1"'),
        icon(ICON["award"], X + PAD + 14, PAD + 5, 18, T["gold"]),
        cv.text_box(X + PAD + 38, PAD + 4, cr["header"], sans(800), 14, T["ink"], 20),
    )
    aw = tw(cr["aside"], HAND, 23)
    right = X + CONTENT_W - PAD - 14
    cv.add(
        f'<g transform="rotate(-1.8 {n(right - aw / 2)} {PAD + 14})">'
        + cv.text_box(right, PAD + 1, cr["aside"], HAND, 23, T["hand"], 26, "end")
        + "</g>"
    )

    cy = PAD + 44
    w3 = (inner_w - 24) / 3
    w2 = (inner_w - 12) / 2
    certs = cr["certs"]
    placements = [
        (X + PAD, cy, w3, certs[0]),
        (X + PAD + w3 + 12, cy, w3, certs[1]),
        (X + PAD + (w3 + 12) * 2, cy, w3, certs[2]),
        (X + PAD, cy + cert_h + 12, w2, certs[3]),
        (X + PAD + w2 + 12, cy + cert_h + 12, w2, certs[4]),
    ]
    for cx, ccy, cw, cert in placements:
        cv.add(
            rrect(cx, ccy, cw, cert_h, 16, T["plate"], f' fill-opacity="{0.66 if dark else 0.88}" stroke="{T["plate_stroke"]}" stroke-opacity="0.62" stroke-width="1.2"'),
        )
        uri = encode_badge_png(cert["image"], 92)
        b_size = 52
        bx, by = cx + 14, ccy + (cert_h - b_size) / 2
        cv.add(
            rrect(bx - 2, by - 2, b_size + 4, b_size + 4, 12, "#ffffff", f' stroke="{T["plate_stroke"]}" stroke-opacity="0.4"'),
            f'<image x="{n(bx)}" y="{n(by)}" width="{b_size}" height="{b_size}" href="{uri}" preserveAspectRatio="xMidYMid meet"/>',
        )
        tx = bx + b_size + 12
        tw_avail = cw - (b_size + 36)
        tl = wrap(cert["title"], sans(700), 13, tw_avail)
        cv.add(*cv.lines(tx, ccy + 16, tl, sans(700), 13, T["ink"], 17))
        iy = ccy + 16 + 17 * len(tl) + 3
        cv.add(
            cv.text_box(tx, iy, cert["issuer"], sans(500), 11.2, T["muted"], 15),
            cv.text_box(tx, iy + 15, cert["tag"], mono(600), 10, T["accent"], 14),
        )

    note_w = tw(cr["credlyNote"], mono(600), 11) + 28
    note_x = X + (CONTENT_W - note_w) / 2
    note_y = cy + cert_h * 2 + 12 + 14
    cv.add(
        rrect(note_x, note_y, note_w, 26, 13, T["plate"], f' fill-opacity="{0.74 if dark else 0.90}" stroke="{T["plate_stroke"]}" stroke-opacity="0.58" stroke-width="1"'),
        cv.text_box(X + CONTENT_W / 2, note_y + 5, cr["credlyNote"], mono(600), 11, T["ink"] if not dark else T["muted"], 16, "middle"),
    )
    return cv


def key_w(label, level):
    return 18 + tw(label, sans(700 if level == "daily" else 600), 12.2)


def draw_key(cv, x, y, label, level, dark_bg, dark_sh, light_bg, light_sh, theme_key):
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    w = key_w(label, level)
    if level == "daily":
        bg = dark_bg if dark else light_bg
        sh = dark_sh if dark else light_sh
        fg = "#ffffff" if dark else "#05102f"
        els = [
            rrect(x, y + 3, w, 33, 9, sh),
            rrect(x, y, w, 33, 9, bg, f' stroke="{T["accent"] if dark else "#7aa7ea"}" stroke-opacity="0.45" stroke-width="1"'),
        ]
        font = sans(700)
    elif level == "used":
        ub = cv.linear([(0, T["key_used_bg"][0]), (1, T["key_used_bg"][1])], 180)
        els = [
            rrect(x, y + 3, w, 33, 9, T["key_used_sh"]),
            rrect(x + 0.5, y + 0.5, w - 1, 32, 8.5, ub, f' stroke="{T["key_used_stroke"]}" stroke-width="1"'),
        ]
        font, fg = sans(600), T["key_used_fg"]
    else:
        els = [
            rrect(
                x + 0.75, y + 0.75, w - 1.5, 31.5, 8.25, "none",
                f' stroke="{T["key_exp_stroke"]}" stroke-width="1.5" stroke-dasharray="4 3"'
            )
        ]
        font, fg = sans(600), T["muted"]
    els.append(cv.text_box(x + 9, y, label, font, 12.2, fg, 33))
    return els


def build_stack(theme_key):
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    st = P["stack"]
    X, PAD = MARGIN, 22
    inner_w = CONTENT_W - 2 * PAD
    col_w = (inner_w - 14) / 2
    clusters = st["groups"]

    def layout(keys, max_w):
        items = [(key_w(k["label"], k["level"]), (k["label"], k["level"])) for k in keys]
        return flow(items, max_w, 6, 8, 33)

    def sec_h(rows_h):
        return 14 + 16 + 12 + rows_h + 4 + 14

    rows = []
    for a, b in ((0, 1), (2, 3)):
        la, ha = layout(clusters[a]["keys"], col_w - 30)
        lb, hb = layout(clusters[b]["keys"], col_w - 30)
        rows.append(((a, la), (b, lb), sec_h(max(ha, hb))))

    H = PAD + 36 + 14 + sum(r[2] for r in rows) + 14 * (len(rows) - 1) + PAD
    cv = Canvas(CONTENT_W + 2 * MARGIN, H + MARGIN, stack_alt())
    cv.add(*oil_box(cv, X, 0, CONTENT_W, H, 28, theme_key, seed=91))

    # Sleek glazed bar behind legend & handwritten note so text reads sharply over brushwork
    cv.add(
        rrect(
            X + PAD, PAD - 2, inner_w, 38, 14,
            T["plate"], f' fill-opacity="{0.70 if dark else 0.88}" stroke="{T["plate_stroke"]}" stroke-opacity="0.58" stroke-width="1.1"'
        )
    )
    lx, ly = X + PAD + 14, PAD + 5
    legend = [("daily", st["legend"]["daily"]), ("used", st["legend"]["used"]), ("exploring", st["legend"]["exploring"])]
    for lv, label in legend:
        if lv == "daily":
            cv.add(
                rrect(lx, ly + 4, 22, 18, 6, "#0b2459" if dark else "#93b7ed"),
                rrect(lx, ly + 2, 22, 18, 6, "#1c4da8" if dark else "#c8defd"),
            )
        elif lv == "used":
            cv.add(
                rrect(lx, ly + 4, 22, 18, 6, T["key_used_sh"]),
                rrect(lx + 0.5, ly + 2.5, 21, 17, 5.5, T["key_used_bg"][0], f' stroke="{T["key_used_stroke"]}"'),
            )
        else:
            cv.add(
                rrect(
                    lx + 0.75, ly + 2.75, 20.5, 18.5, 5.25, "none",
                    f' stroke="{T["key_exp_stroke"]}" stroke-width="1.5" stroke-dasharray="3 2.5"'
                )
            )
        cv.add(cv.text_box(lx + 30, ly, label, sans(600), 12.5, T["ink"], 24))
        lx += 30 + tw(label, sans(600), 12.5) + 18

    right = X + CONTENT_W - PAD - 14
    aw = tw(st["aside"], HAND, 23)
    cv.add(
        f'<g transform="rotate(-1.8 {n(right - aw / 2)} {ly + 12})">'
        + cv.text_box(right, ly - 2, st["aside"], HAND, 23, T["hand"], 28, "end")
        + "</g>"
    )

    def draw_cluster(cx, cy, cw, ch, g, placed):
        dot, dbg, dsh, lbg, lsh = STACK_PALETTES[g["key"]]
        out = [
            rrect(cx, cy, cw, ch, 18, T["plate"], f' fill-opacity="{0.62 if dark else 0.84}" stroke="{T["plate_stroke"]}" stroke-opacity="0.58" stroke-width="1.1"'),
            f'<circle cx="{n(cx + 20)}" cy="{n(cy + 22)}" r="4.2" fill="{dot}"/>',
            cv.text_box(cx + 32, cy + 14, g["name"], sans(800), 13.5, T["ink"], 16),
        ]
        for qx, qy, (lbl, lv), _w in placed:
            out += draw_key(cv, cx + 15 + qx, cy + 42 + qy, lbl, lv, dbg, dsh, lbg, lsh, theme_key)
        return out

    y = PAD + 36 + 14
    for (a, la), (b, lb), row_h in rows:
        cv.add(*draw_cluster(X + PAD, y, col_w, row_h, clusters[a], la))
        cv.add(*draw_cluster(X + PAD + col_w + 14, y, col_w, row_h, clusters[b], lb))
        y += row_h + 14

    return cv


def build_contact(theme_key):
    T = THEMES[theme_key]
    dark = theme_key == "dark"
    ct = P["contact"]
    H = 312
    X = MARGIN
    cv = Canvas(CONTENT_W + 2 * MARGIN, H, contact_alt())
    cv.add(*oil_box(cv, X, 0, CONTENT_W, H, 28, theme_key, seed=151))

    # Left glazed text block
    cv.add(
        rrect(
            X + 20, 20, 428, H - 40, 20,
            T["plate"], f' fill-opacity="{0.62 if dark else 0.85}" stroke="{T["plate_stroke"]}" stroke-opacity="0.52" stroke-width="1.1"'
        )
    )
    ax, ay = X + 40, 36
    aside = cv.text_box(ax, ay, ct["aside"], HAND, 27, T["hand"], 30)
    cv.add(f'<g transform="rotate(-3 {n(ax + 70)} {ay + 14})">{aside}</g>')
    cv.add(cv.text_box(X + 38, 68, ct["title"], DISPLAY, 48, T["ink"], 50, ls=-1.7))

    body = wrap(ct["text"], sans(400), 14.8, 386)
    cv.add(*cv.lines(X + 40, 128, body, sans(400), 14.8, T["body"], 21.5))

    ptop = 128 + 21.5 * len(body) + 18
    email = LINKS["email"]
    pw = 20 + 18 + 10 + tw(email, sans(700), 15) + 10 + 12 + 20
    sh = cv.shadow(5, 7, T["shadow_c"], 0.3 if dark else 0.14)
    cv.add(
        rrect(X + 40, ptop, pw, 44, 22, T["btn_bg"], " " + sh),
        icon(ICON["mail"], X + 60, ptop + 13, 18, T["accent_strong"]),
        cv.text_box(X + 88, ptop, email, sans(700), 15, T["btn_fg"], 44),
        icon(ICON["arrow"], X + 40 + pw - 30, ptop + 16, 12, T["btn_fg"], width=3),
    )

    # Ignacio holding letter sprite docked cleanly between left card and postage stamp
    card_inner_clip = cv.clip_rrect(X + 4, 4, CONTENT_W - 8, H - 8, 24)
    mail_h = 208
    mail_g, _ = embed_sprite(cv, "ignacio_mail", X + 458, H - mail_h + 2, mail_h, clip_attr=card_inner_clip)
    cv.add(mail_g)

    # Perforated gallery postage stamp with impasto oil IB logo
    sx, sy, sw, sh_h = X + 616, 36, 186, 232
    mid = cv.uid("mk")
    holes = [(i, 0) for i in range(0, sw + 1, 14)] + [(i, sh_h) for i in range(0, sw + 1, 14)]
    holes += [(0, j) for j in range(14, sh_h, 14)] + [(sw, j) for j in range(14, sh_h, 14)]
    cv.defs.append(
        f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="{sx - 10}" y="{sy - 10}" width="{sw + 20}" height="{sh_h + 20}">'
        f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh_h}" fill="#fff"/>'
        + "".join(f'<circle cx="{sx + a}" cy="{sy + b}" r="5"/>' for a, b in holes)
        + "</mask>"
    )
    ix, iy, iw, ih = sx + 9, sy + 9, sw - 18, sh_h - 18
    stamp = [
        f'<g {cv.shadow(8, 8, T["shadow_c"], 0.35)}><rect x="{sx}" y="{sy}" width="{sw}" height="{sh_h}" fill="#f5f0e8" mask="url(#{mid})"/></g>',
        rrect(ix, iy, iw, ih, 4, cv.linear([(0, "#051030"), (1, "#123780")], 145)),
        cv.text_box(ix + 10, iy + 8, ct["stampCorner"], mono(700), 10.5, "#e2bd79", 14, ls=0.8),
        modern_ib_logo(cv, ix + (iw - 110) / 2, iy + 28, 110, "dark", medallion=True),
        cv.text_box(ix + iw / 2, iy + ih - 50, ct["replyLabel"], mono(700), 9.5, "#93c5fd", 13, "middle", 1.2),
        cv.text_box(ix + iw / 2, iy + ih - 36, ct["reply"], DISPLAY, 28, "#faf7f2", 30, "middle", -0.8),
    ]
    cv.add(f'<g transform="rotate(4 {sx + sw / 2} {sy + sh_h / 2})">' + "".join(stamp) + "</g>")

    # Postmark placed cleanly clear of sprite and stamp
    pcx, pcy = X + 594, 72
    p1, p2 = ct["postmark"]
    pm_c = "#93c5fd" if dark else "#123685"
    cv.add(
        f'<g transform="rotate(-10 {pcx} {pcy})"><circle cx="{pcx}" cy="{pcy}" r="36" fill="none" stroke="{pm_c}" stroke-opacity=".6" stroke-width="2"/>'
        f'<circle cx="{pcx}" cy="{pcy}" r="31" fill="none" stroke="{pm_c}" stroke-opacity=".3" stroke-width="1"/>'
        + cv.text(pcx, pcy - 2, p1, sans(800), 8, pm_c, "middle", 0.7, ' fill-opacity=".9"')
        + cv.text(pcx, pcy + 9, p2, mono(700), 8, pm_c, "middle", 0.4, ' fill-opacity=".9"')
        + "</g>"
    )
    cv.add(
        f'<g transform="translate({X + 800} 126)"><path d="M4 72 C 16 58, 24 40, 46 28" fill="none" stroke="{T["hand"]}" stroke-width="2.4" stroke-linecap="round" stroke-dasharray="2 7"/>'
        f'<path d="M44 20 L 72 6 L 62 36 L 54 27 Z" fill="{T["accent"]}"/>'
        f'<path d="M54 27 L 72 6" stroke="{T["ink"]}" stroke-width="1.8" stroke-linecap="round"/></g>'
    )
    return cv


# ═══════════════════════════════════════════════════════════════════════════
# ALT TEXT & README GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def hero_alt():
    h = P["hero"]
    return f"{h['name']} — {h['lead']} {' · '.join(h['chips'])}."


def project_alt(p):
    return f"{p['name']} ({p['kicker']}) — {p['big']}: {p['sub']}. {p['text']} Stack: {', '.join(p['tags'])}."


def more_work_alt():
    cl = P["work"]["more"]
    items = "; ".join(f"{it['name']} ({it['badge']}): {it['text']}" for it in cl["items"])
    return f"{cl['label']} — {items}. {cl['footnote']}."


def certifications_alt():
    ct = ", ".join(c["title"] for c in P["certifications"]["certs"])
    return f"Verified Certifications — {ct}."


def stack_alt():
    return "Tech Stack — " + "; ".join(f"{g['name']}: {', '.join(k['label'] for k in g['keys'])}" for g in P["stack"]["groups"])


def contact_alt():
    c = P["contact"]
    return f"Contact — {c['title']} {c['text']} Email: {LINKS['email']}."


def attr(s):
    return s.replace("&", "&amp;").replace('"', "&quot;")


def dual_img(name, alt_text, width="100%", extra=""):
    alt = attr(alt_text)
    return (
        f'<picture>\n'
        f'  <source media="(prefers-color-scheme: dark)" srcset="assets/cards/{name}-dark.svg">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="assets/cards/{name}-light.svg">\n'
        f'  <img alt="{alt}" src="assets/cards/{name}-dark.svg" width="{width}"{extra}>\n'
        f'</picture>'
    )


def cool_card(card_name, alt_text):
    base = "https://raw.githubusercontent.com/Ignaciobrenas/ignaciobrenas/cards"
    return (
        f'<picture>\n'
        f'  <source media="(prefers-color-scheme: dark)" srcset="{base}/{card_name}-dark.svg">\n'
        f'  <img src="{base}/{card_name}-light.svg" width="400" alt="{attr(alt_text)}">\n'
        f'</picture>'
    )


def work_md():
    cards = []
    for p in P["work"]["items"]:
        slug = re.sub(r"(?<!^)([A-Z])", r"-\1", p["key"]).lower()
        img = dual_img(f"work-{slug}", project_alt(p), width="49%")
        cards.append(f'<a href="{p["url"]}">\n{img}\n</a>')
    rows = [cards[i:i + 2] for i in range(0, len(cards), 2)]
    body = '<p align="center">\n' + "\n<br>\n".join("\n".join(r) for r in rows) + "\n</p>\n"
    body += f'\n{dual_img("work-more", more_work_alt())}\n'
    more = P["work"]["more"]
    link_items = more["items"] + more.get("extraLinks", [])
    cl_links = " &nbsp;·&nbsp; ".join(
        f'<a href="{it["url"]}"><b>{it["name"]} ↗</b></a>' for it in link_items
    )
    body += (
        f'\n<p align="center">\n'
        f'  <sub>{cl_links} &nbsp;·&nbsp; <a href="{LINKS["repos"]}"><b>Explore all 40+ repositories ↗</b></a></sub>\n'
        f'</p>\n'
    )
    return body


def activity_md():
    return (
        '<p align="center">\n'
        + cool_card("summary", "GitHub Summary Stats") + "\n"
        + cool_card("about", "Developer Profile") + "\n"
        + '</p>\n'
        + '<p align="center">\n'
        + cool_card("weekly", "Weekly Coding Rhythm") + "\n"
        + cool_card("languages", "Most Used Languages") + "\n"
        + '</p>\n'
    )


def build_readme():
    out = [
        "<!-- Generated by assets/gen_cards.py from assets/profile.json -->\n",
        f'<a href="{LINKS["portfolio"]}">\n{dual_img("hero", hero_alt())}\n</a>\n',
        (
            '<p align="center">\n'
            f'  <a href="{LINKS["portfolio"]}"><img src="https://img.shields.io/badge/Portfolio-0a215c?style=for-the-badge&logo=vercel&logoColor=white" alt="Portfolio"/></a>\n'
            f'  <a href="{LINKS["linkedin"]}"><img src="https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge" alt="LinkedIn"/></a>\n'
            f'  <a href="{LINKS["cv"]}"><img src="https://img.shields.io/badge/Resume%20%2F%20CV-1d4ed8?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Resume / CV"/></a>\n'
            f'  <a href="{LINKS["credly"]}"><img src="https://img.shields.io/badge/Credly-06143a?style=for-the-badge&logo=credly&logoColor=e2bd79" alt="Credly"/></a>\n'
            f'  <a href="mailto:{LINKS["email"]}"><img src="https://img.shields.io/badge/Email-0f172a?style=for-the-badge&logo=gmail&logoColor=60a5fa" alt="Email"/></a>\n'
            '</p>\n'
        ),
    ]
    bodies = {
        "work": work_md,
        "stack": lambda: dual_img("stack", stack_alt()) + "\n",
        "certifications": lambda: f'<a href="{LINKS["credly"]}">\n{dual_img("certifications", certifications_alt())}\n</a>\n',
        "activity": activity_md,
        "contact": lambda: f'<a href="mailto:{LINKS["email"]}">\n{dual_img("contact", contact_alt())}\n</a>\n',
    }
    for sec in P["sections"]:
        key = sec["key"]
        sec_alt = f"{sec['num']} · {sec['title']} — {sec['note']}"
        out.append(dual_img(f"section-{key}", sec_alt) + "\n")
        out.append(bodies[key]())

    out.append(
        '<p align="center">\n'
        '  <sub>Barcelona, Spain (On-site · Hybrid · Remote) · ES / CAT / EN · '
        'Generated by <a href="assets/gen_cards.py"><code>assets/gen_cards.py</code></a> '
        '&amp; <a href="cool-readme.yml"><code>github-cool-readme</code></a> · '
        f'<a href="{LINKS["portfolio"]}">ignaciobrenas.vercel.app</a></sub>\n'
        '</p>\n'
    )
    return "\n".join(out)


def main():
    FONT_PATHS.update(ensure_fonts())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for mode in ("dark", "light"):
        jobs.append((f"hero-{mode}.svg", lambda m=mode: build_hero(m)))
        for sec in P["sections"]:
            jobs.append((
                f"section-{sec['key']}-{mode}.svg",
                lambda s=sec, m=mode: build_section(s["num"], s["title"], s["note"], m),
            ))
        for p in P["work"]["items"]:
            slug = re.sub(r"(?<!^)([A-Z])", r"-\1", p["key"]).lower()
            jobs.append((f"work-{slug}-{mode}.svg", lambda proj=p, m=mode: build_project(proj, m)))
        jobs.append((f"work-more-{mode}.svg", lambda m=mode: build_more_work(m)))
        jobs.append((f"stack-{mode}.svg", lambda m=mode: build_stack(m)))
        jobs.append((f"certifications-{mode}.svg", lambda m=mode: build_certifications(m)))
        jobs.append((f"contact-{mode}.svg", lambda m=mode: build_contact(m)))

    made = set()
    for name, builder in jobs:
        svg = builder().render()
        (OUT_DIR / name).write_text(svg, encoding="utf-8")
        made.add(name)
        print(f"wrote assets/cards/{name:<34} {len(svg.encode()) / 1024:6.1f} KB")

    for old in OUT_DIR.glob("*.svg"):
        if old.name not in made:
            old.unlink()
            print(f"removed stale assets/cards/{old.name}")

    (ROOT / "README.md").write_text(build_readme(), encoding="utf-8")
    print("wrote README.md")


if __name__ == "__main__":
    main()
