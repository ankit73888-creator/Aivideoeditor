# Whisper captions

[whisper.cpp](https://github.com/ggml-org/whisper.cpp) se video ke captions (`.srt`) banane ka setup. Sab kuch aapke Windows PC par offline chalta hai.

## Ek baar: setup

Repo folder ke andar PowerShell kholkar:

```powershell
powershell -ExecutionPolicy Bypass -File Tools\whisper\setup.ps1
```

Yeh whisper.cpp, model (lagbhag 1.6 GB) aur ffmpeg download karta hai. ffmpeg naya install hua ho to PowerShell band karke dobara kholein.

## Har video ke liye

```powershell
powershell -ExecutionPolicy Bypass -File Tools\whisper\transcribe.ps1 "Raw\video.mp4"
```

Video ke bagal mein `video.srt` ban jaati hai. Ise Premiere Pro ya DaVinci Resolve mein import karein.

| Option | Kaam |
|---|---|
| `-Language en` | English video (default `hi` = Hindi, `auto` = khud pehchane) |
| `-Translate` | Hindi audio se English captions |
| `-MaxLen 30` | Reels ke liye chhoti caption lines |

## Dhyan rahe

- Hindi captions Devanagari (हिंदी) mein aate hain, Roman Hinglish mein nahi.
- `bin/` aur `models/` GitHub par nahi jaate (bahut bade hain); har PC par `setup.ps1` ek baar chalana hota hai.
- Chhota/tez model chahiye to: `setup.ps1 -Model small`, phir `transcribe.ps1 ... -Model small`.
