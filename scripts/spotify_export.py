#!/usr/bin/env python3
"""
spotify_export.py — Lee el export de Spotify y busca torrents en TPB.

Cómo obtener tus datos:
  1. spotify.com/account/privacy → "Descarga tus datos"
  2. Pide "Historial de reproducción extendido"
  3. En ~5 días recibes un ZIP — extráelo en la carpeta 'spotify_data/'
  4. Ejecuta: python3 spotify_export.py

No necesita cuenta Premium ni credenciales de API.
"""

import json
import time
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from collections import defaultdict
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

DATA_DIR = Path(__file__).parent.parent / "spotify_data"

TPB_API = "https://apibay.org/q.php"
TPB_WEB = "https://thepiratebay.org/search.php"

# Mínimo de segundos reproducidos para contar una escucha (30 seg)
MIN_MS_PLAYED = 30_000

# Cuántos artistas top buscar en TPB (los más escuchados)
TOP_ARTISTS = 50


# ─────────────────────────────────────────────────────────────────────────────
# Leer historial
# ─────────────────────────────────────────────────────────────────────────────

def load_history(data_dir: Path):
    """Lee todos los Streaming_History_Audio_*.json del directorio (busca recursivamente)."""
    files = sorted(data_dir.rglob("Streaming_History_Audio_*.json"))
    if not files:
        files = sorted(data_dir.rglob("StreamingHistory*.json"))
    if not files:
        sys.exit(
            f"\n[!] No se encontraron archivos de historial en: {data_dir}\n"
            "    Extrae el ZIP de Spotify dentro de la carpeta 'spotify_data/'\n"
            "    Los archivos deben llamarse Streaming_History_Audio_*.json\n"
        )

    records = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        records.extend(data)
        print(f"  ✓ {f.name} — {len(data):,} registros")

    return records


def aggregate(records):
    """
    Agrupa por artista y canción.
    Retorna:
      artists: {artist: {"plays": int, "ms": int, "tracks": {track: plays}}}
      tracks:  [(artist, track, plays, ms_played)]
    """
    artists = defaultdict(lambda: {"plays": 0, "ms": 0, "tracks": defaultdict(int)})
    tracks  = defaultdict(lambda: {"plays": 0, "ms": 0})

    for r in records:
        ms = r.get("ms_played", 0)
        if ms < MIN_MS_PLAYED:
            continue

        # Formato extendido
        artist = r.get("master_metadata_album_artist_name") or r.get("artistName", "")
        track  = r.get("master_metadata_track_name")        or r.get("trackName",  "")

        if not artist or not track:
            continue

        artists[artist]["plays"] += 1
        artists[artist]["ms"]    += ms
        artists[artist]["tracks"][track] += 1

        key = (artist, track)
        tracks[key]["plays"] += 1
        tracks[key]["ms"]    += ms

    return artists, tracks


def top_tracks_list(tracks, n=200):
    """Retorna las N canciones más escuchadas."""
    return sorted(
        [{"artist": k[0], "track": k[1], **v} for k, v in tracks.items()],
        key=lambda x: x["plays"],
        reverse=True,
    )[:n]


# ─────────────────────────────────────────────────────────────────────────────
# The Pirate Bay
# ─────────────────────────────────────────────────────────────────────────────

def tpb_search(query, category=100, max_results=5):
    """
    Busca en apibay.org (API JSON de TPB).
    category=100 Music all, 101 MP3, 104 Lossless
    """
    params = {"q": query, "cat": category}
    url = f"{TPB_API}?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        if data and data[0].get("id") == "0":
            return []
        return data[:max_results]
    except Exception as e:
        print(f"    [!] Error buscando '{query}': {e}")
        return []


