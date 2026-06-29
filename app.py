#!/usr/bin/env python3
"""
MediaHub — App local para descargar música, ebooks y arreglar metadatos.
Ejecutar: streamlit run app.py
"""

import streamlit as st
import subprocess
import sys
import json
import os
import time
import threading
import functools
import concurrent.futures as _cf
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
PYTHON      = sys.executable

# Las API keys viven en config.json (gitignored) o en variables de entorno —
# nunca hardcodeadas aquí: este archivo se commitea.
DEFAULT_CONFIG = {
    "lastfm_api_key":    os.environ.get("LASTFM_API_KEY", ""),
    "spotify_client_id": os.environ.get("SPOTIFY_CLIENT_ID", ""),
    "spotify_secret":    os.environ.get("SPOTIFY_SECRET", ""),
    "tmdb_api_key":      os.environ.get("TMDB_API_KEY", ""),
    "opensubtitles_api_key": os.environ.get("OPENSUBTITLES_API_KEY", ""),
    "music_folder":      str(Path.home() / "Downloads" / "Musica"),
    "ebooks_folder":     str(Path.home() / "Downloads" / "Ebooks"),
    "movies_folder":     str(Path.home() / "Downloads" / "Peliculas"),
    "phone_folder":      str(Path.home() / "Downloads" / "Musica_Movil"),
    "phone_use_limit":   False,
    "phone_limit_gb":    32,
    "top_tracks":        100,
    "top_books":         120,
    "min_seeds":         3,
    "qbit_url":          "",          # ej. http://localhost:8080
    "qbit_user":         "admin",
    "qbit_pass":         "",
    "use_qbit":          False,       # enviar magnets a qBittorrent en vez de `open`
    "genres": [
        "rock", "pop", "electronic", "hip-hop", "jazz",
        "metal", "classical", "reggae", "latin", "blues",
        "soul", "punk", "indie", "alternative", "r&b",
    ],
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Historial de descargas  (feature #6)
# ─────────────────────────────────────────────────────────────────────────────

HISTORY_FILE = BASE_DIR / "download_history.json"

def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _record_download(kind: str, count: int, detail: str = ""):
    """Append one event to the download history."""
    history = _load_history()
    history.append({
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "kind": kind,
        "count": count,
        "detail": detail,
    })
    HISTORY_FILE.write_text(json.dumps(history[-500:], ensure_ascii=False, indent=2),
                            encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist de películas  (feature #2)
# ─────────────────────────────────────────────────────────────────────────────

WATCHLIST_FILE = BASE_DIR / "watchlist.json"

def _load_watchlist() -> list:
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_watchlist(data: list):
    WATCHLIST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Cache de resultados de búsqueda por canción de Spotify
# ─────────────────────────────────────────────────────────────────────────────

SPOTIFY_RESULTS_FILE = BASE_DIR / "output" / "spotify_torrents_results.json"


def _spotify_load_results() -> dict:
    if SPOTIFY_RESULTS_FILE.exists():
        try:
            return json.loads(SPOTIFY_RESULTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _spotify_save_results(data: dict):
    SPOTIFY_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPOTIFY_RESULTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Metadatos de Shazam (catálogo Apple Music, sin API key) — da álbum/género/año
# que el historial de Spotify no incluye, para buscar el torrent del álbum real.
# ─────────────────────────────────────────────────────────────────────────────

SHAZAM_CACHE_FILE = BASE_DIR / "output" / "shazam_cache.json"
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


# ─────────────────────────────────────────────────────────────────────────────
# Biblioteca local de música — para marcar qué canciones ya están descargadas
# ─────────────────────────────────────────────────────────────────────────────

def _norm_music(s: str) -> str:
    import unicodedata as _ud, re as _re
    s = _ud.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if _ud.category(c) != "Mn")
    s = _re.sub(r"\(feat[^)]*\)|\[feat[^\]]*\]", " ", s)   # quita (feat. ...)
    s = _re.sub(r"[^a-z0-9 ]", " ", s)
    return _re.sub(r"\s+", " ", s).strip()


@st.cache_data(show_spinner=False)
def _scan_music_library(folder: str) -> set:
    """Escanea la carpeta de música y devuelve un set de claves
    'artista|||titulo' normalizadas (tags ID3 vía mutagen + nombre de archivo).
    Cacheado; usa _scan_music_library.clear() para re-escanear."""
    import re as _re
    keys: set = set()
    base = Path(folder) if folder else None
    if not base or not base.exists():
        return keys
    try:
        from mutagen import File as _MFile
        has_mutagen = True
    except Exception:
        has_mutagen = False
    exts = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac", ".wma", ".alac"}
    for p in base.rglob("*"):
        if p.suffix.lower() not in exts:
            continue
        artist = title = ""
        if has_mutagen:
            try:
                mf = _MFile(str(p), easy=True)
                if mf is not None and mf.tags:
                    artist = (mf.tags.get("artist") or [""])[0]
                    title  = (mf.tags.get("title") or [""])[0]
            except Exception:
                pass
        if artist and title:
            keys.add(f"{_norm_music(artist)}|||{_norm_music(title)}")
        # Fallback: "Artista - Titulo" deducido del nombre de archivo
        m = _re.match(r"^(.+?)\s*[-–—]\s*(.+)$", p.stem)
        if m:
            keys.add(f"{_norm_music(m.group(1))}|||{_norm_music(m.group(2))}")
    return keys


def _is_downloaded(lib_keys: set, artist: str, track: str,
                   ledger: dict = None) -> bool:
    """True si la canción está en la biblioteca local o marcada `completed`
    en el ledger de descargas."""
    key = f"{_norm_music(artist)}|||{_norm_music(track)}"
    if lib_keys and key in lib_keys:
        return True
    if ledger and ledger.get(f"{artist} — {track}", {}).get("status") == "completed":
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Ledger de descargas — registra qué se pidió/descargó para futuras consultas
# ─────────────────────────────────────────────────────────────────────────────

LEDGER_FILE = BASE_DIR / "output" / "downloads_ledger.json"


def _ledger_load() -> dict:
    if LEDGER_FILE.exists():
        try:
            return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _ledger_save(data: dict):
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")


def _ledger_record_request(artist: str, track: str, result: dict) -> None:
    """Registra (o actualiza) una descarga pedida al pulsar 🧲 Abrir."""
    ledger = _ledger_load()
    key = f"{artist} — {track}"
    prev = ledger.get(key, {})
    ledger[key] = {
        "artist": artist, "track": track,
        "info_hash": result.get("info_hash", ""),
        "magnet": _build_magnet(result.get("info_hash", ""), result.get("name", "")),
        "torrent_name": result.get("name", ""),
        "source": result.get("source", ""),
        "seeds": result.get("seeds", 0),
        "size": result.get("size", ""),
        "requested_at": time.strftime("%Y-%m-%d %H:%M"),
        "status": prev.get("status", "requested"),
        "completed_at": prev.get("completed_at"),
        "file_path": prev.get("file_path"),
        "tagged": prev.get("tagged", False),
    }
    _ledger_save(ledger)


def _ledger_status(ledger: dict, artist: str, track: str) -> str:
    """'completed' | 'requested' | '' para una canción."""
    return ledger.get(f"{artist} — {track}", {}).get("status", "") if ledger else ""


# ─────────────────────────────────────────────────────────────────────────────
# Cliente qBittorrent (WebUI API v2) — opcional (F3)
# ─────────────────────────────────────────────────────────────────────────────

def _qbit_opener(cfg: dict):
    """Devuelve un opener urllib autenticado contra qBittorrent, o None si no
    hay URL configurada o el login falla."""
    url = (cfg.get("qbit_url", "") or "").rstrip("/")
    if not url:
        return None
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = _ureq_mod.build_opener(_ureq_mod.HTTPCookieProcessor(cj))
    data = _uparse_mod.urlencode({
        "username": cfg.get("qbit_user", ""), "password": cfg.get("qbit_pass", ""),
    }).encode()
    try:
        req = _ureq_mod.Request(f"{url}/api/v2/auth/login", data=data,
                                headers={"Referer": url, "User-Agent": "mediahub"})
        body = opener.open(req, timeout=8).read().decode().strip()
        return opener if body == "Ok." else None
    except Exception:
        return None


def _qbit_add_magnet(cfg: dict, magnet: str, savepath: str = "") -> bool:
    opener = _qbit_opener(cfg)
    if not opener:
        return False
    url = cfg["qbit_url"].rstrip("/")
    fields = {"urls": magnet}
    if savepath:
        fields["savepath"] = savepath
    try:
        req = _ureq_mod.Request(f"{url}/api/v2/torrents/add",
                                data=_uparse_mod.urlencode(fields).encode(),
                                headers={"Referer": url})
        opener.open(req, timeout=10).read()
        return True
    except Exception:
        return False


def _qbit_list(cfg: dict):
    """Lista de torrents (dicts de la API) o None si no conecta."""
    opener = _qbit_opener(cfg)
    if not opener:
        return None
    url = cfg["qbit_url"].rstrip("/")
    try:
        req = _ureq_mod.Request(f"{url}/api/v2/torrents/info",
                                headers={"Referer": url})
        return json.loads(opener.open(req, timeout=8).read())
    except Exception:
        return None


def _open_magnet(mag: str, savepath: str = "") -> None:
    """Envía el magnet a qBittorrent (si está configurado/activado) o lo abre en
    el cliente del SO."""
    cfg = load_config()
    sent = False
    if cfg.get("use_qbit") and cfg.get("qbit_url"):
        sent = _qbit_add_magnet(cfg, mag, savepath)
    if not sent:
        subprocess.Popen(["open", mag])   # fallback al handler del SO


def _open_and_log(mag: str, name: str, kind: str = "Torrent") -> None:
    """Abre un magnet genérico (búsqueda directa/rápida) y lo deja en el
    historial de descargas (B2)."""
    _open_magnet(mag)
    _record_download(kind, 1, (name or "")[:80])


def _download_and_record(artist: str, track: str, result: dict) -> None:
    """Envía el magnet a qBittorrent (si está configurado y activado) o lo abre
    en el cliente del SO; en ambos casos registra la petición en el ledger."""
    mag = _build_magnet(result.get("info_hash", ""), result.get("name", ""))
    _open_magnet(mag, load_config().get("music_folder", ""))
    _ledger_record_request(artist, track, result)


def _song_query_variants(artist: str, track: str, album: str = "") -> list:
    """Variantes de búsqueda para una canción: primero la canción exacta,
    luego el álbum real (vía Shazam) y por último la discografía del artista
    (mejor cobertura, ya que la música casi siempre se publica como álbum)."""
    import unicodedata as _ud

    def _no_acc(s: str) -> str:
        return "".join(c for c in _ud.normalize("NFKD", s) if _ud.category(c) != "Mn")

    artist_n, track_n = _no_acc(artist), _no_acc(track)
    variants = [
        f"{artist} {track}",        # canción exacta
        f"{artist_n} {track_n}",    # canción exacta sin acentos
    ]
    if album:
        variants += [
            f"{artist} {album}",            # álbum real (Shazam)
            f"{_no_acc(artist)} {_no_acc(album)}",
        ]
    variants += [
        f"{artist} discografia",    # nivel álbum / discografía
        f"{artist_n} discography",
        f"{artist_n} album",
        artist_n,                   # artista solo (último recurso)
    ]
    return list(dict.fromkeys(v.strip() for v in variants if v.strip()))


def _all_sources_search(q: str, n: int = 10) -> list:
    """Busca en todas las fuentes (Knaben, SolidTorrents, BitSearch, TPB)
    y devuelve la lista combinada de resultados normalizados."""
    results = []
    results += _knaben_search_music(q, n)
    results += _solid_search_music(q, n)
    results += _bitsearch_search_music(q, n)
    # TPB cat 100 = Música (todo) → cubre MP3 y lossless/FLAC
    for r in _tpb_search_cached(q, 100, n):
        results.append({
            "name": r.get("name", ""),
            "seeders": int(r.get("seeders", 0)),
            "leechers": int(r.get("leechers", 0)),
            "size": int(r.get("size", 0)),
            "info_hash": r.get("info_hash", ""),
            "source": "TPB",
        })
    return results


def _search_song_torrent(artist: str, track: str, use_shazam: bool = True,
                         min_seeds: int = 3) -> dict:
    """Busca el mejor torrent para una canción en múltiples fuentes
    (Knaben, SolidTorrents, BitSearch, The Pirate Bay), probando primero la
    canción exacta, luego el álbum real (vía Shazam) y la discografía.
    Elige el torrent más sano (ver _best_torrent). Devuelve dict found/not_found."""
    meta  = _shazam_lookup(artist, track) if use_shazam else {}
    album = meta.get("album", "")
    extra = {"album": album, "genre": meta.get("genre", ""), "year": meta.get("year", "")}
    # Guardamos el mejor "con pocos seeds" por si ninguna variante da uno sano
    fallback = None
    for q in _song_query_variants(artist, track, album):
        best = _best_torrent(_all_sources_search(q, 10), single_track=True,
                             min_seeds=min_seeds)
        if best and not best.get("low_seeds"):
            return _song_result_found(best, q, extra)
        if best and fallback is None:
            fallback = (best, q)
    if fallback:
        return _song_result_found(fallback[0], fallback[1], extra)
    return {"status": "not_found", "searched_at": time.strftime("%Y-%m-%d %H:%M"), **extra}


def _song_result_found(best: dict, q: str, extra: dict) -> dict:
    return {
        "status": "found",
        "name": best["name"],
        "seeds": int(best.get("seeders", 0)),
        "size": _size_human(best.get("size", 0)),
        "info_hash": best.get("info_hash", ""),
        "source": best.get("source", ""),
        "low_seeds": bool(best.get("low_seeds", False)),
        "query": q,
        "searched_at": time.strftime("%Y-%m-%d %H:%M"),
        **extra,
    }


def _parallel_searches(items: list, min_seeds: int = 3, max_workers: int = 6):
    """Lanza _search_song_torrent en paralelo (pool acotado) para una lista de
    items con 'artist'/'track' y va devolviendo (item, result) conforme terminan.
    La red corre en hilos; el consumidor (hilo principal) hace los st.* y
    escrituras de archivos. La concurrencia acotada hace de límite de cortesía."""
    with _cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {
            ex.submit(_search_song_torrent, it["artist"], it["track"], True, min_seeds): it
            for it in items
        }
        for fut in _cf.as_completed(fut_map):
            it = fut_map[fut]
            try:
                res = fut.result()
            except Exception:
                res = {"status": "not_found", "searched_at": time.strftime("%Y-%m-%d %H:%M")}
            yield it, res


# ─────────────────────────────────────────────────────────────────────────────
# Búsqueda TPB cacheada a nivel módulo  (feature #11)
# ─────────────────────────────────────────────────────────────────────────────

import urllib.request as _ureq_mod, urllib.parse as _uparse_mod

@functools.lru_cache(maxsize=512)
def _tpb_search_cached(q: str, cat: int, n: int) -> tuple:
    """TPB search, cacheado por args (lru_cache). Thread-safe — usable desde
    hilos del pool de descargas (no usa st.cache_data, que requiere contexto)."""
    url = "https://apibay.org/q.php?" + _uparse_mod.urlencode({"q": q, "cat": cat})
    try:
        req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq_mod.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        if data and data[0].get("id") == "0":
            return ()
        return tuple(data[:n])
    except Exception:
        return ()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers compartidos de música  (tab Canciones de Spotify + búsqueda directa)
# ─────────────────────────────────────────────────────────────────────────────

def _size_human(b) -> str:
    try:
        b = int(b)
        for u in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.0f} {u}"
            b /= 1024
        return f"{b:.1f} TB"
    except Exception:
        return "?"


def _build_magnet(info_hash: str, name: str) -> str:
    tr = ("tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
          "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
          "&tr=udp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce")
    return f"magnet:?xt=urn:btih:{info_hash}&dn={_uparse_mod.quote(name)}&{tr}"


def _magnet_button(label: str, mag_url: str, key: str = "", full_width: bool = True) -> None:
    """Renders a magnet link as a plain <a> tag so the browser triggers the OS handler directly,
    avoiding the target=_blank behavior of st.link_button that blocks protocol handlers."""
    width = "width:100%;display:inline-flex;justify-content:center;" if full_width else ""
    st.markdown(
        f'<a href="{mag_url}" '
        f'style="{width}padding:6px 14px;background:#7c3aed;color:#fff;'
        f'border-radius:6px;text-decoration:none;font-size:0.84rem;font-weight:500;'
        f'align-items:center;gap:4px;">{label}</a>',
        unsafe_allow_html=True,
    )


def _song_preview_ui(artist: str, track: str, ui_key: str) -> None:
    """Botón '▶️ Muestra' que, al pulsarlo, reproduce 30s de la canción y
    muestra la carátula (vía Shazam/Apple Music). El estado persiste por fila."""
    open_set = st.session_state.setdefault("_previews_open", set())
    if st.button("▶️ Muestra", key=f"prev_btn_{ui_key}", use_container_width=True):
        if ui_key in open_set:
            open_set.discard(ui_key)   # toggle: vuelve a pulsar para ocultar
        else:
            open_set.add(ui_key)
    if ui_key in open_set:
        with st.spinner("Cargando muestra…"):
            meta = _shazam_lookup(artist, track)
        pv = meta.get("preview", "")
        if pv:
            art = meta.get("artwork", "")
            if art:
                st.image(art.replace("{w}", "300").replace("{h}", "300"), width=80)
            st.audio(pv)
        else:
            st.caption("🔇 Sin muestra disponible")


def _knaben_search_music(q: str, n: int = 12) -> list:
    # API v1 POST en api.knaben.org. Nota: el host .eu y el parámetro order_by
    # ignoran el query (devuelven top-seeders global), así que pedimos por
    # relevancia con filtro de categoría audio (1000000) y ordenamos por
    # seeders del lado del cliente.
    try:
        body = json.dumps({
            "query": q,
            "categories": [1000000],   # 1000000 = Audio
            "hide_unsafe": True,
            "size": max(n, 20),
        }).encode()
        req = _ureq_mod.Request(
            "https://api.knaben.org/v1",
            data=body,
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
        )
        with _ureq_mod.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        hits = data.get("hits") or []
        out = []
        for h in hits:
            ih    = (h.get("hash") or h.get("info_hash") or "").lower()
            name  = h.get("title") or h.get("name") or ""
            seeds = int(h.get("seeders") or 0)
            peers = int(h.get("peers") or h.get("leechers") or 0)
            size_b = int(h.get("bytes") or 0)
            if not ih or not name:
                continue
            out.append({"name": name, "seeders": seeds, "leechers": peers,
                        "size": size_b, "info_hash": ih, "source": "Knaben"})
        out.sort(key=lambda r: r["seeders"], reverse=True)
        return out[:n]
    except Exception:
        return []


def _solid_search_music(q: str, n: int = 12) -> list:
    try:
        url = "https://solidtorrents.to/api/v1/search?" + _uparse_mod.urlencode({
            "q": q, "sort": "seeders", "category": "music", "size": n,
        })
        req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq_mod.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        hits = (data.get("hits") or {}).get("hits") or data.get("results") or []
        out  = []
        for h in hits:
            src    = h.get("_source") or h
            ih     = (src.get("infohash") or src.get("info_hash") or "").lower()
            name   = src.get("title") or src.get("name") or ""
            swarm  = src.get("swarm") or {}
            seeds  = int(swarm.get("seeders") or src.get("seeders") or 0)
            peers  = int(swarm.get("leechers") or src.get("leechers") or 0)
            size_b = int(src.get("size") or 0)
            if not ih or not name:
                continue
            out.append({"name": name, "seeders": seeds, "leechers": peers,
                        "size": size_b, "info_hash": ih, "source": "Solid"})
        return out[:n]
    except Exception:
        return []


def _bitsearch_search_music(q: str, n: int = 20) -> list:
    try:
        url = "https://bitsearch.to/api/v1/search?" + _uparse_mod.urlencode({
            "q": q, "category": "music", "subcat": "", "page": 1,
        })
        req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with _ureq_mod.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        hits = data.get("results") or data.get("hits") or []
        out  = []
        for h in hits:
            ih     = (h.get("infoHash") or h.get("info_hash") or h.get("infohash") or "").lower()
            name   = h.get("name") or h.get("title") or ""
            stats  = h.get("stats") or {}
            seeds  = int(stats.get("seeders") or h.get("seeders") or 0)
            peers  = int(stats.get("leechers") or h.get("leechers") or 0)
            size_b = int(h.get("size") or 0)
            if not ih or not name:
                continue
            out.append({"name": name, "seeders": seeds, "leechers": peers,
                        "size": size_b, "info_hash": ih, "source": "BitSearch"})
        return out[:n]
    except Exception:
        return []


def _torrent_health_score(r: dict, single_track: bool) -> float:
    """Score de salud: prioriza seeds, penaliza torrents enormes cuando se busca
    una canción (una discografía de decenas de GB con pocos seeds no completa),
    y usa la calidad (FLAC/320/MP3) solo como pequeño desempate."""
    seeds = int(r.get("seeders", 0))
    name  = (r.get("name", "") or "").upper()
    quality_bonus = 1.3 if any(k in name for k in ("FLAC", "320", "MP3")) else 1.0
    size_gb = int(r.get("size", 0)) / 1e9
    size_penalty = 1.0
    if single_track and size_gb > 1.5:
        size_penalty = 1 + (size_gb - 1.5) * 0.15
    return seeds * quality_bonus / size_penalty


def _best_torrent(results: list, single_track: bool = True, min_seeds: int = 3):
    """Elige el torrent más sano. Descarta los que tengan menos de `min_seeds`;
    si ninguno llega al mínimo, devuelve el mejor disponible marcado con
    `low_seeds=True` para que la UI avise. Devuelve None si no hay nada con seeds."""
    with_seeds = [r for r in results if int(r.get("seeders", 0)) > 0]
    if not with_seeds:
        return None
    healthy = [r for r in with_seeds if int(r.get("seeders", 0)) >= min_seeds]
    pool, low = (healthy, False) if healthy else (with_seeds, True)
    best = max(pool, key=lambda r: _torrent_health_score(r, single_track))
    best = dict(best)
    best["low_seeds"] = low
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Top de canciones en tendencia — chart público de Apple Music (sin API key)
# ─────────────────────────────────────────────────────────────────────────────

# País → etiqueta para el chart
APPLE_CHART_COUNTRIES = {
    "mx": "🇲🇽 México", "us": "🇺🇸 EE.UU.", "es": "🇪🇸 España",
    "ar": "🇦🇷 Argentina", "co": "🇨🇴 Colombia", "cl": "🇨🇱 Chile",
    "gb": "🇬🇧 Reino Unido", "global": "🌎 Global (US)",
}

# Género → id de Apple Music (0 = todos)
APPLE_CHART_GENRES = {
    "Todos": 0, "Pop": 14, "Hip-Hop/Rap": 18, "Latino": 12,
    "Rock": 21, "Dance": 17, "Electrónica": 7, "Alternativa": 20,
    "R&B/Soul": 15, "Country": 6, "Reggae": 19, "Jazz": 11, "Clásica": 5,
}


@st.cache_data(ttl=3600, show_spinner=False)
def _apple_top_songs(country: str, genre_id: int, limit: int = 50) -> list:
    """Top de canciones del chart de Apple Music vía RSS público (sin API key).
    Devuelve [{artist, track, genre}] deduplicado. Cacheado 1 hora."""
    cc = "us" if country == "global" else country
    genre_path = f"genre={genre_id}/" if genre_id else ""
    url = f"https://itunes.apple.com/{cc}/rss/topsongs/limit={limit}/{genre_path}json"
    try:
        req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq_mod.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        entries = data.get("feed", {}).get("entry", [])
        out, seen = [], set()
        for e in entries:
            artist = (e.get("im:artist", {}) or {}).get("label", "")
            track  = (e.get("im:name", {}) or {}).get("label", "")
            genre  = (e.get("category", {}) or {}).get("attributes", {}).get("label", "")
            if not artist or not track:
                continue
            key = f"{artist}|||{track}".lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"artist": artist, "track": track, "genre": genre})
        return out
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# YouTube → MP3 (vía yt-dlp + ffmpeg)
# ─────────────────────────────────────────────────────────────────────────────

def _youtube_deps_ok() -> bool:
    from shutil import which
    return which("yt-dlp") is not None and which("ffmpeg") is not None


@st.cache_data(ttl=600, show_spinner=False)
def _youtube_search(query: str, n: int = 8) -> list:
    """Busca en YouTube vía yt-dlp. Devuelve [{id, title, uploader, duration}]."""
    script = BASE_DIR / "scripts" / "youtube_dl.py"
    try:
        out = subprocess.run(
            [PYTHON, str(script), "search", query, str(n)],
            capture_output=True, text=True, timeout=40,
        ).stdout
    except Exception:
        return []
    results = []
    for line in out.splitlines():
        try:
            results.append(json.loads(line))
        except Exception:
            continue
    return results


def _fmt_duration(seconds) -> str:
    try:
        s = int(seconds)
        return f"{s // 60}:{s % 60:02d}"
    except Exception:
        return "?"


def _youtube_top_id(artist: str, track: str) -> str:
    """Devuelve el id del primer resultado de YouTube para la canción, o ''."""
    hits = _youtube_search(f"{artist} {track}", 1)
    return hits[0].get("id", "") if hits else ""


def _youtube_download_cmd(vid: str, dest: str, artist: str, track: str) -> list:
    """Comando para descargar un id de YouTube como MP3 (para stream_script)."""
    return [PYTHON, "-u", str(BASE_DIR / "scripts" / "youtube_dl.py"),
            "download", vid, "--dest", dest, "--artist", artist, "--track", track]


def _youtube_download_song(artist: str, track: str, dest: str) -> bool:
    """Busca la canción en YouTube (top 1) y la descarga como MP3 en `dest`,
    con metadata + portada (vía youtube_dl/tag_music). True si tuvo éxito."""
    vid = _youtube_top_id(artist, track)
    if not vid:
        return False
    try:
        r = subprocess.run(_youtube_download_cmd(vid, dest, artist, track),
                           capture_output=True, text=True, timeout=300)
        return r.returncode == 0
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Salud de fuentes (F1) — pingea cada API y reporta estado/latencia
# ─────────────────────────────────────────────────────────────────────────────

def _sources_health() -> dict:
    """Pingea cada fuente (en paralelo) con una consulta mínima y devuelve
    {nombre: {ok, ms, detail}}. Usa pings independientes del caché de la app."""
    cfg = load_config()

    def _ck_knaben():
        r = _knaben_search_music("queen", 3)
        return bool(r), f"{len(r)} resultados"

    def _ck_solid():
        r = _solid_search_music("queen", 3)
        return bool(r), f"{len(r)} resultados"

    def _ck_bits():
        r = _bitsearch_search_music("queen", 3)
        return bool(r), f"{len(r)} resultados"

    def _ck_tpb():
        r = _tpb_search_cached("queen", 100, 3)
        return bool(r), f"{len(r)} resultados"

    def _ck_shazam():
        m = _shazam_lookup("Queen", "Bohemian Rhapsody")
        return bool(m.get("album")), (m.get("album") or "sin match")

    def _ck_apple():
        d = json.loads(_ureq_mod.urlopen(_ureq_mod.Request(
            "https://itunes.apple.com/us/rss/topsongs/limit=3/json",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read())
        n = len(d.get("feed", {}).get("entry", []))
        return n > 0, f"{n} en chart"

    def _ck_youtube():
        from shutil import which
        if not (which("yt-dlp") and which("ffmpeg")):
            return False, "falta yt-dlp/ffmpeg"
        out = subprocess.run(["yt-dlp", "ytsearch1:test", "--flat-playlist",
                              "--dump-json", "--no-warnings"],
                             capture_output=True, text=True, timeout=25).stdout
        return bool(out.strip()), "ok" if out.strip() else "sin respuesta"

    def _ck_tmdb():
        key = cfg.get("tmdb_api_key", "").strip()
        if not key:
            return None, "sin API key"
        _ureq_mod.urlopen(_ureq_mod.Request(
            f"https://api.themoviedb.org/3/configuration?api_key={key}",
            headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read()
        return True, "ok"

    def _ck_lastfm():
        key = cfg.get("lastfm_api_key", "").strip()
        if not key:
            return None, "sin API key"
        u = ("https://ws.audioscrobbler.com/2.0/?method=chart.gettoptracks"
             f"&api_key={key}&format=json&limit=1")
        _ureq_mod.urlopen(_ureq_mod.Request(u, headers={"User-Agent": "Mozilla/5.0"}),
                          timeout=10).read()
        return True, "ok"

    checks = {
        "Knaben": _ck_knaben, "SolidTorrents": _ck_solid, "BitSearch": _ck_bits,
        "The Pirate Bay": _ck_tpb, "Shazam": _ck_shazam, "Apple Music": _ck_apple,
        "YouTube (yt-dlp)": _ck_youtube, "TMDB": _ck_tmdb, "Last.fm": _ck_lastfm,
    }

    def _timed(fn):
        t0 = time.time()
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, str(e)[:80]
        return {"ok": ok, "ms": int((time.time() - t0) * 1000), "detail": detail}

    out = {}
    with _cf.ThreadPoolExecutor(max_workers=len(checks)) as ex:
        futs = {ex.submit(_timed, fn): name for name, fn in checks.items()}
        for f in _cf.as_completed(futs):
            out[futs[f]] = f.result()
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades UI
# ─────────────────────────────────────────────────────────────────────────────

def stream_script(cmd, log_placeholder, status_placeholder, extra_env=None):
    """Ejecuta un comando y muestra su salida en tiempo real.

    extra_env: dict con variables de entorno extra (API keys, parámetros) —
    así los scripts reciben config sin reescribir su código fuente.
    """
    log_lines = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1", **(extra_env or {})},
        )
        for line in iter(proc.stdout.readline, ""):
            log_lines.append(line.rstrip())
            log_placeholder.code("\n".join(log_lines[-60:]), language="")
        proc.wait()
        return proc.returncode == 0
    except Exception as e:
        st.error(f"Error ejecutando script: {e}")
        return False


def output_files_section(folder, extensions=None):
    """Muestra los archivos generados con botón de descarga."""
    folder = Path(folder)
    if not folder.exists():
        return
    files = sorted(folder.iterdir()) if not extensions else [
        f for f in sorted(folder.iterdir()) if f.suffix in extensions
    ]
    if not files:
        return
    st.caption(f"📁 {folder} — {len(files)} archivos")
    cols = st.columns(min(len(files), 4))
    for i, f in enumerate(files[:8]):
        with cols[i % 4]:
            with open(f, "rb") as fh:
                st.download_button(
                    label=f"⬇ {f.name[:30]}",
                    data=fh.read(),
                    file_name=f.name,
                    use_container_width=True,
                    key=f"dl_{f.name}_{i}",
                )


# ─────────────────────────────────────────────────────────────────────────────
# Helper compartido: cabecera de página
# ─────────────────────────────────────────────────────────────────────────────

def _page_header(icon: str, title: str, subtitle: str = ""):
    """Renderiza un header consistente arriba de cada página."""
    sub_html = (f'<div class="mh-page-header-sub">{subtitle}</div>'
                if subtitle else "")
    st.markdown(
        f'<div class="mh-page-header">'
        f'  <div class="mh-page-header-icon">{icon}</div>'
        f'  <div class="mh-page-header-text">'
        f'    <div class="mh-breadcrumb">MediaHub &rsaquo; {title}</div>'
        f'    <div class="mh-page-header-title">{title}</div>'
        f'    {sub_html}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Páginas
# ─────────────────────────────────────────────────────────────────────────────

def page_inicio():
    cfg = load_config()

    # ── Hero ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="mh-hero">
        <div style="font-size:2.6rem;font-weight:900;font-family:'Inter',sans-serif;
             background:linear-gradient(135deg,#b09afd,#60a5fa,#34d399);
             -webkit-background-clip:text;-webkit-text-fill-color:transparent;
             background-clip:text;margin-bottom:12px;line-height:1.1;letter-spacing:-1px;">
            MediaHub
        </div>
        <div style="color:#a8a8cc;font-size:1rem;max-width:580px;line-height:1.8;">
            Tu biblioteca de <strong style="color:#c4b5fd;">música</strong>,
            <strong style="color:#60a5fa;">películas</strong>,
            <strong style="color:#34d399;">ebooks</strong> y
            <strong style="color:#fb923c;">ROMs</strong>,
            completamente local y sin suscripciones.<br>
            Descarga, organiza y limpia — todo desde tu máquina.
        </div>
        <div style="margin-top:18px;display:flex;gap:8px;flex-wrap:wrap;">
            <span class="mh-badge mh-badge-purple">100% Local</span>
            <span class="mh-badge mh-badge-blue">Last.fm + TPB</span>
            <span class="mh-badge mh-badge-green">Películas Latino MX</span>
            <span class="mh-badge mh-badge-yellow">Fix Metadata</span>
            <span class="mh-badge mh-badge-red">Kindle Ready</span>
            <span class="mh-badge mh-badge-orange">🎮 Miyoo A30</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Barra de estadísticas ─────────────────────────────────────────────────
    music_folder = Path(cfg.get("music_folder", ""))
    music_count  = len(list(music_folder.rglob("*.mp3"))) if music_folder.exists() else 0
    music_gb     = sum(f.stat().st_size for f in music_folder.rglob("*.mp3")) / 1e9 \
                   if music_folder.exists() and music_count > 0 else 0

    t_music  = BASE_DIR / "output" / "torrents"
    t_ebooks = BASE_DIR / "output_ebooks" / "torrents"
    n_t_music  = len(list(t_music.glob("*.torrent")))  if t_music.exists()  else 0
    n_t_ebooks = len(list(t_ebooks.glob("*.torrent"))) if t_ebooks.exists() else 0

    mag_movies = Path(cfg.get("movies_folder", "")) / "magnets_movies.txt"
    n_magnets  = sum(1 for l in mag_movies.read_text(encoding="utf-8").splitlines()
                     if l.startswith("magnet:")) if mag_movies.exists() else 0

    st.markdown(
        f'<div class="mh-stats-bar">'
        f'  <div class="mh-stat-item">'
        f'    <div class="mh-stat-item-val">{music_count:,}</div>'
        f'    <div class="mh-stat-item-lbl">🎵 MP3s</div>'
        f'  </div>'
        f'  <div class="mh-stat-divider"></div>'
        f'  <div class="mh-stat-item">'
        f'    <div class="mh-stat-item-val">{music_gb:.1f} GB</div>'
        f'    <div class="mh-stat-item-lbl">💾 Música</div>'
        f'  </div>'
        f'  <div class="mh-stat-divider"></div>'
        f'  <div class="mh-stat-item">'
        f'    <div class="mh-stat-item-val">{n_t_music}</div>'
        f'    <div class="mh-stat-item-lbl">📦 Torrents música</div>'
        f'  </div>'
        f'  <div class="mh-stat-divider"></div>'
        f'  <div class="mh-stat-item">'
        f'    <div class="mh-stat-item-val">{n_magnets}</div>'
        f'    <div class="mh-stat-item-lbl">🎬 Magnets guardados</div>'
        f'  </div>'
        f'  <div class="mh-stat-divider"></div>'
        f'  <div class="mh-stat-item">'
        f'    <div class="mh-stat-item-val">{n_t_ebooks}</div>'
        f'    <div class="mh-stat-item-lbl">📚 Torrents ebooks</div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Sección DESCARGA ──────────────────────────────────────────────────────
    st.markdown('<div class="mh-section-title">Descarga de contenido</div>',
                unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    _DOWNLOAD_CARDS = [
        ("🎵", "Música", "dl",
         "Obtiene el top de canciones de <b>Last.fm</b> por género y busca torrents MP3 en The Pirate Bay.",
         "🎵 Música"),
        ("🎬", "Películas", "dl",
         "Explora por década o búsqueda vía <b>TMDB</b>. Torrents en español <b>latino MX</b>, filtro CAM/TS.",
         "🎬 Películas"),
        ("📚", "Ebooks", "dl",
         "Lista los libros más leídos y descarga archivos <b>.torrent</b> compatibles con Kindle.",
         "📚 Ebooks"),
        ("🟢", "Mi Spotify", "dl",
         "Importa tu historial de Spotify y busca torrents de tus <b>artistas más escuchados</b>.",
         "🟢 Mi Spotify"),
    ]

    for col, (icon, title, tag, desc, page_key) in zip(
            [col1, col2, col3, col4], _DOWNLOAD_CARDS):
        with col:
            st.markdown(
                f'<div class="mh-module-card">'
                f'  <span class="mh-mc-icon">{icon}</span>'
                f'  <span class="mh-mc-tag mh-mc-tag-dl">Descarga</span>'
                f'  <div class="mh-mc-title">{title}</div>'
                f'  <div class="mh-mc-desc">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button(f"Abrir {title}", use_container_width=True,
                         key=f"home_{page_key}", type="primary"):
                st.session_state.page = page_key
                st.rerun()

    # ── ROMs card ─────────────────────────────────────────────────────────────
    col_rom, col_rom_spacer = st.columns([1, 3])
    with col_rom:
        st.markdown(
            '<div class="mh-module-card">'
            '  <span class="mh-mc-icon">🎮</span>'
            '  <span class="mh-mc-tag mh-mc-tag-dl">Descarga</span>'
            '  <div class="mh-mc-title">ROMs</div>'
            '  <div class="mh-mc-desc">Busca ROMs para <b>Miyoo A30</b> y otras consolas — '
            'GBA, SNES, PS1, Genesis y más. No-Intro · Redump · Archive.org</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("Abrir ROMs", use_container_width=True,
                     key="home_🎮 ROMs", type="primary"):
            st.session_state.page = "🎮 ROMs"
            st.rerun()

    # ── Sección BIBLIOTECA ────────────────────────────────────────────────────
    st.markdown('<div class="mh-section-title">Gestión de biblioteca</div>',
                unsafe_allow_html=True)

    col5, col6, col7 = st.columns(3)

    _LIB_CARDS = [
        ("🔧", "Fix Metadata", "lib",
         "Completa los tags ID3 de tus MP3s — artista, álbum, año, género y portada — con MusicBrainz.",
         "🔧 Fix Metadata"),
        ("🧹", "Limpiar duplicados", "lib",
         "Detecta y borra duplicados <b>directamente en tu biblioteca</b>, liberando espacio al instante.",
         "🧹 Limpiar duplicados"),
        ("📊", "Explorador", "lib",
         "Visualiza qué carpetas ocupan más espacio, navega nivel a nivel y detecta el peso de tu colección.",
         "📊 Explorador"),
    ]

    for col, (icon, title, tag, desc, page_key) in zip(
            [col5, col6, col7], _LIB_CARDS):
        with col:
            st.markdown(
                f'<div class="mh-module-card mh-card-highlight">'
                f'  <span class="mh-mc-icon">{icon}</span>'
                f'  <span class="mh-mc-tag mh-mc-tag-lib">Biblioteca</span>'
                f'  <div class="mh-mc-title">{title}</div>'
                f'  <div class="mh-mc-desc">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button(f"Abrir {title}", use_container_width=True,
                         key=f"home_{page_key}"):
                st.session_state.page = page_key
                st.rerun()

    # ── Buscador unificado (feature #7) ──────────────────────────────────────
    st.markdown('<div class="mh-section-title">Búsqueda rápida</div>', unsafe_allow_html=True)
    col_sq, col_scat, col_sbtn = st.columns([4, 2, 1])
    with col_sq:
        quick_q = st.text_input("Buscar en TPB", placeholder="artista, película, libro...",
                                key="home_search_q", label_visibility="collapsed")
    with col_scat:
        quick_cat = st.selectbox("", ["Música (MP3)", "Música (FLAC)", "Películas", "Ebooks"],
                                 key="home_search_cat", label_visibility="collapsed")
    with col_sbtn:
        quick_btn = st.button("Buscar", use_container_width=True, key="home_search_btn",
                              disabled=not quick_q)

    if quick_btn and quick_q:
        cat_map_q = {"Música (MP3)": 101, "Música (FLAC)": 100, "Películas": 200, "Ebooks": 601}
        with st.spinner(f"Buscando «{quick_q}»..."):
            st.session_state["home_q_results"] = list(
                _tpb_search_cached(quick_q, cat_map_q[quick_cat], 6))

    hq_results = st.session_state.get("home_q_results")
    if hq_results is not None:
        if not hq_results:
            st.warning("Sin resultados.")
        else:
            for i, r in enumerate(hq_results[:6]):
                seeds = int(r.get("seeders", 0))
                sc = "🟢" if seeds >= 20 else ("🟡" if seeds >= 5 else "🔴")
                ih = r.get("info_hash", "")
                name = _uparse_mod.quote(r.get("name", ""))
                tr = "tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
                mag = f"magnet:?xt=urn:btih:{ih}&dn={name}&{tr}"
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.caption(f"{sc} {r.get('name','')[:90]}  ·  {seeds} seeds")
                    with c2:
                        if st.button("🧲 Abrir", key=f"hq_dl_{i}",
                                     use_container_width=True):
                            _open_and_log(mag, r.get("name", ""))
                            st.toast("Magnet abierto y registrado en Historial")

    # ── Accesos rápidos ───────────────────────────────────────────────────────
    st.markdown('<div class="mh-section-title">Acceso rápido</div>',
                unsafe_allow_html=True)
    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        if st.button("Configuración", use_container_width=True, key="home_cfg"):
            st.session_state.page = "⚙️ Configuración"
            st.rerun()
    with qa2:
        if st.button("Historial", use_container_width=True, key="home_hist"):
            st.session_state.page = "📋 Historial"
            st.rerun()
    with qa3:
        if st.button("Estadísticas", use_container_width=True, key="home_stats"):
            st.session_state.page = "📈 Estadísticas"
            st.rerun()
    with qa4:
        if st.button("Documentación", use_container_width=True, key="home_help"):
            st.session_state.page = "📖 Ayuda"
            st.rerun()

    # ── Actividad reciente (feature #1) ──────────────────────────────────────
    history = _load_history()
    if history:
        st.markdown('<div class="mh-section-title">Actividad reciente</div>',
                    unsafe_allow_html=True)
        for ev in history[-5:][::-1]:
            kind_colors = {
                "Música": "mh-badge-blue", "Música (manual)": "mh-badge-blue",
                "Película": "mh-badge-purple", "Película (magnet)": "mh-badge-purple",
                "Fix Metadata": "mh-badge-yellow", "Renombrado": "mh-badge-yellow",
                "Ebooks": "mh-badge-green",
            }
            cls = kind_colors.get(ev["kind"], "mh-badge-red")
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;padding:5px 0;'
                f'border-bottom:1px solid rgba(120,80,255,0.1);">'
                f'<span class="mh-badge {cls}">{ev["kind"]}</span>'
                f'<span style="color:#c0c0dc;font-size:0.875rem;">{ev.get("detail","")[:60]}</span>'
                f'<span style="color:#7070a8;font-size:0.75rem;margin-left:auto;">{ev["date"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    tmdb_ok = bool(cfg.get("tmdb_api_key", "").strip())
    if not tmdb_ok:
        st.warning("TMDB API key no configurada — Películas no funcionará hasta configurarla.")


def page_musica():
    _page_header("🎵", "Música", "Descarga MP3s · Last.fm + The Pirate Bay")
    cfg = load_config()

    with st.expander("⚙️ Opciones", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            top_tracks = st.number_input("Número de canciones a buscar", 10, 300, cfg["top_tracks"], 10)
        with col2:
            genres_all = [
                "rock", "pop", "electronic", "hip-hop", "jazz", "metal",
                "classical", "reggae", "latin", "blues", "soul", "punk",
                "indie", "alternative", "r&b", "country", "folk",
            ]
            genres = st.multiselect("Géneros", genres_all, default=cfg["genres"])

    st.markdown("---")

    tab1, tab2, tab_trend, tab3 = st.tabs([
        "📻 Top Last.fm → torrents", "🔎 Buscar artista / canción",
        "🔥 Tendencias", "📂 Resultados anteriores",
    ])

    # ── Tab Tendencias: top de canciones de Apple Music + descarga ────────────
    with tab_trend:
        st.info(
            "**Fuente:** chart de Apple Music (elige país y género)  ·  "
            "**Qué busca:** el mejor torrent de cada canción en las 4 fuentes "
            "(Knaben, SolidTorrents, BitSearch, TPB), usando el álbum real de Shazam  ·  "
            "**Salida:** abre el magnet en tu cliente torrent y marca las que ya tienes."
        )
        tcol1, tcol2, tcol3 = st.columns([2, 2, 1])
        with tcol1:
            t_country = st.selectbox(
                "País", list(APPLE_CHART_COUNTRIES.keys()),
                format_func=lambda c: APPLE_CHART_COUNTRIES[c],
                key="trend_country",
            )
        with tcol2:
            t_genre = st.selectbox("Género", list(APPLE_CHART_GENRES.keys()),
                                   key="trend_genre")
        with tcol3:
            t_limit = st.selectbox("Top", [25, 50, 100], index=1, key="trend_limit")

        top_songs = _apple_top_songs(t_country, APPLE_CHART_GENRES[t_genre], t_limit)

        if not top_songs:
            st.warning("No se pudo cargar el chart. Reintenta en unos segundos.")
        else:
            # Biblioteca local + ledger para marcar descargadas/pedidas
            lib_keys  = _scan_music_library(cfg.get("music_folder", ""))
            ledger    = _ledger_load()
            results   = _spotify_load_results()
            min_seeds = int(cfg.get("min_seeds", 3))

            n_dl = sum(1 for s in top_songs
                       if _is_downloaded(lib_keys, s["artist"], s["track"], ledger))
            mt1, mt2 = st.columns(2)
            mt1.metric("🔥 En el top", len(top_songs))
            mt2.metric("⬇️ Ya en biblioteca", n_dl)

            cba, cbb = st.columns(2)
            run_all_trend = cba.button("🚀 Buscar y descargar todas las que faltan",
                                       type="primary", use_container_width=True,
                                       key="trend_run_all")
            if cbb.button("🔄 Re-escanear biblioteca", use_container_width=True,
                          key="trend_rescan"):
                _scan_music_library.clear()
                st.rerun()

            if run_all_trend:
                pending = [s for s in top_songs
                           if not _is_downloaded(lib_keys, s["artist"], s["track"], ledger)]
                prog = st.progress(0.0)
                ptxt = st.empty()
                total_p = max(len(pending), 1)
                done = 0
                for s, res in _parallel_searches(pending, min_seeds=min_seeds):
                    label = f"{s['artist']} — {s['track']}"
                    results[label] = res
                    if res.get("status") == "found":
                        _download_and_record(s["artist"], s["track"], res)
                    done += 1
                    prog.progress(done / total_p)
                    ptxt.text(f"Buscando {done}/{len(pending)}: {label}…")
                    if done % 10 == 0:
                        _spotify_save_results(results)
                _spotify_save_results(results)
                ptxt.success(f"✅ Listo — {len(pending)} canciones procesadas.")
                st.rerun()

            st.markdown("---")
            for i, s in enumerate(top_songs):
                cache_key  = f"{s['artist']} — {s['track']}"
                res        = results.get(cache_key, {})
                status     = res.get("status")
                downloaded = _is_downloaded(lib_keys, s["artist"], s["track"], ledger)
                requested  = (not downloaded and
                              _ledger_status(ledger, s["artist"], s["track"]) == "requested")
                with st.container(border=True):
                    ci, cs, ca = st.columns([4, 2, 2])
                    with ci:
                        badge = (" &nbsp;⬇️ **En biblioteca**" if downloaded else
                                 " &nbsp;⬇️ *Pedida*" if requested else "")
                        st.markdown(f"**{i+1}. {s['artist']}** — {s['track']}{badge}",
                                    unsafe_allow_html=True)
                        st.caption(f"🎵 {s.get('genre','')}")
                        _song_preview_ui(s["artist"], s["track"], f"trend_{i}")
                    with cs:
                        if downloaded:
                            st.caption("⬇️ Ya descargada")
                        elif status == "found":
                            seeds = res.get("seeds", 0)
                            ic = "🟢" if seeds >= 20 else ("🟡" if seeds >= 5 else "🔴")
                            st.caption(f"✅ {res.get('name','')[:50]}")
                            warn = " · ⚠️ pocos seeds" if res.get("low_seeds") else ""
                            st.caption(f"{ic} {seeds} seeds · {res.get('size','?')}"
                                       f" · {res.get('source','')}{warn}")
                        elif requested:
                            st.caption("⬇️ Pedida (bajando)")
                        elif status == "not_found":
                            st.caption("❌ Sin resultado")
                        else:
                            st.caption("⏳ Sin buscar")
                    with ca:
                        if status == "found" and not downloaded:
                            if st.button("🧲 Descargar", key=f"trend_dl_{i}",
                                         use_container_width=True):
                                _download_and_record(s["artist"], s["track"], res)
                                st.rerun()
                        elif not downloaded:
                            if st.button("🔍 Buscar", key=f"trend_s_{i}",
                                         use_container_width=True):
                                with st.spinner(f"Buscando {cache_key}…"):
                                    results[cache_key] = _search_song_torrent(
                                        s["artist"], s["track"], min_seeds=min_seeds)
                                    _spotify_save_results(results)
                                    if results[cache_key].get("status") == "found":
                                        _download_and_record(s["artist"], s["track"],
                                                             results[cache_key])
                                st.rerun()

    with tab1:
        st.info(
            "**Fuente:** tu top de canciones de **Last.fm** por género  ·  "
            "**Qué busca:** cada canción en **The Pirate Bay**  ·  "
            "**Salida:** ficheros `.torrent` en `output/torrents` + un registro que "
            "verás en **📂 Resultados anteriores**.  \n"
            "Requiere tu **API key de Last.fm** (⚙️ Configuración)."
        )
        if not cfg.get("lastfm_api_key", "").strip():
            st.warning("⚠️ Falta tu API key de Last.fm — configúrala en ⚙️ Configuración "
                       "antes de ejecutar.")

        # Feature #13: formato de audio
        fmt_col1, fmt_col2 = st.columns([2, 1])
        with fmt_col1:
            audio_fmt = st.radio(
                "Formato de audio",
                ["MP3", "FLAC", "Cualquier formato"],
                horizontal=True,
                key="mus_fmt",
                help="FLAC busca en la categoría Música (todo) con calidad sin pérdida",
            )
        fmt_cat_map = {"MP3": 101, "FLAC": 100, "Cualquier formato": 100}

        if st.button("🚀 Iniciar búsqueda", type="primary", use_container_width=True):
            cfg["top_tracks"] = top_tracks
            cfg["genres"]     = genres
            save_config(cfg)

            script = BASE_DIR / "scripts" / "lastfm_export.py"
            extra_env = {
                "LASTFM_API_KEY":         cfg["lastfm_api_key"],
                "MEDIAHUB_TOP_TRACKS":    str(top_tracks),
                "MEDIAHUB_GENRES":        json.dumps(genres),
                "MEDIAHUB_TPB_MUSIC_CAT": str(fmt_cat_map[audio_fmt]),
            }

            status = st.empty()
            log    = st.empty()
            status.info("⏳ Ejecutando — puede tardar varios minutos...")
            ok = stream_script([PYTHON, "-u", str(script)], log, status,
                               extra_env=extra_env)
            if ok:
                status.success("✅ ¡Listo!")
                _record_download("Música", top_tracks,
                                 f"{len(genres)} géneros · formato {audio_fmt}")
            else:
                status.error("❌ El script terminó con errores")

    # ── Tab 2: Búsqueda directa multi-fuente ─────────────────────────────────
    with tab2:
        st.markdown(
            "Busca música en **BitSearch**, **Knaben DHT**, **SolidTorrents** y **The Pirate Bay**. "
            "Activa **Búsqueda ampliada** para probar automáticamente variantes sin acentos, "
            "apellido solo y sufijo *discografia* — ideal para Vicente Fernández, Juan Gabriel, etc."
        )

        # ── Helpers ──────────────────────────────────────────────────────────
        def _size_human_music(b):
            try:
                b = int(b)
                for u in ("B","KB","MB","GB"):
                    if b < 1024: return f"{b:.0f} {u}"
                    b //= 1024
                return f"{b:.1f} TB"
            except: return "?"

        def _magnet_music(r):
            ih   = r.get("info_hash","")
            name = _uparse_mod.quote(r.get("name",""))
            tr   = ("tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
                    "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
                    "&tr=udp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce")
            return f"magnet:?xt=urn:btih:{ih}&dn={name}&{tr}"

        def _knaben_music(q, n=12):
            # Delega en la implementación corregida a nivel de módulo (API POST .org).
            return _knaben_search_music(q, n)

        def _solid_music(q, n=12):
            try:
                url = "https://solidtorrents.to/api/v1/search?" + _uparse_mod.urlencode({
                    "q": q, "sort": "seeders", "category": "music", "size": n,
                })
                req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with _ureq_mod.urlopen(req, timeout=8) as r:
                    data = json.loads(r.read())
                hits = (data.get("hits") or {}).get("hits") or data.get("results") or []
                out  = []
                for h in hits:
                    src   = h.get("_source") or h
                    ih    = (src.get("infohash") or src.get("info_hash") or "").lower()
                    name  = src.get("title") or src.get("name") or ""
                    swarm = src.get("swarm") or {}
                    seeds = int(swarm.get("seeders") or src.get("seeders") or 0)
                    peers = int(swarm.get("leechers") or src.get("leechers") or 0)
                    size_b= int(src.get("size") or 0)
                    if not ih or not name:
                        continue
                    out.append({"name": name, "seeders": seeds, "leechers": peers,
                                "size": size_b, "info_hash": ih, "source": "Solid"})
                return out[:n]
            except Exception:
                return []

        def _bitsearch_music(q, n=20):
            try:
                url = "https://bitsearch.to/api/v1/search?" + _uparse_mod.urlencode({
                    "q": q, "category": "music", "subcat": "", "page": 1,
                })
                req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
                with _ureq_mod.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                hits = data.get("results") or data.get("hits") or []
                out  = []
                for h in hits:
                    ih    = (h.get("infoHash") or h.get("info_hash") or h.get("infohash") or "").lower()
                    name  = h.get("name") or h.get("title") or ""
                    stats = h.get("stats") or {}
                    seeds = int(stats.get("seeders") or h.get("seeders") or 0)
                    peers = int(stats.get("leechers") or h.get("leechers") or 0)
                    size_b= int(h.get("size") or 0)
                    if not ih or not name:
                        continue
                    out.append({"name": name, "seeders": seeds, "leechers": peers,
                                "size": size_b, "info_hash": ih, "source": "BitSearch"})
                return out[:n]
            except Exception:
                return []

        def _expand_queries(q):
            """Genera variantes del query para mejor cobertura de música latina."""
            import unicodedata as _ud
            variants = [q]
            # Sin acentos
            no_acc = "".join(c for c in _ud.normalize("NFKD", q) if _ud.category(c) != "Mn")
            if no_acc.lower() != q.lower():
                variants.append(no_acc)
            # Apellido/palabra clave + discografia
            words = q.strip().split()
            base  = no_acc if no_acc.lower() != q.lower() else q
            if "discografia" not in q.lower() and "discography" not in q.lower():
                variants.append(base + " discografia")
                # Solo apellido (última palabra) + discografia, útil para "Vicente Fernandez" → "Fernandez discografia"
                if len(words) >= 2:
                    variants.append(words[-1] + " discografia")
                # Solo apellido solo
                if len(words) >= 2:
                    variants.append(words[-1])
            return list(dict.fromkeys(v.strip() for v in variants if v.strip()))

        # ── Controles de búsqueda ─────────────────────────────────────────────
        col_q, col_src = st.columns([3, 1])
        with col_q:
            query = st.text_input(
                "Artista, canción o álbum",
                placeholder="ej: Vicente Fernandez, ranchera discografia, Banda MS...",
                key="tpb_query",
            )
        with col_src:
            fuente_mus = st.selectbox(
                "Fuente",
                ["Todas 🔍", "BitSearch 🎵", "Knaben DHT 🔗", "SolidTorrents 🌐", "The Pirate Bay 🏴"],
                key="mus_fuente",
                help="BitSearch, Knaben y SolidTorrents tienen mejor cobertura de música latina y ranchera.",
            )

        col_cat, col_fmt = st.columns(2)
        with col_cat:
            categoria = st.selectbox(
                "Categoría (TPB)", ["MP3", "Música (todo)", "Todas"], key="tpb_cat",
                help="Solo aplica a The Pirate Bay.",
            )
        with col_fmt:
            fmt_suffix = st.selectbox("Formato", ["Auto", "MP3", "FLAC"], key="tpb_fmt_suffix")

        cat_map     = {"MP3": 101, "Música (todo)": 100, "Todas": 0}
        col_sl, col_exp = st.columns([3, 1])
        with col_sl:
            n_resultados = st.slider("Resultados por fuente", 5, 50, 20, key="tpb_n")
        with col_exp:
            expandir = st.toggle(
                "Búsqueda ampliada",
                value=True,
                key="mus_expandir",
                help="Prueba automáticamente variantes: sin acentos, + discografia, solo apellido. Ideal para artistas latinos.",
            )

        # ── Sugerencias para ranchera / música latina ─────────────────────────
        SUGERENCIAS_LAT = [
            "Vicente Fernandez discografia", "Juan Gabriel discografia",
            "Banda MS discografia", "Grupo Montez de Durango",
            "Los Bukis discografia", "Marco Antonio Solis",
            "Jenni Rivera discografia", "Pepe Aguilar discografia",
            "Mariachi Vargas", "Los Tigres del Norte discografia",
            "Lupillo Rivera", "Chalino Sanchez",
            "Norteñas mix", "Rancheras clasicas mix", "Banda sinaloense mix",
        ]
        def _set_mus_query(sug):
            st.session_state["tpb_query"] = sug

        with st.expander("💡 Sugerencias de búsqueda — Ranchera & Banda"):
            sug_cols = st.columns(3)
            for j, sug in enumerate(SUGERENCIAS_LAT):
                sug_cols[j % 3].button(
                    sug, key=f"sug_{j}",
                    on_click=_set_mus_query, args=(sug,),
                    use_container_width=True,
                )

        buscar = st.button("🔍 Buscar música", type="primary",
                           use_container_width=True, disabled=not query)

        if buscar and query:
            effective_query = f"{query} {fmt_suffix}" if fmt_suffix != "Auto" else query

            usar_tpb       = fuente_mus in ("Todas 🔍", "The Pirate Bay 🏴")
            usar_knaben    = fuente_mus in ("Todas 🔍", "Knaben DHT 🔗")
            usar_solid     = fuente_mus in ("Todas 🔍", "SolidTorrents 🌐")
            usar_bitsearch = fuente_mus in ("Todas 🔍", "BitSearch 🎵")

            # Queries a ejecutar: query principal + variantes si expandir está activo
            queries_to_run = _expand_queries(effective_query) if expandir else [effective_query]

            tpb_res, knaben_res, solid_res, bits_res = [], [], [], []
            buckets = {"tpb": tpb_res, "knaben": knaben_res,
                       "solid": solid_res, "bits": bits_res}
            # Una tarea por (variante × fuente); se ejecutan todas en paralelo
            tasks = []
            for q_var in queries_to_run:
                if usar_tpb:
                    tasks.append(("tpb", lambda q=q_var: [
                        {**r, "source": "TPB"}
                        for r in _tpb_search_cached(q, cat_map[categoria], n_resultados)]))
                if usar_knaben:
                    tasks.append(("knaben", lambda q=q_var: _knaben_music(q, n_resultados)))
                if usar_solid:
                    tasks.append(("solid", lambda q=q_var: _solid_music(q, n_resultados)))
                if usar_bitsearch:
                    tasks.append(("bits", lambda q=q_var: _bitsearch_music(q, n_resultados)))

            with st.spinner(f"Buscando «{effective_query}»… "
                            f"({len(queries_to_run)} variante(s), {len(tasks)} consultas)"):
                with _cf.ThreadPoolExecutor(max_workers=min(len(tasks) or 1, 8)) as ex:
                    futs = {ex.submit(fn): name for name, fn in tasks}
                    for f in _cf.as_completed(futs):
                        try:
                            buckets[futs[f]] += f.result()
                        except Exception:
                            pass

            # Deduplicar por info_hash, ordenar por seeds
            seen, resultados = set(), []
            for r in bits_res + knaben_res + solid_res + tpb_res:
                ih = r.get("info_hash", "")
                if ih and ih in seen:
                    continue
                seen.add(ih)
                resultados.append(r)
            resultados.sort(key=lambda r: int(r.get("seeders", 0)), reverse=True)
            st.session_state["mus_results"] = resultados
            st.session_state["mus_results_query"] = effective_query

        # Render desde session_state: el clic en ⬇ Guardar dispara un rerun en
        # el que `buscar` vuelve a False, y sin esto el bloque desaparecía
        resultados = st.session_state.get("mus_results")
        if resultados is not None:
            TORRENT_SOURCES = [
                "https://itorrents.org/torrent/{ih}.torrent",
                "https://torcache.net/torrent/{ih}.torrent",
            ]
            if not resultados:
                st.warning("Sin resultados. Prueba con otro artista, amplía la fuente, o usa una sugerencia de arriba.")
            else:
                src_counts = {}
                for r in resultados:
                    src_counts[r.get("source","?")] = src_counts.get(r.get("source","?"), 0) + 1
                badges = " · ".join(f"**{v}** {k}" for k, v in src_counts.items())
                st.success(f"✅ {len(resultados)} resultados — {badges}")

                torrents_dir = BASE_DIR / "output" / "torrents"
                torrents_dir.mkdir(parents=True, exist_ok=True)

                for i, r in enumerate(resultados):
                    name    = r.get("name","")
                    seeds   = int(r.get("seeders", 0))
                    leeches = int(r.get("leechers", 0))
                    size    = _size_human_music(r.get("size", 0))
                    ih      = r.get("info_hash","")
                    mag     = _magnet_music(r)
                    source  = r.get("source", "TPB")

                    seed_color = "🟢" if seeds >= 20 else ("🟡" if seeds >= 5 else "🔴")
                    src_badge  = {"TPB": "🏴 TPB", "Knaben": "🔗 Knaben", "Solid": "🌐 Solid", "BitSearch": "🎵 BitSearch"}.get(source, source)

                    with st.container(border=True):
                        col_info, col_meta, col_btns = st.columns([4, 2, 2])

                        with col_info:
                            st.markdown(f"**{name[:80]}**")
                            st.caption(src_badge)

                        with col_meta:
                            st.caption(f"{seed_color} {seeds} seeds · {leeches} leechers")
                            st.caption(f"💾 {size}")

                        with col_btns:
                            keep  = set(" ._-()[]")
                            fname = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)[:80].strip() + ".torrent"
                            dest  = torrents_dir / fname

                            col_dl, col_mag = st.columns(2)
                            with col_dl:
                                if dest.exists():
                                    with open(dest, "rb") as fh:
                                        st.download_button("⬇ .torrent", fh.read(), fname,
                                                           key=f"dl_s_{i}", use_container_width=True)
                                elif ih:
                                    if st.button("⬇ Guardar", key=f"save_{i}",
                                                 use_container_width=True, help="Descargar .torrent por hash"):
                                        try:
                                            saved = False
                                            for tpl in TORRENT_SOURCES:
                                                try:
                                                    req = _ureq_mod.Request(
                                                        tpl.format(ih=ih.upper()),
                                                        headers={"User-Agent": "Mozilla/5.0"})
                                                    with _ureq_mod.urlopen(req, timeout=10) as resp:
                                                        data = resp.read()
                                                    if data and data[0:1] == b'd':
                                                        dest.write_bytes(data)
                                                        saved = True
                                                        break
                                                except: continue
                                            if saved:
                                                _record_download("Música (manual)", 1, name[:60])
                                                st.success("✅ Guardado")
                                            else:
                                                st.error("Sin servidor disponible")
                                        except Exception as ex:
                                            st.error(f"Error: {ex}")
                                else:
                                    st.caption("Sin hash")
                            with col_mag:
                                if st.button("🧲 Abrir", key=f"mag_{i}",
                                             use_container_width=True):
                                    _open_and_log(mag, name)
                                    st.toast("Magnet abierto y registrado en Historial")

            # CSV export
            import io as _io, csv as _csv
            csv_buf = _io.StringIO()
            writer  = _csv.writer(csv_buf)
            writer.writerow(["nombre","fuente","seeds","leechers","tamaño","info_hash"])
            for r in resultados:
                writer.writerow([r.get("name","")[:80], r.get("source",""),
                                 r.get("seeders",0), r.get("leechers",0),
                                 _size_human_music(r.get("size",0)), r.get("info_hash","")])
            q_csv = st.session_state.get("mus_results_query", "busqueda")
            st.download_button(
                "Exportar resultados a CSV", csv_buf.getvalue().encode(),
                file_name=f"musica_{q_csv[:30].replace(' ','_')}.csv",
                mime="text/csv", use_container_width=True, key="mus_csv_export",
            )

    # ── Tab 3: Resultados anteriores ─────────────────────────────────────────
    with tab3:
        out  = BASE_DIR / "output"
        torr = out / "torrents"
        log_path = out / "lastfm_search_log.json"

        # ── Descargas recientes (ledger — todas las fuentes) ───────────────
        ledger = _ledger_load()
        if ledger:
            entries = sorted(ledger.values(),
                             key=lambda e: e.get("requested_at", ""), reverse=True)
            n_done = sum(1 for e in entries if e.get("status") == "completed")
            st.markdown("#### ⬇️ Descargas recientes")
            st.caption(f"{len(entries)} registradas · {n_done} completadas · "
                       "incluye torrents (Tendencias/Spotify) y YouTube")
            for e in entries[:20]:
                icon = "✅" if e.get("status") == "completed" else "⬇️"
                src  = e.get("source", "?")
                when = e.get("completed_at") or e.get("requested_at", "")
                with st.container(border=True):
                    cda, cdb = st.columns([5, 2])
                    cda.markdown(f"{icon} **{e.get('artist','')}** — {e.get('track','')}")
                    cda.caption(f"📦 {src} · {e.get('torrent_name','')[:55]}")
                    cdb.caption(f"{'✅ Descargada' if e.get('status')=='completed' else '⬇️ Pedida'}"
                                f"\n\n{when}")
            if len(entries) > 20:
                st.caption(f"… y {len(entries) - 20} más.")
            st.markdown("---")

        # ── Búsqueda Last.fm (flujo 'Top Last.fm → torrents') ──────────────
        st.markdown("#### 📻 Última búsqueda de Last.fm")
        # ── Métricas ──────────────────────────────────────────────────────
        search_log_data = None
        if log_path.exists():
            with open(log_path) as f:
                search_log_data = json.load(f)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            count = len(list(torr.glob("*.torrent"))) if torr.exists() else 0
            st.metric("Torrents en disco", count)
        with col2:
            if search_log_data:
                st.metric("🆕 Nuevas", search_log_data.get("new", 0),
                          help="Encontradas en la última búsqueda")
            else:
                st.metric("🆕 Nuevas", "—")
        with col3:
            if search_log_data:
                st.metric("♻️ Reutilizadas", search_log_data.get("cached", 0),
                          help="Ya existían de búsquedas anteriores")
            else:
                st.metric("♻️ Reutilizadas", "—")
        with col4:
            if search_log_data:
                st.metric("✗ Sin resultado", search_log_data.get("not_found", 0))
            else:
                st.metric("✗ Sin resultado", "—")

        if search_log_data:
            st.caption(f"Última búsqueda: {search_log_data.get('date', '—')}")

        st.markdown("---")

        # ── Lista de canciones con estado ────────────────────────────────
        if search_log_data and search_log_data.get("results"):
            st.markdown("#### 🎵 Resultados de la búsqueda")

            # Filtros rápidos
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                search_q = st.text_input("🔎 Filtrar por canción o artista",
                                         placeholder="ej: metallica, bohemian...",
                                         key="lfm_search")
            with col_f2:
                show_filter = st.selectbox("Mostrar", ["Todas", "🆕 Solo nuevas", "♻️ Solo reutilizadas", "✗ Sin resultado"])

            results = search_log_data["results"]

            # Aplica filtros
            if search_q:
                q = search_q.lower()
                results = [r for r in results if q in r["song"].lower()]
            if show_filter == "🆕 Solo nuevas":
                results = [r for r in results if r["status"] == "new"]
            elif show_filter == "♻️ Solo reutilizadas":
                results = [r for r in results if r["status"] == "cached"]
            elif show_filter == "✗ Sin resultado":
                results = [r for r in results if r["status"] == "not_found"]

            # Feature #12: CSV export for music results
            import io as _io_mus, csv as _csv_mus
            _csv_buf = _io_mus.StringIO()
            _cw = _csv_mus.writer(_csv_buf)
            _cw.writerow(["canción", "estado", "seeds", "tamaño", "fallback"])
            for _r in search_log_data["results"]:
                _cw.writerow([_r.get("song",""), _r.get("status",""),
                              _r.get("seeds",""), _r.get("size",""), _r.get("fallback","")])
            st.download_button(
                "Exportar lista a CSV",
                _csv_buf.getvalue().encode(),
                file_name="musica_resultados.csv",
                mime="text/csv",
                key="mus_results_csv",
            )

            st.caption(f"Mostrando {len(results)} canciones")

            for r in results:
                status = r["status"]

                if status == "new":
                    badge = '<span class="badge-new">🆕 NUEVA</span>'
                    icon  = "✅"
                elif status == "cached":
                    badge = '<span class="badge-cached">♻️ YA EXISTÍA</span>'
                    icon  = "💾"
                else:
                    badge = '<span class="badge-nf">✗ NO ENCONTRADA</span>'
                    icon  = "❌"

                fb_txt = f"  ·  via {r['fallback']}" if r.get("fallback") and r["fallback"] not in ("", "caché") else ""
                seeds  = r.get("seeds", "—")
                size   = r.get("size", "—")
                meta   = f"{seeds} seeds · {size}" if seeds != "—" else ""

                col_a, col_b, col_c = st.columns([4, 2, 1])
                with col_a:
                    st.markdown(
                        f'<div class="song-row">{badge} &nbsp; {icon} <b>{r["song"][:60]}</b>'
                        f'<span style="color:#888;font-size:.8rem">{fb_txt}</span></div>',
                        unsafe_allow_html=True,
                    )
                with col_b:
                    st.caption(meta)
                with col_c:
                    # Descarga del .torrent si existe en disco
                    if status != "not_found":
                        fname_stem = f"{r['song']} — {r['torrent']}"
                        keep = set(" ._-()[]")
                        fname = "".join(c if (c.isalnum() or c in keep) else "_" for c in fname_stem)[:80].strip() + ".torrent"
                        torrent_file = torr / fname if torr.exists() else None
                        if torrent_file and torrent_file.exists():
                            with open(torrent_file, "rb") as fh:
                                st.download_button("⬇", fh.read(), fname,
                                                   key=f"dl_{r['song'][:30]}",
                                                   help="Descargar .torrent")
                        elif r.get("magnet"):
                            st.markdown(f"[🧲]({r['magnet']})", help="Abrir magnet link")
        else:
            # Fallback: muestra ficheros .torrent en disco sin clasificar
            if torr.exists() and list(torr.glob("*.torrent")):
                st.markdown("#### 🧲 Ficheros .torrent (para uTorrent)")
                torrents = sorted(torr.glob("*.torrent"))
                for t in torrents[:30]:
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.caption(t.stem[:60])
                    with col_b:
                        with open(t, "rb") as fh:
                            st.download_button("⬇", fh.read(), t.name, key=f"m_{t.name}")
                if len(torrents) > 30:
                    st.caption(f"... y {len(torrents)-30} más")

        if (out / "magnets_lastfm.txt").exists():
            st.markdown("#### 📄 Archivos de reporte")
            output_files_section(out, extensions=[".txt", ".html"])


def page_ebooks():
    _page_header("📚", "Ebooks", "Descarga libros compatibles con Kindle")
    cfg = load_config()

    # ── Helpers compartidos ───────────────────────────────────────────────────
    import urllib.request as _ureq, urllib.parse as _uparse, json as _json

    TPB_API_EB = "https://apibay.org/q.php"
    TORRENT_SOURCES_EB = [
        "https://itorrents.org/torrent/{ih}.torrent",
        "https://torcache.net/torrent/{ih}.torrent",
    ]

    def _eb_search(q, cat, n):
        url = f"{TPB_API_EB}?" + _uparse.urlencode({"q": q, "cat": cat})
        try:
            req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _ureq.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read().decode())
            if data and data[0].get("id") == "0":
                return []
            return data[:n]
        except Exception as e:
            st.error(f"Error conectando con TPB: {e}")
            return []

    def _eb_size(b):
        try:
            b = int(b)
            for u in ("B", "KB", "MB", "GB"):
                if b < 1024: return f"{b:.0f} {u}"
                b //= 1024
            return f"{b:.1f} TB"
        except: return "?"

    def _eb_magnet(r):
        ih   = r.get("info_hash", "")
        name = _uparse.quote(r.get("name", ""))
        tr   = ("tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
                "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce")
        return f"magnet:?xt=urn:btih:{ih}&dn={name}&{tr}"

    def _seed_badge(seeds):
        if seeds >= 20:  return "🟢", "Buena disponibilidad — descarga rápida"
        if seeds >= 5:   return "🟡", "Disponibilidad media — puede tardar"
        return "🔴",            "Pocos seeders — descarga lenta o puede no completar"

    def _safe_fname(name):
        keep = set(" ._-()[]")
        return "".join(c if (c.isalnum() or c in keep) else "_" for c in name)[:80].strip()

    def _libgen_search(q, n=10, lang_es=False, fmt=None):
        """Search Library Genesis. Returns list of book dicts with direct download links."""
        import re
        params = {"req": q, "res": min(n, 25), "phrase": 1,
                  "column": "def", "lg_topic": "libgen", "open": 0, "view": "simple"}
        if lang_es:
            params["language"] = "Spanish"
        mirrors = ["https://libgen.is", "https://libgen.rs", "https://libgen.st"]
        strip_tags = lambda s: re.sub(r'<[^>]+>', '', s).strip()
        for mirror in mirrors:
            try:
                url = f"{mirror}/search.php?" + _uparse.urlencode(params)
                req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
                with _ureq.urlopen(req, timeout=15) as r:
                    html = r.read().decode("utf-8", errors="ignore")
                books = []
                rows = re.findall(r'<tr[^>]*valign=["\']?top["\']?[^>]*>(.*?)</tr>', html, re.DOTALL | re.I)
                for row in rows:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.I)
                    if len(cells) < 9:
                        continue
                    id_ = strip_tags(cells[0])
                    if not id_.isdigit():
                        continue
                    author = strip_tags(cells[1])[:80]
                    title_m = re.search(r'<a[^>]+>(.*?)</a>', cells[2], re.DOTALL | re.I)
                    title = strip_tags(title_m.group(1) if title_m else cells[2])[:120]
                    publisher = strip_tags(cells[3])[:60]
                    year = strip_tags(cells[4])
                    language = strip_tags(cells[6])
                    size = strip_tags(cells[7])
                    ext = strip_tags(cells[8]).lower()
                    md5 = ""
                    for c in cells[9:]:
                        m = re.search(r'[?&]md5=([a-fA-F0-9]{32})', c, re.I)
                        if m:
                            md5 = m.group(1).upper()
                            break
                    if not md5:
                        m = re.search(r'md5=([a-fA-F0-9]{32})', cells[2], re.I)
                        if m:
                            md5 = m.group(1).upper()
                    if not title:
                        continue
                    if fmt and fmt != "Todos" and ext != fmt.lower():
                        continue
                    books.append({
                        "title": title, "author": author, "year": year,
                        "language": language, "size": size,
                        "ext": ext or "?", "md5": md5,
                        "dl_url": f"http://library.lol/main/{md5}" if md5 else "",
                    })
                if books:
                    return books[:n]
            except Exception:
                continue
        return []

    # Leyenda seeds (se muestra en varias pestañas)
    SEED_LEGEND = (
        "🟢 **≥20 seeds** — descarga rápida  ·  "
        "🟡 **5-19 seeds** — velocidad media  ·  "
        "🔴 **<5 seeds** — lenta o incompleta  \n"
        "*Seeds = personas compartiendo el archivo. Más seeds = mejor descarga.*"
    )

    with st.expander("⚙️ Opciones", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            top_books = st.number_input("Libros a buscar (total, mitad ES / mitad EN)", 20, 300, cfg["top_books"], 10)
        with col2:
            lang = st.multiselect("Idiomas", ["Español 🇪🇸", "Inglés 🇬🇧"],
                                  default=["Español 🇪🇸", "Inglés 🇬🇧"])

    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["▶ Ejecutar búsqueda", "🔎 Buscar libro", "📂 Resultados anteriores"])

    # ── Tab 1: búsqueda automática ────────────────────────────────────────────
    with tab1:
        st.markdown(
            "Busca los libros más leídos en **Open Library** más una lista curada "
            "de clásicos, premios Nobel/Booker/Pulitzer y bestsellers. "
            "Descarga `.torrent` en formato **EPUB / MOBI / AZW3** para Kindle."
        )
        if st.button("🚀 Iniciar búsqueda", type="primary", use_container_width=True):
            cfg["top_books"] = top_books
            save_config(cfg)
            script = BASE_DIR / "scripts" / "ebooks_export.py"
            status = st.empty()
            log    = st.empty()
            status.info("⏳ Ejecutando — puede tardar varios minutos...")
            ok = stream_script([PYTHON, "-u", str(script)], log, status,
                               extra_env={"MEDIAHUB_TOP_BOOKS": str(top_books)})
            if ok:
                status.success("✅ ¡Listo!")
            else:
                status.error("❌ El script terminó con errores")

    # ── Tab 2: búsqueda directa ───────────────────────────────────────────────
    with tab2:
        st.markdown(
            "Busca libros en **The Pirate Bay** (torrents) y/o **Library Genesis** "
            "(descarga directa — EPUB, PDF, MOBI). Library Genesis tiene cobertura "
            "mucho mayor, especialmente en español."
        )
        st.caption(SEED_LEGEND)
        st.markdown("---")

        # ── Controles de búsqueda ──────────────────────────────────────────
        col_q, col_src = st.columns([3, 1])
        with col_q:
            query_eb = st.text_input(
                "📖 Título, autor o colección",
                placeholder="ej: Gabriel García Márquez, Sapiens, Stephen King...",
                key="eb_query",
            )
        with col_src:
            fuente_eb = st.selectbox(
                "Fuente",
                ["Library Genesis 📚", "The Pirate Bay 🏴", "Ambas fuentes 🔍"],
                key="eb_fuente",
                help="Library Genesis: descarga directa (EPUB/PDF/MOBI). TPB: torrent.",
            )

        col_lang, col_fmt, col_cat = st.columns(3)
        with col_lang:
            solo_es = st.checkbox(
                "Solo en español 🇪🇸", value=False, key="eb_es",
                help="Filtra resultados por idioma español. Muy efectivo en Library Genesis.",
            )
        with col_fmt:
            fmt_eb = st.selectbox(
                "Formato (LibGen)",
                ["Todos", "EPUB", "PDF", "MOBI", "AZW3"],
                key="eb_fmt",
                help="Filtra por formato de archivo en Library Genesis.",
            )
        with col_cat:
            cat_eb = st.selectbox(
                "Categoría (TPB)",
                ["Ebooks (601)", "Todas"],
                key="eb_cat",
                help="Categoría de búsqueda en The Pirate Bay.",
            )

        cat_map_eb = {"Ebooks (601)": 601, "Todas": 0}
        n_eb = st.slider("Resultados por fuente", 3, 20, 8, key="eb_n")

        buscar_eb = st.button("🔍 Buscar", type="primary",
                              use_container_width=True, disabled=not query_eb)

        if buscar_eb and query_eb:
            usar_libgen = fuente_eb in ("Library Genesis 📚", "Ambas fuentes 🔍")
            usar_tpb    = fuente_eb in ("The Pirate Bay 🏴", "Ambas fuentes 🔍")

            # Consulta efectiva para TPB: añadir "español" si procede
            tpb_query = query_eb
            if solo_es and usar_tpb:
                tpb_query = f"{query_eb} español"

            res_libgen, res_tpb = [], []

            with st.spinner("Buscando…"):
                if usar_libgen:
                    res_libgen = _libgen_search(
                        query_eb, n=n_eb, lang_es=solo_es,
                        fmt=fmt_eb if fmt_eb != "Todos" else None,
                    )
                if usar_tpb:
                    res_tpb = _eb_search(tpb_query, cat_map_eb[cat_eb], n_eb)

            st.session_state["eb_results"] = {
                "libgen": res_libgen, "tpb": res_tpb,
                "query": query_eb, "solo_es": solo_es,
            }

        # Render desde session_state: el clic en ⬇ Guardar dispara un rerun en
        # el que `buscar_eb` vuelve a False, y sin esto el clic se perdía
        eb_state = st.session_state.get("eb_results")
        if eb_state is not None:
            torrents_dir_eb = BASE_DIR / "output_ebooks" / "torrents"
            torrents_dir_eb.mkdir(parents=True, exist_ok=True)
            res_libgen, res_tpb = eb_state["libgen"], eb_state["tpb"]

            total = len(res_libgen) + len(res_tpb)
            if total == 0:
                st.warning("Sin resultados. Prueba con otro título, amplía la fuente o desactiva el filtro de español.")
            else:
                st.success(f"✅ {total} resultados para **{eb_state['query']}**"
                           + (" (en español)" if eb_state["solo_es"] else ""))

            # ── Resultados Library Genesis ─────────────────────────────────
            if res_libgen:
                st.markdown(f"#### 📚 Library Genesis — {len(res_libgen)} resultados")
                for i, b in enumerate(res_libgen):
                    ext_badge = {
                        "epub": "🟢 EPUB", "pdf": "🔵 PDF",
                        "mobi": "🟠 MOBI", "azw3": "🟠 AZW3",
                        "fb2":  "⚪ FB2",  "djvu": "⚪ DJVU",
                    }.get(b["ext"], f"📄 {b['ext'].upper()}")

                    lang_flag = "🇪🇸 " if "spanish" in b["language"].lower() or "español" in b["language"].lower() else ""

                    with st.container(border=True):
                        col_info, col_btns = st.columns([5, 2])
                        with col_info:
                            st.markdown(f"**{b['title']}**")
                            meta_parts = []
                            if b["author"]: meta_parts.append(f"✍️ {b['author']}")
                            if b["year"]:   meta_parts.append(b["year"])
                            meta_parts.append(f"{lang_flag}{b['language']}")
                            meta_parts.append(f"💾 {b['size']}")
                            meta_parts.append(ext_badge)
                            st.caption("  ·  ".join(meta_parts))
                        with col_btns:
                            if b["dl_url"]:
                                st.link_button(
                                    "⬇ Descargar", b["dl_url"],
                                    use_container_width=True,
                                    help="Abre library.lol — haz clic en 'GET' para descargar el archivo directamente.",
                                )
                            else:
                                st.caption("Sin enlace disponible")

            # ── Resultados The Pirate Bay ──────────────────────────────────
            if res_tpb:
                st.markdown(f"#### 🏴 The Pirate Bay — {len(res_tpb)} resultados")
                for i, r in enumerate(res_tpb):
                    name    = r.get("name", "")
                    seeds   = int(r.get("seeders", 0))
                    leeches = int(r.get("leechers", 0))
                    size    = _eb_size(r.get("size", 0))
                    ih      = r.get("info_hash", "")
                    mag     = _eb_magnet(r)
                    emoji, tip = _seed_badge(seeds)

                    fname = _safe_fname(name) + ".torrent"
                    dest  = torrents_dir_eb / fname
                    ya_dl = dest.exists()

                    with st.container(border=True):
                        col_info, col_meta, col_btns = st.columns([4, 2, 2])
                        with col_info:
                            prefix = "✅ " if ya_dl else ""
                            st.markdown(f"**{prefix}{name[:80]}**")
                            if ya_dl:
                                st.caption("💾 Ya descargado")
                        with col_meta:
                            st.caption(
                                f"{emoji} {seeds} seeds · {leeches} leechers",
                                help=f"{tip}\n\n*Leechers = personas descargando ahora*",
                            )
                            st.caption(f"📦 {size}")
                        with col_btns:
                            col_dl, col_mag = st.columns(2)
                            with col_dl:
                                if ya_dl:
                                    with open(dest, "rb") as fh:
                                        st.download_button(
                                            "⬇ .torrent", fh.read(), fname,
                                            key=f"eb_dl_{i}", use_container_width=True,
                                        )
                                else:
                                    if st.button("⬇ Guardar", key=f"eb_save_{i}",
                                                 use_container_width=True,
                                                 help="Descarga el .torrent a output_ebooks/torrents/"):
                                        try:
                                            saved = False
                                            for tpl in TORRENT_SOURCES_EB:
                                                try:
                                                    req = _ureq.Request(
                                                        tpl.format(ih=ih.upper()),
                                                        headers={"User-Agent": "Mozilla/5.0"})
                                                    with _ureq.urlopen(req, timeout=10) as resp:
                                                        data = resp.read()
                                                    if data and data[0:1] == b'd':
                                                        dest.write_bytes(data)
                                                        saved = True
                                                        break
                                                except: continue
                                            if saved:
                                                st.success("✅ Guardado")
                                            else:
                                                st.error("Sin caché disponible — usa el magnet")
                                        except Exception as ex:
                                            st.error(f"Error: {ex}")
                            with col_mag:
                                st.link_button(
                                    "🧲 Magnet", mag,
                                    use_container_width=True,
                                    help="Abre en uTorrent sin guardar .torrent",
                                )

    # ── Tab 3: resultados anteriores ──────────────────────────────────────────
    with tab3:
        out  = BASE_DIR / "output_ebooks"
        torr = out / "torrents"

        # Métricas
        torrents_list = sorted(torr.glob("*.torrent")) if torr.exists() else []
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📥 Torrents descargados", len(torrents_list))
        with col2:
            mag_f = out / "magnets_ebooks.txt"
            if mag_f.exists():
                n_mag = sum(1 for l in mag_f.read_text().splitlines() if l.startswith("magnet:"))
                st.metric("🧲 Magnet links", n_mag)
        with col3:
            html_f = out / "utorrent_ebooks.html"
            st.metric("📄 Vista HTML", "✓ Disponible" if html_f.exists() else "—")

        st.markdown("---")

        if not torrents_list:
            st.info("Aún no hay ebooks descargados. Ejecuta la búsqueda automática o busca uno en **🔎 Buscar libro**.")
        else:
            # Leyenda seeds
            st.caption(SEED_LEGEND)
            st.markdown("---")

            # Buscador
            filtro = st.text_input("🔎 Filtrar por título", placeholder="ej: márquez, tolkien, epub...",
                                   key="eb_filtro")
            mostrados = [t for t in torrents_list
                         if not filtro or filtro.lower() in t.stem.lower()]

            st.caption(f"Mostrando {len(mostrados)} de {len(torrents_list)} torrents descargados")

            for t in mostrados[:100]:
                col_a, col_b = st.columns([5, 1])
                with col_a:
                    st.markdown(f"✅ **{t.stem[:75]}**")
                with col_b:
                    with open(t, "rb") as fh:
                        st.download_button(
                            "⬇", fh.read(), t.name,
                            key=f"eb_prev_{t.name}",
                            help="Descargar este .torrent a tu equipo para importar en uTorrent",
                        )
            if len(mostrados) > 100:
                st.caption(f"... y {len(mostrados)-100} más (usa el filtro para buscar)")

        if (out / "utorrent_ebooks.html").exists():
            st.markdown("---")
            st.markdown("#### 📄 Archivos de reporte")
            output_files_section(out, extensions=[".txt", ".html"])


def page_metadata():
    _page_header("🔧", "Fix Metadata", "Corrige tags ID3 de tus MP3s automáticamente")
    cfg = load_config()

    col1, col2 = st.columns([2, 1])
    with col1:
        folder = st.text_input("📁 Carpeta con MP3s", value=cfg["music_folder"])
    with col2:
        mode = st.radio("Modo", ["Normal", "Dry Run (sin cambios)", "Force (sobreescribir todo)"])

    mode_flag = {"Normal": [], "Dry Run (sin cambios)": ["--dry-run"], "Force (sobreescribir todo)": ["--force"]}[mode]

    # Info previa
    folder_path = Path(folder)
    if folder_path.exists():
        mp3_count = len(list(folder_path.rglob("*.mp3")))
        eta_min   = round(mp3_count * 1.2 / 60)
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("MP3s encontrados", mp3_count)
        col_b.metric("Tiempo estimado", f"~{eta_min} min")
        col_c.metric("Fuentes", "MusicBrainz + Last.fm")
    else:
        st.warning("La carpeta no existe. Verifica la ruta.")

    st.markdown("---")
    tab1, tab2, tab_preview, tab_rename = st.tabs([
        "▶ Ejecutar", "📊 Último reporte",
        "👁 Preview cambios",   # feature #4
        "✏️ Renombrar archivos",  # feature #8
    ])

    with tab1:
        st.markdown(
            "El script analiza cada MP3, detecta qué tags faltan "
            "(título, artista, álbum, año, género, **portada**) y los completa "
            "consultando **MusicBrainz** y **Last.fm**."
        )

        col_run, col_info = st.columns([1, 2])
        with col_run:
            run = st.button("🚀 Iniciar análisis", type="primary", use_container_width=True)
        with col_info:
            st.info("💡 Usa **Dry Run** primero para ver qué cambiaría sin modificar nada.")

        if run:
            if not folder_path.exists():
                st.error("La carpeta no existe.")
            else:
                cfg["music_folder"] = folder
                save_config(cfg)

                script = BASE_DIR / "scripts" / "fix_metadata.py"
                cmd    = [PYTHON, "-u", str(script), folder] + mode_flag

                status = st.empty()
                log    = st.empty()
                status.info("⏳ Analizando MP3s — esto puede tardar bastante...")
                ok = stream_script(cmd, log, status,
                                   extra_env={"LASTFM_API_KEY": cfg["lastfm_api_key"]})
                if ok:
                    status.success("✅ ¡Análisis completado!")
                    if mode == "Normal":
                        report_p = folder_path / "_metadata_report.json"
                        if report_p.exists():
                            rpt = json.loads(report_p.read_text())
                            _record_download("Fix Metadata",
                                             rpt.get("summary", {}).get("updated", 0),
                                             folder[:60])
                else:
                    status.error("❌ Terminó con errores")

    with tab2:
        report_path = folder_path / "_metadata_report.json"
        if report_path.exists():
            with open(report_path) as f:
                report = json.load(f)

            summary = report.get("summary", {})
            total   = sum(summary.values())

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("✓ Completos",    summary.get("ok", 0))
            col2.metric("✅ Actualizados", summary.get("updated", 0))
            col3.metric("— Sin cambios",  summary.get("no_changes", 0))
            col4.metric("✗ Errores",      summary.get("errors", 0))

            st.caption(f"Fecha: {report.get('date', '—')} | Total: {total} archivos")

            files = report.get("files", [])
            updated = [f for f in files if f.get("status") == "updated"]
            if updated:
                st.markdown(f"#### ✅ Archivos actualizados ({len(updated)})")
                for f in updated[:50]:
                    name    = Path(f["file"]).name
                    changes = " · ".join(f.get("changes", []))
                    st.markdown(f"- **{name[:50]}** — {changes[:80]}")
                if len(updated) > 50:
                    st.caption(f"... y {len(updated)-50} más")

            errors = [f for f in files if f.get("status") == "error"]
            if errors:
                with st.expander(f"✗ Errores ({len(errors)})"):
                    for f in errors:
                        st.markdown(f"- `{Path(f['file']).name}` — {f.get('error')}")
        else:
            st.info("Aún no hay reporte. Ejecuta el análisis primero.")

    # Feature #4 — Preview antes/después
    with tab_preview:
        st.markdown(
            "Ejecuta un **Dry Run** y visualiza los cambios propuestos como tabla "
            "antes de aplicarlos."
        )
        if st.button("🔍 Generar preview (sin modificar nada)", type="primary",
                     use_container_width=True, key="meta_preview_btn"):
            if not folder_path.exists():
                st.error("La carpeta no existe.")
            else:
                script = BASE_DIR / "scripts" / "fix_metadata.py"
                cmd    = [PYTHON, "-u", str(script), folder, "--dry-run"]
                status_p = st.empty()
                log_p    = st.empty()
                status_p.info("⏳ Analizando — Dry Run en curso...")
                ok = stream_script(cmd, log_p, status_p,
                                   extra_env={"LASTFM_API_KEY": cfg["lastfm_api_key"]})
                if ok:
                    status_p.success("✅ Preview listo")

        report_path = folder_path / "_metadata_report.json"
        if report_path.exists():
            with open(report_path) as f:
                rpt = json.load(f)
            files_rpt = rpt.get("files", [])
            proposed = [f for f in files_rpt if f.get("status") in ("updated", "would_update")]
            if proposed:
                import pandas as pd
                rows = []
                for f in proposed[:200]:
                    rows.append({
                        "Archivo": Path(f["file"]).name[:50],
                        "Cambios": " · ".join(f.get("changes", [])),
                        "Estado": f.get("status", ""),
                    })
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"{len(proposed)} archivos con cambios propuestos")

                # Feature #12: CSV export of preview
                import io as _io_meta, csv as _csv_meta
                _buf = _io_meta.StringIO()
                _wr  = _csv_meta.DictWriter(_buf, fieldnames=["Archivo","Cambios","Estado"])
                _wr.writeheader(); _wr.writerows(rows)
                st.download_button("Exportar preview a CSV", _buf.getvalue().encode(),
                                   "metadata_preview.csv", mime="text/csv",
                                   key="meta_csv_export")
            else:
                st.info("Sin cambios propuestos — todos los tags están completos.")
        else:
            st.info("Haz clic en 'Generar preview' para ver los cambios propuestos.")

    # Feature #8 — Renombrar archivos por metadata
    with tab_rename:
        st.markdown(
            "Renombra los MP3s usando sus tags ID3 actuales. "
            "Útil después de corregir la metadata."
        )
        rename_pattern = st.text_input(
            "Patrón de nombre",
            value="{artist} - {title}",
            help="Variables: {artist} {title} {album} {year} {track}",
            key="rename_pattern",
        )
        st.caption("Ejemplo: `{artist} - {album} - {title}` → `Pink Floyd - The Wall - Comfortably Numb.mp3`")

        dry_rename = st.checkbox("Dry Run — solo mostrar, no renombrar", value=True,
                                 key="rename_dry")

        if st.button("▶ Ejecutar renombrado", type="primary",
                     use_container_width=True, key="rename_btn"):
            if not folder_path.exists():
                st.error("La carpeta no existe.")
            else:
                try:
                    import mutagen.id3 as _mid3
                    mp3s = list(folder_path.rglob("*.mp3"))
                    if not mp3s:
                        st.warning("No se encontraron MP3s.")
                    else:
                        results_rename = []
                        renamed = 0
                        errors_r = 0
                        for mp3 in mp3s[:500]:
                            try:
                                tags = _mid3.ID3(str(mp3))
                                artist = str(tags.get("TPE1", "Desconocido")).strip()
                                title  = str(tags.get("TIT2", mp3.stem)).strip()
                                album  = str(tags.get("TALB", "")).strip()
                                year   = str(tags.get("TDRC", "")).strip()[:4]
                                track  = str(tags.get("TRCK", "")).strip().split("/")[0].zfill(2)
                                new_stem = rename_pattern.format(
                                    artist=artist, title=title, album=album,
                                    year=year, track=track,
                                )
                                # sanitize
                                keep_r = set(" ._-()[],'")
                                new_stem = "".join(c if (c.isalnum() or c in keep_r) else "_"
                                                   for c in new_stem)[:120].strip()
                                new_name = new_stem + ".mp3"
                                new_path = mp3.parent / new_name
                                changed  = new_name != mp3.name
                                results_rename.append({
                                    "original": mp3.name[:60],
                                    "nuevo":    new_name[:60],
                                    "cambio":   "Sí" if changed else "No",
                                })
                                if changed and not dry_rename:
                                    mp3.rename(new_path)
                                    renamed += 1
                            except Exception as e:
                                errors_r += 1
                                results_rename.append({
                                    "original": mp3.name[:60],
                                    "nuevo":    f"ERROR: {e}",
                                    "cambio":   "Error",
                                })

                        import pandas as pd
                        df_r = pd.DataFrame(results_rename)
                        st.dataframe(df_r, use_container_width=True, hide_index=True)
                        if dry_rename:
                            changes_count = sum(1 for r in results_rename if r["cambio"] == "Sí")
                            st.info(f"Dry Run: {changes_count} archivos se renombrarían · {errors_r} errores")
                        else:
                            st.success(f"✅ {renamed} archivos renombrados · {errors_r} errores")
                            _record_download("Renombrado", renamed, rename_pattern)
                except ImportError:
                    st.error("Instala `mutagen` para usar esta función: `pip install mutagen`")


def page_spotify():
    _page_header("🟢", "Mi Spotify", "Torrents de tus artistas más escuchados")
    cfg = load_config()

    st.markdown(
        "Cuando recibas el ZIP de Spotify (puede tardar hasta 30 días), "
        "extráelo en la carpeta `spotify_data/` y ejecuta aquí el análisis."
    )

    data_dir = BASE_DIR / "spotify_data"
    files    = list(data_dir.glob("Streaming_History_Audio_*.json")) if data_dir.exists() else []

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Archivos de historial encontrados", len(files))
    with col2:
        if files:
            total = sum(len(json.loads(f.read_text())) for f in files)
            st.metric("Total reproducciones", f"{total:,}")

    if not files:
        st.info(
            "📬 Aún no hay datos de Spotify.\n\n"
            "1. Ve a **spotify.com → Cuenta → Privacidad → Descarga tus datos**\n"
            "2. Pide el **historial de reproducción extendido**\n"
            f"3. Extrae el ZIP en: `{data_dir}`"
        )
        if st.button("Crear carpeta spotify_data"):
            data_dir.mkdir(exist_ok=True)
            st.success(f"Carpeta creada: {data_dir}")
    else:
        tab1, tab2, tab3, tab_yt = st.tabs(
            ["▶ Ejecutar", "📂 Resultados", "🎵 Canciones", "🎬 YouTube"])

        # ── Tab YouTube: descargar tu lista de Spotify desde YouTube ──────────
        with tab_yt:
            canciones_path = BASE_DIR / "output" / "top_canciones.json"
            if not canciones_path.exists():
                st.info("Primero ejecuta el análisis en **▶ Ejecutar** para generar "
                        "el listado de canciones.")
            elif not _youtube_deps_ok():
                st.warning("Faltan dependencias. Instala con `brew install yt-dlp ffmpeg` "
                           "y recarga la página.")
            else:
                st.markdown("Descarga tu lista de Spotify directamente desde "
                            "**YouTube** como MP3 (con metadata + portada).")
                canciones = json.loads(canciones_path.read_text(encoding="utf-8"))
                yt_dest = st.text_input("📁 Carpeta destino",
                                        value=cfg.get("music_folder", ""), key="spy_dest")
                lib_keys = _scan_music_library(yt_dest)
                ledger   = _ledger_load()
                missing  = [c for c in canciones
                            if not _is_downloaded(lib_keys, c["artist"], c["track"], ledger)]

                m1, m2 = st.columns(2)
                m1.metric("🎵 En tu lista", len(canciones))
                m2.metric("📥 Faltan en biblioteca", len(missing))

                cqa, cqb = st.columns([1, 2])
                with cqa:
                    lim = st.selectbox("Máximo a bajar", [10, 25, 50], key="spy_limit")
                with cqb:
                    st.write("")
                    run_batch = st.button(f"🎬 Descargar faltantes (máx {lim})",
                                          type="primary", disabled=not missing,
                                          use_container_width=True, key="spy_batch")
                if run_batch:
                    batch = missing[:lim]
                    prog   = st.progress(0.0)
                    status = st.empty()
                    log    = st.empty()
                    okc = 0
                    for i, c in enumerate(batch):
                        status.info(f"⬇️ {i+1}/{len(batch)} — {c['artist']} — {c['track']}")
                        vid = _youtube_top_id(c["artist"], c["track"])
                        if vid:
                            ok = stream_script(
                                _youtube_download_cmd(vid, yt_dest, c["artist"], c["track"]),
                                log, status)
                            okc += 1 if ok else 0
                        else:
                            log.warning(f"❌ No encontrada en YouTube: "
                                        f"{c['artist']} — {c['track']}")
                        prog.progress((i + 1) / len(batch))
                    _scan_music_library.clear()
                    status.success(f"✅ Listo — {okc}/{len(batch)} descargadas.")
                    st.rerun()

                st.markdown("---")
                MAX_ROWS = 100
                shown = canciones[:MAX_ROWS]
                if len(canciones) > MAX_ROWS:
                    st.caption(f"Mostrando las primeras {MAX_ROWS} de {len(canciones)}.")
                for i, c in enumerate(shown):
                    downloaded = _is_downloaded(lib_keys, c["artist"], c["track"], ledger)
                    with st.container(border=True):
                        ci, ca = st.columns([5, 2])
                        with ci:
                            badge = " &nbsp;⬇️ **En biblioteca**" if downloaded else ""
                            st.markdown(f"**{c['artist']}** — {c['track']}{badge}",
                                        unsafe_allow_html=True)
                            st.caption(f"🔁 {c.get('plays', 0)} plays")
                            _song_preview_ui(c["artist"], c["track"], f"spy_{i}")
                        with ca:
                            if not downloaded:
                                if st.button("🎬 Bajar MP3", key=f"spy_dl_{i}",
                                             use_container_width=True):
                                    status, log = st.empty(), st.empty()
                                    status.info("🔎 Buscando en YouTube…")
                                    vid = _youtube_top_id(c["artist"], c["track"])
                                    if not vid:
                                        status.error("❌ No encontrada en YouTube")
                                    else:
                                        ok = stream_script(
                                            _youtube_download_cmd(
                                                vid, yt_dest, c["artist"], c["track"]),
                                            log, status)
                                        if ok:
                                            _scan_music_library.clear()
                                            st.rerun()
                                        else:
                                            status.error("❌ Error al descargar")

        with tab1:
            st.markdown("Procesa tu historial y busca tus artistas más escuchados en TPB.")
            if st.button("🚀 Iniciar", type="primary"):
                script = BASE_DIR / "scripts" / "spotify_export.py"
                status = st.empty()
                log    = st.empty()
                status.info("⏳ Procesando historial...")
                ok = stream_script([PYTHON, "-u", str(script)], log, status)
                if ok:
                    status.success("✅ ¡Listo!")

        with tab2:
            out = BASE_DIR / "output"
            if (out / "reporte.txt").exists():
                output_files_section(out, extensions=[".txt", ".json"])

        with tab3:
            canciones_path = BASE_DIR / "output" / "top_canciones.json"
            if not canciones_path.exists():
                st.info("Primero ejecuta el análisis en **▶ Ejecutar** para generar el listado de canciones.")
            else:
                canciones = json.loads(canciones_path.read_text(encoding="utf-8"))
                results   = _spotify_load_results()
                ledger    = _ledger_load()
                min_seeds = int(cfg.get("min_seeds", 3))

                # ── Biblioteca local + ledger (marcar descargadas) ────────────
                music_folder = cfg.get("music_folder", "")
                lib_keys     = _scan_music_library(music_folder)
                dl_set       = {f"{c['artist']} — {c['track']}" for c in canciones
                                if _is_downloaded(lib_keys, c["artist"], c["track"], ledger)}
                req_set      = {f"{c['artist']} — {c['track']}" for c in canciones
                                if f"{c['artist']} — {c['track']}" not in dl_set
                                and _ledger_status(ledger, c["artist"], c["track"]) == "requested"}

                lib_col1, lib_col2 = st.columns([3, 1])
                lib_col1.caption(
                    f"📂 Biblioteca: `{music_folder}` — "
                    f"{len(lib_keys):,} pistas indexadas"
                    if lib_keys else
                    f"📂 Biblioteca vacía o no encontrada: `{music_folder}` "
                    "(ajusta la carpeta en ⚙️ Configuración)"
                )
                if lib_col2.button("🔄 Re-escanear", use_container_width=True,
                                   key="spo_rescan"):
                    _scan_music_library.clear()
                    st.rerun()

                # ── Métricas ──────────────────────────────────────────────────
                n_total     = len(canciones)
                n_found     = sum(1 for c in canciones
                                  if results.get(f"{c['artist']} — {c['track']}", {}).get("status") == "found")
                n_not_found = sum(1 for c in canciones
                                  if results.get(f"{c['artist']} — {c['track']}", {}).get("status") == "not_found")
                n_pending   = n_total - n_found - n_not_found
                n_dl        = len(dl_set)

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Total canciones", n_total)
                m2.metric("✅ Encontradas",  n_found)
                m3.metric("❌ Sin resultado", n_not_found)
                m4.metric("⏳ Sin buscar",    n_pending)
                m5.metric("⬇️ En biblioteca", n_dl)

                st.markdown("---")

                # ── Botones de acción batch ───────────────────────────────────
                col_b1, col_b2 = st.columns(2)
                run_all    = col_b1.button("🚀 Buscar todas las pendientes",
                                           type="primary",
                                           disabled=(n_pending == 0),
                                           use_container_width=True)
                retry_nf   = col_b2.button("🔄 Re-buscar sin resultado",
                                           disabled=(n_not_found == 0),
                                           use_container_width=True)
                skip_owned = st.checkbox("Omitir las que ya tengo en la biblioteca",
                                         value=True, key="spo_skip_owned")

                if run_all or retry_nf:
                    to_search = [
                        c for c in canciones
                        if ((run_all and f"{c['artist']} — {c['track']}" not in results)
                            or (retry_nf and results.get(f"{c['artist']} — {c['track']}", {}).get("status") == "not_found"))
                        and not (skip_owned and f"{c['artist']} — {c['track']}" in dl_set)
                    ]
                    prog_bar  = st.progress(0.0)
                    prog_text = st.empty()
                    total_s   = len(to_search)
                    done = 0
                    for c, res in _parallel_searches(to_search, min_seeds=min_seeds):
                        label = f"{c['artist']} — {c['track']}"
                        results[label] = res
                        if res.get("status") == "found":
                            _download_and_record(c["artist"], c["track"], res)
                        done += 1
                        prog_bar.progress(done / total_s)
                        prog_text.text(f"Buscando {done}/{total_s}: {label}…")
                        if done % 10 == 0:
                            _spotify_save_results(results)
                    _spotify_save_results(results)
                    prog_text.success(f"✅ Listo — {total_s} canciones buscadas.")
                    st.rerun()

                st.markdown("---")

                # ── Filtro ────────────────────────────────────────────────────
                filtro = st.radio(
                    "Filtrar",
                    ["Todas", "✅ Encontradas", "❌ Sin resultado", "⏳ Sin buscar",
                     "⬇️ Descargadas", "📥 Faltantes"],
                    horizontal=True,
                    key="spo_filtro",
                )

                def _filtrar(c):
                    key    = f"{c['artist']} — {c['track']}"
                    status = results.get(key, {}).get("status")
                    if filtro == "✅ Encontradas":   return status == "found"
                    if filtro == "❌ Sin resultado":  return status == "not_found"
                    if filtro == "⏳ Sin buscar":     return status is None
                    if filtro == "⬇️ Descargadas":   return key in dl_set
                    if filtro == "📥 Faltantes":     return key not in dl_set
                    return True

                visible = [c for c in canciones if _filtrar(c)]
                st.caption(f"{len(visible)} canciones")

                # Mostrar máximo 100 filas para no sobrecargar el render
                MAX_ROWS = 100
                if len(visible) > MAX_ROWS:
                    st.info(f"Mostrando las primeras {MAX_ROWS} de {len(visible)}. Usa el filtro para ver el resto.")
                    visible = visible[:MAX_ROWS]

                # ── Filas de canciones ────────────────────────────────────────
                for i, c in enumerate(visible):
                    cache_key   = f"{c['artist']} — {c['track']}"
                    res         = results.get(cache_key, {})
                    status      = res.get("status")
                    plays       = c.get("plays", 0)
                    downloaded  = cache_key in dl_set
                    requested   = cache_key in req_set

                    with st.container(border=True):
                        col_info, col_status, col_action = st.columns([4, 2, 2])

                        with col_info:
                            dl_badge = (" &nbsp;⬇️ **En biblioteca**" if downloaded else
                                        " &nbsp;⬇️ *Pedida*" if requested else "")
                            st.markdown(f"**{c['artist']}** — {c['track']}{dl_badge}",
                                        unsafe_allow_html=True)
                            album = res.get("album", "")
                            year  = res.get("year", "")
                            meta_bits = [f"🔁 {plays} plays"]
                            if album:
                                meta_bits.append(f"💿 {album}" + (f" ({year})" if year else ""))
                            st.caption(" · ".join(meta_bits))
                            _song_preview_ui(c["artist"], c["track"], f"spo_{i}")

                        with col_status:
                            if downloaded:
                                st.caption("⬇️ Ya descargada")
                            elif requested:
                                st.caption("⬇️ Pedida (bajando)")
                            if status == "found" and not downloaded:
                                name_t = res.get("name", "")[:60]
                                seeds  = res.get("seeds", 0)
                                size   = res.get("size", "?")
                                src    = res.get("source", "")
                                seed_icon = "🟢" if seeds >= 20 else ("🟡" if seeds >= 5 else "🔴")
                                st.caption(f"✅ {name_t}")
                                warn = " · ⚠️ pocos seeds" if res.get("low_seeds") else ""
                                src_tag = f" · {src}" if src else ""
                                st.caption(f"{seed_icon} {seeds} seeds · {size}{src_tag}{warn}")
                            elif status == "not_found" and not downloaded and not requested:
                                st.caption("❌ Sin resultado")
                            elif not downloaded and not requested:
                                st.caption("⏳ Sin buscar")

                        with col_action:
                            if downloaded:
                                pass
                            elif status == "found":
                                if st.button("🧲 Descargar", key=f"spo_dl_{i}",
                                             use_container_width=True):
                                    _download_and_record(c["artist"], c["track"], res)
                                    st.rerun()
                            else:
                                btn_label = "🔄 Reintentar" if status == "not_found" else "🔍 Buscar"
                                if st.button(btn_label, key=f"spo_search_{i}",
                                             use_container_width=True):
                                    with st.spinner(f"Buscando {c['artist']} — {c['track']}…"):
                                        results[cache_key] = _search_song_torrent(
                                            c["artist"], c["track"], min_seeds=min_seeds)
                                        _spotify_save_results(results)
                                        if results[cache_key].get("status") == "found":
                                            _download_and_record(c["artist"], c["track"],
                                                                 results[cache_key])
                                    st.rerun()


def page_phone():
    _page_header("🧹", "Limpiar duplicados", "Elimina MP3s repetidos directamente en tu biblioteca")
    cfg = load_config()

    source_folder = st.text_input("📁 Carpeta de música (tus MP3s)", value=cfg["music_folder"])
    source_path   = Path(source_folder)

    # ── Métricas rápidas ──────────────────────────────────────────────────────
    st.markdown("---")
    analysis_path = source_path / "_dedup_analysis.json"
    last_report   = None
    if analysis_path.exists():
        try:
            with open(analysis_path) as f:
                last_report = json.load(f)
        except Exception:
            pass

    if source_path.exists():
        mp3s = list(source_path.rglob("*.mp3"))
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("🎵 MP3s en biblioteca", f"{len(mp3s):,}")
        if last_report:
            col_b.metric("✅ Canciones únicas",      f"{last_report.get('unique', 0):,}")
            col_c.metric("🗑️ Duplicados detectados", f"{last_report.get('duplicates_removed', 0):,}")
            freed = last_report.get("freed_mb", 0)
            freed_str = f"{freed/1024:.2f} GB" if freed > 1024 else f"{freed:.0f} MB"
            col_d.metric("💾 Espacio a liberar", freed_str if freed else "—")
        else:
            col_b.metric("✅ Únicas", "—")
            col_c.metric("🗑️ Duplicados", "—")
            col_d.metric("💾 Por liberar", "—")
    else:
        st.warning("⚠️ La carpeta no existe. Verifica la ruta en ⚙️ Configuración.")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_run, tab_dups, tab_export, tab_meta, tab_m3u = st.tabs([
        "🧹 Limpiar duplicados",
        "🔁 Lista de duplicados",
        "📦 Exportar a carpeta",
        "🏷️ Metadata & Portadas",
        "🎼 Playlist .m3u",
    ])

    script = BASE_DIR / "scripts" / "dedup_music.py"

    # ════════════════════════════════════════════════════════════════════════
    # Tab Playlist — exportar .m3u8 de la biblioteca (F4)
    # ════════════════════════════════════════════════════════════════════════
    with tab_m3u:
        st.markdown("Genera una **playlist `.m3u8`** con toda tu música — "
                    "compatible con VLC, reproductores y tu móvil.")
        if st.button("🎼 Generar playlist", type="primary", key="m3u_gen"):
            if not source_path.exists():
                st.error("La carpeta no existe.")
            else:
                status, log = st.empty(), st.empty()
                status.info("🎼 Generando playlist…")
                out = source_path / "playlist.m3u8"
                cmd = [PYTHON, "-u", str(BASE_DIR / "scripts" / "export_m3u.py"),
                       source_folder, "--out", str(out)]
                ok = stream_script(cmd, log, status)
                if ok and out.exists():
                    status.success(f"✅ Playlist generada: {out}")
                    st.download_button("⬇️ Descargar playlist.m3u8",
                                       data=out.read_bytes(),
                                       file_name="playlist.m3u8", mime="audio/x-mpegurl")
                else:
                    status.error("❌ Error al generar la playlist")

    # ════════════════════════════════════════════════════════════════════════
    # Tab Metadata — arreglar tags y portada de la biblioteca (Componente 2)
    # ════════════════════════════════════════════════════════════════════════
    with tab_meta:
        st.markdown("""
        <div style="background:rgba(120,80,255,0.08);border:1px solid rgba(120,80,255,0.2);
                    border-radius:12px;padding:16px 20px;margin-bottom:16px;">
            <div style="color:#c4b5fd;font-weight:700;margin-bottom:6px;">¿Qué hace?</div>
            <div style="color:#8888b0;font-size:0.9rem;line-height:1.6;">
                Escanea tu carpeta de música y, en los archivos con
                <strong style="color:#e2e2f0;">tags incompletos o sin portada</strong>,
                escribe artista/título/álbum/año/género y embebe la carátula usando
                <strong style="color:#e2e2f0;">Shazam</strong>. También marca como
                descargadas las canciones que pediste desde mediahub. No mueve ni borra
                archivos. Formatos: MP3, FLAC, M4A.
            </div>
        </div>
        """, unsafe_allow_html=True)

        tag_script = BASE_DIR / "scripts" / "tag_music.py"
        col_md1, col_md2 = st.columns(2)
        with col_md1:
            if st.button("🔍 Analizar (sin escribir)", use_container_width=True,
                         key="meta_dry"):
                if not source_path.exists():
                    st.error("La carpeta no existe.")
                else:
                    cfg["music_folder"] = source_folder
                    save_config(cfg)
                    status, log = st.empty(), st.empty()
                    status.info("🔍 Analizando metadata...")
                    cmd = [PYTHON, "-u", str(tag_script), source_folder, "--dry-run"]
                    ok = stream_script(cmd, log, status)
                    status.success("✅ Análisis listo.") if ok else status.error("❌ Error")
        with col_md2:
            confirm_meta = st.checkbox("✅ Confirmo escribir tags/portadas en mis archivos",
                                       key="meta_confirm")
            if st.button("🏷️ Arreglar metadata", type="primary",
                         use_container_width=True, disabled=not confirm_meta,
                         key="meta_run"):
                if not source_path.exists():
                    st.error("La carpeta no existe.")
                else:
                    cfg["music_folder"] = source_folder
                    save_config(cfg)
                    status, log = st.empty(), st.empty()
                    status.warning("🏷️ Escribiendo tags y portadas...")
                    cmd = [PYTHON, "-u", str(tag_script), source_folder]
                    ok = stream_script(cmd, log, status)
                    if ok:
                        status.success("✅ ¡Metadata arreglada!")
                        _scan_music_library.clear()
                    else:
                        status.error("❌ Terminó con errores")

    # ════════════════════════════════════════════════════════════════════════
    # Tab 1 — Borrar duplicados en lugar
    # ════════════════════════════════════════════════════════════════════════
    with tab_run:
        st.markdown("""
        <div style="background:rgba(120,80,255,0.08);border:1px solid rgba(120,80,255,0.2);
                    border-radius:12px;padding:16px 20px;margin-bottom:16px;">
            <div style="color:#c4b5fd;font-weight:700;margin-bottom:6px;">¿Qué hace?</div>
            <div style="color:#8888b0;font-size:0.9rem;line-height:1.6;">
                Escanea tu carpeta de música, detecta canciones repetidas y
                <strong style="color:#e2e2f0;">borra los duplicados directamente</strong>
                conservando siempre el archivo de mayor tamaño (mejor calidad).
                No crea carpetas nuevas ni copia nada — solo limpia los sobrantes.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("**Flujo recomendado:** primero *Analizar* → revisar la lista → luego *Borrar*.")

        col_dry, col_del = st.columns(2)

        with col_dry:
            if st.button("🔍 Analizar (sin borrar nada)", use_container_width=True):
                if not source_path.exists():
                    st.error("La carpeta no existe.")
                else:
                    cfg["music_folder"] = source_folder
                    save_config(cfg)
                    status = st.empty()
                    log    = st.empty()
                    status.info("🔍 Analizando — detectando duplicados...")
                    cmd = [PYTHON, "-u", str(script), source_folder, "--delete-dupes", "--dry-run"]
                    ok = stream_script(cmd, log, status)
                    if ok:
                        status.success("✅ Análisis listo. Ve a la pestaña **🔁 Lista de duplicados**.")
                    else:
                        status.error("❌ Error durante el análisis")

        with col_del:
            # Confirmación antes de borrar
            confirmar = st.checkbox(
                "✅ Confirmo que quiero borrar los duplicados de forma permanente",
                key="confirm_delete",
            )
            if st.button("🗑️ Borrar duplicados", type="primary",
                         use_container_width=True, disabled=not confirmar):
                if not source_path.exists():
                    st.error("La carpeta no existe.")
                else:
                    cfg["music_folder"] = source_folder
                    save_config(cfg)
                    status = st.empty()
                    log    = st.empty()
                    status.warning("🗑️ Borrando duplicados — esto es permanente...")
                    cmd = [PYTHON, "-u", str(script), source_folder, "--delete-dupes"]
                    ok = stream_script(cmd, log, status)
                    if ok:
                        status.success("✅ ¡Listo! Los duplicados han sido eliminados.")
                        st.balloons()
                    else:
                        status.error("❌ Terminó con errores")

        st.caption(
            "💡 El criterio de desempate es el **tamaño del archivo** — "
            "cuando hay varios iguales se conserva el más grande (presumiblemente mayor bitrate)."
        )

    # ════════════════════════════════════════════════════════════════════════
    # Tab 2 — Lista de duplicados
    # ════════════════════════════════════════════════════════════════════════
    with tab_dups:
        data = None
        if analysis_path.exists():
            try:
                with open(analysis_path) as f:
                    data = json.load(f)
            except Exception:
                pass

        if not data:
            st.info("Ejecuta primero **🔍 Analizar** para ver la lista de duplicados.")
        else:
            dup_groups = data.get("duplicate_groups", [])
            dry = data.get("dry_run", True)
            freed = data.get("freed_mb", 0)
            freed_str = f"{freed/1024:.2f} GB" if freed > 1024 else f"{freed:.0f} MB"

            estado = "🔵 Análisis (sin borrar)" if dry else "🟢 Limpieza ejecutada"
            st.caption(f"{estado} · {data.get('source', '—')}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Grupos duplicados",    f"{len(dup_groups):,}")
            col2.metric("Ficheros a/borrados",  f"{data.get('duplicates_removed', 0):,}")
            col3.metric("Espacio liberado",      freed_str if freed else "—")

            if dup_groups:
                st.markdown(f"#### 🔁 Duplicados detectados ({len(dup_groups):,} grupos)")
                st.markdown(
                    "La versión con ✅ es la que **se conserva** (mayor tamaño). "
                    "Las marcadas con ✗ son las que se borran."
                )
                search = st.text_input("🔎 Filtrar por nombre",
                                       placeholder="ej: metallica, enter sandman...",
                                       key="dup_search")
                filtered = dup_groups
                if search:
                    q = search.lower()
                    filtered = [g for g in dup_groups
                                if q in g["keep"]["name"].lower()
                                or any(q in d["name"].lower() for d in g["remove"])]

                st.caption(f"Mostrando {min(len(filtered), 200):,} de {len(filtered):,} grupos")

                for g in filtered[:200]:
                    keep   = g["keep"]
                    remove = g["remove"]
                    with st.container():
                        col_k, col_r = st.columns([4, 1])
                        with col_k:
                            st.markdown(f"**🎵 {keep['name'][:70]}**")
                            st.caption(f"  ✅ Conservar: `{keep['name'][:60]}`  —  {keep['size_kb']:,} KB")
                            for d in remove:
                                st.caption(f"  ✗ Borrar:    `{d['name'][:60]}`  —  {d['size_kb']:,} KB")
                        with col_r:
                            saved_kb = sum(d["size_kb"] for d in remove)
                            st.caption(f"−{saved_kb:,} KB")
                        st.divider()

                if len(filtered) > 200:
                    st.caption(f"... y {len(filtered)-200} grupos más (usa el filtro)")
            else:
                st.success("✅ ¡No hay duplicados! Tu biblioteca está limpia.")

    # ════════════════════════════════════════════════════════════════════════
    # Tab 3 — Exportar a carpeta (modo anterior, ahora opcional)
    # ════════════════════════════════════════════════════════════════════════
    with tab_export:
        st.markdown("""
        <div style="background:rgba(96,165,250,0.08);border:1px solid rgba(96,165,250,0.2);
                    border-radius:12px;padding:14px 18px;margin-bottom:16px;">
            <div style="color:#93c5fd;font-weight:700;margin-bottom:4px;">Modo exportar</div>
            <div style="color:#6688aa;font-size:0.88rem;">
                Crea una carpeta nueva con una copia limpia de tu música
                (útil para transferir al celular o hacer backup).
                La carpeta origen no se modifica.
            </div>
        </div>
        """, unsafe_allow_html=True)

        dest_folder = st.text_input("📱 Carpeta destino (copia limpia)", value=cfg["phone_folder"])
        dest_path   = Path(dest_folder)
        spotify_json = BASE_DIR / "output" / "top_artistas.json"

        with st.expander("⚙️ Límite de tamaño", expanded=False):
            st.markdown(
                "Si el destino tiene espacio limitado, activa el límite. "
                "Las canciones se priorizan por **escuchas en Spotify**."
            )
            col_lim1, col_lim2 = st.columns([1, 2])
            with col_lim1:
                use_limit = st.checkbox("Activar límite", value=cfg.get("phone_use_limit", False))
            with col_lim2:
                limit_gb = st.slider("Máximo (GB)", 1, 256,
                                     cfg.get("phone_limit_gb", 32), 1,
                                     disabled=not use_limit)
            if use_limit != cfg.get("phone_use_limit") or limit_gb != cfg.get("phone_limit_gb"):
                cfg["phone_use_limit"] = use_limit
                cfg["phone_limit_gb"]  = limit_gb
                save_config(cfg)
            if use_limit and spotify_json.exists():
                with open(spotify_json) as f:
                    sp = json.load(f)
                st.success(f"✅ Historial Spotify — {len(sp):,} artistas para priorizar.")
            elif use_limit:
                st.warning("Sin historial de Spotify, la prioridad será por tamaño de archivo.")

        def build_export_cmd(dry: bool) -> list:
            cmd = [PYTHON, "-u", str(script), source_folder, dest_folder]
            if dry:
                cmd.append("--dry-run")
            if use_limit and limit_gb:
                cmd += ["--limit-gb", str(limit_gb)]
            if spotify_json.exists():
                cmd += ["--spotify-data", str(spotify_json)]
            return cmd

        col_dry2, col_run2 = st.columns(2)
        with col_dry2:
            if st.button("🔍 Analizar exportación", use_container_width=True, key="exp_dry"):
                if not source_path.exists():
                    st.error("La carpeta origen no existe.")
                else:
                    cfg["phone_folder"] = dest_folder
                    save_config(cfg)
                    status = st.empty(); log = st.empty()
                    status.info("🔍 Analizando...")
                    ok = stream_script(build_export_cmd(dry=True), log, status)
                    if ok:
                        status.success("✅ Análisis listo.")
        with col_run2:
            if st.button("🚀 Exportar copia limpia", type="primary",
                         use_container_width=True, key="exp_run"):
                if not source_path.exists():
                    st.error("La carpeta origen no existe.")
                else:
                    cfg["phone_folder"] = dest_folder
                    save_config(cfg)
                    status = st.empty(); log = st.empty()
                    lim_txt = f" (límite {limit_gb} GB)" if use_limit else ""
                    status.info(f"⏳ Copiando música sin repetidos{lim_txt}...")
                    ok = stream_script(build_export_cmd(dry=False), log, status)
                    if ok:
                        status.success(f"✅ ¡Listo! Carpeta en: {dest_folder}")
                        st.balloons()
                    else:
                        status.error("❌ Terminó con errores")


def page_ayuda():
    _page_header("📖", "Ayuda", "Guía completa de cada sección de la aplicación")

    # ── Inicio ────────────────────────────────────────────────────────────────
    with st.expander("🏠 Inicio", expanded=False):
        st.markdown("""
**¿Qué hace?**
Dashboard principal con accesos directos a todas las secciones y métricas rápidas de tu biblioteca.

**Métricas que muestra:**
- Total de MP3s en tu carpeta de música
- Torrents de música generados
- Torrents de ebooks generados

**Cómo usarlo:**
Haz clic en cualquier botón de sección para navegar directamente a ella.
""")

    # ── Música ────────────────────────────────────────────────────────────────
    with st.expander("🎵 Música — Last.fm → The Pirate Bay", expanded=False):
        st.markdown("""
**¿Qué hace?**
Consulta los charts de **Last.fm** para obtener las canciones más populares globalmente y por género,
luego busca cada una en **The Pirate Bay** y descarga los ficheros `.torrent` listos para uTorrent.

**Flujo interno:**
1. Descarga el top de artistas y canciones globales de Last.fm (chart global)
2. Descarga el top por cada género configurado (rock, pop, metal, latin, etc.)
3. Consolida y deduplica en una lista única ordenada por oyentes
4. Por cada canción busca en TPB con 4 niveles de fallback:
   - Búsqueda exacta `artista canción mp3` (categoría MP3)
   - Búsqueda en todas las categorías
   - Búsqueda del álbum completo en MP3
   - Búsqueda del artista en MP3
5. Descarga el fichero `.torrent` vía `itorrents.org` y `torcache.net`

**Caché anti-duplicados:**
Si ya ejecutaste una búsqueda antes, las canciones ya encontradas se **reutilizan** del fichero
`magnets_lastfm.txt` sin volver a llamar a TPB. Los `.torrent` ya descargados tampoco se vuelven
a descargar.

**Archivos generados:**
| Archivo | Contenido |
|---|---|
| `output/torrents/*.torrent` | Ficheros para importar en uTorrent Web |
| `output/magnets_lastfm.txt` | Magnet links en texto plano |
| `output/reporte_lastfm.txt` | Resumen completo con seeds y tamaños |
| `output/lastfm_top_tracks.json` | JSON con todos los tracks encontrados |

**Configuración:**
- **Número de canciones:** cuántas canciones del top buscar (default 100)
- **Géneros:** qué géneros musicales incluir en la búsqueda
""")

    # ── Ebooks ────────────────────────────────────────────────────────────────
    with st.expander("📚 Ebooks — Libros para Kindle", expanded=False):
        st.markdown("""
**¿Qué hace?**
Genera una lista de los libros más leídos en inglés y español combinando **Open Library** con una
lista curada de clásicos, premios Nobel, Booker, Pulitzer y bestsellers, y busca cada uno en
The Pirate Bay en formatos compatibles con Kindle.

**Fuentes de libros:**
- **Open Library** — trending anual en inglés y búsqueda en español
- **Lista curada** — ~200 títulos: clásicos universales, premios literarios, bestsellers modernos

**Formatos buscados (en orden de preferencia):**
`EPUB` → `MOBI` → `AZW3` → `Kindle`

**Archivos generados:**
| Archivo | Contenido |
|---|---|
| `output_ebooks/torrents/*.torrent` | Ficheros para importar en uTorrent Web |
| `output_ebooks/magnets_ebooks.txt` | Magnet links en texto plano |
| `output_ebooks/utorrent_ebooks.html` | Página web con botones de descarga directa |

**Cómo importar en Kindle:**
1. uTorrent descarga los `.epub` / `.mobi` a tu carpeta de descargas
2. Conecta el Kindle por USB y copia los ficheros, o usa la app **Send to Kindle**

**Configuración:**
- **Número de libros:** total a buscar (mitad en inglés, mitad en español)
""")

    # ── Mi Spotify ────────────────────────────────────────────────────────────
    with st.expander("🟢 Mi Spotify — Tu historial personal", expanded=False):
        st.markdown("""
**¿Qué hace?**
Procesa tu **exportación personal de Spotify** (ZIP de datos de privacidad) para extraer tus
artistas más escuchados y buscar sus discografías completas en The Pirate Bay.

**Cómo obtener tus datos de Spotify:**
1. Ve a [spotify.com/account/privacy](https://www.spotify.com/account/privacy/)
2. Baja hasta *"Descarga tus datos"* → pide el **Historial de reproducción extendido**
3. Recibirás un email con un ZIP en unos días (hasta 30 días)
4. Extrae el ZIP en la carpeta `spotify_data/` del proyecto
5. Ejecuta esta sección

**Qué analiza:**
- Lee todos los ficheros `Streaming_History_Audio_*.json` (busca en subcarpetas automáticamente)
- Cuenta reproducciones por artista y por canción (mínimo 30 segundos para contar)
- Ordena los 50 artistas más escuchados
- Busca la discografía de cada artista en TPB

**Archivos generados:**
| Archivo | Contenido |
|---|---|
| `output/reporte.txt` | Resumen con top canciones y resultados de TPB |
| `output/magnets.txt` | Magnet links de las discografías encontradas |
| `output/top_artistas.json` | Todos tus artistas ordenados por reproducciones |
| `output/top_canciones.json` | Top 200 canciones más escuchadas |

> **Nota:** El fichero `top_artistas.json` también lo usa la sección **🧹 Limpiar duplicados**
> para priorizar qué canciones incluir cuando hay un límite de tamaño.
""")

    # ── Fix Metadata ──────────────────────────────────────────────────────────
    with st.expander("🔧 Fix Metadata — Completar tags de MP3s", expanded=False):
        st.markdown("""
**¿Qué hace?**
Escanea todos los MP3s de tu biblioteca, detecta qué información falta en los tags ID3
(título, artista, álbum, año, género, portada) y la completa automáticamente consultando
bases de datos musicales gratuitas.

**Fuentes de datos:**
- **MusicBrainz** — base de datos de música abierta y gratuita (1 req/segundo, sin key)
- **Last.fm** — para portadas de álbumes y datos adicionales

**Tags que completa:**
| Tag | Campo ID3 |
|---|---|
| Título | TIT2 |
| Artista | TPE1 |
| Álbum | TALB |
| Año | TDRC |
| Género | TCON |
| Portada | APIC (imagen embebida) |

**Modos de ejecución:**
| Modo | Comportamiento |
|---|---|
| **Normal** | Rellena solo los campos vacíos, no toca los que ya tienen datos |
| **Dry Run** | Solo muestra qué cambiaría, sin modificar ningún fichero |
| **Force** | Sobreescribe todos los tags aunque ya existan datos |

**Rendimiento:**
- MusicBrainz tiene límite de 1 petición/segundo → con 3,000 MP3s tarda ~55 minutos
- Se genera un reporte JSON en `_metadata_report.json` dentro de la carpeta de música

**Recomendación:** ejecuta primero en modo **Dry Run** para revisar qué cambiaría.
""")

    # ── Exportar al Móvil ─────────────────────────────────────────────────────
    with st.expander("🧹 Limpiar duplicados — Sin canciones repetidas", expanded=False):
        st.markdown("""
**¿Qué hace?**
Escanea toda tu biblioteca de MP3s, detecta canciones duplicadas y copia una sola versión
de cada canción a una carpeta destino, lista para transferir al celular.

**¿Cómo detecta duplicados?**
1. Lee los tags ID3 de cada MP3 → usa `artista + título` como identidad única
2. Si los tags están vacíos, usa el nombre del fichero como fallback
3. Cuando hay varias copias del mismo tema, **conserva la de mayor tamaño** (= mejor calidad / bitrate)
4. Los ficheros en la carpeta destino se renombran como `Artista - Título.mp3`

**Límite de tamaño con prioridad inteligente:**
Si tu celular o tarjeta SD tiene espacio limitado, puedes activar un límite en GB.
Cuando la biblioteca no cabe completa, las canciones se priorizan por **escuchas en Spotify**
(artistas más escuchados van primero). Para esto se requiere haber ejecutado **Mi Spotify** antes.

**Pestañas:**
| Pestaña | Contenido |
|---|---|
| **▶ Ejecutar** | Botones para analizar (sin copiar) o exportar (con copia) |
| **🔁 Lista de duplicados** | Muestra cada grupo de duplicados con cuál se conserva y cuáles se omiten |
| **📊 Reporte** | Estadísticas de la última exportación y lista de canciones copiadas |

**Archivos generados:**
- `Musica_Movil/` — carpeta con todos los MP3s únicos renombrados
- `Musica_Movil/_dedup_report.json` — reporte detallado con estadísticas
- `_dedup_analysis.json` — resultado del último análisis (dry run)
""")

    # ── Configuración ─────────────────────────────────────────────────────────
    with st.expander("⚙️ Configuración", expanded=False):
        st.markdown("""
**¿Qué configura?**

| Campo | Descripción |
|---|---|
| **Last.fm API Key** | Clave para consultar charts y buscar portadas. Gratis en [last.fm/api](https://www.last.fm/api/account/create) |
| **Carpeta de música** | Ruta donde están tus MP3s descargados (default: `~/Downloads/Musica`) |
| **Carpeta de ebooks** | Ruta de destino para ebooks (default: `~/Downloads/Ebooks`) |
| **Carpeta para el móvil** | Destino de la exportación sin duplicados (default: `~/Downloads/Musica_Movil`) |
| **Límite de tamaño** | GB máximos para la exportación al móvil (se guarda automáticamente) |
| **Canciones top** | Cuántas canciones buscar en Last.fm (10–300) |
| **Géneros** | Géneros musicales a incluir en la búsqueda de Last.fm |
| **Libros a buscar** | Total de libros (mitad inglés / mitad español) |

La configuración se guarda en `config.json` y persiste entre sesiones.
""")

    st.divider()

    # ── Estructura de archivos ─────────────────────────────────────────────────
    st.markdown("### 📁 Estructura de carpetas generadas")
    st.code("""
spotify-export/
├── output/                        ← Resultados de música (Last.fm y Spotify)
│   ├── torrents/                  ← .torrent de canciones (Last.fm)
│   ├── torrents_spotify/          ← .torrent de discografías (Mi Spotify)
│   ├── magnets_lastfm.txt         ← Magnet links de música
│   ├── magnets.txt                ← Magnet links de Spotify
│   ├── reporte_lastfm.txt         ← Reporte de búsqueda Last.fm
│   ├── reporte.txt                ← Reporte de búsqueda Spotify
│   ├── top_artistas.json          ← Tus artistas ordenados por plays
│   └── top_canciones.json         ← Tus top 200 canciones
│
├── output_ebooks/                 ← Resultados de ebooks
│   ├── torrents/                  ← .torrent de libros
│   ├── magnets_ebooks.txt         ← Magnet links de ebooks
│   └── utorrent_ebooks.html       ← Página con botones de descarga
│
├── spotify_data/                  ← ZIP de Spotify extraído aquí
│   └── Spotify Extended Streaming History/
│       └── Streaming_History_Audio_*.json
│
├── scripts/                       ← Scripts internos (no editar)
│   ├── lastfm_export.py
│   ├── ebooks_export.py
│   ├── spotify_export.py
│   ├── fix_metadata.py
│   └── dedup_music.py
│
├── app.py                         ← App principal (Streamlit)
├── iniciar.sh                     ← Script de inicio (doble clic)
└── config.json                    ← Configuración guardada
""", language="")

    # ── Flujo recomendado ──────────────────────────────────────────────────────
    st.markdown("### 🗺️ Flujo recomendado de uso")
    st.markdown("""
```
1. PRIMERA VEZ
   └─ ⚙️ Configuración → verifica carpetas y API Key de Last.fm

2. DESCARGAR MÚSICA
   ├─ 🎵 Música → busca top Last.fm por géneros → importa .torrent en uTorrent
   └─ 🟢 Mi Spotify (si tienes el ZIP) → busca tus artistas favoritos

3. ORGANIZAR BIBLIOTECA
   └─ 🔧 Fix Metadata → completa tags y portadas de todos los MP3s

4. EXPORTAR AL CELULAR
   ├─ 🧹 Limpiar duplicados → Analizar (dry run) → ver duplicados
   └─ 🧹 Limpiar duplicados → Exportar → copiar carpeta al celular
```
""")

    # ── Solución de problemas ──────────────────────────────────────────────────
    st.markdown("### ❓ Solución de problemas frecuentes")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
**Los torrents no descargan (sin seeds)**
→ Normal en torrents antiguos. Busca manualmente en [thepiratebay.org](https://thepiratebay.org)
o usa el magnet link del reporte como alternativa.

**Fix Metadata es muy lento**
→ MusicBrainz tiene límite de 1 req/segundo. No se puede acelerar sin riesgo de bloqueo.
Con 3,000 MP3s tarda ~55 minutos.

**La app no abre el navegador**
→ Abre manualmente: [http://localhost:8501](http://localhost:8501)

**Error "port already in use"**
→ Ejecuta en terminal:
```bash
pkill -f "streamlit run"
bash iniciar.sh
```
""")

    with col2:
        st.markdown("""
**Los ebooks no aparecen en el Kindle**
→ Transfiere los `.epub` / `.mobi` por cable USB o usa la app **Send to Kindle**.

**No encuentro mi ZIP de Spotify**
→ Puede tardar hasta 30 días. Spotify envía un email cuando está listo.
Extrae el ZIP en la carpeta `spotify_data/` del proyecto.

**Duplicados no detectados correctamente**
→ Ocurre cuando los MP3s no tienen tags ID3 y el nombre del fichero no sigue
el formato `Artista - Título`. Ejecuta **Fix Metadata** primero para completar los tags,
luego vuelve a exportar.

**La búsqueda en Last.fm no termina**
→ Verifica que la API Key es correcta en ⚙️ Configuración.
Puedes obtener una gratis en [last.fm/api](https://www.last.fm/api/account/create).
""")


def _test_lastfm_key(key: str) -> tuple[bool, str]:
    try:
        url = (f"https://ws.audioscrobbler.com/2.0/?method=chart.gettoptracks"
               f"&api_key={key}&format=json&limit=1")
        req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq_mod.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        if "error" in data:
            return False, data.get("message", "Key inválida")
        return True, "Conectado correctamente"
    except Exception as e:
        return False, str(e)

def _test_tmdb_key(key: str) -> tuple[bool, str]:
    try:
        url = f"https://api.themoviedb.org/3/movie/popular?api_key={key}&page=1"
        req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq_mod.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        if "results" in data:
            return True, f"Conectado · {data.get('total_results', '?')} películas disponibles"
        return False, data.get("status_message", "Key inválida")
    except Exception as e:
        return False, str(e)

def page_config():
    _page_header("⚙️", "Configuración", "API keys, rutas y preferencias globales")
    cfg = load_config()

    st.markdown("### 🔑 APIs")

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        lastfm_key = st.text_input("Last.fm API Key", value=cfg["lastfm_api_key"], type="password")
    with col2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("Probar", key="test_lastfm", use_container_width=True):
            ok, msg = _test_lastfm_key(lastfm_key)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"✗ {msg}")
    with col3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.markdown("🔗 [Obtener key](https://www.last.fm/api/account/create)")

    col4, col5, col6 = st.columns([3, 1, 1])
    with col4:
        tmdb_key = st.text_input("TMDB API Key (películas)", value=cfg.get("tmdb_api_key", ""),
                                 type="password",
                                 help="Necesaria para la sección 🎬 Películas")
    with col5:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("Probar", key="test_tmdb", use_container_width=True):
            ok, msg = _test_tmdb_key(tmdb_key)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"✗ {msg}")
    with col6:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.markdown("🔗 [Obtener key](https://www.themoviedb.org/settings/api)")

    col7, col8 = st.columns([3, 2])
    with col7:
        opensubs_key = st.text_input("OpenSubtitles API Key (subtítulos)",
                                     value=cfg.get("opensubtitles_api_key", ""),
                                     type="password",
                                     help="Opcional — habilita la búsqueda de subtítulos en la API de OpenSubtitles. Sin key, solo se muestran los enlaces a fuentes alternativas.")
    with col8:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.markdown("🔗 [Obtener key](https://www.opensubtitles.com/es/consumers)")

    st.markdown("### 📁 Carpetas")
    music_folder  = st.text_input("Carpeta de música (MP3s)", value=cfg["music_folder"])
    ebooks_folder = st.text_input("Carpeta de ebooks", value=cfg["ebooks_folder"])
    movies_folder = st.text_input("Carpeta de películas", value=cfg.get("movies_folder", str(Path.home() / "Downloads" / "Peliculas")))
    phone_folder  = st.text_input("Carpeta para el móvil (sin duplicados)", value=cfg.get("phone_folder", str(Path.home() / "Downloads" / "Musica_Movil")))
    col_ph1, col_ph2 = st.columns([1, 2])
    with col_ph1:
        phone_use_limit = st.checkbox("Activar límite de tamaño para el móvil",
                                      value=cfg.get("phone_use_limit", False))
    with col_ph2:
        phone_limit_gb = st.slider("Límite (GB)", 1, 256,
                                   cfg.get("phone_limit_gb", 32), 1,
                                   disabled=not phone_use_limit)

    st.markdown("### 🎵 Preferencias de música")
    top_tracks = st.slider("Canciones top a buscar", 10, 300, cfg["top_tracks"], 10)
    min_seeds  = st.slider(
        "Seeds mínimos para un torrent sano", 0, 30, int(cfg.get("min_seeds", 3)),
        help="Las búsquedas descartan torrents por debajo de este número de seeds "
             "(los que abren pero no completan). Si ninguno llega, se marca ⚠️ pocos seeds.",
    )

    genres_all = [
        "rock", "pop", "electronic", "hip-hop", "jazz", "metal",
        "classical", "reggae", "latin", "blues", "soul", "punk",
        "indie", "alternative", "r&b", "country", "folk",
    ]
    genres = st.multiselect("Géneros activos", genres_all, default=cfg.get("genres", genres_all[:10]))

    st.markdown("### 📚 Preferencias de ebooks")
    top_books = st.slider("Libros a buscar", 20, 300, cfg["top_books"], 10)

    st.markdown("### 🧲 qBittorrent (opcional)")
    st.caption("Si lo configuras, los magnets se envían a qBittorrent vía su WebUI "
               "(Ajustes → Web UI) en vez de abrirse en el cliente del SO.")
    qbit_url  = st.text_input("URL WebUI", value=cfg.get("qbit_url", ""),
                              placeholder="http://localhost:8080")
    qcol1, qcol2 = st.columns(2)
    with qcol1:
        qbit_user = st.text_input("Usuario", value=cfg.get("qbit_user", "admin"))
    with qcol2:
        qbit_pass = st.text_input("Contraseña", value=cfg.get("qbit_pass", ""),
                                  type="password")
    use_qbit = st.toggle("Enviar magnets a qBittorrent", value=cfg.get("use_qbit", False))

    st.markdown("---")
    if st.button("💾 Guardar configuración", type="primary"):
        new_cfg = {
            **cfg,
            "qbit_url":  qbit_url.strip(),
            "qbit_user": qbit_user.strip(),
            "qbit_pass": qbit_pass,
            "use_qbit":  use_qbit,
            "lastfm_api_key": lastfm_key,
            "tmdb_api_key":   tmdb_key,
            "opensubtitles_api_key": opensubs_key,
            "music_folder":   music_folder,
            "ebooks_folder":  ebooks_folder,
            "movies_folder":  movies_folder,
            "phone_folder":      phone_folder,
            "phone_use_limit":   phone_use_limit,
            "phone_limit_gb":    phone_limit_gb,
            "top_tracks":     top_tracks,
            "top_books":      top_books,
            "min_seeds":      min_seeds,
            "genres":         genres,
        }
        save_config(new_cfg)
        st.success("✅ Configuración guardada")


def page_peliculas():
    import urllib.request, urllib.parse, json as _json, re as _re, time as _time

    _page_header("🎬", "Películas", "Descarga en español latino · TMDB + The Pirate Bay + YTS")
    cfg = load_config()

    # ── Importar helpers del script ───────────────────────────────────────────
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        from movies_export import (
            tmdb_discover, tmdb_search, tmdb_popular, tmdb_trending,
            find_movie_torrents, find_movie_torrents_combined,
            yts_search, solidtorrents_search, knaben_search, GENRE_IDS, _format_movie,
        )
        MOVIES_OK = True
    except Exception as e:
        st.error(f"Error cargando módulo de películas: {e}")
        MOVIES_OK = False
        return

    # ── TMDB API key ──────────────────────────────────────────────────────────
    tmdb_key = cfg.get("tmdb_api_key", "").strip()
    if not tmdb_key:
        st.markdown("""
        <div style="background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.35);
                    border-radius:14px;padding:22px 24px;margin-bottom:20px;">
            <div style="color:#fcd34d;font-weight:700;font-size:1.05rem;margin-bottom:10px;">
                🔑 Se necesita una API Key de TMDB
            </div>
            <div style="color:#a89060;line-height:1.7;font-size:0.9rem;">
                TMDB (The Movie Database) es gratis y tarda menos de 2 minutos en registrarse.<br>
                <strong style="color:#fcd34d;">1.</strong> Ve a
                <a href="https://www.themoviedb.org/signup" target="_blank"
                   style="color:#60a5fa;">themoviedb.org/signup</a> y crea tu cuenta.<br>
                <strong style="color:#fcd34d;">2.</strong> En tu perfil →
                <a href="https://www.themoviedb.org/settings/api" target="_blank"
                   style="color:#60a5fa;">Configuración → API</a> → solicita una API key (tipo <em>Developer</em>).<br>
                <strong style="color:#fcd34d;">3.</strong> Pega la key en
                <strong>⚙️ Configuración → TMDB API Key</strong> y guarda.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Configuración →", type="primary"):
            st.session_state.page = "⚙️ Configuración"
            st.rerun()
        return

    # Feature #11: cached TMDB calls
    @st.cache_data(ttl=600, show_spinner=False)
    def _tmdb_search_c(key, q, year=None):
        return tmdb_search(key, q, year=year)

    @st.cache_data(ttl=600, show_spinner=False)
    def _tmdb_discover_c(key, y_gte, y_lte, genre_id=None, limit=40, sort_by="popularity.desc"):
        return tmdb_discover(key, y_gte, y_lte, genre_id=genre_id, limit=limit, sort_by=sort_by)

    @st.cache_data(ttl=300, show_spinner=False)
    def _tmdb_popular_c(key, limit=40):
        return tmdb_popular(key, limit=limit)

    @st.cache_data(ttl=300, show_spinner=False)
    def _tmdb_trending_c(key, limit=40):
        return tmdb_trending(key, limit=limit)

    @st.cache_data(ttl=600, show_spinner=False)
    def _yts_top_c(quality, genre, min_rating, sort_label, limit, page):
        sort_map = {
            "🌱 Más seeds":       "seeds",
            "⬇️ Más descargadas": "download_count",
            "⭐ Mejor rating":    "rating",
            "📅 Más recientes":   "year",
        }
        params = {
            "sort_by":       sort_map.get(sort_label, "seeds"),
            "order_by":      "desc",
            "limit":         limit,
            "page":          page,
            "minimum_rating": min_rating,
        }
        if quality != "Todas":
            params["quality"] = {"4K": "2160p"}.get(quality, quality)
        if genre != "Todos":
            params["genre"] = genre
        url = "https://yts.mx/api/v2/list_movies.json?" + _uparse_mod.urlencode(params)
        try:
            req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0 MediaHub/1.0"})
            with _ureq_mod.urlopen(req, timeout=12) as r:
                data = json.loads(r.read())
            if data.get("status") != "ok":
                return []
            return (data.get("data") or {}).get("movies") or []
        except Exception:
            return []

    @st.cache_data(ttl=1800, show_spinner=False)
    def _tmdb_cult_c(key, extra_params_str, limit=40):
        import json as _j
        ep = _j.loads(extra_params_str)
        return tmdb_discover(key, sort_by="vote_average.desc", limit=limit, extra_params=ep)

    # ─── Subgéneros de culto ───────────────────────────────────────────────────
    # CULT_SUBGENRES: cada entrada usa with_keywords para géneros amplios que
    # incluyen blockbusters, o popularity.lte para géneros inherentemente de culto.
    CULT_SUBGENRES = [
        {
            "name": "Neo-Noir",        "icon": "🌆",
            "desc": "Crimen, sombras y antihéroes",
            "extra": {"with_genres": "80,18",
                      "with_keywords": "9715|9816|10349",
                      "vote_average.gte": "6.5",
                      "vote_count.gte": "100",
                      "primary_release_date.gte": "1960-01-01",
                      "primary_release_date.lte": "2005-12-31"},
        },
        {
            "name": "J-Horror",        "icon": "👹",
            "desc": "Terror japonés: Ringu, Juon, Audition",
            # Género inherentemente de culto — popularity cap en lugar de keyword
            "extra": {"with_genres": "27", "with_original_language": "ja",
                      "vote_count.gte": "50",
                      "popularity.lte": "40",
                      "primary_release_date.gte": "1988-01-01",
                      "primary_release_date.lte": "2015-12-31"},
        },
        {
            "name": "Slasher Clásico", "icon": "🔪",
            "desc": "Terror slasher de los 70s y 80s",
            # Género inherentemente de culto
            "extra": {"with_genres": "27",
                      "vote_count.gte": "50",
                      "popularity.lte": "50",
                      "primary_release_date.gte": "1974-01-01",
                      "primary_release_date.lte": "1993-12-31"},
        },
        {
            "name": "Sci-Fi Culto",    "icon": "🚀",
            "desc": "2001, Soylent Green, Dark Star — no Star Wars ni E.T.",
            "extra": {"with_genres": "878",
                      "with_keywords": "9715|9816|10349",
                      "vote_average.gte": "6.0",
                      "vote_count.gte": "80",
                      "primary_release_date.gte": "1950-01-01",
                      "primary_release_date.lte": "1995-12-31"},
        },
        {
            "name": "Spaghetti Western", "icon": "🤠",
            "desc": "Leone, Corbucci, Django, Trinità",
            # Género inherentemente de culto
            "extra": {"with_genres": "37",
                      "vote_count.gte": "30",
                      "popularity.lte": "35",
                      "primary_release_date.gte": "1960-01-01",
                      "primary_release_date.lte": "1980-12-31"},
        },
        {
            "name": "Post-Apocalíptico", "icon": "☢️",
            "desc": "Road Warrior, Escape de NY, Damnation Alley",
            "extra": {"with_genres": "878,28",
                      "with_keywords": "9715|9816|10349",
                      "vote_count.gte": "50",
                      "primary_release_date.gte": "1975-01-01",
                      "primary_release_date.lte": "2005-12-31"},
        },
        {
            "name": "Cyberpunk",       "icon": "💻",
            "desc": "Blade Runner, Ghost in the Shell, Johnny Mnemonic",
            "extra": {"with_genres": "878,53",
                      "with_keywords": "9715|9816|9882",   # 9882 = cyberpunk
                      "vote_count.gte": "50",
                      "primary_release_date.gte": "1980-01-01",
                      "primary_release_date.lte": "2010-12-31"},
        },
        {
            "name": "Kung Fu / Artes Marciales", "icon": "🥋",
            "desc": "Shaw Brothers, Bruce Lee, Jackie Chan clásico",
            # Inherentemente de culto para audiencia occidental
            "extra": {"with_genres": "28", "with_original_language": "zh",
                      "vote_count.gte": "20",
                      "popularity.lte": "30",
                      "primary_release_date.gte": "1965-01-01",
                      "primary_release_date.lte": "1998-12-31"},
        },
        {
            "name": "Giallo / Terror Italiano", "icon": "🔴",
            "desc": "Argento, Bava, Fulci",
            # Inherentemente de culto
            "extra": {"with_genres": "27,53", "with_original_language": "it",
                      "vote_count.gte": "20",
                      "popularity.lte": "30",
                      "primary_release_date.gte": "1960-01-01",
                      "primary_release_date.lte": "1990-12-31"},
        },
        {
            "name": "Anime Culto",     "icon": "🎌",
            "desc": "Otomo, Oshii, Satoshi Kon, Madhouse",
            "extra": {"with_genres": "16", "with_original_language": "ja",
                      "with_keywords": "9715|9816",
                      "vote_average.gte": "6.5",
                      "vote_count.gte": "80"},
        },
        {
            "name": "Exploitation",    "icon": "🎞️",
            "desc": "Blaxploitation, Grindhouse, drive-in de los 70s",
            "extra": {"with_genres": "28,80",
                      "with_keywords": "9715|9816|10349",
                      "vote_count.gte": "20",
                      "primary_release_date.gte": "1966-01-01",
                      "primary_release_date.lte": "1985-12-31"},
        },
        {
            "name": "Peplum / Espadas & Brujería", "icon": "⚔️",
            "desc": "Conan, gladiadores italianos, mitología clásica",
            "extra": {"with_genres": "28,12,14",
                      "with_keywords": "9715|9816|10349",
                      "vote_count.gte": "20",
                      "primary_release_date.gte": "1950-01-01",
                      "primary_release_date.lte": "1990-12-31"},
        },
        {
            "name": "Horror Ochentero", "icon": "🎃",
            "desc": "Criaturas, gore y VHS de los 80s",
            "extra": {"with_genres": "27",
                      "with_keywords": "9715|9816|10349",
                      "vote_count.gte": "30",
                      "primary_release_date.gte": "1980-01-01",
                      "primary_release_date.lte": "1989-12-31"},
        },
        {
            "name": "New Wave Francesa", "icon": "🎬",
            "desc": "Godard, Truffaut, Rohmer, Varda",
            "extra": {"with_original_language": "fr",
                      "with_genres": "18",
                      "vote_count.gte": "30",
                      "popularity.lte": "25",
                      "primary_release_date.gte": "1958-01-01",
                      "primary_release_date.lte": "1980-12-31"},
        },
    ]

    # ─── Tabs principales ─────────────────────────────────────────────────────
    (tab_top, tab_buscar, tab_decadas, tab_culto, tab_yt, tab_rename_mov,
     tab_resultados, tab_watchlist, tab_subs) = st.tabs([
        "📥 Top Descargas",
        "🔎 Buscar película",
        "📅 Explorar por época / género",
        "🎭 Cine de Culto",
        "🎬 YouTube",
        "✏️ Renombrar archivos",
        "📂 Resultados guardados",
        "⭐ Watchlist",
        "💬 Subtítulos",
    ])

    movies_dir = BASE_DIR / "output" / "movies"
    movies_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB YouTube — descargar video/película de YouTube como MP4
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_yt:
        st.markdown(
            "Busca (o pega un enlace de) **YouTube** y descarga el video como **MP4** "
            "a tu carpeta de películas."
        )
        st.caption("⚠️ Solo contenido de libre acceso. Las películas de pago/renta "
                   "(YouTube Movies) o con DRM no se pueden descargar.")
        yt_script = BASE_DIR / "scripts" / "youtube_dl.py"
        if not _youtube_deps_ok():
            st.warning("Faltan dependencias. Instala con `brew install yt-dlp ffmpeg` "
                       "y recarga la página.")
        else:
            ytv_dest = st.text_input(
                "📁 Carpeta destino",
                value=cfg.get("movies_folder", str(Path.home() / "Downloads" / "Peliculas")),
                key="ytv_dest")
            quality_map = {"720p": 720, "1080p": 1080, "Máxima disponible": 0}
            qc1, qc2 = st.columns([3, 1])
            with qc1:
                ytv_query = st.text_input(
                    "Buscar en YouTube o pegar URL",
                    placeholder="ej: nombre de la película  ·  o https://youtube.com/watch?v=…",
                    key="ytv_query", label_visibility="collapsed")
            with qc2:
                ytv_quality = st.selectbox("Calidad", list(quality_map.keys()),
                                           index=1, key="ytv_quality")

            def _ytv_download(url):
                if not ytv_dest or not Path(ytv_dest).parent.exists():
                    st.error("Carpeta destino inválida.")
                    return
                status, log = st.empty(), st.empty()
                status.info("⬇️ Descargando video… (puede tardar según tamaño)")
                cmd = [PYTHON, "-u", str(yt_script), "video", url,
                       "--dest", ytv_dest,
                       "--max-height", str(quality_map[ytv_quality])]
                ok = stream_script(cmd, log, status)
                status.success("✅ ¡Video descargado!") if ok else \
                    status.error("❌ Error (¿contenido con DRM/pago o no disponible?)")

            is_url = ytv_query.strip().startswith("http")
            cbtn1, cbtn2 = st.columns(2)
            if is_url:
                if cbtn1.button("⬇️ Descargar de este URL", type="primary",
                                use_container_width=True, key="ytv_url_dl"):
                    _ytv_download(ytv_query.strip())
            else:
                if cbtn1.button("🔍 Buscar", use_container_width=True,
                                key="ytv_search", disabled=not ytv_query):
                    st.session_state["ytv_results"] = _youtube_search(ytv_query, 8)

            for j, r in enumerate(st.session_state.get("ytv_results", []) if not is_url else []):
                vid = r.get("id", "")
                with st.container(border=True):
                    ri, rn, ra = st.columns([1, 4, 2])
                    with ri:
                        if vid:
                            st.image(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                                     use_container_width=True)
                    with rn:
                        st.markdown(f"**{r.get('title','')[:80]}**")
                        st.caption(f"📺 {r.get('uploader','')}  ·  "
                                   f"⏱️ {_fmt_duration(r.get('duration'))}")
                        po = st.session_state.setdefault("_ytv_preview_open", set())
                        if st.button("▶️ Ver", key=f"ytv_prev_{j}"):
                            po.symmetric_difference_update({vid})
                        if vid in po:
                            st.video(f"https://www.youtube.com/watch?v={vid}")
                    with ra:
                        if st.button("⬇️ Descargar MP4", key=f"ytv_dl_{j}",
                                     type="primary", use_container_width=True):
                            _ytv_download(f"https://www.youtube.com/watch?v={vid}")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 0 — Top Descargas (YTS)
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_top:
        st.markdown(
            "Películas con **más seeds activos ahora mismo** en YTS — "
            "la fuente con mejor calidad BluRay/WEB-DL. "
            "Filtra por calidad, género y rating."
        )

        YTS_GENRES = [
            "Todos", "Action", "Adventure", "Animation", "Biography", "Comedy",
            "Crime", "Documentary", "Drama", "Fantasy", "History", "Horror",
            "Music", "Mystery", "Romance", "Sci-Fi", "Thriller", "War", "Western",
        ]

        col_q, col_g, col_r, col_s = st.columns(4)
        with col_q:
            top_quality = st.selectbox(
                "Calidad", ["1080p", "4K", "720p", "Todas"],
                key="top_dl_q",
                help="1080p recomendado — mejor relación tamaño/calidad.",
            )
        with col_g:
            top_genre = st.selectbox("Género", YTS_GENRES, key="top_dl_genre")
        with col_r:
            top_rating = st.slider("Rating mínimo ⭐", 0, 9, 6, key="top_dl_rating")
        with col_s:
            top_sort = st.selectbox(
                "Ordenar por",
                ["🌱 Más seeds", "⬇️ Más descargadas", "⭐ Mejor rating", "📅 Más recientes"],
                key="top_dl_sort",
            )

        col_lim, col_pg = st.columns(2)
        with col_lim:
            top_limit = st.select_slider("Películas por página", [10, 20, 30, 50], value=20, key="top_dl_limit")
        with col_pg:
            top_page = st.number_input("Página", 1, 50, 1, key="top_dl_page")

        col_load, col_ref = st.columns([3, 1])
        with col_load:
            load_top = st.button("📥 Cargar Top", type="primary", use_container_width=True, key="top_dl_btn")
        with col_ref:
            if st.button("🔄 Limpiar caché", use_container_width=True, key="top_dl_clear"):
                _yts_top_c.clear()
                st.success("Caché limpiado")

        if load_top:
            with st.spinner("Consultando YTS…"):
                top_movies = _yts_top_c(
                    top_quality, top_genre, top_rating, top_sort, top_limit, top_page
                )
            st.session_state["top_dl_results"] = top_movies

        top_movies = st.session_state.get("top_dl_results")

        if top_movies is not None:
            if not top_movies:
                st.warning("Sin resultados. Prueba con otro género o calidad.")
            else:
                st.success(f"✅ {len(top_movies)} películas · página {top_page}")
                st.markdown("---")

                # Trackers para construir magnets
                _TR = (
                    "udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
                    "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
                    "&tr=udp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce"
                    "&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce"
                )

                for i, m in enumerate(top_movies):
                    title   = m.get("title", "")
                    year    = m.get("year", "")
                    rating  = m.get("rating", 0)
                    summary = (m.get("summary") or "")[:180]
                    genres  = ", ".join(m.get("genres") or [])
                    poster  = m.get("medium_cover_image") or m.get("small_cover_image")
                    torrents= m.get("torrents") or []

                    # Ordenar torrents: primero por seeds desc, luego por calidad
                    torrents = sorted(torrents, key=lambda t: int(t.get("seeds", 0)), reverse=True)

                    with st.container(border=True):
                        c_img, c_info = st.columns([1, 5])
                        with c_img:
                            if poster:
                                st.image(poster, width=80)
                        with c_info:
                            medal = {0: "🥇", 1: "🥈", 2: "🥉"}.get(i, f"**#{i+1}**")
                            st.markdown(
                                f"{medal} **{title}** ({year}) &nbsp;"
                                f'<span style="color:#fbbf24;">⭐ {rating}</span>',
                                unsafe_allow_html=True,
                            )
                            if genres:
                                st.caption(f"🎬 {genres}")
                            if summary:
                                st.caption(summary + ("…" if len(m.get("summary","")) > 180 else ""))

                            # Torrents disponibles
                            if torrents:
                                t_cols = st.columns(min(len(torrents), 4))
                                for j, t in enumerate(torrents[:4]):
                                    q     = t.get("quality", "?")
                                    ttype = t.get("type", "")
                                    seeds = int(t.get("seeds", 0))
                                    size  = t.get("size", "?")
                                    ih    = (t.get("hash") or "").lower()
                                    dn    = _uparse_mod.quote(f"{title} ({year}) {q}")
                                    mag   = f"magnet:?xt=urn:btih:{ih}&dn={dn}&tr={_TR}"

                                    seed_icon = "🟢" if seeds >= 50 else ("🟡" if seeds >= 10 else "🔴")
                                    q_label   = f"{q} {ttype.upper()}".strip()

                                    with t_cols[j]:
                                        st.link_button(
                                            f"🧲 {q_label}",
                                            mag,
                                            use_container_width=True,
                                            help=f"{seed_icon} {seeds} seeds · {size}",
                                        )
                            else:
                                st.caption("Sin torrents disponibles en YTS")

                            # Botón para búsqueda completa (TPB + Knaben)
                            if st.button("🔍 Más fuentes", key=f"top_dl_more_{i}",
                                         help="Busca en TPB + Knaben + SolidTorrents"):
                                with st.spinner(f"Buscando «{title}»…"):
                                    g_t, b_t = find_movie_torrents_combined(
                                        title, str(year), n=10,
                                        title_orig=m.get("title_english") or title,
                                    )
                                _render_torrents(g_t, b_t, {"title": title, "year": str(year)},
                                                 movies_dir, show_blocked=False,
                                                 key_prefix=f"topdl_{i}")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 1 — Búsqueda directa
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_buscar:
        st.markdown("Busca cualquier película y encuentra sus torrents en **The Pirate Bay** con prioridad en **español latino**.")

        col_q, col_yr = st.columns([3, 1])
        with col_q:
            query = st.text_input("🎬 Título de la película",
                                  placeholder="ej: El Padrino, Titanic, Interstellar...",
                                  key="mov_query")
        with col_yr:
            year_hint = st.number_input("Año (opcional)", min_value=0, max_value=2030,
                                        value=0, step=1, key="mov_year",
                                        help="Ayuda a encontrar la versión correcta")

        col_opts1, col_opts2 = st.columns(2)
        with col_opts1:
            show_blocked = st.checkbox("Mostrar resultados bloqueados (CAM/TS)",
                                       value=False, key="mov_show_blocked")
        with col_opts2:
            n_torrents = st.slider("Máx. torrents a mostrar", 5, 20, 10, key="mov_n")

        buscar = st.button("🔍 Buscar", type="primary",
                           use_container_width=True, disabled=not query)

        if buscar and query:
            with st.spinner(f"Buscando «{query}» en TMDB..."):
                yr = year_hint if year_hint > 0 else None
                movies = _tmdb_search_c(tmdb_key, query, year=yr)  # feature #11
            st.session_state["mov_buscar_results"] = movies
            st.session_state.pop("mov_buscar_torrents", None)
            st.session_state.pop("mov_sel", None)   # evita selección obsoleta de otra búsqueda

        # Render desde session_state: cambiar de película en el selectbox o
        # pulsar cualquier botón dispara un rerun en el que `buscar` vuelve a False
        movies = st.session_state.get("mov_buscar_results")
        if movies is not None:
            if not movies:
                st.warning("Sin resultados en TMDB. Prueba con el título en inglés.")
            else:
                opciones = [f"{m['title']} ({m['year']}) ⭐{m['rating']}" for m in movies]
                seleccion = st.selectbox("Selecciona la película correcta", opciones, key="mov_sel")
                idx = opciones.index(seleccion)
                movie = movies[idx]

                _render_movie_card(movie)

                # Feature #2: Add to watchlist button
                wl = _load_watchlist()
                wl_ids = {w.get("id") for w in wl}
                if movie.get("id") not in wl_ids:
                    if st.button("⭐ Guardar en Watchlist", key="wl_add_buscar"):
                        wl.append(movie)
                        _save_watchlist(wl)
                        st.success("Agregado a la Watchlist")
                        st.rerun()
                else:
                    st.success("✅ Ya está en tu Watchlist")

                st.markdown("---")
                st.markdown("#### Torrents disponibles")
                # Caché por película: sin esto cada rerun (guardar magnet,
                # watchlist) repetiría la búsqueda multi-fuente completa
                t_cache = st.session_state.get("mov_buscar_torrents")
                if not t_cache or t_cache[0] != movie.get("id"):
                    with st.spinner("Buscando en TPB · YTS · Knaben · SolidTorrents..."):
                        good_t, blocked_t = find_movie_torrents_combined(
                            movie["title"], movie["year"], n=n_torrents,
                            title_orig=movie.get("title_orig"),
                        )
                    if good_t:
                        _record_download("Película", len(good_t),
                                         f"{movie['title']} ({movie['year']})")
                    st.session_state["mov_buscar_torrents"] = (movie.get("id"), good_t, blocked_t)
                else:
                    good_t, blocked_t = t_cache[1], t_cache[2]

                _render_torrents(good_t, blocked_t, movie, movies_dir, show_blocked,
                                 key_prefix="buscar")

                # Feature #12: CSV export of torrent results
                if good_t:
                    import io as _io_mov, csv as _csv_mov
                    _cbuf = _io_mov.StringIO()
                    _cwr  = _csv_mov.writer(_cbuf)
                    _cwr.writerow(["nombre","idioma","calidad","seeds","tamaño","magnet"])
                    for t in good_t:
                        _cwr.writerow([t.get("name","")[:80], t.get("lang_icon",""),
                                       t.get("q_label",""), t.get("seeds",0),
                                       t.get("size",""), t.get("magnet","")[:80]])
                    st.download_button("Exportar torrents a CSV", _cbuf.getvalue().encode(),
                                       f"{movie['title'][:30]}_torrents.csv", mime="text/csv",
                                       key="mov_csv_buscar")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 2 — Explorar por épocas y géneros
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_decadas:
        st.markdown("Descubre las **películas más populares** de cada época.")

        col_d, col_g = st.columns([2, 2])
        with col_d:
            decada_label = st.selectbox("📅 Época", [
                "70s (1970–1979)", "80s (1980–1989)", "90s (1990–1999)",
                "2000s (2000–2009)", "2010s (2010–2019)", "2020s (2020–hoy)",
                "Tendencias semana", "Populares ahora",
            ], key="mov_decade")
        with col_g:
            generos_display = ["Todos los géneros"] + [
                g.replace("_", " ").title() for g in GENRE_IDS
            ]
            genero_sel = st.selectbox("🎭 Género", generos_display, key="mov_genre")

        col_ord, col_lim = st.columns([2, 1])
        with col_ord:
            orden_label = st.selectbox(
                "🔀 Ordenar por",
                ["🔥 Popularidad (mayor primero)",
                 "📅 Año — más recientes primero",
                 "📅 Año — más antiguos primero",
                 "⭐ Calificación (mayor primero)"],
                key="mov_sort",
            )
        with col_lim:
            limite = st.number_input("Nº películas", 10, 200, 40, 10, key="mov_limit")

        # Mapear label → sort_by de TMDB
        sort_map = {
            "🔥 Popularidad (mayor primero)":      "popularity.desc",
            "📅 Año — más recientes primero":       "primary_release_date.desc",
            "📅 Año — más antiguos primero":        "primary_release_date.asc",
            "⭐ Calificación (mayor primero)":      "vote_average.desc",
        }
        tmdb_sort = sort_map.get(orden_label, "popularity.desc")

        buscar_epoca = st.button("🚀 Explorar", type="primary",
                                 use_container_width=True, key="mov_explore_btn")

        if buscar_epoca:
            genre_key = None
            if genero_sel != "Todos los géneros":
                genre_key = genero_sel.lower().replace(" ", "_")

            pages_needed = max(1, (limite + 19) // 20)   # cuántas páginas TMDB necesita
            with st.spinner(f"Consultando TMDB ({pages_needed} página{'s' if pages_needed > 1 else ''})..."):
                if decada_label == "Tendencias semana":
                    movies = _tmdb_trending_c(tmdb_key, limit=limite)
                elif decada_label == "Populares ahora":
                    movies = _tmdb_popular_c(tmdb_key, limit=limite)
                else:
                    decade_map = {
                        "70s (1970–1979)":  (1970, 1979),
                        "80s (1980–1989)":  (1980, 1989),
                        "90s (1990–1999)":  (1990, 1999),
                        "2000s (2000–2009)":(2000, 2009),
                        "2010s (2010–2019)":(2010, 2019),
                        "2020s (2020–hoy)": (2020, 2030),
                    }
                    y_gte, y_lte = decade_map[decada_label]
                    genre_id = GENRE_IDS.get(genre_key) if genre_key else None
                    movies = _tmdb_discover_c(tmdb_key, y_gte, y_lte,
                                             genre_id=genre_id, limit=limite,
                                             sort_by=tmdb_sort)

            if not movies:
                st.warning("Sin resultados. Prueba con otro filtro.")
            else:
                st.success(f"✅ {len(movies)} películas encontradas")
                st.session_state["mov_epoch_results"] = movies
                st.session_state["mov_epoch_sort"]    = orden_label   # para mostrar en header

        # Muestra resultados guardados en session
        movies = st.session_state.get("mov_epoch_results", [])
        if movies:
            active_sort = st.session_state.get("mov_epoch_sort", "")
            sort_label  = active_sort.split(" ", 1)[1] if active_sort else ""
            sort_html   = (f'<span>· ordenadas por <b style="color:#e2e2f0;">'
                           f'{sort_label}</b></span>') if sort_label else ""
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;'
                f'margin-bottom:10px;font-size:0.82rem;color:#8888b0;">'
                f'<span>📋 <b style="color:#c4b5fd;">{len(movies)}</b> películas</span>'
                f'{sort_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

            for i, movie in enumerate(movies):
                # Emoji de rating + año destacado en el título del expander
                rating      = movie["rating"]
                rating_icon = "🏆" if rating >= 8 else ("⭐" if rating >= 7 else "🎬")
                votes_k     = f"{movie['votes']//1000}k" if movie['votes'] >= 1000 else str(movie['votes'])

                with st.expander(
                    f"{rating_icon} {movie['title']}  "
                    f"({movie['year']})  ·  ⭐ {rating}  ·  👥 {votes_k} votos",
                    expanded=False,
                ):
                    _render_movie_card(movie, compact=True)
                    st.markdown("##### 🏴‍☠️ Torrents")

                    key = f"epoch_{i}"
                    if st.button("🔍 Buscar torrents", key=f"btn_{key}",
                                 use_container_width=True):
                        with st.spinner("Buscando en TPB · YTS · Knaben..."):
                            good_t, blocked_t = find_movie_torrents_combined(
                                movie["title"], movie["year"],
                                title_orig=movie.get("title_orig"),
                            )
                        st.session_state[f"good_{key}"] = good_t
                        st.session_state[f"blocked_{key}"] = blocked_t

                    good_t    = st.session_state.get(f"good_{key}")
                    blocked_t = st.session_state.get(f"blocked_{key}")
                    if good_t is not None or blocked_t is not None:
                        _render_torrents(good_t or [], blocked_t or [], movie, movies_dir,
                                         show_blocked=False, key_prefix=key)

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 3 — Cine de Culto
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_culto:
        import json as _cult_json

        # ── Cached call para el top global de culto ───────────────────────────
        @st.cache_data(ttl=3600, show_spinner=False)
        def _tmdb_top_cult_c(key, sort_by, min_votes, limit):
            # Keywords: 9715=cult film | 9816=cult classic | 10349=B-movie | 212372=midnight movie
            ep = {
                "with_keywords":   "9715|9816|10349|212372",
                "vote_count.gte":  str(min_votes),
                "popularity.lte":  "60",   # excluye blockbusters; Blade Runner ~15, The Matrix ~180
                "vote_average.gte": "5.5",  # descarta títulos muy malos sin audiencia real
            }
            return tmdb_discover(key, sort_by=sort_by, limit=limit, extra_params=ep)

        # ── Modo de vista ─────────────────────────────────────────────────────
        cult_mode = st.radio(
            "Vista",
            ["🏆 Top Películas de Culto", "🎭 Explorar por Subgénero"],
            horizontal=True,
            key="cult_mode",
            label_visibility="collapsed",
        )

        st.markdown("---")

        # ══════════════════════════════════════════════════════════════════════
        # MODO TOP CULTO
        # ══════════════════════════════════════════════════════════════════════
        if cult_mode == "🏆 Top Películas de Culto":
            st.markdown(
                "Las películas clasificadas como **cult film** en TMDB, ordenadas por "
                "calificación de usuarios. Incluye todas las épocas y géneros."
            )

            col_ts, col_tv, col_tl = st.columns([2, 2, 1])
            with col_ts:
                top_sort_label = st.selectbox(
                    "Ordenar por",
                    ["⭐ Calificación", "🔥 Popularidad", "📅 Más recientes"],
                    key="top_cult_sort",
                )
            with col_tv:
                top_min_votes = st.select_slider(
                    "Votos mínimos",
                    options=[100, 200, 500, 1000, 2000, 5000],
                    value=500,
                    key="top_cult_votes",
                    help="Filtra películas poco conocidas",
                )
            with col_tl:
                top_limit = st.number_input("Cantidad", 10, 200, 50, 10, key="top_cult_limit")

            top_sort_map = {
                "⭐ Calificación":  "vote_average.desc",
                "🔥 Popularidad":   "popularity.desc",
                "📅 Más recientes": "primary_release_date.desc",
            }
            top_sort = top_sort_map.get(top_sort_label, "vote_average.desc")

            if st.button("🏆 Cargar Top Culto", type="primary",
                         use_container_width=True, key="top_cult_btn"):
                with st.spinner("Consultando TMDB — keyword 'cult film'..."):
                    top_movies = _tmdb_top_cult_c(
                        tmdb_key, top_sort, top_min_votes, top_limit
                    )
                if top_sort == "popularity.desc":
                    top_movies.sort(key=lambda m: m.get("popularity", 0), reverse=True)
                elif top_sort == "primary_release_date.desc":
                    top_movies.sort(key=lambda m: str(m.get("year", "0")), reverse=True)
                st.session_state["top_cult_results"] = top_movies

            top_movies = st.session_state.get("top_cult_results", [])
            if top_movies:
                st.success(f"✅ {len(top_movies)} películas de culto")

                # Tabla resumen en la parte superior
                import pandas as _pd_top
                df_top = _pd_top.DataFrame([{
                    "#":       i + 1,
                    "título":  m["title"],
                    "año":     m.get("year", ""),
                    "⭐ nota": m.get("rating", ""),
                    "géneros": m.get("genres", ""),
                } for i, m in enumerate(top_movies)])
                st.dataframe(
                    df_top, use_container_width=True, hide_index=True,
                    column_config={
                        "#":       st.column_config.NumberColumn("#", width="small"),
                        "⭐ nota": st.column_config.NumberColumn("⭐ Nota", format="%.1f"),
                    },
                )

                st.markdown("---")
                st.markdown("#### Detalles y torrents")

                for i, movie in enumerate(top_movies):
                    rating = movie.get("rating", 0)
                    year   = movie.get("year", "")
                    # Medalla para el top 3
                    medal = {0: "🥇", 1: "🥈", 2: "🥉"}.get(i, f"**#{i+1}**")
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([5, 1, 1])
                        with c1:
                            st.markdown(
                                f'{medal} **{movie["title"]}** ({year})'
                                f'&nbsp;&nbsp;<span style="color:#fbbf24;font-size:0.9rem;">'
                                f'⭐ {rating}</span>',
                                unsafe_allow_html=True,
                            )
                            if movie.get("overview"):
                                st.caption(movie["overview"][:180] + "…"
                                           if len(movie.get("overview", "")) > 180
                                           else movie.get("overview", ""))
                        with c2:
                            wl = _load_watchlist()
                            wl_ids = {w.get("id") for w in wl}
                            if movie.get("id") not in wl_ids:
                                if st.button("⭐", key=f"top_wl_{i}",
                                             use_container_width=True,
                                             help="Guardar en Watchlist"):
                                    wl.append(movie)
                                    _save_watchlist(wl)
                                    st.rerun()
                            else:
                                st.markdown("✅", unsafe_allow_html=True)
                        with c3:
                            show_top_t = st.button("🧲", key=f"top_t_{i}",
                                                   use_container_width=True,
                                                   help="Buscar torrents")
                        if show_top_t:
                            with st.spinner(f"Buscando «{movie['title']}»..."):
                                g_t, b_t = find_movie_torrents_combined(
                                    movie["title"], movie["year"], n=10,
                                    title_orig=movie.get("title_orig"),
                                )
                            _render_torrents(g_t, b_t, movie, movies_dir,
                                             show_blocked=False,
                                             key_prefix=f"top_{i}")

        # ══════════════════════════════════════════════════════════════════════
        # MODO SUBGÉNERO
        # ══════════════════════════════════════════════════════════════════════
        else:
            st.markdown(
                "Explora subgéneros de **cine de culto** curados. "
                "Selecciona uno y busca torrents."
            )

        # ── Selector de subgénero (grid de cards) ─────────────────────────────
        if cult_mode == "🎭 Explorar por Subgénero":
            cols_per_row = 4
            sg_names = [sg["name"] for sg in CULT_SUBGENRES]
            selected_cult = st.session_state.get("cult_selected", sg_names[0])

            rows = [CULT_SUBGENRES[i:i+cols_per_row] for i in range(0, len(CULT_SUBGENRES), cols_per_row)]
            for row in rows:
                rcols = st.columns(len(row))
                for col, sg in zip(rcols, row):
                    with col:
                        is_active = sg["name"] == selected_cult
                        bg = "rgba(120,80,255,0.25)" if is_active else "rgba(19,19,46,0.8)"
                        border = "rgba(120,80,255,0.7)" if is_active else "rgba(60,60,100,0.4)"
                        st.markdown(
                            f'<div style="background:{bg};border:1.5px solid {border};'
                            f'border-radius:12px;padding:14px 12px;text-align:center;'
                            f'margin-bottom:4px;min-height:80px;">'
                            f'<div style="font-size:1.6rem;">{sg["icon"]}</div>'
                            f'<div style="font-size:0.8rem;font-weight:600;color:#e2e2f0;'
                            f'margin-top:4px;">{sg["name"]}</div>'
                            f'<div style="font-size:0.68rem;color:#8888b0;margin-top:3px;">'
                            f'{sg["desc"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if st.button("Seleccionar", key=f"cult_sel_{sg['name']}",
                                     use_container_width=True,
                                     type="primary" if is_active else "secondary"):
                            st.session_state["cult_selected"] = sg["name"]
                            st.session_state.pop("cult_results", None)
                            st.rerun()

            st.markdown("---")
            sg_data = next((s for s in CULT_SUBGENRES if s["name"] == selected_cult), CULT_SUBGENRES[0])

            col_l, col_n = st.columns([3, 1])
            with col_l:
                cult_limit = st.slider("Número de películas", 10, 80, 30, 10, key="cult_limit")
            with col_n:
                cult_sort_label = st.selectbox(
                    "Ordenar por",
                    ["⭐ Calificación", "🔥 Popularidad", "📅 Más recientes"],
                    key="cult_sort",
                )

            cult_sort_map = {
                "⭐ Calificación":  "vote_average.desc",
                "🔥 Popularidad":   "popularity.desc",
                "📅 Más recientes": "primary_release_date.desc",
            }
            cult_sort = cult_sort_map.get(cult_sort_label, "vote_average.desc")

            if st.button(f"🎬 Explorar {sg_data['icon']} {sg_data['name']}",
                         type="primary", use_container_width=True, key="cult_explore"):
                ep_str = _cult_json.dumps(sg_data["extra"])
                with st.spinner(f"Cargando {sg_data['name']}..."):
                    movies_cult = _tmdb_cult_c(tmdb_key, ep_str, limit=cult_limit)
                if cult_sort == "popularity.desc":
                    movies_cult.sort(key=lambda m: m.get("popularity", 0), reverse=True)
                elif cult_sort == "primary_release_date.desc":
                    movies_cult.sort(key=lambda m: str(m.get("year", "0")), reverse=True)
                st.session_state["cult_results"] = movies_cult
                st.session_state["cult_subgenre"] = sg_data["name"]

            cult_movies = st.session_state.get("cult_results", [])
            if cult_movies:
                active_sg = st.session_state.get("cult_subgenre", selected_cult)
                st.success(f"✅ {len(cult_movies)} películas · {active_sg}")

                for i, movie in enumerate(cult_movies):
                    with st.container():
                        c1, c2 = st.columns([4, 1])
                        with c1:
                            _render_movie_card(movie)
                        with c2:
                            wl = _load_watchlist()
                            wl_ids = {w.get("id") for w in wl}
                            if movie.get("id") not in wl_ids:
                                if st.button("⭐ Watchlist", key=f"cult_wl_{i}",
                                             use_container_width=True):
                                    wl.append(movie)
                                    _save_watchlist(wl)
                                    st.success("Agregado")
                                    st.rerun()
                            else:
                                st.success("✅ En WL")

                            show_t = st.button("🧲 Torrents", key=f"cult_t_{i}",
                                               use_container_width=True)

                        if show_t:
                            with st.spinner(f"Buscando torrents de «{movie['title']}»..."):
                                cult_n = st.session_state.get("mov_n", 10)
                                good_t, blocked_t = find_movie_torrents_combined(
                                    movie["title"], movie["year"], n=cult_n,
                                    title_orig=movie.get("title_orig"),
                                )
                            _render_torrents(good_t, blocked_t, movie, movies_dir,
                                             show_blocked=False, key_prefix=f"cult_{i}")
                        st.markdown(
                            '<hr style="border:none;border-top:1px solid rgba(60,60,100,0.3);margin:8px 0;">',
                            unsafe_allow_html=True,
                        )

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 4 — Renombrar archivos de película
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_rename_mov:
        import re as _re_mov, shutil as _shutil_mov

        VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".ts", ".webm"}
        SUB_EXTS   = {".srt", ".sub", ".ass", ".ssa", ".vtt", ".idx", ".sup"}
        KEEP_EXTS  = VIDEO_EXTS | SUB_EXTS

        def _parse_movie_filename(stem: str) -> tuple:
            s = _re_mov.sub(r'\[.*?\]|\(.*?\)', ' ', stem)
            s = _re_mov.sub(r'[._]', ' ', s)
            m = _re_mov.search(r'\b(19[0-9]{2}|20[0-2][0-9])\b', s)
            year   = m.group(1) if m else ""
            title  = s[:m.start()].strip() if m else s.strip()
            title  = _re_mov.sub(
                r'\s+(1080p|720p|4[kK]|2160p|blu.?ray|bdrip|web.?rip|web.?dl|'
                r'hdtv|dvdrip|dvd|remux|hdrip|hdcam|proper|remastered|extended|'
                r'directors|theatrical|unrated|limited|internal|hevc|x264|x265|'
                r'h264|h265|aac|ac3|dts|dovi|hdr|sdr|atmos).*$',
                '', title, flags=_re_mov.IGNORECASE,
            ).strip()
            title = ' '.join(w.capitalize() for w in title.split() if w)
            return title, year

        cfg_r = load_config()
        dest_root = Path(cfg_r.get("movies_folder", str(Path.home() / "Downloads" / "Peliculas")))

        st.markdown(
            f"Limpia y organiza tu carpeta de películas en un solo paso: "
            f"**renombra** los vídeos, **mueve** todo a la raíz configurada "
            f"(`{dest_root}`) y **elimina** archivos irrelevantes."
        )

        folder_mov = st.text_input(
            "📁 Carpeta origen (donde están las películas ahora)",
            value=str(dest_root),
            key="mov_rename_folder",
            help="Puede ser la misma carpeta destino — buscará en todas las subcarpetas.",
        )

        st.markdown("**¿Qué hace cada opción?**")
        col_o1, col_o2, col_o3, col_o4 = st.columns(4)
        with col_o1:
            do_rename  = st.checkbox("✏️ Renombrar", value=True, key="mov_do_rename",
                                     help="Renombra el fichero a 'Título (Año).ext'")
        with col_o2:
            do_move    = st.checkbox("📦 Mover a raíz", value=True, key="mov_do_move",
                                     help=f"Mueve el fichero a la raíz de '{dest_root}', "
                                          "eliminando la subcarpeta")
        with col_o3:
            do_cleanup = st.checkbox("🗑️ Borrar basura", value=True, key="mov_do_cleanup",
                                     help="Elimina .nfo, .jpg, .txt, .sfv, .exe y demás "
                                          "— solo conserva vídeos y subtítulos")
        with col_o4:
            do_tmdb    = st.checkbox("🎬 TMDB lookup", value=False, key="mov_rename_tmdb",
                                     help="Confirma el título oficial con TMDB (más lento)")

        rename_pattern_mov = st.selectbox(
            "Formato del nombre de salida",
            ["{titulo} ({año})", "{titulo} ({año}) [{calidad}]", "{titulo}"],
            key="mov_rename_pattern",
        )

        dry_mov = st.checkbox("Dry Run — solo previsualizar, NO tocar nada",
                              value=True, key="mov_rename_dry")

        col_pb, col_ab = st.columns(2)
        with col_pb:
            preview_btn = st.button("🔍 Previsualizar", type="primary",
                                    use_container_width=True, key="mov_rename_preview")
        with col_ab:
            apply_btn = st.button("⚡ Aplicar ahora", type="secondary",
                                  use_container_width=True, key="mov_rename_apply",
                                  disabled=dry_mov,
                                  help="Desactiva 'Dry Run' para habilitar")

        if preview_btn or apply_btn:
            folder_p = Path(folder_mov)
            if not folder_p.exists() or not folder_p.is_dir():
                st.error(f"La carpeta no existe: {folder_mov}")
            else:
                executing = apply_btn and not dry_mov

                def _rel(p: Path, base: Path) -> str:
                    try:    return str(p.relative_to(base))
                    except: return str(p)

                # ── Escanear ──────────────────────────────────────────────────
                all_files   = [f for f in folder_p.rglob("*") if f.is_file()]
                video_files = [f for f in all_files if f.suffix.lower() in VIDEO_EXTS]
                sub_files   = [f for f in all_files if f.suffix.lower() in SUB_EXTS]
                junk_files  = [f for f in all_files if f.suffix.lower() not in KEEP_EXTS]
                # subcarpetas directas (no la raíz)
                subdirs     = sorted(
                    {f.parent for f in all_files if f.parent.resolve() != folder_p.resolve()},
                    key=lambda d: str(d),
                )

                if not video_files:
                    st.warning(f"No se encontraron archivos de vídeo en `{folder_mov}`")
                else:
                    dest_root.mkdir(parents=True, exist_ok=True)

                    rows_vid  = []
                    rows_subs = []
                    rows_junk = []
                    rows_dirs = []
                    renamed_mov = moved_mov = moved_subs = deleted_mov = deleted_dirs = errors_mov = 0

                    prog = st.progress(0, text="Analizando archivos de vídeo...")
                    total = len(video_files)

                    for idx, vf in enumerate(video_files[:300]):
                        prog.progress((idx + 1) / min(total, 300),
                                      text=f"[{idx+1}/{total}] {vf.name[:55]}...")
                        try:
                            title_p, year_p = _parse_movie_filename(vf.stem)

                            qual_m = _re_mov.search(
                                r'(1080p|720p|4[kK]|2160p|480p)', vf.stem, _re_mov.IGNORECASE
                            )
                            calidad = qual_m.group(1).upper() if qual_m else ""

                            if do_tmdb and title_p:
                                try:
                                    res = _tmdb_search_c(tmdb_key, title_p,
                                                        year=int(year_p) if year_p else None)
                                    if res:
                                        title_p = res[0]["title"]
                                        if not year_p:
                                            year_p = str(res[0].get("year", ""))
                                except Exception:
                                    pass

                            if do_rename:
                                new_stem = rename_pattern_mov.format(
                                    titulo=title_p or vf.stem,
                                    año=year_p or "????",
                                    calidad=calidad,
                                ).strip()
                                keep_ch = set(" ._-()[],'")
                                new_stem = "".join(
                                    c if (c.isalnum() or c in keep_ch) else "_"
                                    for c in new_stem
                                )[:160].strip()
                                new_video_stem = new_stem
                                new_name = new_stem + vf.suffix.lower()
                            else:
                                new_video_stem = vf.stem
                                new_name = vf.name

                            final_dest = dest_root / new_name if do_move else vf.parent / new_name

                            action_parts = []
                            if do_rename and new_name != vf.name:
                                action_parts.append("✏️")
                            if do_move and vf.parent.resolve() != dest_root.resolve():
                                action_parts.append("📦")
                            action = " + ".join(action_parts) if action_parts else "— igual"

                            conflict = final_dest.exists() and final_dest.resolve() != vf.resolve()
                            if conflict:
                                action = "⚠️ conflicto"

                            rows_vid.append({
                                "original":  _rel(vf, folder_p)[:80],
                                "→ nuevo":   final_dest.name[:80],
                                "año":       year_p,
                                "acción":    action,
                            })

                            if executing and not conflict and action != "— igual":
                                final_dest.parent.mkdir(parents=True, exist_ok=True)
                                vf.rename(final_dest)
                                if "✏️" in action: renamed_mov += 1
                                if "📦" in action: moved_mov   += 1

                            # ── Subtítulos de la misma carpeta que el vídeo ───────
                            # Mueve TODOS los subs del mismo directorio, no solo
                            # los que coincidan por stem (evita problemas con puntos
                            # en el nombre y subs con sufijos de idioma como .es.srt)
                            if do_move:
                                for sf in list(vf.parent.iterdir()):
                                    if not sf.is_file():
                                        continue
                                    if sf.suffix.lower() not in SUB_EXTS:
                                        continue
                                    # Preservar sufijo de idioma (ej. .es.srt, .eng.srt)
                                    extra = sf.name[len(vf.stem):] if sf.name.startswith(vf.stem) \
                                            else sf.suffix.lower()
                                    new_sub_name = new_video_stem + extra
                                    sub_dest = dest_root / new_sub_name
                                    sub_conflict = sub_dest.exists() and sub_dest.resolve() != sf.resolve()
                                    rows_subs.append({
                                        "original": _rel(sf, folder_p)[:80],
                                        "→ nuevo":  new_sub_name[:80],
                                        "acción":   "⚠️ conflicto" if sub_conflict else "📦 mover sub",
                                    })
                                    if executing and not sub_conflict:
                                        sf.rename(sub_dest)
                                        moved_subs += 1

                        except Exception as e:
                            errors_mov += 1
                            rows_vid.append({
                                "original": vf.name[:80],
                                "→ nuevo":  f"ERROR: {e}",
                                "año":      "",
                                "acción":   "❌ Error",
                            })

                    # ── Basura ────────────────────────────────────────────────
                    if do_cleanup:
                        prog.progress(1.0, text="Catalogando archivos basura...")
                        for jf in junk_files:
                            rows_junk.append({
                                "fichero": _rel(jf, folder_p)[:100],
                                "tipo":    jf.suffix.lower() or "(sin ext)",
                                "acción":  "🗑️ borrar",
                            })
                            if executing:
                                try:
                                    jf.unlink()
                                    deleted_mov += 1
                                except Exception:
                                    rows_junk[-1]["acción"] = "❌ error"

                    # ── Carpetas vacías — SIEMPRE después de mover ────────────
                    # (independiente de do_cleanup)
                    if do_move:
                        # Preview: qué subdirs quedarán vacíos
                        for d in sorted(subdirs, key=lambda x: len(x.parts), reverse=True):
                            if d.resolve() == dest_root.resolve():
                                continue
                            rows_dirs.append({
                                "carpeta": _rel(d, folder_p)[:100],
                                "acción":  "🗂️ eliminar",
                            })
                        if executing:
                            # Re-escanear de más profundo a menos para poder borrar
                            # en el orden correcto (hijos antes que padres)
                            all_subdirs = sorted(
                                [p for p in folder_p.rglob("*")
                                 if p.is_dir()
                                 and p.resolve() != folder_p.resolve()
                                 and p.resolve() != dest_root.resolve()],
                                key=lambda x: len(x.parts),
                                reverse=True,
                            )
                            for sub in all_subdirs:
                                if not sub.exists():
                                    continue
                                remaining = list(sub.iterdir())
                                # Mover cualquier fichero KEEP que haya quedado huérfano
                                for leftover in remaining:
                                    if leftover.is_file() and leftover.suffix.lower() in KEEP_EXTS:
                                        lo_dest = dest_root / leftover.name
                                        if not lo_dest.exists():
                                            try:
                                                leftover.rename(lo_dest)
                                            except Exception:
                                                pass
                                # Después del rescate, re-evaluar qué queda
                                remaining2 = list(sub.iterdir())
                                only_junk = all(
                                    f.is_file() and f.suffix.lower() not in KEEP_EXTS
                                    for f in remaining2
                                )
                                try:
                                    if not remaining2 or only_junk:
                                        _shutil_mov.rmtree(sub)  # borra junk residual + carpeta
                                    else:
                                        sub.rmdir()   # solo si quedó vacía (no debería llegar aquí)
                                    deleted_dirs += 1
                                except Exception:
                                    pass

                    prog.empty()

                    # ── Métricas ──────────────────────────────────────────────
                    n_rename = sum(1 for r in rows_vid  if "✏️" in r["acción"])
                    n_move   = sum(1 for r in rows_vid  if "📦" in r["acción"])
                    n_junk   = len(rows_junk)
                    n_dirs   = len(rows_dirs)

                    cols5 = st.columns(5)
                    cols5[0].metric("📼 Vídeos",        len(video_files))
                    cols5[1].metric("✏️ Renombrar",     n_rename)
                    cols5[2].metric("📦 Mover",         n_move)
                    cols5[3].metric("🗑️ Basura",        n_junk)
                    cols5[4].metric("🗂️ Carpetas",      n_dirs)

                    if executing:
                        st.success(
                            f"✅ {renamed_mov} renombrados · {moved_mov} movidos · "
                            f"{moved_subs} subs movidos · {deleted_mov} basura borrada · "
                            f"{deleted_dirs} carpetas eliminadas · {errors_mov} errores"
                        )
                        if renamed_mov + moved_mov > 0:
                            _record_download("Organizar películas",
                                             renamed_mov + moved_mov, str(dest_root))
                    else:
                        st.info(
                            "👁 **Dry Run** — solo previsualización. "
                            "Desactiva 'Dry Run' y pulsa **⚡ Aplicar ahora** para ejecutar."
                        )

                    import pandas as _pd_mov
                    st.markdown("#### 📼 Archivos de vídeo")
                    st.dataframe(
                        _pd_mov.DataFrame(rows_vid),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "acción": st.column_config.TextColumn("Acción", width="small"),
                            "año":    st.column_config.TextColumn("Año",    width="small"),
                        },
                    )

                    if rows_subs:
                        with st.expander(f"🔤 Subtítulos a mover junto al vídeo ({len(rows_subs)})", expanded=False):
                            st.dataframe(_pd_mov.DataFrame(rows_subs),
                                         use_container_width=True, hide_index=True)

                    if rows_junk:
                        with st.expander(f"🗑️ Archivos a borrar ({n_junk})", expanded=False):
                            st.caption(
                                "Se eliminarán .nfo, .jpg, .png, .txt, .sfv, .url, .exe y similares. "
                                "Los subtítulos (.srt .sub .ass .vtt etc.) se conservan."
                            )
                            st.dataframe(_pd_mov.DataFrame(rows_junk),
                                         use_container_width=True, hide_index=True)

                    if rows_dirs:
                        with st.expander(f"🗂️ Carpetas a eliminar ({n_dirs})", expanded=False):
                            st.caption("Estas subcarpetas quedarán vacías y se eliminarán automáticamente.")
                            st.dataframe(_pd_mov.DataFrame(rows_dirs),
                                         use_container_width=True, hide_index=True)

                    # CSV export
                    import io as _io_rmov, csv as _csv_rmov
                    _rbuf = _io_rmov.StringIO()
                    _rwr  = _csv_rmov.DictWriter(_rbuf, fieldnames=["original","→ nuevo","año","acción"])
                    _rwr.writeheader(); _rwr.writerows(rows_vid)
                    st.download_button("⬇ Exportar preview a CSV", _rbuf.getvalue().encode(),
                                       "organizar_peliculas.csv", mime="text/csv",
                                       key="mov_rename_csv")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 5 — Resultados guardados
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_resultados:
        mag_path = movies_dir / "magnets_movies.txt"
        rep_path = movies_dir / "movies_report.json"

        col_m, col_r = st.columns(2)
        with col_m:
            if mag_path.exists():
                content = mag_path.read_text(encoding="utf-8")
                n_mag = content.count("magnet:")
                st.metric("🔗 Magnet links guardados", n_mag)
                with open(mag_path, "rb") as f:
                    st.download_button("⬇ Descargar magnets_movies.txt",
                                       f.read(), "magnets_movies.txt",
                                       use_container_width=True)
            else:
                st.info("Aún no hay magnets guardados.")

        with col_r:
            if rep_path.exists():
                with open(rep_path) as f:
                    report = _json.load(f)
                n_movies   = len(report)
                n_with_tor = sum(1 for r in report if r.get("torrents"))
                st.metric("🎬 Películas en reporte", n_movies)
                st.metric("✅ Con torrents encontrados", n_with_tor)
            else:
                st.info("Sin reporte aún.")

        if rep_path.exists():
            st.markdown("---")
            search_r = st.text_input("🔎 Filtrar por título", key="mov_rep_search")
            with open(rep_path) as f:
                report = _json.load(f)
            filtered = [r for r in report
                        if not search_r or search_r.lower() in r["movie"]["title"].lower()]

            for entry in filtered[:60]:
                m = entry["movie"]
                torrents = entry.get("torrents", [])
                best = torrents[0] if torrents else None
                with st.container(border=True):
                    c1, c2 = st.columns([4, 2])
                    with c1:
                        rating_stars = "⭐" * int(m["rating"] / 2)
                        st.markdown(f"**{m['title']}** ({m['year']}) {rating_stars}")
                        if best:
                            st.caption(
                                f"{best['lang_icon']}  ·  {best['q_label']}  ·  "
                                f"{best['seed_icon']} {best['seeds']} seeds  ·  {best['size']}"
                            )
                        else:
                            st.caption("Sin torrents registrados")
                    with c2:
                        if best:
                            st.code(best["magnet"][:60] + "...", language="")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 4 — Watchlist  (feature #2)
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_watchlist:
        wl = _load_watchlist()
        if not wl:
            st.info("Tu watchlist está vacía. Busca una película y pulsa '⭐ Guardar en Watchlist'.")
        else:
            st.markdown(f'<div class="mh-section-title">{len(wl)} películas guardadas</div>',
                        unsafe_allow_html=True)
            for i, m in enumerate(wl):
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 2, 1])
                    with c1:
                        st.markdown(f"**{m['title']}** ({m.get('year','')})")
                        st.caption(f"⭐ {m.get('rating','')}  ·  {m.get('votes',0):,} votos")
                    with c2:
                        if st.button("Buscar torrents", key=f"wl_tor_{i}",
                                     use_container_width=True):
                            st.session_state["wl_active"] = i
                    with c3:
                        if st.button("✕", key=f"wl_del_{i}", help="Eliminar de watchlist"):
                            wl.pop(i)
                            _save_watchlist(wl)
                            st.rerun()

                if st.session_state.get("wl_active") == i:
                    with st.spinner("Buscando torrents..."):
                        good_t, blocked_t = find_movie_torrents_combined(
                            m["title"], m.get("year", ""),
                            title_orig=m.get("title_orig"),
                        )
                    _render_torrents(good_t, blocked_t, m, movies_dir,
                                     show_blocked=False, key_prefix=f"wl_{i}")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 5 — Subtítulos  (feature #9)
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_subs:
        st.markdown(
            "Busca subtítulos en español para cualquier película. "
            "Los resultados enlazan directamente a las fuentes de descarga."
        )
        col_sq, col_sl = st.columns([3, 1])
        with col_sq:
            sub_query = st.text_input("Título de la película", placeholder="ej: The Matrix, Inception...",
                                      key="sub_query")
        with col_sl:
            sub_lang = st.selectbox("Idioma", ["Español Latino", "Español España", "Ambos"], key="sub_lang")

        if st.button("Buscar subtítulos", type="primary", use_container_width=True,
                     disabled=not sub_query, key="sub_btn"):
            lang_code = {"Español Latino": "lat", "Español España": "spa", "Ambos": "spa,lat"}[sub_lang]
            q_enc    = _uparse_mod.quote(sub_query)
            q_subdivx = _uparse_mod.quote(sub_query.replace(" ", "+"))

            # OpenSubtitles REST search — requiere API key (⚙️ Configuración)
            subs_found = []
            os_api_key = cfg.get("opensubtitles_api_key", "").strip()
            if os_api_key:
                try:
                    os_url = (f"https://api.opensubtitles.com/api/v1/subtitles"
                              f"?query={q_enc}&languages=es&order_by=download_count&order_direction=desc")
                    os_req = _ureq_mod.Request(
                        os_url,
                        headers={"User-Agent": "MediaHub/1.0", "Api-Key": os_api_key},
                    )
                    with _ureq_mod.urlopen(os_req, timeout=8) as r:
                        os_data = json.loads(r.read().decode())
                    for sub in os_data.get("data", [])[:15]:
                        attr = sub.get("attributes", {})
                        subs_found.append({
                            "title":    attr.get("feature_details", {}).get("movie_name", sub_query),
                            "year":     attr.get("feature_details", {}).get("year", ""),
                            "language": attr.get("language", "es"),
                            "release":  attr.get("release", ""),
                            "downloads": attr.get("download_count", 0),
                            "url":      f"https://www.opensubtitles.com/es/subtitles/{sub.get('id','')}"
                        })
                except Exception:
                    pass
            else:
                st.caption("💡 Configura una API key de OpenSubtitles en ⚙️ Configuración "
                           "para buscar directamente aquí. Mientras tanto usa las fuentes alternativas.")

            if subs_found:
                st.success(f"✅ {len(subs_found)} subtítulos encontrados en OpenSubtitles")
                for s in subs_found:
                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        with c1:
                            st.markdown(f"**{s['release'][:80] or s['title']}**")
                            st.caption(f"Año: {s['year']} · Idioma: {s['language']} · "
                                       f"Descargas: {s['downloads']:,}")
                        with c2:
                            st.link_button("Descargar", s["url"], use_container_width=True)
            else:
                st.info("No se encontraron resultados en OpenSubtitles. Prueba en las fuentes alternativas:")

            st.markdown("**Fuentes alternativas:**")
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                st.link_button(
                    "Subdivx.com",
                    f"https://www.subdivx.com/index.php?buscar={q_subdivx}&accion=5",
                    use_container_width=True,
                )
            with col_s2:
                st.link_button(
                    "OpenSubtitles",
                    f"https://www.opensubtitles.org/es/search/sublanguageid-spa/moviename-{q_enc}",
                    use_container_width=True,
                )
            with col_s3:
                st.link_button(
                    "SubDL",
                    f"https://subdl.com/search/{q_enc}",
                    use_container_width=True,
                )


# ─── Helpers de renderizado ───────────────────────────────────────────────────

def _render_movie_card(movie: dict, compact: bool = False):
    """Tarjeta visual de una película con datos de TMDB."""
    col_poster, col_info = st.columns([1, 4])
    with col_poster:
        if movie.get("poster"):
            st.image(movie["poster"], width=90 if compact else 130)
        else:
            st.markdown(
                '<div style="width:90px;height:130px;background:rgba(120,80,255,0.12);'
                'border-radius:8px;display:flex;align-items:center;justify-content:center;'
                'font-size:2rem;">🎬</div>',
                unsafe_allow_html=True,
            )
    with col_info:
        stars = "⭐" * max(1, round(movie["rating"] / 2))
        lang_tag = ("🇲🇽" if movie.get("language") in ("es",) else "🌐")
        st.markdown(
            f"**{movie['title']}**"
            + (f"  ·  *{movie['title_orig']}*" if movie.get("title_orig") and
               movie["title_orig"] != movie["title"] else "")
        )
        st.markdown(
            f'<span class="mh-badge mh-badge-purple">{movie.get("year","")}</span> '
            f'<span class="mh-badge mh-badge-yellow">⭐ {movie["rating"]}</span> '
            f'<span class="mh-badge mh-badge-blue">{lang_tag} {movie.get("language","").upper()}</span> '
            f'<span class="mh-badge mh-badge-green">{movie.get("votes",0):,} votos</span>',
            unsafe_allow_html=True,
        )
        if movie.get("overview") and not compact:
            st.markdown(
                f'<div style="color:#8888b0;font-size:0.87rem;margin-top:8px;line-height:1.6;">'
                f'{movie["overview"]}</div>',
                unsafe_allow_html=True,
            )


def _render_torrents(good_torrents: list, blocked_torrents: list,
                     movie: dict, movies_dir: Path,
                     show_blocked: bool, key_prefix: str):
    """
    Muestra la lista unificada y ordenada de torrents (TPB + YTS).
    good_torrents ya viene ordenada por score compuesto (mejor primero).
    El primer elemento lleva badge "⭐ Mejor opción".
    """
    mag_path = movies_dir / "magnets_movies.txt"

    if not good_torrents and not blocked_torrents:
        title_q = _uparse_mod.quote_plus(movie.get("title", ""))
        year_q  = str(movie.get("year", ""))
        q_full  = _uparse_mod.quote_plus(f"{movie.get('title','')} {year_q}".strip())
        st.warning("Sin torrents encontrados. Prueba buscarlo manualmente en estas fuentes:")
        st.markdown(
            f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;">'
            f'<a href="https://www.1337x.to/search/{q_full}/1/" target="_blank" '
            f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
            f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🔎 1337x</a>'
            f'<a href="https://torrentgalaxy.to/torrents.php?search={title_q}" target="_blank" '
            f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
            f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🌌 TorrentGalaxy</a>'
            f'<a href="https://knaben.eu/search/?query={q_full}" target="_blank" '
            f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
            f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🔍 Knaben</a>'
            f'<a href="https://torrentz2.nz/search?q={q_full}" target="_blank" '
            f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
            f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">⚡ Torrentz2</a>'
            f'<a href="https://www.magnetdl.com/search/?q={q_full}" target="_blank" '
            f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
            f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🧲 MagnetDL</a>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Resumen disponibilidad ────────────────────────────────────────────────
    has_lat    = any(t.get("s_score", 0) == 2  for t in good_torrents)
    has_esp    = any(t.get("s_score", 0) >= 1  for t in good_torrents)
    has_hd     = any("1080p" in t.get("q_label","") or "4K" in t.get("q_label","")
                     for t in good_torrents)
    has_yts    = any(t.get("source") == "YTS"    for t in good_torrents)
    has_knaben = any(t.get("source") == "Knaben" for t in good_torrents)

    pills = []
    if has_lat:    pills.append('<span class="mh-badge mh-badge-green">🇲🇽 Latino disponible</span>')
    elif has_esp:  pills.append('<span class="mh-badge mh-badge-blue">🌎 Español disponible</span>')
    else:          pills.append('<span class="mh-badge mh-badge-red">⚠️ Sin audio latino</span>')
    if has_hd:     pills.append('<span class="mh-badge mh-badge-purple">🎥 HD disponible</span>')
    if has_yts:    pills.append('<span class="mh-badge mh-badge-yellow">🎬 YTS incluido</span>')
    if has_knaben: pills.append('<span class="mh-badge mh-badge-blue">🔍 Knaben incluido</span>')
    st.markdown(" ".join(pills) + "<br>", unsafe_allow_html=True)

    # ── Lista unificada ───────────────────────────────────────────────────────
    st.markdown(
        f'<div class="mh-section-title">Resultados ordenados — mejor primero '
        f'({len(good_torrents)} opciones)</div>',
        unsafe_allow_html=True,
    )

    for t in good_torrents:
        rank      = t.get("rank", 0)
        is_best   = t.get("best", False)
        seeds     = t.get("seeds", 0)
        is_dead   = seeds == 0
        saved_key = f"saved_{key_prefix}_{rank}"
        is_saved  = st.session_state.get(saved_key, False)
        mag       = t["magnet"]
        s         = t.get("s_score", 0)
        source    = t.get("source", "TPB")

        # ── Badge de idioma / fuente ──────────────────────────────────────────
        if is_dead:
            lang_badge, border = "⚫ Sin seeds",              "rgba(80,80,80,0.2)"
        elif source == "YTS":
            lang_badge, border = "🎬 YTS · Alta calidad",    "rgba(251,191,36,0.5)"
        elif source == "Knaben":
            lang_badge, border = "🔍 Knaben DHT",            "rgba(96,165,250,0.4)"
        elif s == 2:
            lang_badge, border = "🇲🇽 Latino",               "rgba(52,211,153,0.55)"
        elif s == 1:
            lang_badge, border = "🌎 Español",                "rgba(96,165,250,0.5)"
        elif s == -1:
            lang_badge, border = "🇪🇸 España",                "rgba(180,100,100,0.35)"
        else:
            lang_badge, border = "🔤 Sin info idioma",       "rgba(100,100,130,0.25)"

        # ── Encabezado de la tarjeta ──────────────────────────────────────────
        best_ribbon = ""
        if is_best:
            best_ribbon = (
                '<span style="background:linear-gradient(135deg,#f59e0b,#d97706);'
                'color:#fff;font-size:0.7rem;font-weight:800;padding:2px 10px;'
                'border-radius:20px;margin-right:8px;letter-spacing:0.5px;">'
                '⭐ MEJOR OPCIÓN</span>'
            )
        elif is_dead:
            best_ribbon = (
                '<span style="background:rgba(60,60,60,0.6);'
                'color:#666;font-size:0.7rem;font-weight:700;padding:2px 10px;'
                'border-radius:20px;margin-right:8px;">'
                '💀 Sin seeds — no disponible</span>'
            )

        rank_txt = f'<span style="color:#44448a;font-size:0.75rem;">#{rank+1}</span>'

        with st.container(border=True):
            # Nombre + ribbon
            st.markdown(
                f'<div style="border-left:4px solid {border};padding-left:10px;'
                f'margin-bottom:6px;">'
                f'{best_ribbon}{rank_txt} '
                f'<span style="font-weight:700;font-size:0.88rem;color:#e2e2f0;">'
                f'{t["name"][:100]}</span></div>',
                unsafe_allow_html=True,
            )

            col_meta, col_actions = st.columns([3, 3])

            with col_meta:
                q      = t.get("q_score", 0)
                res    = t.get("res", "")
                codec  = t.get("codec", "")
                audio  = t.get("audio", "")
                src    = t.get("src", source)

                # ── Pastilla de resolución ────────────────────────────────────
                res_colors = {
                    "4K":    ("linear-gradient(135deg,#7c3aed,#a855f7)", "#fff"),
                    "1080p": ("linear-gradient(135deg,#1d4ed8,#3b82f6)", "#fff"),
                    "720p":  ("linear-gradient(135deg,#0369a1,#38bdf8)", "#fff"),
                    "480p":  ("rgba(80,80,100,0.5)",                     "#aaa"),
                    "SD":    ("rgba(60,60,80,0.4)",                      "#888"),
                }
                res_bg, res_fg = res_colors.get(res, ("rgba(80,80,100,0.4)", "#aaa"))

                # ── Pastilla de fuente (BluRay/WEB-DL/etc.) ───────────────────
                src_colors = {
                    "REMUX":  "#d97706", "BLURAY": "#7c3aed", "BLU-RAY": "#7c3aed",
                    "WEB-DL": "#1d4ed8", "WEBDL":  "#1d4ed8", "WEBRIP": "#0369a1",
                    "WEB":    "#0369a1", "AMZN":   "#f97316", "NFLX":   "#dc2626",
                    "DSNP":   "#1e40af", "HDTV":   "#374151", "HDRIP":  "#374151",
                    "DVDRIP": "#6b7280", "YTS":    "#d97706",
                }
                src_clr = src_colors.get(src.upper(), "#4b5563")

                # ── Pastilla de codec ─────────────────────────────────────────
                codec_badge = ""
                if codec:
                    codec_clr = "#6366f1" if "265" in codec or "AV1" in codec else "#4b5563"
                    codec_badge = (
                        f'<span style="background:{codec_clr};color:#fff;font-size:0.65rem;'
                        f'font-weight:700;padding:1px 7px;border-radius:4px;">{codec}</span>&nbsp;'
                    )

                # ── Pastilla de audio ─────────────────────────────────────────
                audio_badge = ""
                if audio:
                    audio_badge = (
                        f'<span style="background:rgba(16,185,129,0.2);color:#34d399;'
                        f'font-size:0.65rem;font-weight:600;padding:1px 7px;border-radius:4px;">'
                        f'🔊 {audio}</span>&nbsp;'
                    )

                st.markdown(
                    # Fila 1: idioma + formato
                    f'<div style="margin-bottom:6px;">'
                    f'<b style="color:#c4b5fd;font-size:0.82rem;">{lang_badge}</b>'
                    f'&nbsp;&nbsp;'
                    # Pastilla resolución grande
                    f'<span style="background:{res_bg};color:{res_fg};font-size:0.75rem;'
                    f'font-weight:900;padding:2px 10px;border-radius:6px;letter-spacing:0.5px;">'
                    f'{res}</span>'
                    f'&nbsp;'
                    # Pastilla fuente
                    f'<span style="background:{src_clr};color:#fff;font-size:0.65rem;'
                    f'font-weight:700;padding:2px 8px;border-radius:4px;">{src or source}</span>'
                    f'</div>'
                    # Fila 2: codec + audio
                    f'<div style="margin-bottom:4px;">'
                    f'{codec_badge}{audio_badge}'
                    f'</div>'
                    # Fila 3: seeds / size
                    f'<div style="font-size:0.8rem;color:#8888b0;">'
                    f'{t["seed_icon"]} <b style="color:#e2e2f0;">{t["seeds"]}</b> seeds'
                    f'&nbsp;·&nbsp;{t["leeches"]} leechers'
                    f'&nbsp;·&nbsp;💾 <b style="color:#c4b5fd;">{t["size"]}</b>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            with col_actions:
                # ── Abrir en uTorrent (magnet link como href) ─────────────────
                btn_bg = "linear-gradient(135deg,#f59e0b,#d97706)" if is_best \
                         else "linear-gradient(135deg,#7050ff,#a855f7)"
                st.markdown(
                    f'<a href="{mag}" '
                    f'style="display:block;text-align:center;'
                    f'background:{btn_bg};color:#fff;font-weight:700;'
                    f'font-size:0.84rem;border-radius:10px;padding:9px 0;'
                    f'text-decoration:none;margin-bottom:6px;">'
                    f'▶ Abrir en uTorrent Web</a>',
                    unsafe_allow_html=True,
                )

                # ── Guardar magnet ────────────────────────────────────────────
                save_label = "✅ Guardado" if is_saved else "💾 Guardar magnet"
                if st.button(save_label, key=f"btn_save_{key_prefix}_{rank}",
                             use_container_width=True, disabled=is_saved):
                    mag_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(mag_path, "a", encoding="utf-8") as fh:
                        fh.write(
                            f"# {movie.get('title','')} ({movie.get('year','')}) "
                            f"— {t['q_label']} — {lang_badge} — {source}\n"
                            f"{mag}\n\n"
                        )
                    _record_download("Película (magnet)", 1,
                                     f"{movie.get('title','')} {t.get('q_label','')}")
                    st.session_state[saved_key] = True

            # ── Magnet expandible ─────────────────────────────────────────────
            with st.expander("🔗 Ver magnet link"):
                st.code(mag, language="")
                st.caption(
                    "Pega este link en uTorrent Web → botón ➕ → "
                    "'Agregar enlace de torrent'."
                )

        if source == "YTS" and rank == list(
            t2 for t2 in good_torrents if t2.get("source") == "YTS"
        )[0].get("rank", -1):
            st.caption(
                "⚠️ Los resultados de YTS no incluyen audio en español. "
                "Descarga subtítulos latinos en [Subdivx.com](https://www.subdivx.com)."
            )

    # ── Fallback links cuando hay muy pocos resultados ───────────────────────
    if len(good_torrents) < 3:
        title_q = _uparse_mod.quote_plus(movie.get("title", ""))
        year_q  = str(movie.get("year", ""))
        q_full  = _uparse_mod.quote_plus(f"{movie.get('title','')} {year_q}".strip())
        with st.expander("🔎 ¿Pocos resultados? Buscar en más fuentes"):
            st.caption("Estas fuentes externas pueden tener más opciones para esta película:")
            st.markdown(
                f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:6px;">'
                f'<a href="https://www.1337x.to/search/{q_full}/1/" target="_blank" '
                f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
                f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🔎 1337x</a>'
                f'<a href="https://torrentgalaxy.to/torrents.php?search={title_q}" target="_blank" '
                f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
                f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🌌 TorrentGalaxy</a>'
                f'<a href="https://knaben.eu/search/?query={q_full}" target="_blank" '
                f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
                f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🔍 Knaben</a>'
                f'<a href="https://torrentz2.nz/search?q={q_full}" target="_blank" '
                f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
                f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">⚡ Torrentz2</a>'
                f'<a href="https://www.magnetdl.com/search/?q={q_full}" target="_blank" '
                f'   style="background:rgba(120,80,255,0.15);border:1px solid rgba(120,80,255,0.35);'
                f'   color:#c4b5fd;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;">🧲 MagnetDL</a>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Bloqueados ────────────────────────────────────────────────────────────
    if show_blocked and blocked_torrents:
        with st.expander(f"🚫 Filtrados por mala calidad — {len(blocked_torrents)}"):
            st.caption("CAM · TS · HDCAM · DVDSCR — grabaciones de cine o ilegibles.")
            for t in blocked_torrents:
                st.markdown(
                    f'<div style="color:#6b2020;font-size:0.8rem;padding:3px 0;">'
                    f'🚫 {t["name"][:95]}'
                    f'<span style="color:#552222;"> · {t["seeds"]} seeds</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def page_historial():
    """Feature #6 — Download history tracker."""
    _page_header("📋", "Historial", "Registro de todas las descargas y operaciones")
    history = _load_history()

    if not history:
        st.info("Aún no hay historial. Las descargas aparecerán aquí automáticamente.")
        return

    # ── Métricas rápidas ──────────────────────────────────────────────────────
    from collections import Counter
    kind_counts = Counter(e["kind"] for e in history)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de operaciones", len(history))
    col2.metric("Música", kind_counts.get("Música", 0) + kind_counts.get("Música (manual)", 0))
    col3.metric("Películas", kind_counts.get("Película", 0) + kind_counts.get("Película (magnet)", 0))
    col4.metric("Otros", len(history) - kind_counts.get("Música", 0) -
                kind_counts.get("Música (manual)", 0) - kind_counts.get("Película", 0) -
                kind_counts.get("Película (magnet)", 0))

    st.markdown("---")

    # ── Filtros ───────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        search_h = st.text_input("Filtrar", placeholder="buscar en historial...", key="hist_search")
    with col_f2:
        kinds = ["Todos"] + sorted(set(e["kind"] for e in history))
        kind_filter = st.selectbox("Tipo", kinds, key="hist_kind")

    filtered_h = history[::-1]  # más reciente primero
    if kind_filter != "Todos":
        filtered_h = [e for e in filtered_h if e["kind"] == kind_filter]
    if search_h:
        q = search_h.lower()
        filtered_h = [e for e in filtered_h if q in e.get("detail","").lower()
                      or q in e.get("kind","").lower()]

    st.caption(f"{len(filtered_h)} registros")

    # ── Tabla ─────────────────────────────────────────────────────────────────
    import pandas as pd
    if filtered_h:
        df_h = pd.DataFrame(filtered_h)[["date", "kind", "count", "detail"]]
        df_h.columns = ["Fecha", "Tipo", "Cantidad", "Detalle"]
        st.dataframe(df_h, use_container_width=True, hide_index=True)

        # Feature #12: export history
        import io as _io_h, csv as _csv_h
        _hbuf = _io_h.StringIO()
        df_h.to_csv(_hbuf, index=False)
        st.download_button("Exportar historial a CSV", _hbuf.getvalue().encode(),
                           "historial.csv", mime="text/csv", key="hist_csv")

    # ── Borrar historial ──────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("Limpiar historial completo", key="hist_clear"):
        HISTORY_FILE.write_text("[]", encoding="utf-8")
        st.success("Historial borrado")
        st.rerun()


def page_estadisticas():
    """Feature #10 — Library statistics dashboard."""
    _page_header("📈", "Estadísticas", "Métricas de tu biblioteca y actividad de descargas")
    cfg = load_config()
    history = _load_history()

    import pandas as pd
    from collections import Counter

    # ── Biblioteca actual ─────────────────────────────────────────────────────
    st.markdown('<div class="mh-section-title">Biblioteca actual</div>', unsafe_allow_html=True)

    music_folder  = Path(cfg.get("music_folder", ""))
    ebooks_folder = Path(cfg.get("ebooks_folder", ""))
    movies_folder = Path(cfg.get("movies_folder", ""))

    col1, col2, col3, col4 = st.columns(4)
    mp3s  = list(music_folder.rglob("*.mp3"))  if music_folder.exists()  else []
    flacs = list(music_folder.rglob("*.flac")) if music_folder.exists()  else []
    epubs = list(ebooks_folder.rglob("*.epub")) + list(ebooks_folder.rglob("*.mobi")) \
            if ebooks_folder.exists() else []
    t_music  = BASE_DIR / "output" / "torrents"
    t_ebooks = BASE_DIR / "output_ebooks" / "torrents"
    n_torr_m = len(list(t_music.glob("*.torrent")))  if t_music.exists()  else 0
    n_torr_e = len(list(t_ebooks.glob("*.torrent"))) if t_ebooks.exists() else 0

    col1.metric("MP3s", f"{len(mp3s):,}")
    col2.metric("FLACs", f"{len(flacs):,}")
    col3.metric("Ebooks", f"{len(epubs):,}")
    col4.metric("Torrents generados", f"{n_torr_m + n_torr_e:,}")

    if mp3s:
        total_gb = sum(f.stat().st_size for f in mp3s) / 1e9
        st.metric("Tamaño música", f"{total_gb:.1f} GB")

    # ── Actividad por tipo ────────────────────────────────────────────────────
    if history:
        st.markdown('<div class="mh-section-title">Actividad de descargas</div>',
                    unsafe_allow_html=True)

        # Actividad por día
        by_date = Counter(e["date"][:10] for e in history)
        if len(by_date) > 1:
            df_dates = pd.DataFrame(
                sorted(by_date.items()), columns=["Fecha", "Operaciones"]
            ).set_index("Fecha")
            st.bar_chart(df_dates, color="#7050ff", height=200)

        # Tipos
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown('<div class="mh-section-title">Por tipo</div>', unsafe_allow_html=True)
            kind_df = pd.DataFrame(
                Counter(e["kind"] for e in history).most_common(),
                columns=["Tipo", "Operaciones"],
            )
            st.dataframe(kind_df, use_container_width=True, hide_index=True)

        with col_t2:
            # Tasa de éxito música (si hay log de búsqueda)
            log_path = BASE_DIR / "output" / "lastfm_search_log.json"
            if log_path.exists():
                st.markdown('<div class="mh-section-title">Última búsqueda músical</div>',
                            unsafe_allow_html=True)
                log_data = json.loads(log_path.read_text())
                new_c    = log_data.get("new", 0)
                cached_c = log_data.get("cached", 0)
                nf_c     = log_data.get("not_found", 0)
                total_c  = new_c + cached_c + nf_c
                if total_c:
                    success_pct = round((new_c + cached_c) / total_c * 100, 1)
                    st.metric("Tasa de éxito", f"{success_pct}%")
                    st.metric("Nuevas / Cacheadas / No encontradas",
                              f"{new_c} / {cached_c} / {nf_c}")
                    df_status = pd.DataFrame({
                        "Estado": ["Nuevas", "Cacheadas", "No encontradas"],
                        "Cantidad": [new_c, cached_c, nf_c],
                    })
                    st.bar_chart(df_status.set_index("Estado"), color="#7050ff", height=160)
    else:
        st.info("Sin historial de actividad todavía. Las estadísticas aparecerán tras realizar descargas.")

    # ── Top artistas en la biblioteca ─────────────────────────────────────────
    if mp3s:
        st.markdown('<div class="mh-section-title">Artistas en biblioteca (por nº de MP3s)</div>',
                    unsafe_allow_html=True)
        artist_counter: Counter = Counter()
        for mp3 in mp3s[:2000]:
            parts = mp3.stem.split(" - ")
            artist = parts[0].strip() if len(parts) >= 2 else "Desconocido"
            artist_counter[artist] += 1
        top_artists = artist_counter.most_common(20)
        df_art = pd.DataFrame(top_artists, columns=["Artista", "MP3s"])
        st.bar_chart(df_art.set_index("Artista"), color="#a855f7", height=300)


def page_roms():
    _page_header("🎮", "ROMs", "Busca ROMs para Miyoo A30 y otras consolas · TPB · Knaben · Archive.org")

    # ── Plataformas compatibles con Miyoo A30 ─────────────────────────────────
    PLATFORMS = {
        "Game Boy Advance (GBA)":     {"query": "gba roms no-intro", "archive": "GBA", "tpb_cat": 404},
        "Game Boy / GBC":             {"query": "gameboy color roms no-intro", "archive": "GBC", "tpb_cat": 404},
        "Super Nintendo (SNES)":      {"query": "snes roms no-intro", "archive": "SNES", "tpb_cat": 404},
        "Nintendo NES / Famicom":     {"query": "nes famicom roms no-intro", "archive": "NES", "tpb_cat": 404},
        "PlayStation 1 (PS1/PSX)":    {"query": "psx ps1 roms redump", "archive": "PS1", "tpb_cat": 404},
        "Sega Genesis / Mega Drive":  {"query": "sega genesis mega drive roms no-intro", "archive": "genesis", "tpb_cat": 404},
        "Sega Game Gear":             {"query": "game gear roms no-intro", "archive": "GameGear", "tpb_cat": 404},
        "Nintendo 64 (N64)":          {"query": "n64 roms no-intro", "archive": "N64", "tpb_cat": 404},
        "Neo Geo / MAME Arcade":      {"query": "mame arcade roms", "archive": "MAME", "tpb_cat": 404},
        "Pokémon (todos los juegos)": {"query": "pokemon rom gba gbc nds complete", "archive": "pokemon", "tpb_cat": 404},
    }

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _rom_size(b):
        try:
            b = int(b)
            for u in ("B", "KB", "MB", "GB"):
                if b < 1024: return f"{b:.0f} {u}"
                b //= 1024
            return f"{b:.1f} TB"
        except: return "?"

    def _rom_magnet(r):
        ih   = r.get("info_hash", "")
        name = _uparse_mod.quote(r.get("name", ""))
        tr   = ("tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
                "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
                "&tr=udp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce")
        return f"magnet:?xt=urn:btih:{ih}&dn={name}&{tr}"

    def _knaben_roms(q, n=15):
        try:
            url = "https://knaben.eu/api/v1/search?" + _uparse_mod.urlencode({
                "search": q, "orderBy": "seeders", "orderType": "desc", "size": n,
            })
            req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _ureq_mod.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            hits = data.get("hits") or []
            out = []
            for h in hits:
                ih    = (h.get("info_hash") or "").lower()
                name  = h.get("title") or h.get("name") or ""
                seeds = int(h.get("seeders") or 0)
                size_b= int(h.get("bytes") or 0)
                if not ih or not name: continue
                out.append({"name": name, "seeders": seeds, "leechers": int(h.get("leechers") or 0),
                            "size": size_b, "info_hash": ih, "source": "Knaben"})
            return out[:n]
        except Exception:
            return []

    def _archive_search(q, n=8):
        """Search Internet Archive for ROM sets."""
        try:
            url = "https://archive.org/advancedsearch.php?" + _uparse_mod.urlencode({
                "q": f"{q} mediatype:software",
                "fl[]": "identifier,title,description,downloads,item_size",
                "sort[]": "downloads desc",
                "rows": n, "page": 1, "output": "json",
            })
            req = _ureq_mod.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _ureq_mod.urlopen(req, timeout=12) as r:
                data = json.loads(r.read())
            docs = (data.get("response") or {}).get("docs") or []
            out = []
            for d in docs:
                ident = d.get("identifier", "")
                title = d.get("title", ident)
                dl    = d.get("downloads", 0)
                size_b= d.get("item_size", 0)
                if not ident: continue
                out.append({
                    "name": title[:120],
                    "identifier": ident,
                    "downloads": dl,
                    "size": size_b,
                    "url": f"https://archive.org/details/{ident}",
                    "source": "Archive.org",
                })
            return out[:n]
        except Exception:
            return []

    # ── Top juegos por plataforma (curados) ──────────────────────────────────
    TOP_GAMES = {
        "Game Boy Advance (GBA)": [
            "Pokemon FireRed GBA", "Pokemon Emerald GBA", "Pokemon Ruby GBA",
            "The Legend of Zelda Minish Cap GBA", "Metroid Fusion GBA",
            "Castlevania Aria of Sorrow GBA", "Golden Sun GBA",
            "Final Fantasy VI Advance GBA", "Fire Emblem GBA",
            "Mega Man Zero GBA", "Mother 3 GBA", "Kirby Amazing Mirror GBA",
            "Sonic Advance GBA", "Mario Kart Super Circuit GBA",
            "Super Mario World GBA", "Dragon Ball Z GBA",
        ],
        "Game Boy / GBC": [
            "Pokemon Gold GBC", "Pokemon Silver GBC", "Pokemon Crystal GBC",
            "The Legend of Zelda Oracle of Ages GBC",
            "The Legend of Zelda Oracle of Seasons GBC",
            "Metal Gear Solid GBC", "Dragon Warrior Monsters GBC",
            "Tetris GB", "Kirby Dream Land GB", "Super Mario Land 2 GB",
            "Donkey Kong Land GB", "Wario Land GB",
        ],
        "Super Nintendo (SNES)": [
            "Chrono Trigger SNES", "Super Metroid SNES",
            "The Legend of Zelda A Link to the Past SNES",
            "Final Fantasy VI SNES", "Super Mario World SNES",
            "Donkey Kong Country SNES", "Street Fighter II SNES",
            "Mega Man X SNES", "EarthBound SNES", "Contra III SNES",
            "Castlevania Super Metroid SNES", "Secret of Mana SNES",
            "Kirby Super Star SNES", "Super Mario RPG SNES",
            "Star Fox SNES", "Mortal Kombat SNES",
        ],
        "Nintendo NES / Famicom": [
            "Super Mario Bros 3 NES", "Mega Man 2 NES",
            "The Legend of Zelda NES", "Contra NES",
            "Castlevania NES", "Metroid NES", "Tecmo Super Bowl NES",
            "Ninja Gaiden NES", "DuckTales NES", "Batman NES",
            "Battletoads NES", "Mike Tyson Punch-Out NES",
            "Final Fantasy NES", "Kirby Adventure NES",
        ],
        "PlayStation 1 (PS1/PSX)": [
            "Final Fantasy VII PS1", "Metal Gear Solid PS1",
            "Castlevania Symphony of the Night PS1",
            "Crash Bandicoot PS1", "Spyro the Dragon PS1",
            "Tekken 3 PS1", "Resident Evil 2 PS1",
            "Tomb Raider PS1", "Gran Turismo 2 PS1",
            "Silent Hill PS1", "Vagrant Story PS1",
            "Chrono Cross PS1", "Final Fantasy IX PS1",
            "Twisted Metal 2 PS1", "Tony Hawk Pro Skater 2 PS1",
        ],
        "Sega Genesis / Mega Drive": [
            "Sonic the Hedgehog 2 Genesis", "Streets of Rage 2 Genesis",
            "Mortal Kombat Genesis", "Aladdin Genesis",
            "The Lion King Genesis", "Contra Hard Corps Genesis",
            "Gunstar Heroes Genesis", "Phantasy Star IV Genesis",
            "Earthworm Jim Genesis", "Comix Zone Genesis",
            "Sonic & Knuckles Genesis", "Road Rash Genesis",
        ],
        "Sega Game Gear": [
            "Sonic the Hedgehog Game Gear", "Mortal Kombat Game Gear",
            "Columns Game Gear", "Ristar Game Gear",
            "Castle of Illusion Game Gear", "Shinobi Game Gear",
        ],
        "Nintendo 64 (N64)": [
            "Super Mario 64 N64", "The Legend of Zelda Ocarina of Time N64",
            "GoldenEye 007 N64", "Mario Kart 64 N64",
            "Super Smash Bros N64", "Banjo-Kazooie N64",
            "Donkey Kong 64 N64", "Star Fox 64 N64",
            "The Legend of Zelda Majoras Mask N64",
            "Perfect Dark N64", "Paper Mario N64",
        ],
        "Neo Geo / MAME Arcade": [
            "Metal Slug MAME", "Metal Slug 2 MAME", "Metal Slug 3 MAME",
            "King of Fighters 98 MAME", "Street Fighter III MAME",
            "Samurai Shodown MAME", "Garou Mark of the Wolves MAME",
            "Cadillacs and Dinosaurs MAME", "The Simpsons arcade MAME",
            "X-Men arcade MAME", "Captain Commando MAME",
        ],
        "Pokémon (todos los juegos)": [
            "Pokemon FireRed GBA", "Pokemon Emerald GBA", "Pokemon Crystal GBC",
            "Pokemon Gold GBC", "Pokemon Silver GBC",
            "Pokemon Ruby GBA", "Pokemon Sapphire GBA",
            "Pokemon Yellow GB", "Pokemon Blue GB",
            "Pokemon Diamond NDS", "Pokemon HeartGold NDS",
        ],
    }

    # ── Layout ────────────────────────────────────────────────────────────────
    tab_top, tab_plat, tab_buscar, tab_info = st.tabs([
        "🏆 Top juegos", "🕹️ Por plataforma", "🔎 Buscar juego", "ℹ️ Miyoo A30 info"
    ])

    # ── Tab 0: Top juegos por plataforma ─────────────────────────────────────
    with tab_top:
        st.markdown(
            "Selecciona una plataforma y haz clic en un juego para buscarlo "
            "directamente en TPB y Knaben."
        )

        top_plat_sel = st.selectbox(
            "Plataforma",
            list(TOP_GAMES.keys()),
            key="top_plat_sel",
        )

        top_fuente = st.selectbox(
            "Fuente",
            ["Todas 🔍", "Knaben DHT 🔗", "The Pirate Bay 🏴", "Archive.org 📦"],
            key="top_fuente",
        )

        st.markdown("---")

        juegos = TOP_GAMES.get(top_plat_sel, [])
        cols_per_row = 3
        rows = [juegos[i:i+cols_per_row] for i in range(0, len(juegos), cols_per_row)]

        if "top_selected_game" not in st.session_state:
            st.session_state.top_selected_game = None

        for row in rows:
            cols = st.columns(cols_per_row)
            for col, game in zip(cols, row):
                with col:
                    if st.button(game, key=f"top_{game}", use_container_width=True):
                        st.session_state.top_selected_game = game

        # ── Resultados del juego seleccionado ─────────────────────────────
        if st.session_state.top_selected_game:
            q_top = st.session_state.top_selected_game
            st.markdown(f"---\n#### Resultados para: **{q_top}**")

            usar_tpb_top     = top_fuente in ("Todas 🔍", "The Pirate Bay 🏴")
            usar_knaben_top  = top_fuente in ("Todas 🔍", "Knaben DHT 🔗")
            usar_archive_top = top_fuente in ("Todas 🔍", "Archive.org 📦")

            tpb_top, knaben_top, archive_top = [], [], []
            with st.spinner(f"Buscando «{q_top}»…"):
                if usar_tpb_top:
                    raw_top = _tpb_search_cached(q_top, 404, 10)
                    tpb_top = [{**r, "source": "TPB"} for r in raw_top]
                if usar_knaben_top:
                    knaben_top = _knaben_roms(q_top, 10)
                if usar_archive_top:
                    archive_top = _archive_search(q_top, 5)

            seen_top, results_top = set(), []
            for r in knaben_top + tpb_top:
                ih = r.get("info_hash", "")
                if ih and ih in seen_top: continue
                seen_top.add(ih)
                results_top.append(r)
            results_top.sort(key=lambda r: int(r.get("seeders", 0)), reverse=True)

            if not results_top and not archive_top:
                st.warning("Sin resultados. Prueba en otra fuente.")

            for i, r in enumerate(results_top):
                name  = r.get("name", "")
                seeds = int(r.get("seeders", 0))
                size  = _rom_size(r.get("size", 0))
                mag   = _rom_magnet(r)
                sc    = "🟢" if seeds >= 10 else ("🟡" if seeds >= 3 else "🔴")
                src_b = {"TPB": "🏴 TPB", "Knaben": "🔗 Knaben"}.get(r.get("source",""), r.get("source",""))
                with st.container(border=True):
                    c1, c2, c3 = st.columns([5, 2, 2])
                    with c1:
                        st.markdown(f"**{name[:80]}**")
                        st.caption(src_b)
                    with c2:
                        st.caption(f"{sc} {seeds} seeds · 💾 {size}")
                    with c3:
                        _magnet_button("🧲 Magnet", mag)

            for b in archive_top:
                sz  = _rom_size(b.get("size", 0))
                iid = b["identifier"]
                torrent_url_top = f"https://archive.org/download/{iid}/{iid}_archive.torrent"
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 1, 1])
                    with c1:
                        st.markdown(f"**{b['name'][:90]}**")
                        st.caption(f"📦 Archive.org · 💾 {sz}")
                    with c2:
                        st.link_button("⬇ .torrent", torrent_url_top, use_container_width=True)
                    with c3:
                        st.link_button("🌐 Ver", b["url"], use_container_width=True)

    # ── Tab 1: Por plataforma ─────────────────────────────────────────────────
    with tab_plat:
        st.markdown(
            "Selecciona una plataforma para buscar **colecciones completas de ROMs** "
            "(No-Intro / Redump). Ideal para llenar tu Miyoo A30."
        )

        col_plat, col_src = st.columns([3, 1])
        with col_plat:
            plat_name = st.selectbox(
                "Plataforma",
                list(PLATFORMS.keys()),
                key="rom_plat",
            )
        with col_src:
            rom_fuente = st.selectbox(
                "Fuente",
                ["Todas 🔍", "Knaben DHT 🔗", "The Pirate Bay 🏴", "Archive.org 📦"],
                key="rom_fuente",
            )

        col_n, col_quality = st.columns(2)
        with col_n:
            n_rom = st.slider("Resultados por fuente", 5, 30, 12, key="rom_n")
        with col_quality:
            solo_nointro = st.toggle(
                "Preferir No-Intro / Redump",
                value=True,
                key="rom_nointro",
                help="No-Intro y Redump son las colecciones más limpias y verificadas de ROMs.",
            )

        buscar_plat = st.button("🔍 Buscar ROMs", type="primary",
                                use_container_width=True, key="rom_buscar_plat")

        if buscar_plat:
            plat = PLATFORMS[plat_name]
            q    = plat["query"]
            if solo_nointro and "no-intro" not in q and "redump" not in q:
                q = q + " no-intro"

            tpb_res, knaben_res, archive_res = [], [], []

            usar_tpb     = rom_fuente in ("Todas 🔍", "The Pirate Bay 🏴")
            usar_knaben  = rom_fuente in ("Todas 🔍", "Knaben DHT 🔗")
            usar_archive = rom_fuente in ("Todas 🔍", "Archive.org 📦")

            with st.spinner(f"Buscando ROMs de {plat_name}…"):
                if usar_tpb:
                    raw = _tpb_search_cached(q, plat["tpb_cat"], n_rom)
                    tpb_res = [{**r, "source": "TPB"} for r in raw]
                if usar_knaben:
                    knaben_res = _knaben_roms(q, n_rom)
                if usar_archive:
                    archive_res = _archive_search(plat_name, n_rom)

            # ── Resultados TPB + Knaben ────────────────────────────────────
            torrent_results = []
            seen = set()
            for r in knaben_res + tpb_res:
                ih = r.get("info_hash", "")
                if ih and ih in seen: continue
                seen.add(ih)
                torrent_results.append(r)
            torrent_results.sort(key=lambda r: int(r.get("seeders", 0)), reverse=True)

            if torrent_results:
                st.markdown(f"#### 🧲 Torrents — {len(torrent_results)} resultados")
                for i, r in enumerate(torrent_results):
                    name  = r.get("name", "")
                    seeds = int(r.get("seeders", 0))
                    size  = _rom_size(r.get("size", 0))
                    mag   = _rom_magnet(r)
                    sc    = "🟢" if seeds >= 10 else ("🟡" if seeds >= 3 else "🔴")
                    src_b = {"TPB": "🏴 TPB", "Knaben": "🔗 Knaben"}.get(r.get("source",""), r.get("source",""))
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([5, 2, 2])
                        with c1:
                            st.markdown(f"**{name[:80]}**")
                            st.caption(src_b)
                        with c2:
                            st.caption(f"{sc} {seeds} seeds")
                            st.caption(f"💾 {size}")
                        with c3:
                            _magnet_button("🧲 Magnet", mag)

            # ── Resultados Archive.org ─────────────────────────────────────
            if archive_res:
                st.markdown(f"#### 📦 Internet Archive — {len(archive_res)} colecciones")
                st.caption("Colecciones No-Intro/Redump archivadas. El torrent descarga todos los archivos del pack.")
                for b in archive_res:
                    dl  = f"{b['downloads']:,}" if b.get("downloads") else "?"
                    sz  = _rom_size(b.get("size", 0))
                    iid = b["identifier"]
                    torrent_url = f"https://archive.org/download/{iid}/{iid}_archive.torrent"
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([4, 1, 1])
                        with c1:
                            st.markdown(f"**{b['name'][:90]}**")
                            st.caption(f"📥 {dl} descargas · 💾 {sz}")
                        with c2:
                            st.link_button("⬇ .torrent",
                                           torrent_url,
                                           use_container_width=True,
                                           help="Descarga el archivo .torrent del pack completo")
                        with c3:
                            st.link_button("🌐 Ver",
                                           b["url"],
                                           use_container_width=True,
                                           help="Ver los archivos individuales en Archive.org")

            if not torrent_results and not archive_res:
                st.warning("Sin resultados. Prueba con otra fuente o plataforma.")

    # ── Tab 2: Búsqueda directa de juego ─────────────────────────────────────
    with tab_buscar:
        st.markdown(
            "Busca un **juego específico** por nombre. "
            "Usa el nombre en inglés para mejores resultados."
        )

        col_q2, col_src2 = st.columns([3, 1])
        with col_q2:
            rom_query = st.text_input(
                "Nombre del juego",
                placeholder="ej: Pokemon Fire Red, Zelda, Chrono Trigger...",
                key="rom_query",
            )
        with col_src2:
            rom_fuente2 = st.selectbox(
                "Fuente",
                ["Todas 🔍", "Knaben DHT 🔗", "The Pirate Bay 🏴", "Archive.org 📦"],
                key="rom_fuente2",
            )

        col_plat2, col_n2 = st.columns(2)
        with col_plat2:
            plat_hint = st.selectbox(
                "Plataforma (opcional)",
                ["Cualquiera"] + list(PLATFORMS.keys()),
                key="rom_plat2",
                help="Añade la plataforma al query para resultados más precisos.",
            )
        with col_n2:
            n_rom2 = st.slider("Resultados por fuente", 5, 30, 15, key="rom_n2")

        # Sugerencias rápidas
        SUGERENCIAS_ROM = [
            "Pokemon Fire Red GBA", "Zelda Link to the Past SNES",
            "Chrono Trigger SNES", "Final Fantasy VI SNES",
            "Castlevania Symphony of the Night PS1",
            "Mega Man X SNES", "Street Fighter II SNES",
            "Super Mario World SNES", "Donkey Kong Country SNES",
            "Metal Slug Neo Geo", "Sonic the Hedgehog Genesis",
        ]

        def _set_rom_query(sug):
            st.session_state["rom_query"] = sug

        with st.expander("💡 Sugerencias de búsqueda"):
            sug_cols = st.columns(3)
            for j, sug in enumerate(SUGERENCIAS_ROM):
                sug_cols[j % 3].button(
                    sug, key=f"rom_sug_{j}",
                    on_click=_set_rom_query, args=(sug,),
                    use_container_width=True,
                )

        buscar_juego = st.button("🔍 Buscar juego", type="primary",
                                 use_container_width=True,
                                 disabled=not rom_query,
                                 key="rom_buscar_juego")

        if buscar_juego and rom_query:
            plat_suffix = ""
            if plat_hint != "Cualquiera":
                short = plat_hint.split("(")[0].strip().split("/")[0].strip()
                plat_suffix = f" {short.split()[-1]}"  # last word: GBA, SNES, PS1...
            q2 = rom_query + plat_suffix

            usar_tpb2     = rom_fuente2 in ("Todas 🔍", "The Pirate Bay 🏴")
            usar_knaben2  = rom_fuente2 in ("Todas 🔍", "Knaben DHT 🔗")
            usar_archive2 = rom_fuente2 in ("Todas 🔍", "Archive.org 📦")

            tpb_res2, knaben_res2, archive_res2 = [], [], []
            with st.spinner(f"Buscando «{q2}»…"):
                if usar_tpb2:
                    raw2 = _tpb_search_cached(q2, 404, n_rom2)
                    tpb_res2 = [{**r, "source": "TPB"} for r in raw2]
                if usar_knaben2:
                    knaben_res2 = _knaben_roms(q2, n_rom2)
                if usar_archive2:
                    archive_res2 = _archive_search(q2, 6)

            seen2, resultados2 = set(), []
            for r in knaben_res2 + tpb_res2:
                ih = r.get("info_hash", "")
                if ih and ih in seen2: continue
                seen2.add(ih)
                resultados2.append(r)
            resultados2.sort(key=lambda r: int(r.get("seeders", 0)), reverse=True)

            total2 = len(resultados2) + len(archive_res2)
            if total2 == 0:
                st.warning("Sin resultados. Prueba el nombre en inglés o sin la plataforma.")
            else:
                st.success(f"✅ {total2} resultados para **{q2}**")

            if resultados2:
                st.markdown(f"#### 🧲 Torrents — {len(resultados2)} resultados")
                for i, r in enumerate(resultados2):
                    name  = r.get("name", "")
                    seeds = int(r.get("seeders", 0))
                    size  = _rom_size(r.get("size", 0))
                    mag   = _rom_magnet(r)
                    sc    = "🟢" if seeds >= 10 else ("🟡" if seeds >= 3 else "🔴")
                    src_b = {"TPB": "🏴 TPB", "Knaben": "🔗 Knaben"}.get(r.get("source",""), r.get("source",""))
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([5, 2, 2])
                        with c1:
                            st.markdown(f"**{name[:80]}**")
                            st.caption(src_b)
                        with c2:
                            st.caption(f"{sc} {seeds} seeds")
                            st.caption(f"💾 {size}")
                        with c3:
                            _magnet_button("🧲 Magnet", mag)

            if archive_res2:
                st.markdown(f"#### 📦 Archive.org — {len(archive_res2)} resultados")
                for b in archive_res2:
                    sz  = _rom_size(b.get("size", 0))
                    iid = b["identifier"]
                    torrent_url2 = f"https://archive.org/download/{iid}/{iid}_archive.torrent"
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([4, 1, 1])
                        with c1:
                            st.markdown(f"**{b['name'][:90]}**")
                            st.caption(f"💾 {sz}")
                        with c2:
                            st.link_button("⬇ .torrent",
                                           torrent_url2,
                                           use_container_width=True,
                                           help="Descarga el .torrent del pack")
                        with c3:
                            st.link_button("🌐 Ver",
                                           b["url"],
                                           use_container_width=True,
                                           help="Ver archivos en Archive.org")

    # ── Tab 3: Info Miyoo A30 ─────────────────────────────────────────────────
    with tab_info:
        st.markdown("### Miyoo A30 — Sistemas compatibles")
        st.markdown(
            "El **Miyoo A30** corre **OnionOS** y soporta la mayoría de los "
            "sistemas listados abajo. Las colecciones **No-Intro** son las más "
            "recomendadas: sin duplicados, verificadas por checksum."
        )
        st.markdown("---")

        COMPAT = [
            ("🟢 Perfecto",  ["Game Boy (GB)", "Game Boy Color (GBC)", "Game Boy Advance (GBA)",
                               "NES / Famicom", "SNES / Super Famicom", "Sega Genesis",
                               "Sega Master System", "Game Gear", "Neo Geo Pocket"]),
            ("🟡 Bueno",     ["PlayStation 1 (PS1)", "Neo Geo (FBA)", "MAME Arcade",
                               "PC-Engine / TurboGrafx", "Atari Lynx", "WonderSwan"]),
            ("🔴 Limitado",  ["Nintendo 64 (N64)", "Sega CD", "Atari 5200/7800"]),
        ]
        for label, systems in COMPAT:
            st.markdown(f"**{label}**")
            cols = st.columns(3)
            for j, s in enumerate(systems):
                cols[j % 3].markdown(f"- {s}")
            st.markdown("")

        st.info(
            "**Tip:** Para PS1 usa colecciones **PBP** (formato comprimido) para ahorrar espacio. "
            "Para GBA busca siempre **No-Intro GBA** — incluye ~3 200 juegos en ~8 GB."
        )


def page_explorador():
    import os

    _page_header("📊", "Explorador de carpetas", "Visualiza el uso de disco por carpeta · navega nivel a nivel")
    cfg = load_config()

    # ── Selector de carpeta raíz ──────────────────────────────────────────────
    col_folder, col_ext = st.columns([3, 1])
    with col_folder:
        root_folder = st.text_input(
            "📁 Carpeta a explorar",
            value=st.session_state.get("exp_folder", cfg["music_folder"]),
            key="exp_folder_input",
        )
    with col_ext:
        ext_filter = st.selectbox(
            "Tipo de archivo",
            ["Todos", "MP3", "FLAC", "M4A", "WAV", "EPUB/MOBI"],
            key="exp_ext",
        )
    ext_map = {
        "Todos":       None,
        "MP3":         [".mp3"],
        "FLAC":        [".flac"],
        "M4A":         [".m4a"],
        "WAV":         [".wav"],
        "EPUB/MOBI":   [".epub", ".mobi", ".azw3"],
    }
    exts = ext_map[ext_filter]

    # Guarda la carpeta en session_state para navegación de drill-down
    if root_folder != st.session_state.get("exp_folder"):
        st.session_state.exp_folder     = root_folder
        st.session_state.exp_drill_path = root_folder

    if "exp_drill_path" not in st.session_state:
        st.session_state.exp_drill_path = root_folder

    root_path  = Path(root_folder)
    drill_path = Path(st.session_state.exp_drill_path)

    # Si el drill_path quedó fuera del root tras cambiar carpeta, resetea
    if not str(drill_path).startswith(str(root_path)):
        st.session_state.exp_drill_path = root_folder
        drill_path = root_path

    if not root_path.exists():
        st.warning("⚠️ La carpeta no existe. Verifica la ruta.")
        return

    # ── Accesos rápidos ───────────────────────────────────────────────────────
    quick_cols = st.columns(3)
    quick_folders = [
        ("🎵 Música",  cfg["music_folder"]),
        ("📚 Ebooks",  cfg["ebooks_folder"]),
        ("🏠 Home",    str(Path.home())),
    ]
    for i, (label, qpath) in enumerate(quick_folders):
        with quick_cols[i]:
            if st.button(label, use_container_width=True, key=f"quick_{i}"):
                st.session_state.exp_folder     = qpath
                st.session_state.exp_drill_path = qpath
                st.rerun()

    st.markdown("---")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def fmt_size(b: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    def count_and_size(folder: Path, extensions) -> tuple[int, int]:
        """Devuelve (nº archivos, tamaño total bytes)."""
        total_size  = 0
        total_files = 0
        try:
            for entry in os.scandir(folder):
                if entry.is_file(follow_symlinks=False):
                    if extensions is None or Path(entry.name).suffix.lower() in extensions:
                        total_size  += entry.stat(follow_symlinks=False).st_size
                        total_files += 1
                elif entry.is_dir(follow_symlinks=False):
                    s, n = count_and_size(Path(entry.path), extensions)
                    total_size  += s
                    total_files += n
        except PermissionError:
            pass
        return total_files, total_size

    # ── Breadcrumb ────────────────────────────────────────────────────────────
    rel_parts = []
    try:
        rel = drill_path.relative_to(root_path)
        rel_parts = rel.parts
    except ValueError:
        pass

    crumb_html = f'<span style="color:#5555a0;">📁 {root_path.name}</span>'
    for i, part in enumerate(rel_parts):
        crumb_html += f' <span style="color:#44448a;">/</span> <span style="color:#c4b5fd;">{part}</span>'
    st.markdown(f'<div style="font-size:0.85rem;margin-bottom:8px;">{crumb_html}</div>',
                unsafe_allow_html=True)

    # Botón subir nivel
    if drill_path != root_path:
        if st.button("⬆ Subir nivel", key="go_up"):
            st.session_state.exp_drill_path = str(drill_path.parent)
            st.rerun()

    # ── Escanear subcarpetas directas ─────────────────────────────────────────
    with st.spinner("Calculando tamaños..."):
        try:
            subdirs = sorted(
                [d for d in drill_path.iterdir() if d.is_dir() and not d.name.startswith(".")],
                key=lambda d: d.name,
            )
        except PermissionError:
            st.error("Sin permisos para leer esta carpeta.")
            return

        # Archivos directo en esta carpeta (sin subcarpetas)
        direct_files = []
        try:
            direct_files = [
                f for f in drill_path.iterdir()
                if f.is_file() and (exts is None or f.suffix.lower() in exts)
            ]
        except PermissionError:
            pass

        # Calcula stats por subcarpeta
        rows = []
        for d in subdirs:
            n_files, size_bytes = count_and_size(d, exts)
            rows.append({
                "path":       d,
                "name":       d.name,
                "files":      n_files,
                "size_bytes": size_bytes,
            })

        rows.sort(key=lambda r: r["size_bytes"], reverse=True)

    # ── Stats globales ────────────────────────────────────────────────────────
    total_bytes = sum(r["size_bytes"] for r in rows)
    direct_size = sum(f.stat().st_size for f in direct_files)
    grand_total = total_bytes + direct_size
    total_files_all = sum(r["files"] for r in rows) + len(direct_files)

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("💾 Tamaño total",     fmt_size(grand_total))
    col_s2.metric("📁 Subcarpetas",      f"{len(subdirs):,}")
    col_s3.metric("📄 Archivos totales", f"{total_files_all:,}")
    col_s4.metric("📄 En esta carpeta",  f"{len(direct_files):,}  ({fmt_size(direct_size)})" if direct_files else "0")

    if not rows and not direct_files:
        st.info("Esta carpeta está vacía.")
        return

    st.markdown("---")

    # ── Tabla de subcarpetas con barras ───────────────────────────────────────
    if rows:
        max_bytes = rows[0]["size_bytes"] if rows else 1

        st.markdown(f'<div class="mh-section-title">Subcarpetas ({len(rows)})</div>',
                    unsafe_allow_html=True)

        for r in rows:
            if r["size_bytes"] == 0 and r["files"] == 0:
                continue

            pct = r["size_bytes"] / max_bytes if max_bytes else 0
            bar_pct = max(int(pct * 100), 1)

            # Color según tamaño relativo
            if pct >= 0.75:
                bar_color = "#f87171"   # rojo
                badge_cls = "mh-badge-red"
            elif pct >= 0.4:
                bar_color = "#fbbf24"   # amarillo
                badge_cls = "mh-badge-yellow"
            elif pct >= 0.15:
                bar_color = "#60a5fa"   # azul
                badge_cls = "mh-badge-blue"
            else:
                bar_color = "#34d399"   # verde
                badge_cls = "mh-badge-green"

            col_name, col_bar, col_meta, col_btn = st.columns([3, 4, 2, 1])

            with col_name:
                st.markdown(
                    f'<div style="color:#e2e2f0;font-weight:600;font-size:0.9rem;'
                    f'padding-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                    f'📁 {r["name"]}</div>',
                    unsafe_allow_html=True,
                )

            with col_bar:
                st.markdown(
                    f'<div style="margin-top:10px;background:rgba(255,255,255,0.06);'
                    f'border-radius:6px;height:14px;overflow:hidden;">'
                    f'<div style="width:{bar_pct}%;background:{bar_color};height:100%;'
                    f'border-radius:6px;transition:width 0.3s;"></div></div>',
                    unsafe_allow_html=True,
                )

            with col_meta:
                st.markdown(
                    f'<div style="text-align:right;padding-top:4px;">'
                    f'<span class="mh-badge {badge_cls}">{fmt_size(r["size_bytes"])}</span><br>'
                    f'<span style="color:#55558a;font-size:0.72rem;">{r["files"]:,} archivos</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            with col_btn:
                if st.button("→", key=f"drill_{r['name']}", help=f"Entrar en {r['name']}"):
                    st.session_state.exp_drill_path = str(r["path"])
                    st.rerun()

    # ── Archivos directos ─────────────────────────────────────────────────────
    if direct_files:
        direct_files_sorted = sorted(direct_files, key=lambda f: f.stat().st_size, reverse=True)
        with st.expander(f"📄 Archivos en esta carpeta ({len(direct_files):,}  —  {fmt_size(direct_size)})",
                         expanded=len(subdirs) == 0):
            search_f = st.text_input("🔎 Filtrar archivos", key="exp_file_search",
                                     placeholder="ej: metallica...")
            show_files = [f for f in direct_files_sorted
                          if not search_f or search_f.lower() in f.name.lower()]

            max_file_size = direct_files_sorted[0].stat().st_size if direct_files_sorted else 1
            for f in show_files[:300]:
                sz = f.stat().st_size
                bar_w = max(int(sz / max_file_size * 100), 1)
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;margin:3px 0;">'
                    f'<div style="min-width:200px;max-width:300px;overflow:hidden;'
                    f'text-overflow:ellipsis;white-space:nowrap;color:#c5c5e8;font-size:0.83rem;">'
                    f'{f.name}</div>'
                    f'<div style="flex:1;background:rgba(255,255,255,0.05);border-radius:4px;height:8px;">'
                    f'<div style="width:{bar_w}%;background:#7050ff;height:100%;border-radius:4px;"></div></div>'
                    f'<div style="min-width:70px;text-align:right;color:#55558a;font-size:0.78rem;">'
                    f'{fmt_size(sz)}</div></div>',
                    unsafe_allow_html=True,
                )
            if len(show_files) > 300:
                st.caption(f"... y {len(show_files)-300} archivos más")

    # ── Gráfico top-10 ────────────────────────────────────────────────────────
    if rows:
        top10 = [r for r in rows[:10] if r["size_bytes"] > 0]
        if top10:
            st.markdown("---")
            st.markdown('<div class="mh-section-title">Top 10 subcarpetas por tamaño</div>',
                        unsafe_allow_html=True)
            chart_data = {r["name"][:28]: round(r["size_bytes"] / 1024**2, 1) for r in top10}
            import pandas as pd
            df = pd.DataFrame.from_dict(chart_data, orient="index", columns=["MB"])
            st.bar_chart(df, color="#7050ff", height=280)
            st.caption("Tamaño en MB · Haz clic en → para entrar en una subcarpeta")


# ─────────────────────────────────────────────────────────────────────────────
# Layout principal
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MediaHub",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS — Dark Music Theme ────────────────────────────────────────────────────
st.markdown("""
<style>
/* ═══════════════════════════════════════════════
   GOOGLE FONTS
═══════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ═══════════════════════════════════════════════
   BASE & BACKGROUND
═══════════════════════════════════════════════ */
html, body, [data-testid="stAppViewContainer"] {
    background: #0d0d1a !important;
    color: #e2e2f0 !important;
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}
[data-testid="stMain"] {
    background: transparent !important;
}

/* Selection color */
::selection { background: rgba(120,80,255,0.35); color: #fff; }

/* Smooth scrolling */
html { scroll-behavior: smooth; }

/* Custom scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: rgba(255,255,255,0.03); }
::-webkit-scrollbar-thumb {
    background: rgba(120,80,255,0.35);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(120,80,255,0.6); }

/* ═══════════════════════════════════════════════
   SIDEBAR
═══════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #13132e 0%, #0d0d1a 100%) !important;
    border-right: 1px solid rgba(120,80,255,0.15) !important;
}
[data-testid="stSidebar"] * { color: #d0d0f0 !important; }

/* Nav buttons — base */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 10px !important;
    color: #b0b0d8 !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    padding: 9px 12px !important;
    transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease !important;
    text-align: left !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(120,80,255,0.15) !important;
    border-color: rgba(120,80,255,0.35) !important;
    color: #e0e0ff !important;
}
[data-testid="stSidebar"] .stButton > button:focus-visible {
    outline: 2px solid rgba(120,80,255,0.8) !important;
    outline-offset: 2px !important;
}
/* Active nav button */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(112,80,255,0.28) 0%, rgba(168,85,247,0.2) 100%) !important;
    border-color: rgba(120,80,255,0.5) !important;
    color: #d4c0ff !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 12px rgba(112,80,255,0.2) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, rgba(112,80,255,0.38) 0%, rgba(168,85,247,0.28) 100%) !important;
    border-color: rgba(120,80,255,0.7) !important;
    color: #fff !important;
}

/* ═══════════════════════════════════════════════
   TYPOGRAPHY
═══════════════════════════════════════════════ */
h1 {
    background: linear-gradient(135deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 800 !important;
    letter-spacing: -0.5px;
    font-family: 'Inter', sans-serif !important;
}
h2, h3 {
    color: #c4b5fd !important;
    font-weight: 700 !important;
    font-family: 'Inter', sans-serif !important;
}
h4, h5 { color: #a5b4fc !important; font-family: 'Inter', sans-serif !important; }
p, .stMarkdown p {
    color: #c0c0dc !important;
    line-height: 1.75 !important;
    font-size: 0.9375rem !important;
}

/* ═══════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════ */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, transform 0.15s ease !important;
    border: 1px solid rgba(120,80,255,0.3) !important;
    background: rgba(120,80,255,0.1) !important;
    color: #c4b5fd !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    background: rgba(120,80,255,0.22) !important;
    border-color: rgba(120,80,255,0.55) !important;
    color: #e0d4ff !important;
    box-shadow: 0 4px 14px rgba(120,80,255,0.25) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:focus-visible {
    outline: 2px solid rgba(120,80,255,0.9) !important;
    outline-offset: 2px !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6d3fff 0%, #a855f7 100%) !important;
    border-color: transparent !important;
    color: #fff !important;
    box-shadow: 0 4px 18px rgba(109,63,255,0.4) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 24px rgba(109,63,255,0.6) !important;
    transform: translateY(-2px) !important;
    filter: brightness(1.08) !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
    box-shadow: 0 2px 10px rgba(109,63,255,0.4) !important;
}

/* ═══════════════════════════════════════════════
   METRICS
═══════════════════════════════════════════════ */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(120,80,255,0.1) 0%, rgba(168,85,247,0.07) 100%) !important;
    border: 1px solid rgba(120,80,255,0.22) !important;
    border-radius: 14px !important;
    padding: 18px 20px !important;
    transition: border-color 0.2s ease !important;
}
[data-testid="stMetric"]:hover {
    border-color: rgba(120,80,255,0.4) !important;
}
[data-testid="stMetricValue"] {
    color: #c4b5fd !important;
    font-size: 1.9rem !important;
    font-weight: 800 !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stMetricLabel"] {
    color: #9898c0 !important;
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
}

/* ═══════════════════════════════════════════════
   TABS
═══════════════════════════════════════════════ */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.03) !important;
    border-radius: 12px !important;
    padding: 4px !important;
    border: 1px solid rgba(120,80,255,0.15) !important;
    gap: 2px !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 9px !important;
    color: #9898c4 !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    padding: 8px 18px !important;
    border: none !important;
    background: transparent !important;
    transition: color 0.15s ease, background 0.15s ease !important;
    cursor: pointer !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color: #c4b5fd !important;
    background: rgba(120,80,255,0.1) !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: linear-gradient(135deg, #6d3fff, #a855f7) !important;
    color: #fff !important;
    box-shadow: 0 2px 10px rgba(109,63,255,0.4) !important;
    font-weight: 600 !important;
}

/* ═══════════════════════════════════════════════
   INPUTS & SELECTS
═══════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(120,80,255,0.22) !important;
    border-radius: 10px !important;
    color: #e2e2f0 !important;
    transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: rgba(120,80,255,0.65) !important;
    box-shadow: 0 0 0 3px rgba(120,80,255,0.15) !important;
    outline: none !important;
}
.stTextInput label, .stNumberInput label, .stSelectbox label,
.stMultiSelect label, .stSlider label, .stRadio label,
.stTextArea label {
    color: #b0b0d8 !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
}
.stSlider [data-baseweb="slider"] { color: #7050ff !important; }
.stSlider [data-baseweb="thumb"] { background: #7050ff !important; }
.stRadio [data-testid="stMarkdownContainer"] p { color: #c0c0dc !important; }

/* ═══════════════════════════════════════════════
   CONTAINERS / CARDS
═══════════════════════════════════════════════ */
[data-testid="stContainer"] { border-radius: 14px !important; }
div[data-testid="stVerticalBlock"] > div:has(> [data-testid="stContainer"][style*="border"]) {
    background: rgba(120,80,255,0.06) !important;
    border-radius: 14px !important;
}

/* ═══════════════════════════════════════════════
   EXPANDERS
═══════════════════════════════════════════════ */
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.025) !important;
    border: 1px solid rgba(120,80,255,0.18) !important;
    border-radius: 12px !important;
    margin-bottom: 8px !important;
    transition: border-color 0.2s ease !important;
}
[data-testid="stExpander"]:hover {
    border-color: rgba(120,80,255,0.38) !important;
}
[data-testid="stExpanderToggleIcon"] { color: #9070e8 !important; }
[data-testid="stExpander"] summary { cursor: pointer !important; }

/* ═══════════════════════════════════════════════
   CODE BLOCKS / LOGS
═══════════════════════════════════════════════ */
.stCode, pre, code {
    background: rgba(0,0,0,0.45) !important;
    border: 1px solid rgba(120,80,255,0.18) !important;
    border-radius: 10px !important;
    color: #a8e6a8 !important;
    font-size: 0.8125rem !important;
    line-height: 1.6 !important;
}

/* ═══════════════════════════════════════════════
   ALERTS & STATUS
═══════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    font-size: 0.9rem !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
    background: rgba(96,165,250,0.1) !important;
    border: 1px solid rgba(96,165,250,0.3) !important;
    color: #93c5fd !important;
}
[data-testid="stAlert"][kind="success"],
div[class*="stSuccess"] {
    background: rgba(52,211,153,0.1) !important;
    border: 1px solid rgba(52,211,153,0.3) !important;
    border-radius: 10px !important;
}
[data-testid="stAlert"][kind="error"],
div[class*="stError"] {
    background: rgba(248,113,113,0.1) !important;
    border: 1px solid rgba(248,113,113,0.3) !important;
    border-radius: 10px !important;
}
[data-testid="stAlert"][kind="warning"],
div[class*="stWarning"] {
    background: rgba(251,191,36,0.1) !important;
    border: 1px solid rgba(251,191,36,0.3) !important;
    border-radius: 10px !important;
}

/* ═══════════════════════════════════════════════
   PROGRESS BAR
═══════════════════════════════════════════════ */
[data-testid="stProgress"] > div > div {
    background: rgba(255,255,255,0.06) !important;
    border-radius: 8px !important;
}
[data-testid="stProgress"] > div > div > div {
    background: linear-gradient(90deg, #6d3fff, #a855f7) !important;
    border-radius: 8px !important;
}

/* ═══════════════════════════════════════════════
   DIVIDERS
═══════════════════════════════════════════════ */
hr {
    border: none !important;
    border-top: 1px solid rgba(120,80,255,0.18) !important;
    margin: 24px 0 !important;
}

/* ═══════════════════════════════════════════════
   CAPTIONS & LABELS
═══════════════════════════════════════════════ */
.stCaption, small, [data-testid="stCaption"] {
    color: #8888b8 !important;
    font-size: 0.8125rem !important;
    line-height: 1.5 !important;
}

/* ═══════════════════════════════════════════════
   DOWNLOAD BUTTONS
═══════════════════════════════════════════════ */
[data-testid="stDownloadButton"] > button {
    background: rgba(52,211,153,0.1) !important;
    border: 1px solid rgba(52,211,153,0.28) !important;
    color: #6ee7b7 !important;
    border-radius: 10px !important;
    cursor: pointer !important;
    transition: background 0.18s ease, box-shadow 0.18s ease, transform 0.15s ease !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: rgba(52,211,153,0.22) !important;
    box-shadow: 0 4px 14px rgba(52,211,153,0.22) !important;
    transform: translateY(-1px) !important;
}

/* ═══════════════════════════════════════════════
   MULTISELECT TAGS
═══════════════════════════════════════════════ */
[data-baseweb="tag"] {
    background: linear-gradient(135deg, rgba(109,63,255,0.38), rgba(168,85,247,0.35)) !important;
    border-radius: 6px !important;
    color: #e2e2f0 !important;
}

/* ═══════════════════════════════════════════════
   CUSTOM HELPER CLASSES (via st.markdown)
═══════════════════════════════════════════════ */
.mh-card {
    background: linear-gradient(135deg, rgba(120,80,255,0.1) 0%, rgba(168,85,247,0.07) 100%);
    border: 1px solid rgba(120,80,255,0.22);
    border-radius: 16px;
    padding: 24px 20px;
    margin-bottom: 12px;
    transition: border-color 0.22s ease, box-shadow 0.22s ease, transform 0.2s ease;
}
.mh-card:hover {
    border-color: rgba(120,80,255,0.5);
    background: linear-gradient(135deg, rgba(120,80,255,0.16) 0%, rgba(168,85,247,0.11) 100%);
    box-shadow: 0 8px 32px rgba(120,80,255,0.18);
    transform: translateY(-2px);
}
.mh-card-icon { font-size: 2.2rem; margin-bottom: 12px; display: block; }
.mh-card-title { color: #c4b5fd; font-size: 1.125rem; font-weight: 700; margin-bottom: 6px; }
.mh-card-desc { color: #9898c0; font-size: 0.875rem; line-height: 1.65; }

.mh-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.3px;
    line-height: 1;
}
.mh-badge-green  { background: rgba(52,211,153,0.14); color: #6ee7b7; border: 1px solid rgba(52,211,153,0.28); }
.mh-badge-yellow { background: rgba(251,191,36,0.14);  color: #fcd34d; border: 1px solid rgba(251,191,36,0.28); }
.mh-badge-red    { background: rgba(248,113,113,0.14); color: #fca5a5; border: 1px solid rgba(248,113,113,0.28); }
.mh-badge-blue   { background: rgba(96,165,250,0.14);  color: #93c5fd; border: 1px solid rgba(96,165,250,0.28); }
.mh-badge-purple { background: rgba(120,80,255,0.14);  color: #c4b5fd; border: 1px solid rgba(120,80,255,0.28); }
.mh-badge-orange { background: rgba(251,146,60,0.14);  color: #fdba74; border: 1px solid rgba(251,146,60,0.28); }

.mh-stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0; }
.mh-stat {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(120,80,255,0.18);
    border-radius: 10px;
    padding: 10px 18px;
    text-align: center;
    min-width: 100px;
}
.mh-stat-val { font-size: 1.4rem; font-weight: 800; color: #c4b5fd; }
.mh-stat-lbl { font-size: 0.75rem; color: #8888b8; margin-top: 3px; }

.mh-hero {
    background: linear-gradient(135deg, rgba(109,63,255,0.14) 0%, rgba(59,130,246,0.09) 50%, rgba(52,211,153,0.07) 100%);
    border: 1px solid rgba(120,80,255,0.2);
    border-radius: 20px;
    padding: 36px 32px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
}
.mh-hero::before {
    content: "";
    position: absolute;
    top: -60px; right: -60px;
    width: 220px; height: 220px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(109,63,255,0.13), transparent 70%);
    pointer-events: none;
}
.mh-hero::after {
    content: "";
    position: absolute;
    bottom: -40px; left: 20%;
    width: 160px; height: 160px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(52,211,153,0.07), transparent 70%);
    pointer-events: none;
}

.mh-section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #8080b8;
    margin: 28px 0 14px;
}
.mh-section-title::after {
    content: "";
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, rgba(120,80,255,0.25), transparent);
}

/* ═══════════════════════════════════════════════
   SIDEBAR — GRUPOS Y ELEMENTOS
═══════════════════════════════════════════════ */
.mh-nav-divider {
    height: 1px;
    background: linear-gradient(90deg, rgba(120,80,255,0.35), transparent);
    margin: 10px 0 14px;
}
.mh-nav-group-label {
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    color: #7878b0 !important;
    padding: 12px 4px 5px;
    margin-bottom: 2px;
}
.mh-nav-hint {
    font-size: 0.75rem;
    color: #7878a8 !important;
    padding: 1px 8px 7px;
    margin-top: -3px;
    line-height: 1.45;
}

/* Status pills sidebar footer */
.mh-status-pill {
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 3px 9px;
    border-radius: 20px;
    text-transform: uppercase;
}
.mh-pill-ok {
    background: rgba(52,211,153,0.14);
    color: #6ee7b7 !important;
    border: 1px solid rgba(52,211,153,0.28);
}
.mh-pill-off {
    background: rgba(100,100,130,0.12);
    color: #8888a8 !important;
    border: 1px solid rgba(100,100,130,0.2);
}

/* ═══════════════════════════════════════════════
   PAGE HEADER COMPONENT
═══════════════════════════════════════════════ */
.mh-page-header {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 22px 28px;
    margin-bottom: 24px;
    background: linear-gradient(135deg,
        rgba(109,63,255,0.11) 0%,
        rgba(59,130,246,0.07) 60%,
        rgba(52,211,153,0.05) 100%);
    border: 1px solid rgba(120,80,255,0.18);
    border-radius: 18px;
    position: relative;
    overflow: hidden;
}
.mh-page-header::after {
    content: "";
    position: absolute;
    top: -50px; right: -50px;
    width: 160px; height: 160px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(109,63,255,0.1), transparent 70%);
    pointer-events: none;
}
.mh-page-header-icon {
    font-size: 2.2rem;
    line-height: 1;
    flex-shrink: 0;
}
.mh-page-header-text { flex: 1; }
.mh-page-header-title {
    font-size: 1.5rem;
    font-weight: 800;
    background: linear-gradient(135deg, #b09afd, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.25;
    margin-bottom: 4px;
    font-family: 'Inter', sans-serif;
}
.mh-page-header-sub {
    font-size: 0.875rem;
    color: #8888b8 !important;
    line-height: 1.5;
}
.mh-breadcrumb {
    font-size: 0.75rem;
    color: #7070a8 !important;
    margin-bottom: 5px;
    letter-spacing: 0.2px;
}

/* ═══════════════════════════════════════════════
   HOME — MÓDULO CARDS
═══════════════════════════════════════════════ */
.mh-module-card {
    background: linear-gradient(145deg,
        rgba(109,63,255,0.09) 0%,
        rgba(168,85,247,0.05) 100%);
    border: 1px solid rgba(120,80,255,0.2);
    border-radius: 16px;
    padding: 22px 18px 18px;
    transition: border-color 0.22s ease, box-shadow 0.22s ease, transform 0.2s ease;
    height: 100%;
}
.mh-module-card:hover {
    border-color: rgba(120,80,255,0.48);
    background: linear-gradient(145deg,
        rgba(109,63,255,0.16) 0%,
        rgba(168,85,247,0.11) 100%);
    box-shadow: 0 8px 28px rgba(109,63,255,0.16);
    transform: translateY(-2px);
}
.mh-module-card.mh-card-highlight {
    border-color: rgba(52,211,153,0.3);
    background: linear-gradient(145deg,
        rgba(52,211,153,0.07) 0%,
        rgba(109,63,255,0.05) 100%);
}
.mh-module-card.mh-card-highlight:hover {
    border-color: rgba(52,211,153,0.55);
    box-shadow: 0 8px 28px rgba(52,211,153,0.12);
}
.mh-mc-icon { font-size: 1.85rem; margin-bottom: 10px; display: block; }
.mh-mc-tag {
    display: inline-block;
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 4px;
    margin-bottom: 9px;
}
.mh-mc-tag-dl  { background: rgba(96,165,250,0.18);  color: #93c5fd; }
.mh-mc-tag-lib { background: rgba(251,191,36,0.18);  color: #fcd34d; }
.mh-mc-title { color: #c4b5fd !important; font-size: 1.0rem; font-weight: 700; margin-bottom: 6px; line-height: 1.3; }
.mh-mc-desc  { color: #9090b8 !important; font-size: 0.8125rem; line-height: 1.6; }

/* ═══════════════════════════════════════════════
   HOME — STATS BAR
═══════════════════════════════════════════════ */
.mh-stats-bar {
    display: flex;
    gap: 0;
    padding: 16px 4px;
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(120,80,255,0.14);
    border-radius: 16px;
    margin-bottom: 28px;
    align-items: center;
}
.mh-stat-item { text-align: center; flex: 1; min-width: 80px; padding: 4px 8px; }
.mh-stat-item-val {
    font-size: 1.45rem;
    font-weight: 800;
    background: linear-gradient(135deg, #b09afd, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.2;
    font-family: 'Inter', sans-serif;
}
.mh-stat-item-lbl {
    font-size: 0.75rem;
    color: #8080b8 !important;
    margin-top: 4px;
    font-weight: 500;
    line-height: 1.3;
}
.mh-stat-divider {
    width: 1px; height: 40px;
    background: rgba(120,80,255,0.18);
    flex-shrink: 0;
}

/* ═══════════════════════════════════════════════
   RESULT SONG ROWS — MUSIC PAGE
═══════════════════════════════════════════════ */
.badge-new    { background: rgba(52,211,153,0.16); color: #6ee7b7; padding: 2px 8px; border-radius: 4px; font-size: .75rem; font-weight: 600; border: 1px solid rgba(52,211,153,0.28); }
.badge-cached { background: rgba(96,165,250,0.16); color: #93c5fd; padding: 2px 8px; border-radius: 4px; font-size: .75rem; font-weight: 600; border: 1px solid rgba(96,165,250,0.28); }
.badge-nf     { background: rgba(248,113,113,0.16); color: #fca5a5; padding: 2px 8px; border-radius: 4px; font-size: .75rem; font-weight: 600; border: 1px solid rgba(248,113,113,0.28); }
.song-row     { padding: 6px 0; border-bottom: 1px solid rgba(120,80,255,0.1); display: flex; align-items: center; gap: 6px; }

/* ═══════════════════════════════════════════════
   SPINNER / LOADING
═══════════════════════════════════════════════ */
[data-testid="stSpinner"] > div {
    border-top-color: #7050ff !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Página YouTube — pega un URL y elige cómo descargarlo (música/película)
# ─────────────────────────────────────────────────────────────────────────────

def page_youtube():
    _page_header("🎬", "YouTube", "Busca o pega un enlace y descárgalo como MP3 o MP4")
    cfg = load_config()

    if not _youtube_deps_ok():
        st.warning("Faltan dependencias. Instálalas con `brew install yt-dlp ffmpeg` "
                   "y recarga la página.")
        return

    yt_script   = BASE_DIR / "scripts" / "youtube_dl.py"
    quality_map = {"720p": 720, "1080p": 1080, "Máxima disponible": 0}

    # ── Controles compartidos (aplican a Buscar y a Pegar URL) ────────────────
    tipo = st.selectbox("¿Qué quieres descargar?",
                        ["🎵 Música (MP3)", "🎬 Película / Video (MP4)"],
                        key="ytu_tipo")
    is_music = tipo.startswith("🎵")
    if is_music:
        dest = st.text_input("📁 Carpeta destino", value=cfg.get("music_folder", ""),
                             key="ytu_dest_m")
        st.caption("Se descarga como **MP3 192k** + metadata y portada (Shazam).")
        quality = "1080p"
    else:
        dest = st.text_input("📁 Carpeta destino", value=cfg.get("movies_folder", ""),
                             key="ytu_dest_v")
        quality = st.selectbox("Calidad", list(quality_map.keys()), index=1,
                               key="ytu_quality")
        st.caption("Se descarga como **MP4 (H.264)**. El contenido de pago/DRM "
                   "(YouTube Movies) no se puede descargar.")

    def _do_download(target_url: str, label: str = ""):
        if not dest or not Path(dest).parent.exists():
            st.error("Carpeta destino inválida.")
            return
        status, log = st.empty(), st.empty()
        if is_music:
            status.info(f"⬇️ Descargando música → MP3… {label}")
            cmd = [PYTHON, "-u", str(yt_script), "download", target_url, "--dest", dest]
        else:
            status.info(f"⬇️ Descargando video → MP4… {label}")
            cmd = [PYTHON, "-u", str(yt_script), "video", target_url,
                   "--dest", dest, "--max-height", str(quality_map[quality])]
        ok = stream_script(cmd, log, status)
        if ok:
            status.success("✅ ¡Descargado!")
            _scan_music_library.clear()
        else:
            status.error("❌ Error (¿URL inválido o contenido con DRM/pago?)")

    modo = st.radio("Modo", ["🔎 Buscar en YouTube", "🔗 Pegar URL"],
                    horizontal=True, key="ytu_mode")
    st.markdown("---")

    # ── Modo Pegar URL ────────────────────────────────────────────────────────
    if modo.startswith("🔗"):
        url = st.text_input("URL de YouTube",
                            placeholder="https://www.youtube.com/watch?v=…", key="ytu_url")
        valid = url.strip().startswith("http")
        if valid:
            with st.expander("▶️ Previsualizar"):
                st.video(url.strip())
        if st.button("⬇️ Descargar", type="primary", disabled=not valid,
                     use_container_width=True, key="ytu_dl"):
            _do_download(url.strip())

    # ── Modo Buscar ───────────────────────────────────────────────────────────
    else:
        yc1, yc2 = st.columns([4, 1])
        with yc1:
            q = st.text_input("Buscar en YouTube",
                              placeholder="ej: Soda Stereo De Música Ligera",
                              key="ytu_q", label_visibility="collapsed")
        with yc2:
            if st.button("🔍 Buscar", use_container_width=True, key="ytu_sbtn",
                         disabled=not q):
                st.session_state["ytu_results"] = _youtube_search(q, 8)
        for j, r in enumerate(st.session_state.get("ytu_results", [])):
            vid = r.get("id", "")
            with st.container(border=True):
                ri, rinfo, ract = st.columns([1, 4, 2])
                with ri:
                    if vid:
                        st.image(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                                 use_container_width=True)
                with rinfo:
                    st.markdown(f"**{r.get('title','')[:80]}**")
                    st.caption(f"📺 {r.get('uploader','')}  ·  "
                               f"⏱️ {_fmt_duration(r.get('duration'))}")
                    po = st.session_state.setdefault("_ytu_prev", set())
                    if st.button("▶️ Ver", key=f"ytu_prev_{j}"):
                        po.symmetric_difference_update({vid})
                    if vid in po:
                        st.video(f"https://www.youtube.com/watch?v={vid}")
                with ract:
                    if st.button("⬇️ MP3" if is_music else "⬇️ MP4", type="primary",
                                 use_container_width=True, key=f"ytu_dl_{j}"):
                        _do_download(f"https://www.youtube.com/watch?v={vid}",
                                     r.get("title", "")[:30])


def page_torrents():
    _page_header("🧲", "Torrents", "Descargas activas en qBittorrent")
    cfg = load_config()
    if not cfg.get("qbit_url"):
        st.info("Configura qBittorrent en **⚙️ Configuración** para ver y enviar "
                "tus descargas aquí.")
        return

    st.button("🔄 Actualizar")  # un clic = rerun = lista fresca
    torrents = _qbit_list(cfg)
    if torrents is None:
        st.error(f"No se pudo conectar a qBittorrent en `{cfg['qbit_url']}`. "
                 "Revisa URL/usuario/contraseña y que la WebUI esté activa "
                 "(Ajustes → Web UI).")
        return
    if not torrents:
        st.info("No hay torrents en qBittorrent ahora mismo.")
        return

    def _eta(s):
        try:
            s = int(s)
            return "∞" if s >= 8640000 else f"{s//3600}h{(s%3600)//60:02d}m" if s >= 3600 \
                else f"{s//60}m{s%60:02d}s"
        except Exception:
            return "?"

    active = sum(1 for t in torrents if 0 < t.get("progress", 0) < 1)
    done   = sum(1 for t in torrents if t.get("progress", 0) >= 1)
    m1, m2, m3 = st.columns(3)
    m1.metric("Total", len(torrents))
    m2.metric("⬇️ Descargando", active)
    m3.metric("✅ Completos", done)
    st.markdown("---")

    for t in sorted(torrents, key=lambda x: x.get("progress", 0)):
        prog = max(0.0, min(float(t.get("progress", 0)), 1.0))
        with st.container(border=True):
            st.markdown(f"**{t.get('name', '')[:75]}**")
            st.progress(prog)
            st.caption(f"{prog*100:.0f}% · {t.get('state','')} · "
                       f"⬇️ {_size_human(t.get('dlspeed', 0))}/s · "
                       f"ETA {_eta(t.get('eta', 0))} · {_size_human(t.get('size', 0))}")


def page_health():
    _page_header("🩺", "Salud de fuentes", "Estado de cada API que usa la app")
    st.caption("Pingea cada fuente con una consulta mínima. Útil para detectar "
               "cuándo una API cambia o deja de responder.")

    if st.button("🔄 Verificar ahora", type="primary") or "health" not in st.session_state:
        with st.spinner("Verificando fuentes…"):
            st.session_state["health"] = _sources_health()

    health = st.session_state.get("health", {})
    n_ok   = sum(1 for v in health.values() if v["ok"] is True)
    n_bad  = sum(1 for v in health.values() if v["ok"] is False)
    n_na   = sum(1 for v in health.values() if v["ok"] is None)
    m1, m2, m3 = st.columns(3)
    m1.metric("🟢 OK", n_ok)
    m2.metric("🔴 Caídas", n_bad)
    m3.metric("⚪ Sin configurar", n_na)
    st.markdown("---")

    for name, v in sorted(health.items(), key=lambda kv: (kv[1]["ok"] is not False)):
        icon = "🟢" if v["ok"] is True else ("🔴" if v["ok"] is False else "⚪")
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 3])
            c1.markdown(f"{icon} **{name}**")
            c2.caption(f"⏱️ {v['ms']} ms")
            c3.caption(v["detail"])


# ─────────────────────────────────────────────────────────────────────────────
# Navegación sidebar — agrupada por categoría
# ─────────────────────────────────────────────────────────────────────────────

if "page" not in st.session_state:
    st.session_state.page = "🏠 Inicio"

# Grupos de navegación
NAV_GROUPS = [
    {
        "label": None,
        "pages": ["🏠 Inicio"],
    },
    {
        "label": "📥  DESCARGA",
        "pages": ["🎵 Música", "🎬 Películas", "📚 Ebooks", "🟢 Mi Spotify",
                  "🎬 YouTube", "🧲 Torrents", "🎮 ROMs"],
    },
    {
        "label": "🗂  BIBLIOTECA",
        "pages": ["🔧 Fix Metadata", "🧹 Limpiar duplicados", "📊 Explorador"],
    },
    {
        "label": "⚙  SISTEMA",
        "pages": ["⚙️ Configuración", "🩺 Salud de fuentes", "📋 Historial",
                  "📈 Estadísticas", "📖 Ayuda"],
    },
]

# Mapa página → función
PAGE_MAP = {
    "🏠 Inicio":             page_inicio,
    "🎵 Música":             page_musica,
    "🎬 Películas":          page_peliculas,
    "📚 Ebooks":             page_ebooks,
    "🟢 Mi Spotify":         page_spotify,
    "🎬 YouTube":            page_youtube,
    "🧲 Torrents":           page_torrents,
    "🎮 ROMs":               page_roms,
    "🔧 Fix Metadata":       page_metadata,
    "🧹 Limpiar duplicados": page_phone,
    "📊 Explorador":         page_explorador,
    "⚙️ Configuración":      page_config,
    "🩺 Salud de fuentes":   page_health,
    "📋 Historial":          page_historial,
    "📈 Estadísticas":       page_estadisticas,
    "📖 Ayuda":              page_ayuda,
}

# Mapa página → descripción corta (tooltip en sidebar)
PAGE_HINTS = {
    "🏠 Inicio":             "Panel principal",
    "🎵 Música":             "Last.fm + The Pirate Bay",
    "🎬 Películas":          "TMDB + TPB + YTS · Latino",
    "📚 Ebooks":             "Libros para Kindle",
    "🟢 Mi Spotify":         "Tu historial personal",
    "🎬 YouTube":            "URL → MP3 (música) o MP4 (video)",
    "🧲 Torrents":           "Progreso de qBittorrent",
    "🎮 ROMs":               "Miyoo A30 · GBA · SNES · PS1",
    "🔧 Fix Metadata":       "Corrige tags ID3 de MP3s",
    "🧹 Limpiar duplicados": "Elimina MP3s repetidos",
    "📊 Explorador":         "Espacio por carpeta",
    "⚙️ Configuración":      "API keys y rutas",
    "🩺 Salud de fuentes":   "Estado de las APIs",
    "📋 Historial":          "Registro de todas las descargas",
    "📈 Estadísticas":       "Métricas de biblioteca y actividad",
    "📖 Ayuda":              "Documentación",
}

with st.sidebar:
    # ── Logo ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="padding:20px 4px 10px;">
        <div style="font-size:1.6rem;font-weight:900;font-family:'Inter',sans-serif;
             background:linear-gradient(135deg,#b09afd,#60a5fa,#34d399);
             -webkit-background-clip:text;-webkit-text-fill-color:transparent;
             background-clip:text;line-height:1.15;letter-spacing:-0.5px;">
            MediaHub
        </div>
        <div style="font-size:0.75rem;color:#7878a8;letter-spacing:0.6px;
             margin-top:5px;text-transform:uppercase;font-weight:500;">
            Música &nbsp;·&nbsp; Películas &nbsp;·&nbsp; Ebooks
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="mh-nav-divider"></div>', unsafe_allow_html=True)

    # ── Grupos de navegación ──────────────────────────────────────────────────
    current = st.session_state.page
    for group in NAV_GROUPS:
        if group["label"]:
            st.markdown(
                f'<div class="mh-nav-group-label">{group["label"]}</div>',
                unsafe_allow_html=True,
            )
        for page_name in group["pages"]:
            is_active = current == page_name
            hint      = PAGE_HINTS.get(page_name, "")
            # Inyectar descripción debajo del nombre cuando está activa
            label = page_name
            if st.button(
                label,
                use_container_width=True,
                key=f"nav_{page_name}",
                type="primary" if is_active else "secondary",
                help=hint,
            ):
                st.session_state.page = page_name
                st.rerun()
            # Sub-descripción solo en ítem activo
            if is_active:
                st.markdown(
                    f'<div class="mh-nav-hint">{hint}</div>',
                    unsafe_allow_html=True,
                )
        if group["label"]:
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Footer sidebar ────────────────────────────────────────────────────────
    st.markdown('<div class="mh-nav-divider" style="margin-top:8px;"></div>',
                unsafe_allow_html=True)

    # Config status pill
    cfg = load_config()
    tmdb_ok = bool(cfg.get("tmdb_api_key", "").strip())
    sp_ok   = bool(cfg.get("spotify_client_id", "").strip())
    st.markdown(
        f'<div style="display:flex;gap:6px;flex-wrap:wrap;padding:4px 0 8px;">'
        f'<span class="mh-status-pill {"mh-pill-ok" if tmdb_ok else "mh-pill-off"}">TMDB</span>'
        f'<span class="mh-status-pill {"mh-pill-ok" if sp_ok   else "mh-pill-off"}">Spotify</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="font-size:0.75rem;color:#6868a0;text-align:center;padding-bottom:8px;letter-spacing:0.3px;">'
        'v1.2 &nbsp;·&nbsp; MIT License</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Renderiza la página activa
# ─────────────────────────────────────────────────────────────────────────────
PAGE_MAP[st.session_state.page]()
