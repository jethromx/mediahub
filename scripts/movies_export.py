#!/usr/bin/env python3
"""
movies_export.py — Busca películas vía TMDB y sus torrents en The Pirate Bay.

Estrategia:
  1. TMDB API → lista de películas por décadas, géneros o búsqueda directa
  2. apibay.org → busca torrents para cada película
  3. Filtros de calidad → bloquea CAM, TS, HDCAM, etc.
  4. Filtro de español latino → prioriza LAT, Latino, Español (no Spain)

Uso:
  python3 movies_export.py --decade 80 --genre accion --limit 20
  python3 movies_export.py --query "El Padrino" --year 1972
"""

import sys
import json
import re
import time
import argparse
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────────────────────

TMDB_BASE    = "https://api.themoviedb.org/3"
TPB_API      = "https://apibay.org/q.php"
TRACKERS     = (
    "udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
    "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
    "&tr=udp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce"
    "&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce"
)

# Calidades bloqueadas (grabaciones de cine o calidad muy mala)
BAD_QUALITY_PATTERNS = re.compile(
    r"\b(cam|camrip|hdcam|ts|telesync|tc|telecine|r5|dvdscr|scr|screener|"
    r"workprint|wp|hqcam|pdvd|dvd-ts|web-ts)\b",
    re.IGNORECASE,
)

# Calidades aceptables (de mejor a peor)
QUALITY_RANK = {
    "remux":   10, "bluray": 9,  "blu-ray": 9, "bdrip": 8,
    "web-dl":  8,  "webdl":  8,  "webrip":  7, "web":   7,
    "amzn":    8,  "nflx":   8,  "hulu":    7, "dsnp":  8,
    "hdtv":    6,  "hdrip":  5,  "dvdrip":  4, "dvd":   3,
    "480p":    2,  "360p":   1,
}

# Keywords de español latino (NO de España)
SPANISH_LATINO = re.compile(
    r"\b(lat|latino|latinoamerica|esp(?:a[ñn]ol)?[\s._-]lat|"
    r"spanish[\s._-]lat|dual[\s._-]lat|castellano[\s._-]lat|"
    r"sub[\s._-]?esp|sub[\s._-]?lat|subtitulo[s]?[\s._-]?esp|"
    r"multi[\s._-]sub|multi[\s._-]audio)\b",
    re.IGNORECASE,
)

# Keywords de España (para penalizar si también contiene "spain")
SPANISH_SPAIN = re.compile(r"\b(spain|espa[ñn]a|castellano[\s._-]espa[ñn])\b", re.IGNORECASE)

# TMDB Género IDs
GENRE_IDS = {
    "accion":    28,  "aventura":  12,  "animacion": 16,
    "comedia":   35,  "crimen":    80,  "documental": 99,
    "drama":     18,  "familia":   10751, "fantasia": 14,
    "historia":  36,  "terror":    27,  "musica":    10402,
    "misterio":  9648, "romance":  10749, "ciencia_ficcion": 878,
    "suspenso":  53,  "guerra":    10752, "western":  37,
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 10) -> dict | list | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 MediaHub/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  [!] HTTP error {url}: {e}")
        return None


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def magnet(info_hash: str, name: str) -> str:
    dn = urllib.parse.quote(name)
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}&tr={TRACKERS}"


