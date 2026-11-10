# HyperFrames

[HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen ka open-source tool) HTML se video banata hai: motion graphics, animated text, captions, transitions. Projects `Compositions/` folder mein rehte hain.

## Ek baar: setup

Repo folder ke andar PowerShell kholkar:

```powershell
powershell -ExecutionPolicy Bypass -File Tools\hyperframes\setup.ps1
```

Yeh Node.js 22+ aur ffmpeg check/install karta hai. Kuch naya install ho to PowerShell dobara kholkar script phir chalayein.

## Naya video

```powershell
cd Compositions
npx hyperframes init bandhan-saree_diwali-offer
cd bandhan-saree_diwali-offer
npx hyperframes preview     # browser mein live preview
npx hyperframes render      # MP4 banaye
```

Final MP4 ko `Exports/` mein rakhein (100 MB se badi ho to Drive par).

## Dhyan rahe

- `node_modules/` GitHub par nahi jaata; naye PC par project folder mein `npm install` chalana hota hai.
- Ready-made blocks (transitions, social overlays, charts): `npx hyperframes add <naam>` — list: https://hyperframes.heygen.com/catalog
- Whisper se bani `.srt` captions project mein la sakte hain: `npx hyperframes transcribe captions.srt`
