#!/usr/bin/env python3
"""captions.py — Hinglish/Hindi word-by-word captions for 9:16 reels.

Style: white bold sans, chest height, soft shadow, accent words in gold italic,
no box, no background bar. Words pop in one by one as they are spoken.

Examples
    python captions.py                          # first clip in Raw/
    python captions.py Raw/IMG_5159.mov         # specific clip
    python captions.py IMG_5159.mov --accent "offer,sirf,free"
    python captions.py clip.mov --script devanagari
    python captions.py clip.mov --words Exports/clip_words.json   # re-render after fixing text

The transcript is saved as Exports/<clip>_words.json — fix any wrong word there and
re-run with --words to skip transcription.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import reelkit as rk

# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

PROMPTS = {
    # whisper copies the script/style of the prompt: Roman prompt -> Hinglish output
    "roman": "Namaste dosto, aaj ka offer bahut special hai. Sirf ₹499 mein!",
    "devanagari": "नमस्ते दोस्तों, आज का ऑफर बहुत स्पेशल है। सिर्फ़ ₹499 में!",
}


def transcribe(path: Path, model_size: str = "small", lang: str | None = "hi",
               device: str = "auto", script: str = "roman") -> list[dict]:
    """Return [{'text', 'start', 'end'}] per word using faster-whisper."""
    from faster_whisper import WhisperModel

    compute = "int8"
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    if device == "cuda":
        compute = "float16"
    print(f"[captions] whisper '{model_size}' on {device} — transcribing {path.name} ...", flush=True)
    t0 = time.time()
    model = WhisperModel(model_size, device=device, compute_type=compute)
    # decode with ffmpeg ourselves (16 kHz mono float) — avoids PyAV version issues with .mov
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    if audio.size == 0:
        raise SystemExit(f"{path.name} me audio track nahi hai — captions ke liye speech chahiye.")
    segments, info = model.transcribe(
        audio,
        language=lang or None,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
        initial_prompt=PROMPTS[script],
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            txt = w.word.strip()
            if txt:
                words.append({"text": txt, "start": round(w.start, 3), "end": round(w.end, 3)})
    print(f"[captions] {len(words)} words, language={info.language} "
          f"({info.language_probability:.2f}), {time.time() - t0:.1f}s", flush=True)
    return words


# ---------------------------------------------------------------------------
# Devanagari -> Hinglish (Roman) transliteration
# ---------------------------------------------------------------------------
_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j",
    "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t",
    "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh",
    "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s",
    "ह": "h", "ळ": "l", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "rh",
    "फ़": "f", "य़": "y",
}
_NUKTA = {"क": "क़", "ख": "ख़", "ग": "ग़", "ज": "ज़", "ड": "ड़", "ढ": "ढ़", "फ": "फ़", "य": "य़"}
_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऋ": "ri", "ऑ": "o", "ऍ": "e"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o",
           "ौ": "au", "ृ": "ri", "ॉ": "o", "ॅ": "e"}
_DIGITS = {chr(0x966 + i): str(i) for i in range(10)}
_VIRAMA, _NUKTA_SIGN = "्", "़"


# common words where casual Hinglish spelling beats the rules (add your own here)
HINGLISH_OVERRIDES = {
    "में": "mein", "हैं": "hain", "नहीं": "nahi", "यह": "yeh", "वह": "woh", "क्यों": "kyun",
    "हूँ": "hoon", "हूं": "hoon", "तो": "toh", "ये": "ye", "वो": "wo", "मैं": "main",
    "ऑफर": "offer", "ऑफ़र": "offer", "सेल": "sale", "फ्री": "free", "प्राइस": "price",
    "डिस्काउंट": "discount", "प्रोडक्ट": "product", "क्वालिटी": "quality", "बेस्ट": "best",
    "लिंक": "link", "फॉलो": "follow", "शेयर": "share", "वीडियो": "video", "रील": "reel",
    "लीजिए": "lijiye", "कीजिए": "kijiye", "दीजिए": "dijiye", "रुपये": "rupaye", "रुपए": "rupaye",
}


def to_hinglish(word: str) -> str:
    """Rule-based Devanagari -> casual Hinglish spelling (karna, aaj, bhi, offer...)."""
    if not rk.has_devanagari(word):
        return word
    core = word.strip("।,.!?")
    if core in HINGLISH_OVERRIDES:
        return word.replace(core, HINGLISH_OVERRIDES[core])
    # tokens: ('C', roman, has_inherent_a) | ('V', roman) | ('X', other)
    toks: list[list] = []
    chars = list(word)
    i = 0
    while i < len(chars):
        ch = chars[i]
        if i + 1 < len(chars) and chars[i + 1] == _NUKTA_SIGN and ch in _NUKTA:
            ch = _NUKTA[ch]
            i += 1
        if ch in _CONS:
            toks.append(["C", _CONS[ch], True])
        elif ch in _MATRAS and toks and toks[-1][0] == "C":
            toks[-1][2] = False
            toks.append(["V", _MATRAS[ch]])
        elif ch == _VIRAMA and toks and toks[-1][0] == "C":
            toks[-1][2] = False
        elif ch in _VOWELS:
            toks.append(["V", _VOWELS[ch]])
        elif ch in ("ं", "ँ"):
            toks.append(["X", "n"])
        elif ch == "ः":
            toks.append(["X", "h"])
        elif ch in _DIGITS:
            toks.append(["X", _DIGITS[ch]])
        elif ch == "।":
            toks.append(["X", "."])
        else:
            toks.append(["X", ch])
        i += 1

    # schwa deletion: word-final, and medial in V C[a] C V context (kar-na, sam-jho)
    # processed right-to-left so a later deletion is known when judging the earlier one
    cons_idx = [k for k, t in enumerate(toks) if t[0] == "C"]
    for k in reversed(cons_idx):
        if not toks[k][2]:
            continue
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        if nxt is None or (nxt[0] == "X" and not nxt[1].isalpha()):
            toks[k][2] = False            # final schwa: kamal, ghar
            continue
        prev_has_vowel = k > 0 and (toks[k - 1][0] == "V" or (toks[k - 1][0] == "C" and toks[k - 1][2]))
        if prev_has_vowel and nxt[0] == "C":
            after = toks[k + 2] if k + 2 < len(toks) else None
            if nxt[2] or (after is not None and after[0] == "V"):
                toks[k][2] = False        # medial: karna, samjho

    out = []
    for t in toks:
        if t[0] == "C":
            out.append(t[1] + ("a" if t[2] else ""))
        else:
            out.append(t[1])
    s = "".join(out)
    # long 'aa' only in the first syllable: hamaara -> hamara, divaali -> divali (aaj, khaas stay)
    m = re.search(r"[aeiou]+", s)
    if m:
        s = s[:m.end()] + s[m.end():].replace("aa", "a")
    # casual Hinglish endings: karnaa -> karna, bhee -> bhi, too -> tu
    s = re.sub(r"aa$", "a", s)
    s = re.sub(r"ee$", "i", s)
    s = re.sub(r"(?<=[^aeiou])oo$", "u", s)
    return s


# ---------------------------------------------------------------------------
# Phrase building + accent detection
# ---------------------------------------------------------------------------
ACCENT_WORDS = {
    # Hinglish marketing hooks
    "offer", "sale", "free", "best", "discount", "sirf", "only", "new", "naya", "nayi", "aaj",
    "abhi", "limited", "special", "premium", "exclusive", "guarantee", "guaranteed", "launch",
    "jaldi", "khatam", "last", "flat", "off", "deal", "combo", "bonus", "gift", "wow", "secret",
    "sabse", "pehli", "first", "100%", "diwali", "festive", "price", "daam", "sasta", "sasti",
}
_NUM_RE = re.compile(r"(\d|₹|%|rs\.?$)", re.I)


def _clean(token: str) -> str:
    return re.sub(r"[^\w₹%]", "", token.lower())


@dataclass
class Word:
    text: str
    start: float
    end: float
    accent: bool = False


@dataclass
class Phrase:
    words: list[Word] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end


def build_phrases(raw_words: list[dict], script: str = "roman", accent_extra: set[str] | None = None,
                  max_words: int = 3, max_chars: int = 18, gap: float = 0.45,
                  uppercase: bool = False) -> list[Phrase]:
    accents = ACCENT_WORDS | {a.lower() for a in (accent_extra or set())}
    words: list[Word] = []
    for w in raw_words:
        txt = w["text"]
        if script == "roman":
            txt = " ".join(to_hinglish(p) for p in txt.split())
        txt = txt.strip(" ,।")
        if not txt:
            continue
        if uppercase:
            txt = txt.upper()
        roman = " ".join(to_hinglish(p) for p in w["text"].split())   # keywords also match Devanagari
        is_acc = bool(w.get("accent")) or _clean(txt) in accents or _clean(w["text"]) in accents \
            or _clean(roman) in accents or bool(_NUM_RE.search(txt))
        words.append(Word(txt, float(w["start"]), float(w["end"]), is_acc))

    phrases: list[Phrase] = []
    cur = Phrase()
    for w in words:
        chars = sum(len(x.text) + 1 for x in cur.words) + len(w.text)
        ends_sentence = bool(re.search(r"[.?!।]$", w.text))
        too_long = len(cur.words) >= max_words or chars > max_chars
        # don't leave a sentence's last word alone on screen ("hai.")
        orphan_ok = ends_sentence and len(cur.words) <= max_words and chars <= max_chars + 6
        if cur.words and ((too_long and not orphan_ok) or w.start - cur.words[-1].end > gap):
            phrases.append(cur)
            cur = Phrase()
        cur.words.append(w)
        if ends_sentence:
            phrases.append(cur)
            cur = Phrase()
    if cur.words:
        phrases.append(cur)

    for p in phrases:
        # one gold accent per phrase keeps it punchy: numbers/prices > your --accent list > keywords
        acc = [w for w in p.words if w.accent]
        if len(acc) > 1:
            def rank(w: Word) -> int:
                if _NUM_RE.search(w.text):
                    return 0
                return 1 if _clean(w.text) in {a.lower() for a in (accent_extra or set())} else 2
            keep = min(acc, key=rank)
            for w in acc:
                w.accent = w is keep
        for w in p.words:              # display without trailing punctuation
            w.text = w.text.rstrip(".,!?।") or w.text
    return phrases


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
@dataclass
class CaptionStyle:
    size: int = 82                 # font px on a 1080x1920 frame
    y: float = 0.64                # vertical centre of the caption block (chest height)
    color: tuple = rk.WHITE
    accent_color: tuple = rk.GOLD
    shadow_alpha: int = 150        # soft shadow strength (0-255)
    shadow_blur: int = 14
    shadow_offset: int = 7
    line_gap: float = 1.12
    word_gap: float = 0.28         # space between words, as a fraction of font size
    pop: float = 0.12              # seconds for the pop-in animation
    hold: float = 0.35             # keep a phrase on screen this long after the last word


class CaptionRenderer:
    """Draw word-by-word captions on 1080x1920 RGB frames: renderer.draw(frame, t)."""

    def __init__(self, phrases: list[Phrase], style: CaptionStyle | None = None):
        self.phrases = phrases
        self.style = style or CaptionStyle()
        self._layout_cache: dict[int, list[tuple[int, int]]] = {}
        self._sprite_cache: dict[tuple, tuple[np.ndarray, int, int]] = {}
        # extend each phrase until the next starts (max hold) so captions don't flicker
        self._ends = []
        for i, p in enumerate(phrases):
            nxt = phrases[i + 1].start if i + 1 < len(phrases) else p.end + 10
            self._ends.append(min(p.end + self.style.hold, nxt))

    # -- fonts / measuring
    def _font(self, word: Word):
        s = self.style.size
        if rk.has_devanagari(word.text):
            return rk.font("devanagari", int(s * 1.08))
        return rk.font("bold_italic" if word.accent else "bold", s)

    def _layout(self, idx: int) -> list[tuple[int, int]]:
        """Top-left position for every word of phrase idx (final positions, no reflow)."""
        if idx in self._layout_cache:
            return self._layout_cache[idx]
        st = self.style
        p = self.phrases[idx]
        max_w = rk.W - 2 * rk.SAFE_SIDE
        gap = int(st.size * st.word_gap)
        sizes = []
        for w in p.words:
            l, t, r, b = self._font(w).getbbox(w.text)
            sizes.append((r, b))
        lines: list[list[int]] = [[]]
        lw = 0
        for i, (w_, _) in enumerate(sizes):
            add = w_ + (gap if lines[-1] else 0)
            if lines[-1] and lw + add > max_w:
                lines.append([])
                lw, add = 0, w_
            lines[-1].append(i)
            lw += add
        line_h = int(st.size * st.line_gap)
        block_h = line_h * len(lines)
        y0 = int(rk.H * st.y - block_h / 2)
        pos = [(0, 0)] * len(p.words)
        for li, line in enumerate(lines):
            total = sum(sizes[i][0] for i in line) + gap * (len(line) - 1)
            x = (rk.W - total) // 2
            for i in line:
                pos[i] = (x, y0 + li * line_h)
                x += sizes[i][0] + gap
        self._layout_cache[idx] = pos
        return pos

    # -- sprites
    def _sprite(self, word: Word, scale_step: int) -> tuple[np.ndarray, int, int]:
        """RGBA sprite (text + soft shadow) and its offset from the word's top-left."""
        key = (word.text, word.accent, scale_step)
        if key in self._sprite_cache:
            return self._sprite_cache[key]
        st = self.style
        f = self._font(word)
        l, t, r, b = f.getbbox(word.text)
        pad = st.shadow_blur * 3 + st.shadow_offset
        w, h = r + pad * 2, b + pad * 2
        color = st.accent_color if word.accent else st.color

        text_l = Image.new("L", (w, h), 0)
        ImageDraw.Draw(text_l).text((pad, pad), word.text, font=f, fill=255)
        if word.accent and rk.has_devanagari(word.text):
            # no italic Devanagari font -> synthetic slant
            text_l = text_l.transform(text_l.size, Image.AFFINE, (1, 0.2, -0.2 * h / 2, 0, 1, 0),
                                      resample=Image.BICUBIC)
        # soft shadow: blurred, offset, semi-transparent black + a tight contact shadow
        soft = text_l.filter(ImageFilter.GaussianBlur(st.shadow_blur))
        tight = text_l.filter(ImageFilter.GaussianBlur(3))
        sh = np.zeros((h, w), np.float32)
        o = st.shadow_offset
        sh[o:, :] += np.asarray(soft, np.float32)[:-o, :] * (st.shadow_alpha / 255)
        sh[2:, :] += np.asarray(tight, np.float32)[:-2, :] * 0.45
        sh = np.clip(sh, 0, 255)

        ta = np.asarray(text_l, np.float32) / 255.0
        rgba = np.zeros((h, w, 4), np.float32)
        rgba[..., :3] = np.array(color, np.float32) * ta[..., None]
        alpha = ta * 255 + sh * (1 - ta)
        rgba[..., 3] = alpha
        # un-premultiply colour where alpha > 0
        nz = alpha > 0
        rgba[..., :3][nz] = rgba[..., :3][nz] * 255 / np.maximum(alpha[nz, None], 1e-3)
        img = rgba.clip(0, 255).astype(np.uint8)
        ox = oy = -pad

        if scale_step < 3:            # pop-in: 82% -> 100% with slight overshoot
            s = [0.82, 0.94, 1.04][scale_step]
            pil = Image.fromarray(img)
            nw, nh = max(1, int(w * s)), max(1, int(h * s))
            pil = pil.resize((nw, nh), Image.BICUBIC)
            img = np.asarray(pil)
            ox = -pad - (nw - w) // 2
            oy = -pad - (nh - h) // 2
        self._sprite_cache[key] = (img, ox, oy)
        return self._sprite_cache[key]

    def active_phrase(self, t: float) -> int | None:
        for i, p in enumerate(self.phrases):
            if p.start - 0.05 <= t < self._ends[i]:
                return i
        return None

    def draw(self, frame: np.ndarray, t: float) -> np.ndarray:
        idx = self.active_phrase(t)
        if idx is None:
            return frame
        p = self.phrases[idx]
        pos = self._layout(idx)
        for w, (x, y) in zip(p.words, pos):
            if t < w.start - 0.03:
                break
            age = t - (w.start - 0.03)
            step = min(3, int(age / (self.style.pop / 3)))
            img, ox, oy = self._sprite(w, step)
            opacity = min(1.0, 0.35 + age / self.style.pop) if step < 3 else 1.0
            rk.alpha_paste(frame, img, x + ox, y + oy, opacity)
        return frame


