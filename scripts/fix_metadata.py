#!/usr/bin/env python3
"""
fix_metadata.py — Analiza MP3s, completa metadatos y descarga portadas.

Qué hace por cada MP3:
  1. Lee los tags existentes (título, artista, álbum, año, género, portada)
  2. Extrae artista/título del nombre de fichero si los tags faltan
  3. Busca la info en MusicBrainz (API gratuita)
  4. Descarga la portada de Cover Art Archive o Last.fm
  5. Escribe todo de vuelta en el fichero

Uso:
  python3 fix_metadata.py /ruta/a/carpeta/de/musica

  # Solo analizar sin modificar (dry run):
  python3 fix_metadata.py /ruta/carpeta --dry-run

  # Forzar actualización aunque ya tenga tags:
  python3 fix_metadata.py /ruta/carpeta --force

Requiere:
  pip install mutagen requests
"""

import sys
import os
import re
import json
import time
import argparse
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

try:
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.id3 import (
        ID3, ID3NoHeaderError,
        TIT2, TPE1, TALB, TDRC, TCON, TRCK,
        APIC,
    )
except ImportError:
    sys.exit("Falta mutagen. Instálalo con: pip install mutagen")

try:
    import requests
except ImportError:
    sys.exit("Falta requests. Instálalo con: pip install requests")

# ── Credenciales ───────────────────────────────────────────────────────────────
LASTFM_API_KEY = "7049ab07a1bbfce19db16bea7b004b29"

MB_BASE    = "https://musicbrainz.org/ws/2"
CAA_BASE   = "https://coverartarchive.org"
LASTFM_API = "https://ws.audioscrobbler.com/2.0/"

MB_HEADERS = {
    "User-Agent": "fix-metadata-script/1.0 ( jethro.gutierrez@gmail.com )",
    "Accept":     "application/json",
}

# Segundos entre llamadas a MusicBrainz (rate limit: 1 req/seg)
MB_DELAY = 1.1

# ─────────────────────────────────────────────────────────────────────────────
# Lectura de tags existentes
# ─────────────────────────────────────────────────────────────────────────────

def read_tags(filepath):
    """Lee los tags ID3 actuales de un MP3. Retorna dict con lo que hay."""
    tags = {
        "title":  "",
        "artist": "",
        "album":  "",
        "year":   "",
        "genre":  "",
        "track":  "",
        "has_cover": False,
    }
    try:
        audio = ID3(filepath)
        tags["title"]  = str(audio.get("TIT2", "")).strip()
        tags["artist"] = str(audio.get("TPE1", "")).strip()
        tags["album"]  = str(audio.get("TALB", "")).strip()
        tags["year"]   = str(audio.get("TDRC", "")).strip()[:4]
        tags["genre"]  = str(audio.get("TCON", "")).strip()
        tags["track"]  = str(audio.get("TRCK", "")).strip()
        tags["has_cover"] = any(k.startswith("APIC") for k in audio.keys())
    except ID3NoHeaderError:
        pass
    except Exception as e:
        print(f"    [!] Error leyendo tags: {e}")
    return tags


def tags_complete(tags):
    """True si los tags esenciales están presentes."""
    return all([tags["title"], tags["artist"], tags["album"], tags["has_cover"]])


def guess_from_filename(filepath):
    """
    Intenta extraer artista y título del nombre de fichero.
    Patrones soportados:
      Artist - Title.mp3
      Artist_Title.mp3
      01 Artist - Title.mp3
    """
    name = Path(filepath).stem
    # Elimina número de pista al inicio
    name = re.sub(r"^\d+[\s._-]+", "", name)

    # Patrón: Artista - Título
    m = re.match(r"^(.+?)\s*[-–—]\s*(.+)$", name)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return "", name.strip()


# ─────────────────────────────────────────────────────────────────────────────
# MusicBrainz
# ─────────────────────────────────────────────────────────────────────────────

