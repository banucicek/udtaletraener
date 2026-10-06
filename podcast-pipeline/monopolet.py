#!/usr/bin/env python3
"""
Find the most used everyday expressions in a Danish podcast and cut native audio clips of them.

Steps: download episodes from the RSS feed -> transcribe with Whisper (word timestamps)
-> count recurring 2-5 word expressions -> cut one clear clip per expression.

Usage:
  python monopolet.py                 # 10 latest Sara & Monopolet episodes, top 80 expressions
  python monopolet.py --episodes 20 --top 120
  python monopolet.py --feed <rss-url> # any other podcast
Output (in ./output):
  expressions.csv     ranked expressions with counts and an example sentence
  clips/*.m4a         one native clip per expression, named after the expression
  transcripts/*.json  full transcripts with word timings (reused on re-runs)
"""
import argparse, csv, json, os, platform, re, subprocess, sys, unicodedata, urllib.request
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET

DEFAULT_FEED = "https://api.dr.dk/podcasts/v1/feeds/mads-monopolet-podcast.xml?format=podcast"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
EP_DIR = os.path.join(HERE, "episodes")
TR_DIR = os.path.join(OUT, "transcripts")
CLIP_DIR = os.path.join(OUT, "clips")

# Words that alone carry no "expression" — an n-gram made only of these is still kept
# (e.g. "ikke også", "det er jo"), but n-grams must contain at least one word that is
# not a pure filler sound.
FILLER = {"øh", "øhm", "eh", "ehm", "hm", "hmm", "mm", "mhm", "ah", "aha"}


def log(*a):
    print(*a, flush=True)


