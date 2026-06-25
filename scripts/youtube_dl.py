#!/usr/bin/env python3
"""
youtube_dl.py — Busca una canción en YouTube y la descarga como MP3.

Requiere: yt-dlp y ffmpeg (brew install yt-dlp ffmpeg).

Modos:
  Buscar (imprime JSON, una línea por resultado):
    python3 youtube_dl.py search "Soda Stereo De Musica Ligera" [N]

  Descargar a MP3 en una carpeta (y arreglar metadata + portada vía Shazam):
    python3 youtube_dl.py download "<url o id>" --dest <carpeta> \
        [--artist "X"] [--track "Y"]
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_DIR  = Path(__file__).parent.parent / "output"
LEDGER_FILE = OUTPUT_DIR / "downloads_ledger.json"

# Reutiliza el tagger (Shazam + escritura de tags/portada) que ya existe
sys.path.insert(0, str(Path(__file__).parent))
try:
    import tag_music
    HAS_TAGGER = True
except Exception:
    HAS_TAGGER = False


# ─────────────────────────────────────────────────────────────────────────────
# Dependencias
# ─────────────────────────────────────────────────────────────────────────────

def have(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


def deps_ok() -> bool:
    return have("yt-dlp") and have("ffmpeg")


# ─────────────────────────────────────────────────────────────────────────────
# Buscar
# ─────────────────────────────────────────────────────────────────────────────

def search(query: str, n: int = 8) -> list:
    """Devuelve [{id, title, uploader, duration}] desde YouTube (sin descargar)."""
    try:
        out = subprocess.run(
            ["yt-dlp", f"ytsearch{n}:{query}", "--flat-playlist",
             "--dump-json", "--no-warnings"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return []
    results = []
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        results.append({
            "id": d.get("id", ""),
            "title": d.get("title", ""),
            "uploader": d.get("uploader") or d.get("channel") or "",
            "duration": d.get("duration") or 0,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Limpieza de título de YouTube → (artista, canción)
# ─────────────────────────────────────────────────────────────────────────────

_JUNK = re.compile(
    r"\((official|lyric|audio|video|music|hd|4k|visuali[sz]er|mv|live|remaster"
    r"|color coded|letra|sub)[^)]*\)"
    r"|\[(official|lyric|audio|video|music|hd|4k|visuali[sz]er|mv|live|remaster)[^\]]*\]"
    r"|official\s+(music\s+)?video|official\s+audio|lyric video",
    re.IGNORECASE,
)


def clean_title(title: str, uploader: str):
    """Deduce (artista, canción) limpiando adornos típicos de YouTube."""
    t = _JUNK.sub("", title)
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—|")
    if " - " in t:
        artist, track = t.split(" - ", 1)
    else:
        artist = re.sub(r"\s*(VEVO|- Topic|Official)\s*$", "", uploader,
                        flags=re.IGNORECASE).strip()
        track = t
    return artist.strip(), track.strip()


def safe_name(s: str, max_len: int = 90) -> str:
    keep = set(" ._-()[]")
    out = "".join(c if (c.isalnum() or c in keep) else "_" for c in s)
    return out[:max_len].strip(" _") or "audio"


# ─────────────────────────────────────────────────────────────────────────────
# Ledger
# ─────────────────────────────────────────────────────────────────────────────

def ledger_upsert_completed(artist: str, track: str, file_path: Path, source_url: str):
    ledger = {}
    if LEDGER_FILE.exists():
        try:
            ledger = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except Exception:
            ledger = {}
    key = f"{artist} — {track}"
    prev = ledger.get(key, {})
    ledger[key] = {
        "artist": artist, "track": track,
        "info_hash": "", "magnet": "",
        "torrent_name": "YouTube → MP3",
        "source": "YouTube", "seeds": 0, "size": "",
        "requested_at": prev.get("requested_at", time.strftime("%Y-%m-%d %H:%M")),
        "status": "completed",
        "completed_at": time.strftime("%Y-%m-%d %H:%M"),
        "file_path": str(file_path),
        "tagged": True,
        "youtube_url": source_url,
    }
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LEDGER_FILE.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Descargar
# ─────────────────────────────────────────────────────────────────────────────

def download(url: str, dest: Path, artist_hint: str = "", track_hint: str = "",
             bitrate: str = "192") -> Path:
    """Descarga el audio como MP3 en `dest` y le aplica metadata + portada."""
    if not deps_ok():
        sys.exit("[!] Faltan dependencias. Instala con: brew install yt-dlp ffmpeg")
    dest.mkdir(parents=True, exist_ok=True)
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={url}"

    # Nombre base provisional; los tags finales los pone Shazam
    base = safe_name(f"{artist_hint} - {track_hint}") if (artist_hint and track_hint) else "%(title)s"
    out_tpl = str(dest / f"{base}.%(ext)s")

    print(f"⬇️  Descargando audio de: {url}")
    cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", f"{bitrate}K",
        "--no-playlist", "--no-warnings", "--newline",
        "-o", out_tpl, url,
    ]
    proc = subprocess.run(cmd, text=True)
    if proc.returncode != 0:
        sys.exit("[!] yt-dlp falló al descargar.")

    # Localiza el mp3 recién creado (el más reciente en dest)
    mp3s = sorted(dest.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp3s:
        sys.exit("[!] No se encontró el MP3 descargado.")
    mp3 = mp3s[0]
    print(f"✓ MP3: {mp3.name}")

    # Metadata + portada vía Shazam (reusa tag_music)
    artist, track = artist_hint, track_hint
    if not (artist and track):
        # Deduce del nombre del archivo
        from_name = mp3.stem
        if " - " in from_name:
            artist, track = from_name.split(" - ", 1)
        else:
            track = from_name

    if HAS_TAGGER and track:
        meta = tag_music.shazam_lookup(artist, track)
        if meta:
            cover = tag_music.fetch_artwork(meta.get("artwork", ""))
            tag_music.write_tags(mp3, meta, cover, dry_run=False)
            artist = meta.get("artist", artist)
            track  = meta.get("track", track)
            print(f"🏷️  Metadata: {artist} — {track}  [{meta.get('album','?')}]"
                  f"  {'🖼️' if cover else ''}")

    ledger_upsert_completed(artist, track, mp3, url)
    print(f"✅ Listo: {mp3}")
    return mp3


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Busca y descarga canciones de YouTube como MP3")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("n", nargs="?", type=int, default=8)

    p_dl = sub.add_parser("download")
    p_dl.add_argument("url")
    p_dl.add_argument("--dest", type=Path, required=True)
    p_dl.add_argument("--artist", default="")
    p_dl.add_argument("--track", default="")
    p_dl.add_argument("--bitrate", default="192")

    args = parser.parse_args()
    if args.mode == "search":
        for r in search(args.query, args.n):
            print(json.dumps(r, ensure_ascii=False))
    elif args.mode == "download":
        download(args.url, args.dest, args.artist, args.track, args.bitrate)
