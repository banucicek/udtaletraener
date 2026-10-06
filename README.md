# Udtaletræner

Practice Danish pronunciation by comparing your melody with a native speaker.

**Live app:** https://banucicek.github.io/udtaletraener/

## The app (`index.html`)

1. Pick a phrase, or add your own native clips with **+ Add clips** (the file name becomes the caption).
2. Play the native clip, then tap **Record** and say the same sentence.
3. Both pitch curves are drawn on top of each other, time-aligned, with a loudness curve for tryk and short feedback on melody, stress and tempo.

Everything runs in the browser. Clips and phrases are stored only in that browser on that device.

## Podcast pipeline (`podcast-pipeline/`)

Finds the most used everyday expressions in a Danish podcast (default: *Sara & Monopolet* from DR) and cuts a native audio clip of each one, ready to load into the app.

```bash
cd podcast-pipeline
bash setup.sh                                   # one time: ffmpeg + Whisper
./.venv/bin/python monopolet.py --episodes 3    # quick test
./.venv/bin/python monopolet.py                 # 10 episodes, top 80 expressions
```

Output lands in `podcast-pipeline/output/` (ignored by git): `expressions.csv` and `clips/*.m4a`.
The podcast audio belongs to DR, so keep downloaded episodes and clips for personal study and out of this repo.