def slug(s, n=60):
    s = unicodedata.normalize("NFC", s).strip().lower()
    s = re.sub(r"[^\wæøå ]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s[:n].strip() or "clip"


def norm_word(w):
    w = unicodedata.normalize("NFC", w).strip().lower()
    w = re.sub(r"^[^\wæøå]+|[^\wæøå]+$", "", w)
    return w


# ---------------------------------------------------------------- download
def fetch_episodes(feed, n):
    os.makedirs(EP_DIR, exist_ok=True)
    log(f"Reading feed {feed}")
    req = urllib.request.Request(feed, headers={"User-Agent": "Mozilla/5.0 udtaletraener"})
    root = ET.fromstring(urllib.request.urlopen(req, timeout=60).read())
    items = root.findall("./channel/item")
    eps = []
    for it in items:
        enc = it.find("enclosure")
        if enc is None or not enc.get("url"):
            continue
        title = (it.findtext("title") or "episode").strip()
        eps.append((title, enc.get("url")))
        if len(eps) >= n:
            break
    paths = []
    for i, (title, url) in enumerate(eps, 1):
        ext = os.path.splitext(url.split("?")[0])[1] or ".mp3"
        path = os.path.join(EP_DIR, slug(title, 80).replace(" ", "_") + ext)
        if not os.path.exists(path):
            log(f"[{i}/{len(eps)}] Downloading {title}")
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 udtaletraener"})
            with urllib.request.urlopen(r, timeout=300) as resp, open(path + ".part", "wb") as f:
                while True:
                    b = resp.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            os.replace(path + ".part", path)
        else:
            log(f"[{i}/{len(eps)}] Already have {title}")
        paths.append((title, path))
    return paths


# ---------------------------------------------------------------- transcribe
def transcribe(path, model_name):
    """Returns list of words: {w, start, end, p}"""
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        import mlx_whisper
        res = mlx_whisper.transcribe(path, path_or_hf_repo=model_name, language="da",
                                     word_timestamps=True, condition_on_previous_text=False)
        words = []
        for seg in res.get("segments", []):
            for w in seg.get("words", []):
                words.append({"w": w["word"].strip(), "start": float(w["start"]),
                              "end": float(w["end"]), "p": float(w.get("probability", 1.0))})
        return words
    from faster_whisper import WhisperModel
    m = WhisperModel(model_name, device="auto", compute_type="int8")
    segs, _ = m.transcribe(path, language="da", word_timestamps=True, vad_filter=True,
                           condition_on_previous_text=False)
    return [{"w": w.word.strip(), "start": w.start, "end": w.end, "p": w.probability}
            for s in segs for w in (s.words or [])]


def get_transcripts(episodes, model_name):
    os.makedirs(TR_DIR, exist_ok=True)
    out = []
    for i, (title, path) in enumerate(episodes, 1):
        tp = os.path.join(TR_DIR, os.path.basename(path) + ".json")
        if os.path.exists(tp):
            words = json.load(open(tp, encoding="utf-8"))["words"]
            log(f"[{i}/{len(episodes)}] Transcript cached: {title}")
        else:
            log(f"[{i}/{len(episodes)}] Transcribing {title} (this takes a while)")
            words = transcribe(path, model_name)
            json.dump({"title": title, "audio": path, "words": words},
                      open(tp, "w", encoding="utf-8"), ensure_ascii=False)
        out.append({"title": title, "audio": path, "words": words})
    return out


# ---------------------------------------------------------------- expressions
def find_expressions(transcripts, top, nmin=2, nmax=5, min_eps=3):
    count = Counter()
    eps_with = defaultdict(set)
    occ = defaultdict(list)  # gram -> [(episode_idx, first_word_idx)]
    for ei, t in enumerate(transcripts):
        toks = [norm_word(w["w"]) for w in t["words"]]
        # sentence breaks: words that ended with . ? ! split n-grams
        breaks = {i for i, w in enumerate(t["words"]) if re.search(r"[.?!]$", w["w"].strip())}
        for i in range(len(toks)):
            for n in range(nmin, nmax + 1):
                j = i + n
                if j > len(toks):
                    break
                seg = toks[i:j]
                if any(not s for s in seg):
                    break
                if any(k in breaks for k in range(i, j - 1)):
                    break
                if all(s in FILLER for s in seg) or seg[0] in FILLER or seg[-1] in FILLER:
                    continue
                g = " ".join(seg)
                count[g] += 1
                eps_with[g].add(ei)
                occ[g].append((ei, i))
    n_eps = len(transcripts)
    need = min(min_eps, max(1, n_eps))
    cands = {g: c for g, c in count.items() if len(eps_with[g]) >= need and c >= 4}
    # Drop a shorter n-gram when a longer one containing it accounts for most of its uses
    # ("ved jeg" is dropped if "det ved jeg ikke" covers 80% of it).
    longest_super = defaultdict(int)  # sub-gram -> largest count of a longer gram containing it
    for h, d in cands.items():
        hs = h.split()
        for n in range(nmin, len(hs)):
            for k in range(len(hs) - n + 1):
                sub = " ".join(hs[k:k + n])
                if d > longest_super[sub]:
                    longest_super[sub] = d
    keep = {g: c for g, c in cands.items() if longest_super[g] < 0.8 * c}
    # Rank: frequency, slightly favouring longer expressions and spread across episodes
    def score(g):
        n = g.count(" ") + 1
        return keep[g] * (1 + 0.35 * (n - 2)) * (len(eps_with[g]) / max(1, n_eps)) ** 0.5
    ranked = sorted(keep, key=score, reverse=True)[:top]
    return [(g, keep[g], len(eps_with[g]), occ[g]) for g in ranked]


def best_occurrence(transcripts, occs, n):
    """Pick the clearest instance: high confidence, not too fast, some silence around it."""
    best, bs = None, -1e9
    for ei, i in occs[:400]:
        ws = transcripts[ei]["words"][i:i + n]
        dur = ws[-1]["end"] - ws[0]["start"]
        if dur <= 0.15 or dur > 4:
            continue
        conf = sum(w["p"] for w in ws) / n
        words = transcripts[ei]["words"]
        gap_before = ws[0]["start"] - words[i - 1]["end"] if i > 0 else 1.0
        gap_after = words[i + n]["start"] - ws[-1]["end"] if i + n < len(words) else 1.0
        rate = n / dur
        s = conf * 3 + min(gap_before, 0.4) + min(gap_after, 0.4) - abs(rate - 3.5) * 0.15
        if s > bs:
            bs, best = s, (ei, i)
    return best


def context(transcripts, ei, i, n, k=8):
    ws = transcripts[ei]["words"]
    return " ".join(w["w"] for w in ws[max(0, i - k): i + n + k]).strip()


def cut_clip(src, start, end, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, start):.3f}",
                    "-to", f"{end:.3f}", "-i", src, "-ac", "1", "-c:a", "aac", "-b:a", "96k",
                    "-af", "afade=t=in:d=0.03,areverse,afade=t=in:d=0.05,areverse", dst], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feed", default=DEFAULT_FEED)
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--top", type=int, default=80)
    ap.add_argument("--model", default=None,
                    help="Whisper model (default: mlx-community/whisper-large-v3-turbo on Apple Silicon, large-v3 otherwise)")
    ap.add_argument("--pad", type=float, default=0.25, help="seconds of audio kept around each clip")
    a = ap.parse_args()
    model = a.model or ("mlx-community/whisper-large-v3-turbo"
                        if platform.system() == "Darwin" and platform.machine() == "arm64" else "large-v3")

    episodes = fetch_episodes(a.feed, a.episodes)
    if not episodes:
        sys.exit("No episodes with audio found in that feed.")
    transcripts = get_transcripts(episodes, model)
    exprs = find_expressions(transcripts, a.top)
    if not exprs:
        sys.exit("No recurring expressions found. Try more episodes.")

    os.makedirs(CLIP_DIR, exist_ok=True)
    rows = []
    for rank, (g, c, ne, occs) in enumerate(exprs, 1):
        n = g.count(" ") + 1
        b = best_occurrence(transcripts, occs, n)
        clip = ""
        example = ""
        if b:
            ei, i = b
            ws = transcripts[ei]["words"][i:i + n]
            name = g.capitalize() + ".m4a"
            dst = os.path.join(CLIP_DIR, name)
            try:
                cut_clip(transcripts[ei]["audio"], ws[0]["start"] - a.pad, ws[-1]["end"] + a.pad, dst)
                clip = name
            except subprocess.CalledProcessError:
                pass
            example = context(transcripts, ei, i, n)
        rows.append({"rank": rank, "expression": g, "count": c, "episodes": ne, "clip": clip, "example": example})
        log(f"{rank:>3}. {g}  ({c}x in {ne} episodes)")

    with open(os.path.join(OUT, "expressions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    log(f"\nDone. {len(rows)} expressions -> {os.path.join(OUT, 'expressions.csv')}")
    log(f"Clips in {CLIP_DIR}. Load them into Udtaletræner with '+ Add clips'.")


if __name__ == "__main__":
    main()