def size_human(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {unit}"
        b //= 1024
    return f"{b:.1f} TB"


def quality_score(name: str) -> tuple[int, str]:
    """
    Devuelve (puntuación, etiqueta).
    -1 = bloqueado (CAM/TS/etc.)
    """
    name_l = name.lower()

    # Bloquear malas calidades
    if BAD_QUALITY_PATTERNS.search(name):
        return -1, "🚫 CAM/TS"

    # Detectar resolución
    res = ""
    if "2160p" in name_l or "4k" in name_l:
        res = "4K"
    elif "1080p" in name_l:
        res = "1080p"
    elif "720p" in name_l:
        res = "720p"
    elif "480p" in name_l:
        res = "480p"

    score = 0
    label_parts = []

    for kw, pts in QUALITY_RANK.items():
        if kw in name_l:
            score = max(score, pts)
            label_parts.append(kw.upper())

    if res:
        label_parts.insert(0, res)

    label = " · ".join(label_parts[:3]) or "SD"
    return score, label


def spanish_score(name: str) -> int:
    """
    2 = audio/subs latino confirmado
    1 = español genérico (puede ser latino)
    0 = sin indicación de español
    -1 = España detectada
    """
    has_lat  = bool(SPANISH_LATINO.search(name))
    has_es   = bool(re.search(r"\b(espa[ñn]ol|spanish|dual|multi)\b", name, re.I))
    has_spain= bool(SPANISH_SPAIN.search(name))

    if has_lat:
        return 2
    if has_spain:
        return -1
    if has_es:
        return 1
    return 0


def classify_torrent(r: dict) -> dict:
    name    = r.get("name", "")
    seeds   = int(r.get("seeders", 0))
    leeches = int(r.get("leechers", 0))
    size_b  = int(r.get("size", 0))
    ih      = r.get("info_hash", "")

    q_score, q_label = quality_score(name)
    s_score          = spanish_score(name)

    # Ícono de semillas
    if seeds >= 30:   seed_icon = "🟢"
    elif seeds >= 10: seed_icon = "🟡"
    elif seeds >= 1:  seed_icon = "🔴"
    else:             seed_icon = "⚫"

    # Ícono de idioma
    if s_score == 2:   lang_icon = "🇲🇽 Latino"
    elif s_score == 1: lang_icon = "🌎 Español"
    elif s_score == -1:lang_icon = "🇪🇸 España"
    else:              lang_icon = "🔤 Sin info"

    return {
        "name":       name,
        "seeds":      seeds,
        "leeches":    leeches,
        "size":       size_human(size_b),
        "size_bytes": size_b,
        "info_hash":  ih,
        "magnet":     magnet(ih, name),
        "q_score":    q_score,
        "q_label":    q_label,
        "s_score":    s_score,
        "seed_icon":  seed_icon,
        "lang_icon":  lang_icon,
        "blocked":    q_score == -1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# YTS API  (yts.mx — sin API key, solo películas, muy buena calidad)
# ─────────────────────────────────────────────────────────────────────────────

YTS_BASE = "https://yts.mx/api/v2"

def yts_search(title: str, year: str = None) -> list[dict]:
    """
    Busca en YTS por título. Devuelve torrents ya clasificados.
    YTS siempre es BluRay/WEB-DL de buena calidad (nunca CAM/TS).
    Nota: YTS no indica idioma — los subtítulos se buscan aparte.
    """
    query = f"{title} {year}".strip() if year else title
    params = {
        "query_term": query,
        "sort_by":    "seeds",
        "order_by":   "desc",
        "limit":      10,
    }
    url  = f"{YTS_BASE}/list_movies.json?" + urllib.parse.urlencode(params)
    data = http_get(url, timeout=12)
    if not data or data.get("status") != "ok":
        return []

    movies_list = (data.get("data") or {}).get("movies") or []
    results = []

    for movie_data in movies_list:
        m_title = movie_data.get("title", title)
        m_year  = str(movie_data.get("year", year or ""))
        for t in (movie_data.get("torrents") or []):
            quality = t.get("quality", "")           # "720p", "1080p", "2160p"
            t_type  = t.get("type", "")              # "bluray", "web"
            seeds   = int(t.get("seeds", 0))
            peers   = int(t.get("peers", 0))
            size_b  = int(t.get("size_bytes", 0))
            ih      = t.get("hash", "")
            name    = f"{m_title} ({m_year}) {quality} {t_type} [YTS]".strip()

            if not ih:
                continue

            # Score de calidad
            q_score = QUALITY_RANK.get(t_type.lower(), 0)
            res_pts  = {"2160p": 3, "1080p": 2, "720p": 1}.get(quality, 0)
            q_score  = max(q_score, res_pts + 5)   # YTS siempre es buena calidad

            q_label = f"{quality} · {t_type.upper()}" if t_type else quality

            if seeds >= 30:   seed_icon = "🟢"
            elif seeds >= 10: seed_icon = "🟡"
            elif seeds >= 1:  seed_icon = "🔴"
            else:             seed_icon = "⚫"

            results.append({
                "name":       name,
                "seeds":      seeds,
                "leeches":    peers,
                "size":       size_human(size_b),
                "size_bytes": size_b,
                "info_hash":  ih.lower(),
                "magnet":     magnet(ih, name),
                "q_score":    q_score,
                "q_label":    q_label,
                "s_score":    0,          # YTS no indica idioma
                "seed_icon":  seed_icon,
                "lang_icon":  "🔤 Subs externos",
                "blocked":    False,
                "source":     "YTS",
            })

    results.sort(key=lambda r: (r["q_score"], r["seeds"]), reverse=True)
    return results


def composite_score(t: dict) -> tuple:
    """
    Puntuación compuesta para ordenar torrents de mejor a peor.

    Prioridades (en orden):
      1. Idioma: Latino(2) > Español(1) > Sin info(0) > España(-1)
      2. Calidad: REMUX/BluRay > WEB-DL > WEBRip > DVDRip …
         YTS suma +2 porque siempre es BluRay/WEB garantizado
      3. Seeds: normalizados con log para que no dominen sobre calidad
    """
    import math
    s     = t.get("s_score", 0)
    q     = t.get("q_score", 0)
    seeds = t.get("seeds", 0)
    yts_b = 2 if t.get("source") == "YTS" else 0          # bonus YTS
    seed_n = math.log10(seeds + 1)                         # 0→0, 10→1, 100→2, 1000→3
    return (s, q + yts_b, round(seed_n, 2))


def find_movie_torrents_combined(title: str, year: str,
                                 n: int = 15) -> tuple[list[dict], list[dict]]:
    """
    Busca en TPB + YTS, combina, ordena por score compuesto y devuelve:
      (good_sorted, blocked)

    good_sorted: lista única con el mejor resultado primero.
    El campo "rank" (0-based) y "best" (True en el #1) se agregan a cada item.
    """
    tpb_all = find_movie_torrents(title, year, n=n, prefer_spanish=True)
    yts_all = yts_search(title, year)

    good    = [t for t in tpb_all if not t.get("blocked")] + yts_all
    blocked = [t for t in tpb_all if t.get("blocked")]

    # Deduplicar por info_hash
    seen  = set()
    dedup = []
    for t in good:
        ih = t.get("info_hash", "")
        if ih and ih in seen:
            continue
        seen.add(ih)
        dedup.append(t)

    dedup.sort(key=composite_score, reverse=True)

    # Marcar posición
    for i, t in enumerate(dedup):
        t["rank"] = i
        t["best"] = (i == 0)

    return dedup[:n], blocked


# ─────────────────────────────────────────────────────────────────────────────
# TMDB
# ─────────────────────────────────────────────────────────────────────────────

def tmdb_discover(api_key: str, year_gte: int, year_lte: int,
                  genre_id: int = None, page: int = 1, limit: int = 20) -> list[dict]:
    """Descubre películas populares en un rango de años."""
    params = {
        "api_key":                    api_key,
        "language":                   "es-MX",
        "sort_by":                    "popularity.desc",
        "primary_release_date.gte":   f"{year_gte}-01-01",
        "primary_release_date.lte":   f"{year_lte}-12-31",
        "vote_count.gte":             100,
        "page":                       page,
    }
    if genre_id:
        params["with_genres"] = genre_id

    url  = f"{TMDB_BASE}/discover/movie?" + urllib.parse.urlencode(params)
    data = http_get(url)
    if not data:
        return []

    results = data.get("results", [])[:limit]
    return [_format_movie(m) for m in results]


def tmdb_search(api_key: str, query: str, year: int = None) -> list[dict]:
    """Busca películas por título."""
    params = {"api_key": api_key, "language": "es-MX", "query": query}
    if year:
        params["year"] = year
    url  = f"{TMDB_BASE}/search/movie?" + urllib.parse.urlencode(params)
    data = http_get(url)
    if not data:
        return []
    return [_format_movie(m) for m in data.get("results", [])[:15]]


def tmdb_popular(api_key: str, page: int = 1) -> list[dict]:
    """Top películas populares actuales."""
    params = {"api_key": api_key, "language": "es-MX", "page": page}
    url  = f"{TMDB_BASE}/movie/popular?" + urllib.parse.urlencode(params)
    data = http_get(url)
    if not data:
        return []
    return [_format_movie(m) for m in data.get("results", [])]


def tmdb_trending(api_key: str) -> list[dict]:
    """Tendencias de la semana."""
    params = {"api_key": api_key, "language": "es-MX"}
    url  = f"{TMDB_BASE}/trending/movie/week?" + urllib.parse.urlencode(params)
    data = http_get(url)
    if not data:
        return []
    return [_format_movie(m) for m in data.get("results", [])]


def _format_movie(m: dict) -> dict:
    return {
        "id":          m.get("id"),
        "title":       m.get("title", ""),
        "title_orig":  m.get("original_title", ""),
        "year":        (m.get("release_date") or "")[:4],
        "rating":      round(m.get("vote_average", 0), 1),
        "votes":       m.get("vote_count", 0),
        "overview":    (m.get("overview") or "")[:300],
        "poster":      (f"https://image.tmdb.org/t/p/w185{m['poster_path']}"
                        if m.get("poster_path") else None),
        "genres":      m.get("genre_ids", []),
        "language":    m.get("original_language", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TPB search
# ─────────────────────────────────────────────────────────────────────────────

def tpb_search(query: str, cat: int = 200, n: int = 15) -> list[dict]:
    """
    cat 200 = Video (todas las calidades)
    cat 207 = HD Movies
    """
    url  = f"{TPB_API}?" + urllib.parse.urlencode({"q": query, "cat": cat})
    data = http_get(url)
    if not data or (data and isinstance(data, list) and data[0].get("id") == "0"):
        return []
    return data[:n]


def find_movie_torrents(title: str, year: str, n: int = 12,
                        prefer_spanish: bool = True) -> list[dict]:
    """
    Busca torrents para una película con varios fallbacks.
    Devuelve lista ordenada: (español-latino > español > otro) x (calidad > seeds)
    """
    year_str = str(year) if year else ""
    queries = []

    if prefer_spanish:
        if year_str:
            queries += [
                f"{title} {year_str} latino 1080p",
                f"{title} {year_str} español latino",
                f"{title} {year_str} lat 1080p",
                f"{title} {year_str} sub español",
            ]
        queries += [
            f"{title} latino 1080p",
            f"{title} español latino",
            f"{title} {year_str} 1080p",
            f"{title} {year_str}",
            title,
        ]
    else:
        if year_str:
            queries += [f"{title} {year_str} 1080p", f"{title} {year_str}"]
        queries.append(title)

    seen_hashes = set()
    raw_results = []

    for q in queries:
        results = tpb_search(q, cat=200, n=15)
        for r in results:
            ih = r.get("info_hash", "")
            if ih and ih not in seen_hashes:
                seen_hashes.add(ih)
                raw_results.append(r)
        if len(raw_results) >= n * 2:
            break
        time.sleep(0.3)

    classified = [classify_torrent(r) for r in raw_results]

    # Filtrar bloqueados (CAM/TS)
    good = [t for t in classified if not t["blocked"]]
    blocked = [t for t in classified if t["blocked"]]

    def sort_key(t):
        return (t["s_score"], t["q_score"], t["seeds"])

    good.sort(key=sort_key, reverse=True)

    return good[:n] + blocked  # Bloqueados al final (por si el usuario quiere verlos)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def run(api_key: str, query: str = None, decade: int = None,
        genre: str = None, limit: int = 20, output_dir: Path = None):

    print("\n🎬  MediaHub — Búsqueda de Películas")
    print("=" * 60)

    movies = []

    if query:
        print(f"\n🔎 Buscando: «{query}»...")
        movies = tmdb_search(api_key, query)
    elif decade:
        year_gte = decade * 10 + (1900 if decade < 100 else 0)
        year_lte = year_gte + 9
        genre_id = GENRE_IDS.get(genre.lower()) if genre else None
        print(f"\n📅 Películas de los {decade}s ({year_gte}–{year_lte})")
        if genre:
            print(f"   Género: {genre}")
        movies = tmdb_discover(api_key, year_gte, year_lte, genre_id, limit=limit)
    else:
        print("\n📈 Tendencias de la semana...")
        movies = tmdb_trending(api_key)

    if not movies:
        print("  Sin resultados de TMDB.")
        return

    print(f"\n  Encontradas: {len(movies)} películas")

    output_dir = output_dir or Path("output/movies")
    output_dir.mkdir(parents=True, exist_ok=True)
    magnets_path = output_dir / "magnets_movies.txt"
    report = []

    with open(magnets_path, "a", encoding="utf-8") as mag_file:
        for i, movie in enumerate(movies, 1):
            title = movie["title"]
            year  = movie["year"]
            rating= movie["rating"]
            print(f"\n  [{i}/{len(movies)}] {title} ({year}) ⭐{rating}")

            torrents = find_movie_torrents(title, year)

            best_lat = next((t for t in torrents if t["s_score"] == 2), None)
            best_esp = next((t for t in torrents if t["s_score"] >= 1), None)
            best_any = next((t for t in torrents if not t["blocked"]), None)

            best = best_lat or best_esp or best_any
            if best:
                flag = "🇲🇽" if best["s_score"] == 2 else ("🌎" if best["s_score"] >= 1 else "🔤")
                print(f"     {flag} {best['name'][:60]}")
                print(f"        Seeds: {best['seeds']} · {best['q_label']} · {best['size']}")
                mag_file.write(f"# {title} ({year})\n{best['magnet']}\n\n")
            else:
                print(f"     ✗ Sin torrents válidos")

            report.append({
                "movie":    movie,
                "torrents": [t for t in torrents if not t["blocked"]],
                "blocked":  [t for t in torrents if t["blocked"]],
            })

    report_path = output_dir / "movies_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  📄 Magnets  : {magnets_path}")
    print(f"  📄 Reporte  : {report_path}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Busca películas y sus torrents")
    parser.add_argument("--api-key",  required=True, help="TMDB API key")
    parser.add_argument("--query",    help="Buscar película por título")
    parser.add_argument("--decade",   type=int, help="Década (70, 80, 90, 2000, 2010, 2020)")
    parser.add_argument("--genre",    help="Género: accion, drama, comedia, terror...")
    parser.add_argument("--limit",    type=int, default=20)
    parser.add_argument("--output",   type=Path, default=Path("output/movies"))
    args = parser.parse_args()

    run(
        api_key    = args.api_key,
        query      = args.query,
        decade     = args.decade,
        genre      = args.genre,
        limit      = args.limit,
        output_dir = args.output,
    )
