"""reelkit — shared helpers for 9:16 vertical reels.

Frame pipeline (used by captions.py and effects.py):

    ffmpeg (decode + fit to 1080x1920) --rgb24 frames--> Python (numpy/PIL)
        --rgb24 frames--> ffmpeg (H.264 + AAC, Instagram/Shorts settings)

The original audio is copied from the source clip, so audio sync stays exact.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "Raw"
REF_DIR = ROOT / "References"
EXPORT_DIR = ROOT / "Exports"
FONT_DIR = ROOT / "fonts"

# ---- Reel spec (Instagram Reels / YouTube Shorts) ---------------------------
W, H = 1080, 1920
FPS = 30
SAFE_TOP = 220      # top UI (username, audio label)
SAFE_BOTTOM = 420   # caption/like/comment buttons at the bottom
SAFE_SIDE = 90      # right-side action buttons

GOLD = (245, 197, 66)
WHITE = (255, 255, 255)

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}


# ---- Fonts ------------------------------------------------------------------
_FONT_CANDIDATES = {
    "bold": [
        FONT_DIR / "Inter-ExtraBold.otf",
        "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    "bold_italic": [
        FONT_DIR / "Inter-ExtraBoldItalic.otf",
        "/usr/share/fonts/opentype/inter/Inter-ExtraBoldItalic.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        "C:/Windows/Fonts/arialbi.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    ],
    "black": [
        FONT_DIR / "Inter-Black.otf",
        "/usr/share/fonts/opentype/inter/Inter-Black.otf",
        FONT_DIR / "Inter-ExtraBold.otf",
        "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "mono": [
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "C:/Windows/Fonts/consolab.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ],
    "devanagari": [
        FONT_DIR / "NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "C:/Windows/Fonts/NirmalaB.ttf",
        "/System/Library/Fonts/Supplemental/DevanagariMT.ttc",
    ],
}
_font_cache: dict = {}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    for cand in _FONT_CANDIDATES[kind]:
        if Path(cand).exists():
            f = ImageFont.truetype(str(cand), size)
            _font_cache[key] = f
            return f
    f = ImageFont.load_default(size)
    _font_cache[key] = f
    return f


def has_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


# ---- Probing ----------------------------------------------------------------
@dataclass
class Info:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"'{tool}' nahi mila. ffmpeg install karein (https://ffmpeg.org/download.html).")


def probe(path: str | Path) -> Info:
    require_ffmpeg()
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    # iPhone .mov files store rotation as metadata; ffmpeg auto-rotates on decode.
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    rot = int(v.get("tags", {}).get("rotate", rot))
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    dur = float(data["format"].get("duration") or v.get("duration") or 0)
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    return Info(w, h, fps, dur, has_audio)


# ---- 9:16 fitting -----------------------------------------------------------
def fit_filter(info: Info, mode: str = "auto", fps: int = FPS) -> str:
    """ffmpeg filtergraph that turns any clip into 1080x1920 @ fps.

    crop : fill the frame, cut the sides (best for vertical / near-vertical phone footage)
    blur : full frame fitted in the middle, blurred copy as background (best for landscape)
    auto : crop if the source is vertical-ish, blur otherwise
    """
    if mode == "auto":
        mode = "crop" if info.width / info.height <= 0.8 else "blur"
    if mode == "crop":
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={W}:{H},setsar=1,fps={fps},format=rgb24")
    if mode == "blur":
        return (f"split=2[a][b];"
                f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=40:2,eq=brightness=-0.08[bg];"
                f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps},format=rgb24")
    raise ValueError(f"unknown fit mode: {mode}")


# ---- Frame I/O --------------------------------------------------------------
class FrameReader:
    """Iterate 1080x1920 RGB frames (numpy uint8, HxWx3) from any clip."""

    def __init__(self, path: str | Path, fit: str = "auto", fps: int = FPS,
                 start: float | None = None, end: float | None = None):
        self.path = str(path)
        self.info = probe(path)
        self.fps = fps
        cmd = ["ffmpeg", "-v", "error"]
        if start:
            cmd += ["-ss", f"{start:.3f}"]
        cmd += ["-i", self.path]
        if end:
            cmd += ["-t", f"{end - (start or 0):.3f}"]
        cmd += ["-filter_complex", fit_filter(self.info, fit, fps),
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=W * H * 3 * 2)

    def __iter__(self):
        size = W * H * 3
        while True:
            buf = self.proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        self.proc.stdout.close()
        self.proc.wait()


class FrameWriter:
    """Encode RGB frames to an Instagram-ready MP4, muxing audio from `audio_src`."""

    def __init__(self, out: str | Path, audio_src: str | Path | None = None,
                 fps: int = FPS, crf: int = 18, start: float | None = None,
                 end: float | None = None, preset: str = "medium"):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-v", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
        has_audio = audio_src is not None and probe(audio_src).has_audio
        if has_audio:
            if start:
                cmd += ["-ss", f"{start:.3f}"]
            cmd += ["-i", str(audio_src)]
            if end:
                cmd += ["-t", f"{end - (start or 0):.3f}"]
        cmd += ["-map", "0:v"]
        if has_audio:
            cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-g", str(fps * 2),
                "-movflags", "+faststart", str(out)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        self.proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg encode failed")


# ---- Compositing ------------------------------------------------------------
def alpha_paste(frame: np.ndarray, rgba: np.ndarray | Image.Image, x: int, y: int,
                opacity: float = 1.0) -> np.ndarray:
    """Alpha-blend an RGBA image onto an RGB frame at (x, y), clipped to the frame. In-place."""
    if isinstance(rgba, Image.Image):
        rgba = np.asarray(rgba.convert("RGBA"))
    h, w = rgba.shape[:2]
    fh, fw = frame.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, fw), min(y + h, fh)
    if x0 >= x1 or y0 >= y1:
        return frame
    src = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = src[..., 3:4] / 255.0 * opacity
    dst = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (src[..., :3] * a + dst * (1 - a)).astype(np.uint8)
    return frame


def ease_out_cubic(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 3 * t * t - 2 * t * t * t


def ease_out_back(t: float, s: float = 1.70158) -> float:
    t = min(max(t, 0.0), 1.0) - 1
    return t * t * ((s + 1) * t + s) + 1


def list_raw_clips() -> list[Path]:
    return sorted(p for p in RAW_DIR.rglob("*") if p.suffix.lower() in VIDEO_EXTS)


def resolve_input(arg: str | None) -> Path:
    """Accept a path, a bare filename inside Raw/, or nothing (first clip in Raw/)."""
    if arg:
        p = Path(arg)
        if p.exists():
            return p
        if (RAW_DIR / arg).exists():
            return RAW_DIR / arg
        raise SystemExit(f"Clip nahi mili: {arg}")
    clips = list_raw_clips()
    if not clips:
        raise SystemExit("Raw/ me koi video nahi hai. Footage Raw/ me daalein ya path dein.")
    return clips[0]


def default_output(src: Path, suffix: str) -> Path:
    return EXPORT_DIR / f"{src.stem}_{suffix}.mp4"
