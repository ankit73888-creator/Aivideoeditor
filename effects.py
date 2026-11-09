#!/usr/bin/env python3
"""effects.py — reel effects for 9:16 vertical videos.

Effects (name@start-end[:key=value,key=value]):
  backdrop-word      giant word BEHIND the person (subject cut-out with MODNet)
                       text=SALE  color=white|gold  y=0.30
  digital-zoom       punch-in zoom towards the face          zoom=1.3  speed=0.25
  locked-on          face-tracking crop + target brackets    zoom=1.35 label=
  the-bill           receipt slides up, items type in, total
                       items=Saree:1499;Blouse:499  title=BILL  currency=₹  discount=20%
  glitter-spotlight  dark vignette spotlight on the face + gold glitter   density=70
  countdown          3-2-1 big numbers with depleting ring   from=3  label=OFFER ENDS IN
  pullback           starts tight on the face, pulls back to full frame   zoom=1.7

Examples
  python effects.py Raw/clip.mov --fx digital-zoom@0-2 --fx "countdown@2-5:label=SALE ENDS IN"
  python effects.py clip.mov --fx "the-bill@4-9:items=Saree:1499;Blouse:499,discount=20%" --captions
  python effects.py clip.mov --demo --captions        # every effect, one after another
  python effects.py --list

Times are in seconds of the (trimmed) clip. Order on screen: camera moves first
(zoom / pullback / locked-on), then backdrop-word, spotlight, graphics; captions last.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import reelkit as rk

MODEL_DIR = rk.ROOT / "models"
MODNET_URL = "https://huggingface.co/Xenova/modnet/resolve/main/onnx/model.onnx"


# ---------------------------------------------------------------------------
# Shared context: face tracking + person matte
# ---------------------------------------------------------------------------
class FaceTracker:
    """Haar-cascade face tracker with smoothing. Works on any CPU, no downloads."""

    def __init__(self, every: int = 3, smooth: float = 0.25):
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self.cascade = cv2.CascadeClassifier(str(path))
        self.every, self.smooth = every, smooth
        self.box = None                     # (cx, cy, size) in frame coords
        self.n = 0

    def update(self, frame: np.ndarray) -> tuple[float, float, float]:
        if self.n % self.every == 0:
            s = 0.33
            small = cv2.cvtColor(cv2.resize(frame, None, fx=s, fy=s), cv2.COLOR_RGB2GRAY)
            faces = self.cascade.detectMultiScale(small, 1.15, 5, minSize=(40, 40))
            if len(faces):
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                det = ((x + w / 2) / s, (y + h / 2) / s, w / s)
                if self.box is None:
                    self.box = det
                else:
                    a = self.smooth
                    self.box = tuple(b * (1 - a) + d * a for b, d in zip(self.box, det))
        self.n += 1
        return self.box or (rk.W / 2, rk.H * 0.36, rk.W * 0.35)


class PersonMatte:
    """Person/background matte using MODNet (ONNX, ~25 MB, auto-downloaded once)."""

    def __init__(self):
        self.sess = None
        try:
            import onnxruntime as ort
            path = MODEL_DIR / "modnet.onnx"
            if not path.exists():
                import urllib.request
                MODEL_DIR.mkdir(exist_ok=True)
                print(f"[effects] downloading MODNet -> {path}", flush=True)
                urllib.request.urlretrieve(MODNET_URL, path)
            so = ort.SessionOptions()
            so.log_severity_level = 3
            self.sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
            self.inp = self.sess.get_inputs()[0].name
        except Exception as e:  # no model / no onnxruntime -> graceful fallback
            print(f"[effects] person matte unavailable ({e}); backdrop-word will use soft overlay")

    def __call__(self, frame: np.ndarray) -> np.ndarray | None:
        if self.sess is None:
            return None
        x = cv2.resize(frame, (288, 512), interpolation=cv2.INTER_AREA).astype(np.float32)
        x = (x - 127.5) / 127.5
        x = x.transpose(2, 0, 1)[None]
        m = self.sess.run(None, {self.inp: x})[0][0, 0]
        m = cv2.resize(m, (rk.W, rk.H), interpolation=cv2.INTER_LINEAR)
        return np.clip(m, 0, 1).astype(np.float32)


@dataclass
class Ctx:
    t: float = 0.0
    face: tuple = (rk.W / 2, rk.H * 0.36, 300.0)
    tracker: FaceTracker = field(default_factory=FaceTracker)
    _matte: PersonMatte | None = None

    def matte(self, frame):
        if self._matte is None:
            self._matte = PersonMatte()
        return self._matte(frame)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def zoom_frame(frame: np.ndarray, z: float, cx: float, cy: float) -> tuple[np.ndarray, callable]:
    """Zoom by z around (cx, cy), clamped to the frame. Returns frame and a point-mapper."""
    if z <= 1.001:
        return frame, (lambda x, y: (x, y))
    cw, ch = rk.W / z, rk.H / z
    x0 = min(max(cx - cw / 2, 0), rk.W - cw)
    y0 = min(max(cy - ch / 2, 0), rk.H - ch)
    m = np.float32([[z, 0, -x0 * z], [0, z, -y0 * z]])
    out = cv2.warpAffine(frame, m, (rk.W, rk.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out, (lambda x, y: ((x - x0) * z, (y - y0) * z))


def text_sprite(text: str, kind: str, size: int, color=rk.WHITE, shadow: int = 140,
                blur: int = 16, offset: int = 8, stroke: int = 0) -> np.ndarray:
    f = rk.font(kind, size)
    l, t, r, b = f.getbbox(text, stroke_width=stroke)
    pad = blur * 3 + offset
    w, h = r - l + pad * 2, b - t + pad * 2
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - l, pad - t), text, font=f, fill=255, stroke_width=stroke)
    sh = np.zeros((h, w), np.float32)
    if shadow:
        soft = np.asarray(mask.filter(ImageFilter.GaussianBlur(blur)), np.float32)
        sh[offset:] = soft[:-offset] * shadow / 255
    a = np.asarray(mask, np.float32) / 255
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[..., :3] = color
    rgba[..., :3] *= a[..., None]
    alpha = a * 255 + sh * (1 - a)
    nz = alpha > 0
    rgba[..., :3][nz] = rgba[..., :3][nz] * 255 / np.maximum(alpha[nz, None], 1e-3)
    rgba[..., 3] = alpha
    return rgba.clip(0, 255).astype(np.uint8)


def scaled(img: np.ndarray, s: float) -> np.ndarray:
    if abs(s - 1) < 1e-3:
        return img
    h, w = img.shape[:2]
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_LINEAR)


def paste_center(frame, img, cx, cy, opacity=1.0):
    h, w = img.shape[:2]
    rk.alpha_paste(frame, img, int(cx - w / 2), int(cy - h / 2), opacity)


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------
class Effect:
    name = ""
    layer = 1          # 0 = camera move, 1 = in-scene, 2 = graphics on top

    def __init__(self, start: float, end: float, **params):
        self.start, self.end, self.p = start, end, params

    @property
    def dur(self):
        return max(self.end - self.start, 1e-3)

    def active(self, t):
        return self.start <= t < self.end

    def local(self, t):            # 0..1 progress
        return (t - self.start) / self.dur

    def apply(self, frame: np.ndarray, ctx: Ctx) -> np.ndarray:
        raise NotImplementedError


class DigitalZoom(Effect):
    """Punch-in towards the face: fast ease to zoom, hold, ease back out at the end."""
    name, layer = "digital-zoom", 0

    def apply(self, frame, ctx):
        z_max = float(self.p.get("zoom", 1.3))
        sp = float(self.p.get("speed", 0.25))
        el = ctx.t - self.start
        rem = self.end - ctx.t
        k = rk.ease_out_cubic(el / sp) if el < sp else 1.0
        if rem < sp * 0.8:
            k = min(k, rk.ease_in_out(rem / (sp * 0.8)))
        z = 1 + (z_max - 1) * k
        fx, fy, fs = ctx.face
        out, mp = zoom_frame(frame, z, fx, fy + fs * 0.35)
        nx, ny = mp(fx, fy)
        ctx.face = (nx, ny, fs * z)
        return out


class Pullback(Effect):
    """Opens tight on the face and pulls back to the full frame, with a zoom-blur at the start."""
    name, layer = "pullback", 0

    def apply(self, frame, ctx):
        z0 = float(self.p.get("zoom", 1.7))
        k = rk.ease_out_cubic(self.local(ctx.t))
        z = z0 + (1 - z0) * k
        fx, fy, fs = ctx.face
        out, mp = zoom_frame(frame, z, fx, fy)
        if k < 0.35:                                  # zoom blur while moving fast
            blur_amt = (0.35 - k) / 0.35
            acc = out.astype(np.float32)
            for i, s in enumerate((1.02, 1.04, 1.06)):
                zz, _ = zoom_frame(frame, z * (1 + (s - 1) * blur_amt), fx, fy)
                acc += zz
            out = (acc / 4).astype(np.uint8)
        nx, ny = mp(fx, fy)
        ctx.face = (nx, ny, fs * z)
        return out


class LockedOn(Effect):
    """Crop locks onto the face (tracked) + corner brackets that snap in like a target lock."""
    name, layer = "locked-on", 0

    def apply(self, frame, ctx):
        z = float(self.p.get("zoom", 1.35))
        el = ctx.t - self.start
        zk = 1 + (z - 1) * rk.ease_out_cubic(el / 0.35)
        fx, fy, fs = ctx.face
        # keep the face at a fixed spot: centre x, 36% height
        tx, ty = fx, fy + (rk.H * 0.5 - rk.H * 0.36) / zk
        out, mp = zoom_frame(frame, zk, tx, ty)
        nx, ny = mp(fx, fy)
        size = fs * zk
        ctx.face = (nx, ny, size)

        snap = rk.ease_out_back(el / 0.3)
        half = size * (0.52 + 0.8 * (1 - snap))
        arm = int(size * 0.16)
        th = 7
        img = Image.new("RGBA", (rk.W, rk.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x0, y0, x1, y1 = nx - half, ny - half * 1.25, nx + half, ny + half * 1.25
        corners = [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]
        for col, w in (((0, 0, 0, 110), th + 6), ((255, 255, 255, 255), th)):
            for cx, cy, sx, sy in corners:
                d.line([(cx, cy + sy * arm), (cx, cy), (cx + sx * arm, cy)], fill=col, width=w, joint="curve")
        # blinking gold lock dot + optional label
        if int(el * 4) % 2 == 0 or el > 1.0:
            r = 9
            d.ellipse([x1 - arm / 2 - r, y0 + arm / 2 - r, x1 - arm / 2 + r, y0 + arm / 2 + r], fill=rk.GOLD + (255,))
        label = self.p.get("label", "")
        if label and snap >= 0.99:
            f = rk.font("bold", 40)
            d.text((x0, y1 + 18), label.upper(), font=f, fill=(255, 255, 255, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0, 120))
        return rk.alpha_paste(out, np.asarray(img), 0, 0)


class BackdropWord(Effect):
    """Giant word placed behind the person: text is drawn, then the person is composited back on top."""
    name, layer = "backdrop-word", 1

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._sprite = None

    def sprite(self):
        if self._sprite is None:
            text = str(self.p.get("text", "SALE")).upper()
            col = rk.GOLD if self.p.get("color", "white") == "gold" else rk.WHITE
            size = 400
            f = rk.font("black", size)
            l, t, r, b = f.getbbox(text)
            size = int(size * min(1.0, (rk.W * 0.94) / max(r - l, 1)))   # fit width
            self._sprite = text_sprite(text, "black", size, col, shadow=90, blur=24, offset=10)
        return self._sprite

    def apply(self, frame, ctx):
        el, rem = ctx.t - self.start, self.end - ctx.t
        s = 0.88 + 0.12 * rk.ease_out_cubic(el / 0.45) + 0.03 * self.local(ctx.t)   # slow drift
        op = min(1.0, el / 0.25, rem / 0.25)
        y = float(self.p.get("y", 0.30)) * rk.H
        matte = ctx.matte(frame)
        layer = frame.copy()
        paste_center(layer, scaled(self.sprite(), s), rk.W / 2, y, op)
        if matte is None:   # fallback: text over everything but semi-transparent
            return (frame * 0.45 + layer * 0.55).astype(np.uint8)
        m = matte[..., None]
        return (frame * m + layer * (1 - m)).astype(np.uint8)


class GlitterSpotlight(Effect):
    """Darkens everything except a soft spotlight on the face, with twinkling gold glitter."""
    name, layer = "glitter-spotlight", 1

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        rng = np.random.default_rng(7)
        n = int(self.p.get("density", 70))
        self.parts = np.column_stack([
            rng.uniform(-1, 1, n), rng.uniform(-1.2, 1.4, n),     # position around spotlight
            rng.uniform(0, 2 * np.pi, n), rng.uniform(2, 6, n),   # twinkle phase / speed
            rng.uniform(6, 22, n), rng.uniform(15, 60, n),        # size / fall speed
            rng.integers(0, 3, n),                                # colour index
        ])
        yy, xx = np.mgrid[0:rk.H // 4, 0:rk.W // 4].astype(np.float32)
        self.grid = (xx * 4, yy * 4)

    def apply(self, frame, ctx):
        el, rem = ctx.t - self.start, self.end - ctx.t
        k = min(1.0, el / 0.4, rem / 0.4)
        fx, fy, fs = ctx.face
        cy = fy + fs * 0.6
        rx, ry = max(fs * 1.4, 300), max(fs * 2.2, 520)
        xx, yy = self.grid
        d = np.sqrt(((xx - fx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        light = np.clip(1.15 - d, 0, 1) ** 1.3
        light = cv2.resize(light, (rk.W, rk.H), interpolation=cv2.INTER_LINEAR)
        dim = 1 - 0.62 * k * (1 - light)
        warm = np.array([1.0 + 0.06 * k, 1.0 + 0.02 * k, 1.0 - 0.04 * k], np.float32)
        out = np.clip(frame.astype(np.float32) * dim[..., None] * warm, 0, 255).astype(np.uint8)

        img = Image.new("RGBA", (rk.W, rk.H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        cols = [rk.GOLD, (255, 236, 170), (255, 255, 255)]
        for px, py, ph, sp, sz, fall, ci in self.parts:
            x = fx + px * rx * 1.1
            y = (cy + py * ry * 0.8 + fall * el) % rk.H
            tw = 0.5 + 0.5 * math.sin(ph + sp * el)
            a = int(255 * k * tw)
            if a < 20:
                continue
            s = sz * (0.5 + 0.5 * tw)
            c = cols[int(ci)] + (a,)
            # 4-point star
            dr.polygon([(x, y - s), (x + s * 0.18, y - s * 0.18), (x + s, y), (x + s * 0.18, y + s * 0.18),
                        (x, y + s), (x - s * 0.18, y + s * 0.18), (x - s, y), (x - s * 0.18, y - s * 0.18)], fill=c)
            dr.ellipse([x - s * 0.15, y - s * 0.15, x + s * 0.15, y + s * 0.15], fill=(255, 255, 255, a))
        glow = img.filter(ImageFilter.GaussianBlur(6))
        out = rk.alpha_paste(out, np.asarray(glow), 0, 0, 0.8)
        return rk.alpha_paste(out, np.asarray(img), 0, 0)


class Countdown(Effect):
    """Big 3-2-1 numbers that pop in, with a gold ring that empties every second."""
    name, layer = "countdown", 2

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.n = int(self.p.get("from", 3))
        self._cache = {}

    def apply(self, frame, ctx):
        step = self.dur / self.n
        el = ctx.t - self.start
        i = min(int(el / step), self.n - 1)
        num = self.n - i
        lt = (el - i * step) / step
        cx, cy = rk.W / 2, rk.H * float(self.p.get("y", 0.42))
        if num not in self._cache:
            self._cache[num] = text_sprite(str(num), "black", 420, rk.WHITE, shadow=150, blur=22, offset=10)
        s = 1.35 - 0.35 * rk.ease_out_back(lt / 0.35)
        op = min(1.0, lt / 0.12) * (1.0 if lt < 0.8 else max(0.0, (1 - lt) / 0.2))
        # ring
        R, th = 250, 16
        ring = Image.new("RGBA", (2 * R + 60, 2 * R + 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(ring)
        box = [30, 30, 30 + 2 * R, 30 + 2 * R]
        d.ellipse(box, outline=(255, 255, 255, 70), width=th)
        d.arc(box, -90, -90 + 360 * (1 - lt), fill=rk.GOLD + (255,), width=th)
        ring = ring.filter(ImageFilter.GaussianBlur(0.6))
        paste_center(frame, np.asarray(ring), cx, cy, min(1.0, el / 0.2))
        paste_center(frame, scaled(self._cache[num], s), cx, cy, op)
        label = self.p.get("label", "")
        if label:
            if "label" not in self._cache:
                self._cache["label"] = text_sprite(label.upper(), "bold", 58, rk.WHITE, shadow=150, blur=10, offset=5)
            paste_center(frame, self._cache["label"], cx, cy - R - 90, min(1.0, el / 0.25))
        return frame


class TheBill(Effect):
    """A paper receipt slides up; items type in line by line; total lands with a gold stamp."""
    name, layer = "the-bill", 2

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        raw = str(self.p.get("items", "Saree:1499;Blouse:499;Delivery:0"))
        self.items = []
        for part in raw.split(";"):
            if ":" in part:
                n, v = part.rsplit(":", 1)
                self.items.append((n.strip(), float(v)))
        self.cur = self.p.get("currency", "₹")
        self.title = self.p.get("title", "BILL")
        disc = str(self.p.get("discount", "")).strip()
        sub = sum(v for _, v in self.items)
        self.discount = 0.0
        if disc.endswith("%"):
            self.discount = sub * float(disc[:-1]) / 100
        elif disc:
            self.discount = float(disc)
        self.total = sub - self.discount
        self._layers = None

    def money(self, v):
        if v == 0:
            return "FREE"
        return f"{self.cur}{v:,.0f}"

    def build(self):
        """Pre-render the receipt in stages: [paper, row1, row2, ..., total]."""
        Wd = 780
        pad = 56
        mono, bold = rk.font("bold", 40), rk.font("bold", 46)   # Inter has the ₹ glyph
        rows = [(n, self.money(v)) for n, v in self.items]
        if self.discount:
            rows.append(("Discount", "-" + self.money(self.discount)))
        row_h = 70
        Hd = pad + 110 + 40 + row_h * len(rows) + 50 + 130 + pad + 30
        paper = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
        d = ImageDraw.Draw(paper)
        # zig-zag torn bottom edge
        z = 22
        poly = [(0, 0), (Wd, 0), (Wd, Hd - z)]
        for x in range(Wd, -1, -z * 2):
            poly += [(x, Hd - z), (x - z, Hd)]
        poly += [(0, Hd - z)]
        d.polygon(poly, fill=(252, 250, 244, 255))
        tf = rk.font("black", 64)
        d.text((Wd / 2, pad + 40), self.title, font=tf, fill=(20, 20, 20, 255), anchor="mm")
        d.text((Wd / 2, pad + 100), "* * * * * * * * * * * * *", font=rk.font("mono", 26),
               fill=(150, 150, 150, 255), anchor="mm")
        # shadow under paper
        sh = Image.new("RGBA", (Wd + 80, Hd + 80), (0, 0, 0, 0))
        sh.paste(Image.new("RGBA", (Wd, Hd), (0, 0, 0, 120)), (40, 52), paper)
        sh = sh.filter(ImageFilter.GaussianBlur(18))
        sh.alpha_composite(paper, (40, 30))
        base = sh
        layers = [np.asarray(base)]
        y = pad + 150 + 30
        cur = base.copy()
        for n, v in rows:
            d = ImageDraw.Draw(cur)
            d.text((40 + pad, y), n, font=mono, fill=(40, 40, 40, 255), anchor="lm")
            col = (30, 130, 60, 255) if v == "FREE" or v.startswith("-") else (40, 40, 40, 255)
            d.text((40 + Wd - pad, y), v, font=mono, fill=col, anchor="rm")
            y += row_h
            layers.append(np.asarray(cur.copy()))
        d = ImageDraw.Draw(cur)
        d.line([(40 + pad, y), (40 + Wd - pad, y)], fill=(60, 60, 60, 255), width=3)
        y += 85
        d.text((40 + pad, y), "TOTAL", font=bold, fill=(20, 20, 20, 255), anchor="lm")
        tot = rk.font("black", 84)
        # gold highlighter swipe behind the total
        l, t, r, b = d.textbbox((40 + Wd - pad, y), self.money(self.total), font=tot, anchor="rm")
        d.rounded_rectangle([l - 16, t + 8, r + 16, b + 6], radius=10, fill=rk.GOLD + (255,))
        d.text((40 + Wd - pad, y), self.money(self.total), font=tot, fill=(20, 20, 20, 255), anchor="rm")
        layers.append(np.asarray(cur))
        self._layers = layers

    def apply(self, frame, ctx):
        if self._layers is None:
            self.build()
        el, rem = ctx.t - self.start, self.end - ctx.t
        n_rows = len(self._layers) - 1
        slide = 0.45
        reveal = max(0.0, min(self.dur - slide - 0.6, 0.35 * n_rows))
        stage = 0 if el < slide else min(n_rows, 1 + int((el - slide) / max(reveal / n_rows, 1e-3)))
        img = self._layers[stage]
        h, w = img.shape[:2]
        y_final = rk.SAFE_TOP + 40
        k = rk.ease_out_back(el / slide, 1.2)
        out_k = rk.ease_in_out(1 - rem / 0.35) if rem < 0.35 else 0.0
        y = y_final + (rk.H - y_final) * (1 - k) + (rk.H - y_final) * out_k
        x = (rk.W - w) // 2
        # tiny tilt for a paper feel
        angle = -2.0 * (1 - min(1.0, el / slide))
        if abs(angle) > 0.05:
            pil = Image.fromarray(img).rotate(angle, resample=Image.BICUBIC, expand=False)
            img = np.asarray(pil)
        # total "stamp" punch
        if stage == n_rows:
            since = el - slide - reveal
            s = 1.0 + 0.05 * max(0.0, 1 - since / 0.2)
            img = scaled(img, s)
            x -= (img.shape[1] - w) // 2
        return rk.alpha_paste(frame, img, int(x), int(y))


EFFECTS = {c.name: c for c in (BackdropWord, DigitalZoom, LockedOn, TheBill, GlitterSpotlight, Countdown, Pullback)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_fx(spec: str) -> Effect:
    """'name@start-end[:k=v,k=v]'"""
    head, _, params = spec.partition(":")
    name, _, rng = head.partition("@")
    name = name.strip()
    if name not in EFFECTS:
        raise SystemExit(f"Unknown effect '{name}'. Available: {', '.join(EFFECTS)}")
    if not rng:
        raise SystemExit(f"'{spec}': time range chahiye, jaise {name}@2-5")
    a, _, b = rng.partition("-")
    kv = {}
    for item in filter(None, (s.strip() for s in params.split(","))):
        k, _, v = item.partition("=")
        kv[k.strip()] = v.strip()
    return EFFECTS[name](float(a), float(b), **kv)


def demo_plan(duration: float) -> list[Effect]:
    """Spread every effect across the clip for a showcase reel."""
    slots = [
        ("pullback", {}),
        ("backdrop-word", {"text": "OFFER"}),
        ("digital-zoom", {"zoom": "1.3"}),
        ("glitter-spotlight", {}),
        ("the-bill", {"items": "Saree:1499;Blouse:499;Delivery:0", "discount": "20%"}),
        ("locked-on", {"label": "best price"}),
        ("countdown", {"from": "3", "label": "offer ends in"}),
    ]
    weights = [1.6, 2.2, 1.8, 2.2, 3.2, 1.8, 3.0]
    scale = duration / sum(weights)
    t, out = 0.0, []
    for (name, kv), w in zip(slots, weights):
        out.append(EFFECTS[name](t, t + w * scale, **kv))
        t += w * scale
    return out


def render(src: Path, out: Path, effects: list[Effect], fit="auto", start=None, end=None,
           captions=None) -> None:
    effects = sorted(effects, key=lambda e: e.layer)
    off = start or 0.0
    reader = rk.FrameReader(src, fit=fit, start=start, end=end)
    writer = rk.FrameWriter(out, audio_src=src, start=start, end=end)
    ctx = Ctx()
    t0 = time.time()
    n = 0
    for n, frame in enumerate(reader):
        t = n / rk.FPS
        ctx.t = t
        ctx.face = ctx.tracker.update(frame)
        for e in effects:
            if e.active(t):
                frame = e.apply(frame, ctx)
        if captions is not None:
            frame = captions.draw(frame, off + t)
        writer.write(frame)
        if n % 90 == 0:
            print(f"\r[effects] {t:5.1f}s rendered", end="", flush=True)
    writer.close()
    print(f"\n[effects] done: {n + 1} frames in {time.time() - t0:.1f}s -> {out}")


def main() -> None:
    import captions as cap_mod

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="clip path or filename in Raw/ (default: first clip in Raw/)")
    ap.add_argument("-o", "--output", help="output mp4 (default Exports/<clip>_fx.mp4)")
    ap.add_argument("--fx", action="append", default=[], help="effect spec, repeatable: name@start-end[:k=v,...]")
    ap.add_argument("--demo", action="store_true", help="apply all 7 effects one after another")
    ap.add_argument("--list", action="store_true", help="list effects and exit")
    ap.add_argument("--fit", choices=["auto", "crop", "blur"], default="auto")
    ap.add_argument("--start", type=float, help="trim start (s)")
    ap.add_argument("--end", type=float, help="trim end (s)")
    ap.add_argument("--captions", action="store_true", help="also burn word-by-word captions (captions.py)")
    cap_mod.add_caption_args(ap)
    args = ap.parse_args()

    if args.list:
        for name, cls in EFFECTS.items():
            print(f"{name:18s} {cls.__doc__.strip()}")
        return

    src = rk.resolve_input(args.input)
    info = rk.probe(src)
    dur = (args.end or info.duration) - (args.start or 0)
    effects = [parse_fx(s) for s in args.fx]
    if args.demo:
        effects += demo_plan(dur)
    if not effects and not args.captions:
        raise SystemExit("Koi effect nahi diya. --fx name@start-end ya --demo use karein (--list dekhein).")

    suffix = "demo" if args.demo else "fx"
    out = Path(args.output) if args.output else rk.default_output(src, suffix)
    cap = None
    if args.captions:
        cap = cap_mod.renderer_from_args(args, src, rk.EXPORT_DIR / f"{src.stem}_words.json")
    print(f"[effects] {src.name} -> {out}")
    for e in sorted(effects, key=lambda e: e.start):
        print(f"   {e.start:5.2f}-{e.end:5.2f}s  {e.name}  {e.p or ''}")
    render(src, out, effects, args.fit, args.start, args.end, cap)


if __name__ == "__main__":
    sys.exit(main())
