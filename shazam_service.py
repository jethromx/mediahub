"""
shazam_service.py — Metadatos de Shazam (catálogo Apple Music, sin API key).

Da álbum/género/año/preview/portada que el historial de Spotify no incluye.
Módulo puro (sin Streamlit): usado por app.py y reutilizable desde scripts.
"""

import json
import threading
import urllib.request as _ureq_mod
import urllib.parse as _uparse_mod
from pathlib import Path

SHAZAM_CACHE_FILE = Path(__file__).parent / "output" / "shazam_cache.json"
_shazam_lock = threading.Lock()   # protege el caché en búsquedas concurrentes


def _shazam_cache_load() -> dict:
    if SHAZAM_CACHE_FILE.exists():
        try:
            return json.loads(SHAZAM_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _shazam_cache_save(data: dict):
    SHAZAM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHAZAM_CACHE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _shazam_lookup(artist: str, track: str) -> dict:
    """Devuelve {album, genre, year, artist, track, preview, artwork} desde
    Shazam (catálogo Apple Music), o {} si falla. Cacheado a disco.
    `preview` es un MP3/M4A de 30s reproducible; `artwork` una miniatura."""
    key = f"{artist} — {track}"
    with _shazam_lock:
        cached = _shazam_cache_load().get(key)
    # Reutiliza la caché salvo entradas antiguas sin el campo `preview` (migración)
    if cached is not None and (cached == {} or "preview" in cached):
        return cached
    out = {}
    try:
        url = "https://www.shazam.com/services/amapi/v1/catalog/US/search?" + \
            _uparse_mod.urlencode({"term": f"{artist} {track}", "limit": 3, "types": "songs"})
        req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                              "Accept": "application/json"})
        with _ureq_mod.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        songs = (data.get("results", {}).get("songs", {}).get("data", []))
        if songs:
            a = songs[0].get("attributes", {})
            # URL cruda con plantilla {w}x{h}; el consumidor elige el tamaño
            artwork = (a.get("artwork") or {}).get("url", "")
            out = {
                "album":   a.get("albumName", ""),
                "genre":   (a.get("genreNames") or [""])[0],
                "year":    (a.get("releaseDate") or "")[:4],
                "artist":  a.get("artistName", ""),
                "track":   a.get("name", ""),
                "preview": (a.get("previews") or [{}])[0].get("url", ""),
                "artwork": artwork,
            }
    except Exception:
        out = {}
    with _shazam_lock:
        cache = _shazam_cache_load()
        cache[key] = out
        _shazam_cache_save(cache)
    return out