def mb_get(endpoint, params):
    params["fmt"] = "json"
    url = f"{MB_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=MB_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {}


def search_recording(artist, title):
    """Busca una grabación en MusicBrainz. Retorna el mejor resultado."""
    query_parts = []
    if title:
        query_parts.append(f'recording:"{title}"')
    if artist:
        query_parts.append(f'artist:"{artist}"')
    query = " AND ".join(query_parts)

    data = mb_get("recording", {"query": query, "limit": 5})
    recordings = data.get("recordings", [])
    if not recordings:
        return None

    # Filtra resultados con score alto
    best = max(recordings, key=lambda r: int(r.get("score", 0)), default=None)
    if not best or int(best.get("score", 0)) < 70:
        return None
    return best


def extract_metadata(recording):
    """Extrae campos útiles de un resultado de MusicBrainz."""
    meta = {
        "title":      recording.get("title", ""),
        "artist":     "",
        "album":      "",
        "year":       "",
        "genre":      "",
        "track":      "",
        "release_id": "",
    }

    # Artista
    credits = recording.get("artist-credit", [])
    artists = [c["artist"]["name"] for c in credits if isinstance(c, dict) and "artist" in c]
    meta["artist"] = ", ".join(artists)

    # Álbum, año, track — del primer release
    releases = recording.get("releases", [])
    if releases:
        rel = releases[0]
        meta["album"]      = rel.get("title", "")
        meta["release_id"] = rel.get("id", "")
        date = rel.get("date", "")
        meta["year"] = date[:4] if date else ""
        # Track number
        medias = rel.get("media", [])
        if medias:
            tracks = medias[0].get("tracks", [])
            if tracks:
                meta["track"] = str(tracks[0].get("number", ""))

    # Género (tags de MusicBrainz)
    mb_tags = recording.get("tags", [])
    if mb_tags:
        top_tag = max(mb_tags, key=lambda t: t.get("count", 0), default=None)
        if top_tag:
            meta["genre"] = top_tag.get("name", "").title()

    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Portada
# ─────────────────────────────────────────────────────────────────────────────

def fetch_cover_caa(release_id):
    """Descarga portada de Cover Art Archive usando el release ID de MB."""
    if not release_id:
        return None
    url = f"{CAA_BASE}/release/{release_id}/front-250"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": MB_HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        if data and len(data) > 1000:
            return data
    except Exception:
        pass
    return None


def fetch_cover_lastfm(artist, album):
    """Descarga portada usando Last.fm como fallback."""
    if not artist or not album:
        return None
    params = {
        "method":  "album.getinfo",
        "api_key": LASTFM_API_KEY,
        "artist":  artist,
        "album":   album,
        "format":  "json",
    }
    url = LASTFM_API + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fix-metadata/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        images = data.get("album", {}).get("image", [])
        # Busca el tamaño "extralarge" o "large"
        img_url = ""
        for img in reversed(images):
            if img.get("#text"):
                img_url = img["#text"]
                break
        if not img_url or "2a96cbd8b46e442fc41c2b86b821562f" in img_url:
            return None
        req2 = urllib.request.Request(img_url, headers={"User-Agent": "fix-metadata/1.0"})
        with urllib.request.urlopen(req2, timeout=10) as r2:
            img_data = r2.read()
        return img_data if len(img_data) > 1000 else None
    except Exception:
        return None


def fetch_cover_lastfm_track(artist, title):
    """Portada via Last.fm track info (último fallback)."""
    if not artist or not title:
        return None
    params = {
        "method":  "track.getinfo",
        "api_key": LASTFM_API_KEY,
        "artist":  artist,
        "track":   title,
        "format":  "json",
    }
    url = LASTFM_API + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fix-metadata/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        album = data.get("track", {}).get("album", {})
        images = album.get("image", [])
        img_url = ""
        for img in reversed(images):
            if img.get("#text"):
                img_url = img["#text"]
                break
        if not img_url or "2a96cbd8b46e442fc41c2b86b821562f" in img_url:
            return None
        req2 = urllib.request.Request(img_url, headers={"User-Agent": "fix-metadata/1.0"})
        with urllib.request.urlopen(req2, timeout=10) as r2:
            img_data = r2.read()
        return img_data if len(img_data) > 1000 else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Escritura de tags
