#!/usr/bin/env python3
"""
lastfm_export.py — Top canciones/artistas de Last.fm → busca torrents en TPB.

Obtiene:
  - Top artistas globales de todos los tiempos
  - Top tracks globales de todos los tiempos
  - Top tracks por género (rock, pop, electronic, hip-hop, jazz, metal, etc.)

API key gratuita e instantánea en: https://www.last.fm/api/account/create

Uso:
  python3 lastfm_export.py
"""

import json
import re
import time
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Credencial Last.fm ─────────────────────────────────────────────────────────
# Regístrate gratis en: https://www.last.fm/api/account/create
# Solo necesitas el API Key (no el secret para lectura)
LASTFM_API_KEY = "7049ab07a1bbfce19db16bea7b004b29"

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

TPB_API = "https://apibay.org/q.php"
TPB_WEB = "https://thepiratebay.org/search.php"

# Géneros a consultar
GENRES = ['rock', 'pop', 'electronic', 'hip-hop', 'jazz', 'metal', 'classical', 'reggae', 'latin', 'blues', 'soul', 'punk', 'indie', 'alternative', 'r&b']

# Cuántas canciones top buscar en TPB
TOP_TRACKS_TPB = 200


# ─────────────────────────────────────────────────────────────────────────────
# Last.fm helpers
# ─────────────────────────────────────────────────────────────────────────────

def lastfm_get(method, extra_params=None, page=1, limit=50):
    params = {
        "method":  method,
        "api_key": LASTFM_API_KEY,
        "format":  "json",
        "limit":   limit,
        "page":    page,
    }
    if extra_params:
        params.update(extra_params)
    url = LASTFM_API + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "spotify-export-script/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"    [!] Error Last.fm ({method}): {e}")
        return {}


def fetch_top_artists(pages=2):
    """Top artistas globales de todos los tiempos."""
    artists = []
    for page in range(1, pages + 1):
        data = lastfm_get("chart.gettopartists", page=page, limit=50)
        items = data.get("artists", {}).get("artist", [])
        for a in items:
            artists.append({
                "name":       a.get("name", ""),
                "listeners":  int(a.get("listeners", 0)),
                "playcount":  int(a.get("playcount", 0)),
                "source":     "global_chart",
            })
    return artists


def fetch_top_tracks(pages=2):
    """Top tracks globales de todos los tiempos."""
    tracks = []
    for page in range(1, pages + 1):
        data = lastfm_get("chart.gettoptracks", page=page, limit=50)
        items = data.get("tracks", {}).get("track", [])
        for t in items:
            tracks.append({
                "track":     t.get("name", ""),
                "artist":    t.get("artist", {}).get("name", ""),
                "album":     t.get("album", {}).get("title", "") if isinstance(t.get("album"), dict) else "",
                "listeners": int(t.get("listeners", 0)),
                "playcount": int(t.get("playcount", 0)),
                "source":    "global_chart",
            })
    return tracks


def fetch_track_info(artist, track):
    """Obtiene info de una canción (incluye álbum) desde Last.fm."""
    data = lastfm_get("track.getinfo", extra_params={"artist": artist, "track": track})
    t = data.get("track", {})
    album = t.get("album", {})
    return album.get("title", "") if isinstance(album, dict) else ""


def fetch_genre_top_tracks(genre, limit=30):
    """Top tracks de un género específico."""
    data = lastfm_get("tag.gettoptracks", extra_params={"tag": genre}, limit=limit)
    tracks = []
    for t in data.get("tracks", {}).get("track", []):
        tracks.append({
            "track":  t.get("name", ""),
            "artist": t.get("artist", {}).get("name", ""),
            "album":  "",
            "genre":  genre,
            "source": f"genre:{genre}",
        })
    return tracks


def fetch_genre_top_artists(genre, limit=20):
    """Top artistas de un género."""
    data = lastfm_get("tag.gettopartists", extra_params={"tag": genre}, limit=limit)
    artists = []
    for a in data.get("topartists", {}).get("artist", []):
        artists.append({
            "name":   a.get("name", ""),
            "genre":  genre,
            "source": f"genre:{genre}",
        })
    return artists


# ─────────────────────────────────────────────────────────────────────────────
# The Pirate Bay helpers
# ─────────────────────────────────────────────────────────────────────────────