def load_or_transcribe(src: Path, words_json: str | None, model: str, lang: str | None,
                       save_to: Path | None, script: str = "roman") -> list[dict]:
    if words_json:
        return json.loads(Path(words_json).read_text(encoding="utf-8"))
    words = transcribe(src, model, lang, script=script)
    if save_to:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[captions] transcript saved -> {save_to}")
    return words


def add_caption_args(ap: argparse.ArgumentParser) -> None:
    g = ap.add_argument_group("captions")
    g.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium/large-v3 (default small)")
    g.add_argument("--lang", default="hi", help="speech language for whisper, 'auto' to detect (default hi)")
    g.add_argument("--script", choices=["roman", "devanagari"], default="roman",
                   help="roman = Hinglish spelling (default), devanagari = हिंदी लिपि")
    g.add_argument("--words", help="use an existing *_words.json instead of transcribing")
    g.add_argument("--accent", default="", help="extra gold-italic words, comma separated")
    g.add_argument("--max-words", type=int, default=3, help="words per caption phrase (default 3)")
    g.add_argument("--caption-y", type=float, default=0.64, help="caption centre height 0-1 (default 0.64 = chest)")
    g.add_argument("--caption-size", type=int, default=82, help="font size in px (default 82)")
    g.add_argument("--upper", action="store_true", help="UPPERCASE captions")