def knaben_search(query, max_results=5):
    """Busca en la API v1 de Knaben (POST, api.knaben.org). Pide por relevancia
    con filtro de categoría audio (1000000) y ordena por seeders en cliente —
    el host .eu y el parámetro order_by ignoran el query."""
    try:
        body = json.dumps({
            "query": query,
            "categories": [1000000],   # 1000000 = Audio
            "hide_unsafe": True,
            "size": max(max_results, 20),
        }).encode()
        req = urllib.request.Request(
            "https://api.knaben.org/v1",
            data=body,
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        out = []
        for h in (data.get("hits") or []):
            ih   = (h.get("hash") or "").lower()
            name = h.get("title") or ""
            if not ih or not name:
                continue
            out.append({
                "info_hash": ih, "name": name,
                "seeders": int(h.get("seeders") or 0),
                "size": int(h.get("bytes") or 0),
            })
        out.sort(key=lambda x: x["seeders"], reverse=True)
        return out[:max_results]
    except Exception as e:
        print(f"    [!] Knaben error '{query}': {e}")
        return []


SHAZAM_CACHE_FILE = OUTPUT_DIR / "shazam_cache.json"


def shazam_lookup(artist, track):
    """Devuelve {album, genre, year, ...} desde Shazam (catálogo Apple Music,
    sin API key), o {} si falla. Cacheado a disco (compartido con la app)."""
    cache = {}
    if SHAZAM_CACHE_FILE.exists():
        try:
            cache = json.loads(SHAZAM_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    key = f"{artist} — {track}"
    if key in cache:
        return cache[key]
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
                "album":  a.get("albumName", ""),
                "genre":  (a.get("genreNames") or [""])[0],
                "year":   (a.get("releaseDate") or "")[:4],
                "artist": a.get("artistName", ""),
                "track":  a.get("name", ""),
            }
    except Exception:
        out = {}
    cache[key] = out
    try:
        SHAZAM_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    except Exception:
        pass
    return out


def expand_artist_queries(artist, album=""):
    """Variantes de búsqueda: primero el álbum real (Shazam) y luego la
    discografía del artista (mejor cobertura)."""
    import unicodedata

    def no_acc(s):
        return "".join(c for c in unicodedata.normalize("NFKD", s)
                       if unicodedata.category(c) != "Mn")

    base = no_acc(artist) if no_acc(artist).lower() != artist.lower() else artist
    variants = []
    if album:
        variants += [f"{artist} {album}", f"{no_acc(artist)} {no_acc(album)}"]
    variants += [
        f"{artist} discografia",
        f"{base} discography",
        f"{base} album",
        base,
    ]
    return list(dict.fromkeys(v.strip() for v in variants if v.strip()))


def search_artist_multi(artist, max_results=3, album=""):
    """Busca el artista en Knaben + TPB probando el álbum real (Shazam) y
    variantes de discografía. Devuelve {info_hash, name, seeders, size} con seeders>0."""
    for q in expand_artist_queries(artist, album):
        combined = knaben_search(q, max_results=10)
        for t in tpb_search(q, category=100, max_results=10):
            combined.append({
                "info_hash": t.get("info_hash", ""),
                "name": t.get("name", ""),
                "seeders": int(t.get("seeders") or 0),
                "size": int(t.get("size") or 0),
            })
        with_seeds = [r for r in combined if r["seeders"] > 0 and r["info_hash"]]
        if with_seeds:
            with_seeds.sort(key=lambda x: x["seeders"], reverse=True)
            return with_seeds[:max_results]
    return []


def magnet_link(torrent):
    ih   = torrent.get("info_hash", "")
    name = urllib.parse.quote(torrent.get("name", ""))
    trackers = (
        "tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
        "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
    )
    return f"magnet:?xt=urn:btih:{ih}&dn={name}&{trackers}"


def tpb_web_url(query):
    return f"{TPB_WEB}?q={urllib.parse.quote(query)}&cat=0"


def size_human(size_bytes):
    try:
        b = int(size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.0f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except Exception:
        return "?"


def ms_to_hours(ms):
    h = ms / 3_600_000
    return f"{h:.1f}h"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run():
    print("\n🎵  Spotify Export → Torrent\n" + "=" * 40)

    if not DATA_DIR.exists():
        DATA_DIR.mkdir()
        sys.exit(
            f"\n[!] Carpeta creada: {DATA_DIR}\n"
            "    Extrae el ZIP de Spotify ahí y vuelve a ejecutar el script.\n"
        )

    print(f"\n[1/4] Leyendo historial desde: {DATA_DIR}")
    records = load_history(DATA_DIR)
    print(f"      Total registros: {len(records):,}")

    print("\n[2/4] Procesando...")
    artists, tracks = aggregate(records)
    top_artists = sorted(artists.items(), key=lambda x: x[1]["plays"], reverse=True)
    top_tracks  = top_tracks_list(tracks, n=200)

    period_start = None
    period_end   = None
    for r in records:
        ts = r.get("ts", "")
        if ts:
            if period_start is None or ts < period_start:
                period_start = ts
            if period_end is None or ts > period_end:
                period_end = ts

    print(f"      Período: {period_start[:10] if period_start else '?'} → {period_end[:10] if period_end else '?'}")
    print(f"      Artistas únicos: {len(artists):,}")
    print(f"      Canciones únicas: {len(tracks):,}")

    # Guarda listas completas
    with open(OUTPUT_DIR / "top_artistas.json", "w", encoding="utf-8") as f:
        json.dump(
            [{"artist": a, **v, "tracks": dict(v["tracks"])} for a, v in top_artists],
            f, ensure_ascii=False, indent=2
        )
    with open(OUTPUT_DIR / "top_canciones.json", "w", encoding="utf-8") as f:
        json.dump(top_tracks, f, ensure_ascii=False, indent=2)

    # ── Reporte de top canciones ───────────────────────────────────────────
    print("\n[3/4] Top 50 canciones más escuchadas:")
    print(f"  {'#':<4} {'Reproducciones':<16} {'Artista — Canción'}")
    print("  " + "─" * 60)
    for i, t in enumerate(top_tracks[:50], 1):
        label = f"{t['artist']} — {t['track']}"
        if len(label) > 52:
            label = label[:49] + "..."
        print(f"  {i:<4} {t['plays']:<16} {label}")

    # ── Buscar en TPB ──────────────────────────────────────────────────────
    print(f"\n[4/4] Buscando top {TOP_ARTISTS} artistas en The Pirate Bay...")

    report_lines = [
        f"# Spotify Export — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Período: {period_start[:10] if period_start else '?'} → {period_end[:10] if period_end else '?'}",
        f"# Artistas únicos: {len(artists):,} | Canciones únicas: {len(tracks):,}",
        "",
        "=" * 60,
        "TOP 50 CANCIONES MÁS ESCUCHADAS",
        "=" * 60,
    ]
    for i, t in enumerate(top_tracks[:50], 1):
        report_lines.append(f"{i:>3}. [{t['plays']} plays] {t['artist']} — {t['track']}")

    report_lines += ["", "=" * 60, "BÚSQUEDA EN THE PIRATE BAY (por artista)", "=" * 60]

    magnet_lines = []

    for i, (artist, info) in enumerate(top_artists[:TOP_ARTISTS], 1):
        top5 = sorted(info["tracks"].items(), key=lambda x: x[1], reverse=True)[:5]
        top5_str = ", ".join(f"{t} ({p})" for t, p in top5)

        header = (
            f"\n[{i}/{TOP_ARTISTS}] {artist}"
            f"  |  {info['plays']} reproducciones  |  {ms_to_hours(info['ms'])}"
        )
        print(header)
        print(f"    Top canciones: {top5_str}")
        report_lines.append(header)
        report_lines.append(f"    Top canciones: {top5_str}")
        report_lines.append(f"    Buscar en web: {tpb_web_url(artist + ' discography')}")

        # Álbum real vía Shazam, usando la canción más escuchada del artista
        album = ""
        if top5:
            meta = shazam_lookup(artist, top5[0][0])
            album = meta.get("album", "")
            if album:
                year = meta.get("year", "")
                album_str = f"    💿 Álbum (Shazam): {album}" + (f" ({year})" if year else "")
                print(album_str)
                report_lines.append(album_str)

        results = search_artist_multi(artist, max_results=3, album=album)

        if results:
            for r in results:
                size  = size_human(r.get("size", 0))
                seeds = r.get("seeders", "?")
                name  = r.get("name", "")
                mag   = magnet_link(r)
                line  = f"    ✓ [{seeds} seeds | {size}] {name}"
                print(line)
                report_lines.append(line)
                report_lines.append(f"      {mag}")
                magnet_lines.append(f"# {artist} — {name}")
                magnet_lines.append(mag)
        else:
            line = f"    ✗ Sin resultados — busca manualmente: {tpb_web_url(artist)}"
            print(line)
            report_lines.append(line)

        time.sleep(1.5)

    # ── Guardar archivos ───────────────────────────────────────────────────
    report_path  = OUTPUT_DIR / "reporte.txt"
    magnets_path = OUTPUT_DIR / "magnets.txt"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    with open(magnets_path, "w", encoding="utf-8") as f:
        f.write("\n".join(magnet_lines))

    print(f"\n{'='*40}")
    print(f"¡Listo! Archivos en: {OUTPUT_DIR.resolve()}")
    print(f"  📄 reporte.txt        — resumen completo con links")
    print(f"  🧲 magnets.txt        — magnet links para qBittorrent")
    print(f"  📁 top_artistas.json  — todos tus artistas ordenados por plays")
    print(f"  📁 top_canciones.json — top 200 canciones\n")


if __name__ == "__main__":
    run()