def tpb_search(query, category=100, max_results=3):
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
        print(f"    [!] Error TPB '{query}': {e}")
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


TORRENT_SOURCES = [
    "https://itorrents.org/torrent/{ih}.torrent",
    "https://torcache.net/torrent/{ih}.torrent",
]

def download_torrent(info_hash, dest_path):
    """Descarga el fichero .torrent usando el info_hash. Retorna True si tuvo éxito."""
    ih = info_hash.upper()
    for tpl in TORRENT_SOURCES:
        url = tpl.format(ih=ih)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            # Un .torrent válido empieza con 'd' (bencoding dict)
            if data and data[0:1] == b'd':
                with open(dest_path, "wb") as f:
                    f.write(data)
                return True
        except Exception:
            continue
    return False


def safe_filename(name, max_len=80):
    """Convierte un string en nombre de fichero seguro."""
    keep = set(" ._-()[]")
    out = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)
    return out[:max_len].strip()


# ─────────────────────────────────────────────────────────────────────────────
# HTML para uTorrent
# ─────────────────────────────────────────────────────────────────────────────

def _build_html(rows, not_found):
    rows_html = ""
    prev_song = None
    for r in rows:
        # Agrupa resultados de la misma canción bajo un solo encabezado
        if r["song"] != prev_song:
            fb = f' <span class="fb">via {r["fallback"]}</span>' if r["fallback"] else ""
            rows_html += f'<tr class="song-header"><td colspan="4"><strong>{r["song"]}</strong>{fb}</td></tr>\n'
            prev_song = r["song"]
        rows_html += (
            f'<tr>'
            f'<td><a class="btn" href="{r["magnet"]}">▶ Abrir en uTorrent</a></td>'
            f'<td>{r["torrent"]}</td>'
            f'<td class="center">{r["seeds"]}</td>'
            f'<td class="center">{r["size"]}</td>'
            f'</tr>\n'
        )

    nf_html = ""
    if not_found:
        nf_html = "<h2>Sin resultados en TPB</h2><ul>" + "".join(f"<li>{s}</li>" for s in not_found) + "</ul>"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>uTorrent — Música Last.fm</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }}
  h1   {{ color: #e94560; }}
  h2   {{ color: #aaa; font-size: 1rem; margin-top: 2rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  tr.song-header td {{ background: #16213e; color: #e94560; padding: 10px 8px 4px; font-size: .95rem; border-top: 2px solid #0f3460; }}
  tr:not(.song-header):hover td {{ background: #0f3460; }}
  td   {{ padding: 5px 8px; border-bottom: 1px solid #222; vertical-align: middle; }}
  td.center {{ text-align: center; white-space: nowrap; }}
  a.btn {{
    display: inline-block; padding: 4px 12px; border-radius: 4px;
    background: #e94560; color: #fff; text-decoration: none; font-size: .8rem; white-space: nowrap;
  }}
  a.btn:hover {{ background: #c73652; }}
  .fb  {{ font-size: .75rem; color: #888; margin-left: 8px; }}
  ul   {{ color: #aaa; }}
</style>
</head>
<body>
<h1>🎵 Música — Top Last.fm → uTorrent</h1>
<p style="color:#888">{len(rows)} torrents encontrados &nbsp;|&nbsp; Haz clic en <strong>▶ Abrir en uTorrent</strong> para descargar</p>
<table>
<thead><tr style="color:#888;font-size:.8rem">
  <th></th><th style="text-align:left">Torrent</th><th>Seeds</th><th>Tamaño</th>
</tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
{nf_html}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run():
    print("\n🎵  Last.fm Charts → Torrent\n" + "=" * 40)

    if LASTFM_API_KEY == "TU_API_KEY_AQUI":
        print("\n[!] Configura LASTFM_API_KEY en el script.")
        print("    Regístrate gratis en: https://www.last.fm/api/account/create\n")
        sys.exit(1)

    # ── 1. Descargar charts ────────────────────────────────────────────────
    print("\n[1/4] Descargando charts de Last.fm...")

    print("  → Top artistas globales...")
    top_artists = fetch_top_artists(pages=2)          # 100 artistas
    print(f"     {len(top_artists)} artistas")

    print("  → Top tracks globales...")
    top_tracks = fetch_top_tracks(pages=4)            # 200 tracks
    print(f"     {len(top_tracks)} tracks")

    print("  → Top por género...")
    genre_tracks  = []
    genre_artists = []
    for genre in GENRES:
        print(f"     {genre}...", end=" ", flush=True)
        gt = fetch_genre_top_tracks(genre, limit=20)
        ga = fetch_genre_top_artists(genre, limit=10)
        genre_tracks.extend(gt)
        genre_artists.extend(ga)
        print(f"{len(gt)} tracks, {len(ga)} artistas")
        time.sleep(0.3)

    # ── 2. Consolidar tracks (deduplicar) ─────────────────────────────────
    print("\n[2/4] Consolidando tracks...")
    track_data = {}  # key: (artist_lower, track_lower)

    for t in top_tracks:
        key = (t["artist"].lower(), t["track"].lower())
        if key not in track_data:
            track_data[key] = {
                "artist":    t["artist"],
                "track":     t["track"],
                "album":     t.get("album", ""),
                "listeners": t.get("listeners", 0),
                "playcount": t.get("playcount", 0),
                "genres":    set(),
                "source":    "global_chart",
            }

    for t in genre_tracks:
        key = (t["artist"].lower(), t["track"].lower())
        if key not in track_data:
            track_data[key] = {
                "artist":    t["artist"],
                "track":     t["track"],
                "album":     t.get("album", ""),
                "listeners": 0,
                "playcount": 0,
                "genres":    set(),
                "source":    f"genre:{t['genre']}",
            }
        track_data[key]["genres"].add(t["genre"])

    # Ordena: primero los del chart global por oyentes, luego los de género
    sorted_tracks = sorted(
        track_data.values(),
        key=lambda x: (
            1 if x["source"] == "global_chart" else 0,
            x["listeners"],
        ),
        reverse=True,
    )
    print(f"      {len(sorted_tracks)} tracks únicos")

    # ── 3. Mostrar top tracks ──────────────────────────────────────────────
    print(f"\n[3/4] Top 50 tracks:")
    print(f"  {'#':<4} {'Oyentes':<12} {'Artista — Canción'}")
    print("  " + "─" * 60)
    for i, t in enumerate(sorted_tracks[:50], 1):
        label = f"{t['artist']} — {t['track']}"
        if len(label) > 52:
            label = label[:49] + "..."
        listeners = f"{t['listeners']:,}" if t.get("listeners") else "-"
        print(f"  {i:<4} {listeners:<12} {label}")

    # Guarda JSONs
    with open(OUTPUT_DIR / "lastfm_top_tracks.json", "w", encoding="utf-8") as f:
        json.dump(
            [{**t, "genres": list(t["genres"])} for t in sorted_tracks],
            f, ensure_ascii=False, indent=2,
        )
    with open(OUTPUT_DIR / "lastfm_genre_tracks.json", "w", encoding="utf-8") as f:
        json.dump(genre_tracks, f, ensure_ascii=False, indent=2)

    # ── 4. Buscar en TPB ───────────────────────────────────────────────────
    print(f"\n[4/4] Buscando top {TOP_TRACKS_TPB} canciones en The Pirate Bay (MP3)...")

    torrents_dir = OUTPUT_DIR / "torrents"
    torrents_dir.mkdir(exist_ok=True)

    # Carga lo que ya existe de búsquedas anteriores
    prev_magnets_path = OUTPUT_DIR / "magnets_lastfm.txt"
    prev_found: dict[str, list] = {}   # "artist — track" → [magnet_line, ...]
    prev_html:  list[dict]      = []

    if prev_magnets_path.exists():
        lines_prev = prev_magnets_path.read_text(encoding="utf-8").splitlines()
        current_label = None
        for ln in lines_prev:
            if ln.startswith("# "):
                current_label = ln[2:].strip()
                # Normaliza: quita el sufijo "[via ...]" si lo hay
                base = current_label.split(" [via ")[0].strip()
                prev_found.setdefault(base, [])
            elif ln.startswith("magnet:") and current_label:
                base = current_label.split(" [via ")[0].strip()
                prev_found[base].append(ln.strip())
        n_prev = len(prev_found)
        if n_prev:
            print(f"      ↺ {n_prev} canciones ya encontradas en búsquedas anteriores (se reutilizan)")

    # Llave de canción normalizada (igual que se guarda en magnets)
    def song_key(artist, track):
        return f"{artist} — {track}"

    report_lines = [
        f"# Last.fm Charts → Torrent MP3 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Tracks únicos: {len(sorted_tracks)} | Globales: {len(top_tracks)} | Por género: {len(genre_tracks)}",
        "",
        "=" * 60,
        "TOP 50 TRACKS (Last.fm)",
        "=" * 60,
    ]
    for i, t in enumerate(sorted_tracks[:50], 1):
        report_lines.append(f"{i:>3}. {t['artist']} — {t['track']}")

    report_lines += ["", "=" * 60, f"BÚSQUEDA EN THE PIRATE BAY — MP3 (top {TOP_TRACKS_TPB})", "=" * 60]

    magnet_lines  = []
    not_found     = []
    html_rows     = []
    search_log    = []   # registro completo para mostrar en la app con estado nuevo/caché

    for i, t in enumerate(sorted_tracks[:TOP_TRACKS_TPB], 1):
        artist = t["artist"]
        track  = t["track"]
        listeners = f"{t['listeners']:,}" if t["listeners"] else "?"
        query  = f"{artist} {track} mp3"
        key    = song_key(artist, track)

        header = f"\n[{i}/{TOP_TRACKS_TPB}] {artist} — {track}  |  {listeners} oyentes"

        # ── ¿Ya existe de una búsqueda anterior? ──────────────────────────
        if key in prev_found and prev_found[key]:
            print(f"{header}")
            print(f"    — Ya existe ({len(prev_found[key])} magnet{'s' if len(prev_found[key])>1 else ''}, se reutiliza)")
            report_lines.append(header)
            report_lines.append(f"    — Reutilizado de búsqueda anterior")
            first_mag = prev_found[key][0]
            ih_match  = re.search(r"urn:btih:([A-Fa-f0-9]{40})", first_mag, re.I)
            ih        = ih_match.group(1) if ih_match else ""
            for mag in prev_found[key]:
                magnet_lines.append(f"# {key}")
                magnet_lines.append(mag)
                html_rows.append({
                    "song":      key,
                    "torrent":   "(reutilizado)",
                    "seeds":     "—",
                    "size":      "—",
                    "magnet":    mag,
                    "fallback":  "caché",
                    "info_hash": ih,
                    "status":    "cached",
                })
            search_log.append({
                "song":      key,
                "artist":    artist,
                "track":     track,
                "listeners": t.get("listeners", 0),
                "status":    "cached",
                "torrent":   "(reutilizado de búsqueda anterior)",
                "seeds":     "—",
                "size":      "—",
                "fallback":  "",
                "magnet":    first_mag,
                "info_hash": ih,
            })
            continue   # ← no llama a TPB ni espera

        # ── Búsqueda nueva en TPB ─────────────────────────────────────────
        print(header)
        report_lines.append(header)
        report_lines.append(f"    Web: {tpb_web_url(query)}")

        album = t.get("album", "")

        results       = tpb_search(query, category=101, max_results=2)
        fallback_used = None

        if not results:
            results = tpb_search(query, category=0, max_results=2)
            if results:
                fallback_used = "canción (todas categorías)"

        if not results:
            if not album:
                album = fetch_track_info(artist, track)
                t["album"] = album
                time.sleep(0.5)
            if album:
                album_query = f"{artist} {album} mp3"
                results = tpb_search(album_query, category=101, max_results=2)
                if not results:
                    results = tpb_search(album_query, category=0, max_results=2)
                if results:
                    fallback_used = f"álbum: {album}"

        if not results:
            artist_query = f"{artist} mp3"
            results = tpb_search(artist_query, category=101, max_results=2)
            if results:
                fallback_used = f"artista: {artist}"

        if results:
            fb = f" [via {fallback_used}]" if fallback_used else ""
            first = True
            for r in results:
                size  = size_human(r.get("size", 0))
                seeds = r.get("seeders", "?")
                name  = r.get("name", "")
                ih    = r.get("info_hash", "")
                mag   = magnet_link(r)
                line  = f"    ✓{fb} [{seeds} seeds | {size}] {name}"
                print(line)
                report_lines.append(line)
                report_lines.append(f"      {mag}")
                magnet_lines.append(f"# {artist} — {track}{fb}")
                magnet_lines.append(mag)
                html_rows.append({
                    "song":      key,
                    "torrent":   name,
                    "seeds":     seeds,
                    "size":      size,
                    "magnet":    mag,
                    "fallback":  fallback_used or "",
                    "info_hash": ih,
                    "status":    "new",
                })
                if first:
                    search_log.append({
                        "song":      key,
                        "artist":    artist,
                        "track":     track,
                        "listeners": t.get("listeners", 0),
                        "status":    "new",
                        "torrent":   name,
                        "seeds":     seeds,
                        "size":      size,
                        "fallback":  fallback_used or "",
                        "magnet":    mag,
                        "info_hash": ih,
                    })
                    first = False
        else:
            line = f"    ✗ Sin resultados — {tpb_web_url(query)}"
            print(line)
            report_lines.append(line)
            not_found.append(key)
            search_log.append({
                "song":      key,
                "artist":    artist,
                "track":     track,
                "listeners": t.get("listeners", 0),
                "status":    "not_found",
                "torrent":   "",
                "seeds":     "—",
                "size":      "—",
                "fallback":  "",
                "magnet":    "",
                "info_hash": "",
            })

        time.sleep(1.5)

    # ── Descargar ficheros .torrent ────────────────────────────────────────
    print(f"\n[5/5] Descargando ficheros .torrent para uTorrent Web...")
    ok_count  = 0
    skip_count = 0
    fail_list = []

    seen_songs  = set()
    seen_hashes = set()
    for row in html_rows:
        ih   = row["info_hash"]
        song = row["song"]
        if song in seen_songs or (ih and ih in seen_hashes):
            continue
        seen_songs.add(song)
        if ih:
            seen_hashes.add(ih)

        fname = safe_filename(f"{song} — {row['torrent']}") + ".torrent"
        dest  = torrents_dir / fname

        # Comprueba si el .torrent ya existe (descarga previa)
        if dest.exists():
            print(f"  — {song[:50]}... ya existe")
            skip_count += 1
            continue

        # Si no tenemos info_hash real (reutilizado sin hash), busca por nombre
        if not ih:
            print(f"  — {song[:50]}... sin hash, omitido")
            skip_count += 1
            continue

        print(f"  ↓ {song[:50]}...", end=" ", flush=True)
        if download_torrent(ih, dest):
            print("✓")
            ok_count += 1
        else:
            print("✗")
            fail_list.append(song)
        time.sleep(0.8)

    # ── Guardar resto de ficheros ──────────────────────────────────────────
    with open(OUTPUT_DIR / "reporte_lastfm.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    with open(OUTPUT_DIR / "magnets_lastfm.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(magnet_lines))

    # Registro de resultados para la app (nuevo / caché / no encontrado)
    n_new    = sum(1 for r in search_log if r["status"] == "new")
    n_cached = sum(1 for r in search_log if r["status"] == "cached")
    n_nf     = sum(1 for r in search_log if r["status"] == "not_found")
    with open(OUTPUT_DIR / "lastfm_search_log.json", "w", encoding="utf-8") as f:
        json.dump({
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total":     len(search_log),
            "new":       n_new,
            "cached":    n_cached,
            "not_found": n_nf,
            "results":   search_log,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*40}")
    print(f"¡Listo! Archivos en: {OUTPUT_DIR.resolve()}")
    print(f"  📂 torrents/                — {ok_count} nuevos + {skip_count} ya existían")
    print(f"     → En uTorrent Web: botón '+' → 'Añadir fichero' → selecciona todos los .torrent")
    print(f"  📄 reporte_lastfm.txt       — resumen completo")
    print(f"  🧲 magnets_lastfm.txt       — magnets en texto plano (alternativa)")
    if n_prev if 'n_prev' in dir() else 0:
        print(f"  ↺ Reutilizadas de caché   — {len(prev_found)} canciones (sin volver a buscar en TPB)")
    if fail_list:
        print(f"\n  ✗ .torrent no descargado ({len(fail_list)}): usar magnet como alternativa")
        for song in fail_list:
            print(f"     - {song}")
    if not_found:
        print(f"\n  ✗ Sin resultados en TPB ({len(not_found)}):")
        for nf in not_found:
            print(f"     - {nf}")
    print()


if __name__ == "__main__":
    run()