# ─────────────────────────────────────────────────────────────────────────────

def write_tags(filepath, current_tags, new_meta, cover_bytes, dry_run=False):
    """
    Escribe los tags al fichero MP3.
    Solo sobreescribe campos que estaban vacíos (respeta los que ya existen).
    """
    changes = []

    try:
        try:
            audio = ID3(filepath)
        except ID3NoHeaderError:
            audio = ID3()

        def set_if_empty(current_val, new_val, tag_class, tag_key, label):
            if not current_val and new_val:
                audio[tag_key] = tag_class(encoding=3, text=new_val)
                changes.append(f"{label}: {new_val[:50]}")

        set_if_empty(current_tags["title"],  new_meta.get("title"),  TIT2, "TIT2", "Título")
        set_if_empty(current_tags["artist"], new_meta.get("artist"), TPE1, "TPE1", "Artista")
        set_if_empty(current_tags["album"],  new_meta.get("album"),  TALB, "TALB", "Álbum")
        set_if_empty(current_tags["year"],   new_meta.get("year"),   TDRC, "TDRC", "Año")
        set_if_empty(current_tags["genre"],  new_meta.get("genre"),  TCON, "TCON", "Género")
        set_if_empty(current_tags["track"],  new_meta.get("track"),  TRCK, "TRCK", "Pista")

        if not current_tags["has_cover"] and cover_bytes:
            mime = "image/jpeg"
            if cover_bytes[:4] == b'\x89PNG':
                mime = "image/png"
            audio["APIC:"] = APIC(
                encoding=3,
                mime=mime,
                type=3,
                desc="Cover",
                data=cover_bytes,
            )
            changes.append(f"Portada: {len(cover_bytes)//1024} KB")

        if changes and not dry_run:
            audio.save(filepath, v2_version=3)

    except Exception as e:
        return [], str(e)

    return changes, None


# ─────────────────────────────────────────────────────────────────────────────
# Proceso principal por fichero
# ─────────────────────────────────────────────────────────────────────────────

def process_file(filepath, dry_run=False, force=False):
    """Procesa un fichero MP3. Retorna dict con el resultado."""
    result = {
        "file":    str(filepath),
        "status":  "",
        "changes": [],
        "error":   None,
    }

    # 1. Leer tags actuales
    current = read_tags(filepath)

    if tags_complete(current) and not force:
        result["status"] = "ok"
        return result

    # 2. Determinar artista/título para buscar
    search_artist = current["artist"]
    search_title  = current["title"]

    if not search_artist or not search_title:
        guessed_artist, guessed_title = guess_from_filename(filepath)
        if not search_artist:
            search_artist = guessed_artist
        if not search_title:
            search_title = guessed_title

    if not search_title:
        result["status"] = "skip_no_info"
        result["error"]  = "No se pudo determinar el título"
        return result

    # 3. Buscar en MusicBrainz
    recording = search_recording(search_artist, search_title)
    time.sleep(MB_DELAY)

    new_meta   = {}
    cover_bytes = None

    if recording:
        new_meta = extract_metadata(recording)
        release_id = new_meta.get("release_id", "")

        # 4. Buscar portada
        if not current["has_cover"]:
            cover_bytes = fetch_cover_caa(release_id)
            if not cover_bytes:
                cover_bytes = fetch_cover_lastfm(
                    new_meta.get("artist") or search_artist,
                    new_meta.get("album", ""),
                )
            if not cover_bytes:
                cover_bytes = fetch_cover_lastfm_track(
                    new_meta.get("artist") or search_artist,
                    new_meta.get("title") or search_title,
                )
    else:
        # Sin resultado MB → solo intenta portada via Last.fm
        if not current["has_cover"]:
            cover_bytes = fetch_cover_lastfm_track(search_artist, search_title)

    # 5. Escribir tags
    changes, error = write_tags(filepath, current, new_meta, cover_bytes, dry_run=dry_run)

    if error:
        result["status"] = "error"
        result["error"]  = error
    elif changes:
        result["status"]  = "updated"
        result["changes"] = changes
    else:
        result["status"] = "no_changes"

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def find_mp3s(root):
    return sorted(Path(root).rglob("*.mp3"))


