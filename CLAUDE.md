# CLAUDE.md — AI Video Editor

Marketing reels (Instagram Reels / YouTube Shorts) banane ka project. Har output **9:16 vertical,
1080x1920, 30 fps, H.264 + AAC** hota hai.

## Folder workflow

| Folder | Kya hai | Rule |
|---|---|---|
| `Raw/` | Original footage (camera/phone clips, audio) | Kabhi overwrite/edit mat karo. Har client/reel ka sub-folder. Badi files Drive par — links `Raw/drive-links.md` me |
| `References/` | Reference reels, style notes, scripts, client brief | Style decide karne se pehle yahan dekho. Links `References/drive-links.md` me |
| `Exports/` | Final ready reels + transcripts (`*_words.json`) | Naam: `client_reel-naam_YYYY-MM-DD.mp4` |

Flow: **Raw/ clip → (effects.py + captions.py) → Exports/ reel**. References/ sirf dekhne ke liye, unko process nahi karna.

## Setup

```bash
# ffmpeg chahiye (ffmpeg -version se check karo)
pip install -r requirements.txt
```

Pehli run par models download hote hain: Whisper (`small`, ~480 MB, Hugging Face) aur MODNet
(~25 MB → `models/`, gitignored). Network me `huggingface.co` + `us.aws.cdn.hf.co` allowed hone chahiye.

## Scripts

- `reelkit.py` — shared helpers: 9:16 fitting (`crop` / `blur` / `auto`), ffmpeg frame reader/writer,
  fonts, safe zones, easing. Naye effects/scripts isi ko use karein.
- `captions.py` — Hinglish/Hindi speech → word-by-word captions.
- `effects.py` — 7 reel effects, `--captions` se ek hi pass me captions bhi.

### Captions style (fixed brand look — change mat karo bina pooche)
- White, bold sans (Inter ExtraBold), **chest height** (`--caption-y 0.64`), soft drop shadow
- Accent words **gold italic** (`#F5C542`, Inter ExtraBold Italic) — max 1 per phrase
  (priority: numbers/₹ → `--accent` list → built-in keywords like offer/sirf/free/best)
- **Koi box ya background bar nahi**
- 3 words per phrase, words pop in jaise bole jaate hain

```bash
python captions.py Raw/client/clip.mov                      # Roman Hinglish (default)
python captions.py clip.mov --accent "saree,diwali"          # extra gold words
python captions.py clip.mov --script devanagari --model medium   # हिंदी लिपि
python captions.py clip.mov --words Exports/clip_words.json  # galat word JSON me fix karke re-render
```
Transcript `Exports/<clip>_words.json` me save hota hai — galat shabd wahan theek karo, phir `--words` se dobara render (transcribe skip).

### Effects
| Effect | Kya karta hai | Params |
|---|---|---|
| `backdrop-word` | Bada word person ke **peeche** (MODNet cut-out) | `text=SALE, color=white\|gold, y=0.30` |
| `digital-zoom` | Face ki taraf punch-in zoom | `zoom=1.3, speed=0.25` |
| `locked-on` | Face-tracking crop + target brackets | `zoom=1.35, label=...` |
| `the-bill` | Receipt slide-up, items type-in, gold total | `items=Saree:1499;Blouse:499, discount=20%, title=BILL, currency=₹` |
| `glitter-spotlight` | Face par spotlight, baaki dim + gold glitter | `density=70` |
| `countdown` | 3-2-1 bade numbers + gold ring | `from=3, label=OFFER ENDS IN, y=0.42` |
| `pullback` | Tight face se full frame tak pull-back | `zoom=1.7` |

```bash
python effects.py --list
python effects.py Raw/clip.mov --fx digital-zoom@0-2 --fx "the-bill@3-7:items=Saree:1499;Blouse:499" --captions
python effects.py Raw/clip.mov --demo --captions        # saare effects ek ke baad ek
```
Spec format: `name@start-end[:key=value,key=value]` (seconds). Layer order: camera moves → backdrop/spotlight → graphics → captions.

## 9:16 rules
- Safe zones (`reelkit.py`): top 220 px, bottom 420 px, sides 90 px — text/graphics inke andar rakho.
- Vertical/phone footage → `--fit crop`; landscape → `--fit blur` (`auto` khud choose karta hai).
- iPhone `.mov` rotation ffmpeg khud handle karta hai.
- Export: CRF 18, `yuv420p`, `+faststart`, AAC 192k 48 kHz — Instagram ke liye seedha upload-ready.

## Test
`Raw/_sample/sample_talking_head.mp4` — synthetic test clip (public-domain NASA portrait + Piper Hindi TTS).
```bash
python effects.py Raw/_sample/sample_talking_head.mp4 --demo --captions --words Exports/sample_talking_head_words.json
```

## Dhyan rahe
- GitHub 100 MB/file limit — `.mov` raw files commit nahi hote (`.gitignore`), Drive par rakho.
- `opencv-python` 4.x hi chahiye (5.x me Haar face detector nahi hai).
- Devanagari font: repo me Inter (Latin) hai; Devanagari ke liye system font (Linux FreeSans/Noto, Windows Nirmala, macOS Devanagari MT). Behtar look ke liye `fonts/NotoSansDevanagari-Bold.ttf` daal sakte ho.
