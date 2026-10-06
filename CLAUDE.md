# Udtaletræner — project notes

Goal: help a Danish learner improve pronunciation (melody, tryk, stød) by comparing their recordings with native speakers.

## Parts
- `index.html` — single-file web app (no build step). Plays a native clip with a caption, records the learner, and overlays pitch (semitones from each speaker's median) and loudness curves after DTW alignment on log-mel features. Pitch is YIN in JS. Phrases and clips are stored in the browser's IndexedDB. Served with GitHub Pages from `main` / root.
- `podcast-pipeline/` — Python pipeline run on the user's Mac:
  - `setup.sh` creates `.venv`, installs ffmpeg (Homebrew) and mlx-whisper (Apple Silicon) or faster-whisper (Intel).
  - `monopolet.py` downloads episodes from a podcast RSS feed (default: DR's *Sara & Monopolet*), transcribes with word timestamps, counts recurring 2–5 word expressions across ≥3 episodes, and cuts one clear clip per expression into `output/clips/`, plus `output/expressions.csv`.

## Conventions
- Episodes, transcripts and clips are DR's audio: never commit them (`podcast-pipeline/.gitignore`).
- Clip file names are the expression itself (capitalised), because the app uses the file name as the caption.
- Keep the app a single self-contained `index.html`.

## Ideas not done yet
- Stød detection (creaky voice: F0 dip, jitter, low HNR) compared against the native clip.
- Forced alignment to show feedback per syllable/word instead of per time span.
- Auto-import of `expressions.csv` + clips into the app.