def renderer_from_args(args, src: Path, words_out: Path | None) -> CaptionRenderer:
    lang = None if args.lang == "auto" else args.lang
    if words_out is not None and args.script == "devanagari":
        words_out = words_out.with_name(words_out.stem + "_deva.json")
    raw = load_or_transcribe(src, args.words, args.model, lang, words_out, args.script)
    extra = {a.strip() for a in args.accent.split(",") if a.strip()}
    phrases = build_phrases(raw, args.script, extra, max_words=args.max_words, uppercase=args.upper)
    style = CaptionStyle(size=args.caption_size, y=args.caption_y)
    return CaptionRenderer(phrases, style)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="clip path or filename in Raw/ (default: first clip in Raw/)")
    ap.add_argument("-o", "--output", help="output mp4 (default Exports/<clip>_captions.mp4)")
    ap.add_argument("--fit", choices=["auto", "crop", "blur"], default="auto", help="how to make it 9:16")
    ap.add_argument("--start", type=float, help="trim start (s)")
    ap.add_argument("--end", type=float, help="trim end (s)")
    add_caption_args(ap)
    args = ap.parse_args()

    src = rk.resolve_input(args.input)
    out = Path(args.output) if args.output else rk.default_output(src, "captions")
    words_out = rk.EXPORT_DIR / f"{src.stem}_words.json"
    cap = renderer_from_args(args, src, words_out)
    print(f"[captions] {len(cap.phrases)} phrases. Rendering -> {out}", flush=True)

    off = args.start or 0.0
    reader = rk.FrameReader(src, fit=args.fit, start=args.start, end=args.end)
    writer = rk.FrameWriter(out, audio_src=src, start=args.start, end=args.end)
    t0 = time.time()
    n = 0
    for n, frame in enumerate(reader):
        writer.write(cap.draw(frame, off + n / rk.FPS))
    writer.close()
    print(f"[captions] done: {n + 1} frames in {time.time() - t0:.1f}s -> {out}")


if __name__ == "__main__":
    sys.exit(main())
