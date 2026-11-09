# Ai Video Editor

Marketing reels ka project folder.

| Folder | Kya rakhna hai |
|---|---|
| `Raw/` | Original footage, photos, audio — bina edit kiya hua |
| `References/` | Reference reels, style notes, scripts, client brief |
| `Exports/` | Final ready reels |

## Editing tools

```bash
pip install -r requirements.txt          # ffmpeg bhi install hona chahiye
python captions.py Raw/clip.mov          # Hinglish word-by-word captions
python effects.py Raw/clip.mov --demo --captions
```

Poora workflow, captions style aur effects list: [CLAUDE.md](CLAUDE.md).

## Naming

`client_reel-naam_tarikh` — jaise `bandhan-saree_diwali-offer_2026-11-10.mp4`

## Dhyan rahe

GitHub ek file 100 MB se badi nahi leta. Badi video files Drive par rakhein aur yahan sirf link ya chhoti files daalein.
