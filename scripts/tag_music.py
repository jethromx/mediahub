#!/usr/bin/env python3
"""
tag_music.py — Arregla metadata (tags ID3) y portada de tu biblioteca musical.

Para cada archivo de audio con tags pobres (sin artista, sin título o sin
portada embebida), consulta Shazam (catálogo Apple Music, sin API key), escribe
artista/título/álbum/año/género y embebe la carátula. Reconcilia con el ledger
de descargas de mediahub (marca como completed + tagged).

Uso:
  python3 tag_music.py <carpeta> [--dry-run] [--limit N]

No borra ni mueve archivos: solo escribe tags en su lugar.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

OUTPUT_DIR        = Path(__file__).parent.parent / "output"
SHAZAM_CACHE_FILE = OUTPUT_DIR / "shazam_cache.json"
LEDGER_FILE       = OUTPUT_DIR / "downloads_ledger.json"

AUDIO_EXTS = {".mp3", ".flac", ".m4a"}

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON, ID3NoHeaderError
    from mutagen.flac import FLAC, Picture
    from mutagen.mp4 import MP4, MP4Cover
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\(feat[^)]*\)|\[feat[^\]]*\]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_filename(stem: str):
    """Deduce (artista, título) de un nombre tipo 'Artista - Título'."""
    m = re.match(r"^\s*(.+?)\s*[-–—]\s*(.+)$", stem)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", stem.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Shazam (cache compartido con la app)
# ─────────────────────────────────────────────────────────────────────────────

def shazam_lookup(artist: str, track: str) -> dict:
    cache = {}
    if SHAZAM_CACHE_FILE.exists():
        try:
            cache = json.loads(SHAZAM_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    key = f"{artist} — {track}"
    cached = cache.get(key)
    if cached is not None and (cached == {} or "preview" in cached):
        return cached
    out = {}
    try:
        url = "https://www.shazam.com/services/amapi/v1/catalog/US/search?" + \
            urllib.parse.urlencode({"term": f"{artist} {track}", "limit": 3, "types": "songs"})
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        songs = (data.get("results", {}).get("songs", {}).get("data", []))
        if songs:
            a = songs[0].get("attributes", {})
            out = {
                "album":   a.get("albumName", ""),
                "genre":   (a.get("genreNames") or [""])[0],
                "year":    (a.get("releaseDate") or "")[:4],
                "artist":  a.get("artistName", ""),
                "track":   a.get("name", ""),
                "preview": (a.get("previews") or [{}])[0].get("url", ""),
                "artwork": (a.get("artwork") or {}).get("url", ""),
            }
    except Exception:
        out = {}
    cache[key] = out
    try:
        SHAZAM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SHAZAM_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    except Exception:
        pass
    return out


def fetch_artwork(url: str, size: int = 600) -> bytes:
    if not url:
        return b""
    real = url.replace("{w}", str(size)).replace("{h}", str(size))
    try:
        req = urllib.request.Request(real, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.read()
    except Exception:
        return b""


# ─────────────────────────────────────────────────────────────────────────────
# Lectura/escritura de tags por formato
# ─────────────────────────────────────────────────────────────────────────────

def read_current(path: Path):
    """Devuelve (artist, title, has_cover)."""
    try:
        mf = MutagenFile(str(path))
    except Exception:
        return "", "", False
    if mf is None:
        return "", "", False
    ext = path.suffix.lower()
    artist = title = ""
    has_cover = False
    try:
        if ext == ".mp3":
            tags = mf.tags
            if tags:
                artist = str(tags.get("TPE1", "")) or str(tags.get("TPE2", ""))
                title  = str(tags.get("TIT2", ""))
                has_cover = any(k.startswith("APIC") for k in tags.keys())
        elif ext == ".flac":
            artist = (mf.get("artist") or [""])[0]
            title  = (mf.get("title") or [""])[0]
            has_cover = bool(mf.pictures)
        elif ext == ".m4a":
            artist = (mf.tags.get("\xa9ART") or [""])[0] if mf.tags else ""
            title  = (mf.tags.get("\xa9nam") or [""])[0] if mf.tags else ""
            has_cover = bool(mf.tags and mf.tags.get("covr"))
    except Exception:
        pass
    return artist.strip(), title.strip(), has_cover


def write_tags(path: Path, meta: dict, cover: bytes, dry_run: bool) -> bool:
    """Escribe tags y portada. Devuelve True si tuvo éxito (o lo haría en dry-run)."""
    if dry_run:
        return True
    ext = path.suffix.lower()
    artist = meta.get("artist", "")
    title  = meta.get("track", "")
    album  = meta.get("album", "")
    year   = meta.get("year", "")
    genre  = meta.get("genre", "")
    try:
        if ext == ".mp3":
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                tags = ID3()
            if artist: tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
            if title:  tags.setall("TIT2", [TIT2(encoding=3, text=title)])
            if album:  tags.setall("TALB", [TALB(encoding=3, text=album)])
            if year:   tags.setall("TDRC", [TDRC(encoding=3, text=year)])
            if genre:  tags.setall("TCON", [TCON(encoding=3, text=genre)])
            if cover:
                tags.delall("APIC")
                tags.add(APIC(encoding=3, mime="image/jpeg", type=3,
                              desc="Cover", data=cover))
            tags.save(str(path))
        elif ext == ".flac":
            mf = FLAC(str(path))
            if artist: mf["artist"] = artist
            if title:  mf["title"] = title
            if album:  mf["album"] = album
            if year:   mf["date"] = year
            if genre:  mf["genre"] = genre
            if cover:
                pic = Picture()
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.data = cover
                mf.clear_pictures()
                mf.add_picture(pic)
            mf.save()
        elif ext == ".m4a":
            mf = MP4(str(path))
            if artist: mf["\xa9ART"] = artist
            if title:  mf["\xa9nam"] = title
            if album:  mf["\xa9alb"] = album
            if year:   mf["\xa9day"] = year
            if genre:  mf["\xa9gen"] = genre
            if cover:
                mf["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
            mf.save()
        else:
            return False
        return True
    except Exception as e:
        print(f"    [!] Error escribiendo {path.name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Ledger
# ─────────────────────────────────────────────────────────────────────────────

def load_ledger() -> dict:
    if LEDGER_FILE.exists():
        try:
            return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def reconcile_ledger(ledger: dict, lookup: dict, artist: str, title: str,
                     path: Path) -> bool:
    """Marca como completed+tagged la entrada del ledger que coincida."""
    target_a, target_t = norm(artist), norm(title)
    changed = False
    for key, entry in ledger.items():
        if (norm(entry.get("artist", "")) == target_a
                and norm(entry.get("track", "")) == target_t):
            entry["status"] = "completed"
            entry["completed_at"] = time.strftime("%Y-%m-%d %H:%M")
            entry["file_path"] = str(path)
            entry["tagged"] = True
            changed = True
    return changed


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run(source_dir: Path, dry_run: bool = False, limit: int = 0):
    print(f"\n🏷️  Arreglo de metadata y portadas")
    print(f"    Carpeta: {source_dir}")
    print(f"    Modo   : {'DRY RUN (no escribe)' if dry_run else 'ESCRITURA REAL'}")
    print("=" * 60)

    if not HAS_MUTAGEN:
        sys.exit("[!] Falta mutagen. Instala con: pip install mutagen")
    if not source_dir.exists():
        sys.exit(f"[!] La carpeta no existe: {source_dir}")

    files = sorted(p for p in source_dir.rglob("*") if p.suffix.lower() in AUDIO_EXTS)
    total = len(files)
    print(f"\n[1/2] Archivos de audio encontrados: {total:,}")
    if total == 0:
        sys.exit(0)

    ledger = load_ledger()
    fixed = skipped = failed = 0
    processed = 0
    report = []

    print(f"\n[2/2] Procesando los que tienen tags pobres...\n")
    for p in files:
        artist, title, has_cover = read_current(p)
        # Tags pobres: falta artista, o título, o portada
        if artist and title and has_cover:
            skipped += 1
            continue

        # Deduce artista/título si faltan, desde el nombre de archivo
        if not artist or not title:
            fa, ft = parse_filename(p.stem)
            artist = artist or fa
            title  = title or ft
        if not title:
            skipped += 1
            continue

        meta = shazam_lookup(artist, title)
        if not meta:
            print(f"  ✗ Sin match Shazam: {p.name[:55]}")
            failed += 1
            continue

        cover = b"" if has_cover else fetch_artwork(meta.get("artwork", ""))
        ok = write_tags(p, meta, cover, dry_run)
        if ok:
            if not dry_run:
                reconcile_ledger(ledger, meta, meta.get("artist", artist),
                                 meta.get("track", title), p)
            fixed += 1
            tag = "[DRY] " if dry_run else ""
            cov = "🖼️" if cover else "—"
            print(f"  ✓ {tag}{meta.get('artist','')} — {meta.get('track','')}"
                  f"  [{meta.get('album','?')}] {cov}")
            report.append({
                "file": str(p), "artist": meta.get("artist", ""),
                "title": meta.get("track", ""), "album": meta.get("album", ""),
                "cover": bool(cover),
            })
        else:
            failed += 1

        processed += 1
        if limit and processed >= limit:
            print(f"\n  (límite de {limit} alcanzado)")
            break
        time.sleep(0.3)

    if not dry_run:
        try:
            LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
            LEDGER_FILE.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            pass

    print(f"\n{'='*60}")
    print(f"  ✓ {'Simulados' if dry_run else 'Arreglados'} : {fixed:,}")
    print(f"  — Ya completos (omitidos): {skipped:,}")
    print(f"  ✗ Sin match / error      : {failed:,}")

    report_path = OUTPUT_DIR / "_tag_report.json"
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "source": str(source_dir), "dry_run": dry_run,
            "fixed": fixed, "skipped": skipped, "failed": failed,
            "files": report,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  📄 Reporte: {report_path}")
    except Exception:
        pass
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arregla metadata y portadas de música")
    parser.add_argument("source", type=Path, help="Carpeta con tu música")
    parser.add_argument("--dry-run", action="store_true", help="Solo simula, no escribe")
    parser.add_argument("--limit", type=int, default=0, help="Máximo de archivos a procesar")
    args = parser.parse_args()
    run(source_dir=args.source, dry_run=args.dry_run, limit=args.limit)