def run():
    parser = argparse.ArgumentParser(description="Fix MP3 metadata + portadas")
    parser.add_argument("folder", help="Carpeta con los MP3s")
    parser.add_argument("--dry-run", action="store_true", help="Solo analiza, no modifica ficheros")
    parser.add_argument("--force",   action="store_true", help="Actualiza aunque ya tenga tags")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        sys.exit(f"[!] Carpeta no encontrada: {folder}")

    mp3s = find_mp3s(folder)
    if not mp3s:
        sys.exit(f"[!] No se encontraron ficheros MP3 en: {folder}")

    mode = ""
    if args.dry_run:
        mode = " [DRY RUN — sin cambios]"
    elif args.force:
        mode = " [FORCE — sobreescribe todo]"

    print(f"\n🎵  Fix Metadata{mode}")
    print(f"    Carpeta : {folder}")
    print(f"    MP3s    : {len(mp3s)}")
    print("=" * 60)

    results    = []
    ok         = 0
    updated    = 0
    no_changes = 0
    errors     = 0
    skipped    = 0

    for i, mp3 in enumerate(mp3s, 1):
        name = mp3.name[:55]
        print(f"\n[{i}/{len(mp3s)}] {name}")

        # Leer tags antes para mostrar estado
        tags = read_tags(mp3)
        flags = []
        if not tags["title"]:  flags.append("sin título")
        if not tags["artist"]: flags.append("sin artista")
        if not tags["album"]:  flags.append("sin álbum")
        if not tags["year"]:   flags.append("sin año")
        if not tags["has_cover"]: flags.append("sin portada")

        if not flags and not args.force:
            print(f"  ✓ Completo — omitido")
            ok += 1
            results.append({"file": mp3.name, "status": "ok", "changes": []})
            continue

        if flags:
            print(f"  ⚠ Faltan: {', '.join(flags)}")

        r = process_file(mp3, dry_run=args.dry_run, force=args.force)
        results.append(r)

        if r["status"] == "updated":
            tag_str = " | ".join(r["changes"])
            label   = "[SIMULADO] " if args.dry_run else ""
            print(f"  ✅ {label}Actualizado → {tag_str}")
            updated += 1
        elif r["status"] == "no_changes":
            print(f"  — Sin cambios nuevos")
            no_changes += 1
        elif r["status"] == "error":
            print(f"  ✗ Error: {r['error']}")
            errors += 1
        elif r["status"] == "skip_no_info":
            print(f"  ? Omitido: {r['error']}")
            skipped += 1

    # ── Reporte final ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Resultado{mode}")
    print(f"  ✓ Ya completos  : {ok}")
    print(f"  ✅ Actualizados  : {updated}")
    print(f"  — Sin cambios   : {no_changes}")
    print(f"  ? Sin info      : {skipped}")
    print(f"  ✗ Errores       : {errors}")
    print(f"  Total           : {len(mp3s)}")

    # Guarda reporte JSON
    report_path = folder / "_metadata_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "date":    datetime.now().isoformat(),
            "folder":  str(folder),
            "summary": {"ok": ok, "updated": updated, "no_changes": no_changes,
                        "skipped": skipped, "errors": errors},
            "files":   results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 Reporte: {report_path}\n")


if __name__ == "__main__":
    run()
