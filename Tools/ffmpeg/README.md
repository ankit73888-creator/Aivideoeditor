# FFmpeg

[FFmpeg](https://ffmpeg.org/) video/audio ko convert, cut, compress aur caption-burn karne ka tool hai. Whisper aur HyperFrames dono isi par chalte hain.

## Ek baar: setup

```powershell
powershell -ExecutionPolicy Bypass -File Tools\ffmpeg\setup.ps1
```

## Kaam ke commands

`in.mp4` ki jagah apni file ka naam likhein.

**Reel ke liye 1080x1920 (9:16) export, Instagram-ready:**

```powershell
ffmpeg -i in.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 192k -movflags +faststart reel.mp4
```

Video 9:16 na ho to upar-neeche ya side mein kaali patti aati hai (crop nahi hota). File chhoti chahiye to `-crf 20` ko `-crf 24` karein.

**Captions video par chipkana (whisper ki `.srt` se):**

```powershell
ffmpeg -i in.mp4 -vf "subtitles=in.srt" -c:a copy captioned.mp4
```

**Sirf audio nikalna:**

```powershell
ffmpeg -i in.mp4 -vn -c:a libmp3lame -q:a 2 audio.mp3
```

**Beech ka hissa kaatna (5 second se 20 second tak):**

```powershell
ffmpeg -ss 00:00:05 -to 00:00:20 -i in.mp4 -c copy cut.mp4
```

Yeh bina re-encode ke kaatta hai, isliye tez hai, par cut sabse paas ke keyframe par lagta hai (thoda aage-peeche ho sakta hai).
