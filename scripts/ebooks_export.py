#!/usr/bin/env python3
"""
ebooks_export.py — Top libros en español e inglés → busca torrents en TPB.

Fuentes:
  - Open Library trending (inglés y español)
  - Lista curada: clásicos, premios Nobel/Booker/Pulitzer, bestsellers modernos
  - Géneros: ficción, ciencia ficción, fantasía, misterio, no-ficción, historia

Formatos Kindle: EPUB, MOBI, AZW3
(El Kindle actual lee EPUB nativamente desde 2022)

Uso:
  python3 ebooks_export.py
"""

import json
import time
import sys
import re
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent.parent / "output_ebooks"
OUTPUT_DIR.mkdir(exist_ok=True)
TORRENTS_DIR = OUTPUT_DIR / "torrents"
TORRENTS_DIR.mkdir(exist_ok=True)

TPB_API = "https://apibay.org/q.php"
TPB_WEB = "https://thepiratebay.org/search.php"

# Cuántos libros buscar en TPB
TOP_BOOKS_TPB = 120

# Formatos Kindle a buscar (en orden de preferencia)
KINDLE_FORMATS = ["epub", "mobi", "azw3", "kindle"]

TORRENT_SOURCES = [
    "https://itorrents.org/torrent/{ih}.torrent",
    "https://torcache.net/torrent/{ih}.torrent",
]

# ─────────────────────────────────────────────────────────────────────────────
# Lista curada de libros imprescindibles
# ─────────────────────────────────────────────────────────────────────────────

CURATED_EN = [
    # Clásicos de la literatura universal
    ("George Orwell",          "1984"),
    ("George Orwell",          "Animal Farm"),
    ("Aldous Huxley",          "Brave New World"),
    ("F. Scott Fitzgerald",    "The Great Gatsby"),
    ("Harper Lee",             "To Kill a Mockingbird"),
    ("J.D. Salinger",          "The Catcher in the Rye"),
    ("John Steinbeck",         "Of Mice and Men"),
    ("Ernest Hemingway",       "The Old Man and the Sea"),
    ("Franz Kafka",            "The Metamorphosis"),
    ("Dostoevsky",             "Crime and Punishment"),
    ("Leo Tolstoy",            "Anna Karenina"),
    ("Leo Tolstoy",            "War and Peace"),
    ("Jane Austen",            "Pride and Prejudice"),
    ("Jane Austen",            "Sense and Sensibility"),
    ("Charlotte Bronte",       "Jane Eyre"),
    ("Emily Bronte",           "Wuthering Heights"),
    ("Charles Dickens",        "Great Expectations"),
    ("Victor Hugo",            "Les Miserables"),
    ("Herman Melville",        "Moby Dick"),
    ("Mark Twain",             "Adventures of Huckleberry Finn"),
    # Premio Nobel Literatura
    ("Toni Morrison",          "Beloved"),
    ("Gabriel Garcia Marquez", "One Hundred Years of Solitude"),
    ("Kazuo Ishiguro",         "The Remains of the Day"),
    ("Kazuo Ishiguro",         "Never Let Me Go"),
    ("Orhan Pamuk",            "My Name Is Red"),
    ("Patrick Modiano",        "Missing Person"),
    ("Olga Tokarczuk",         "Flights"),
    ("Abdulrazak Gurnah",      "Paradise"),
    # Premio Booker / Pulitzer modernos
    ("Hilary Mantel",          "Wolf Hall"),
    ("Paul Auster",            "The New York Trilogy"),
    ("Colson Whitehead",       "The Underground Railroad"),
    ("Anthony Doerr",          "All the Light We Cannot See"),
    ("Donna Tartt",            "The Secret History"),
    ("Cormac McCarthy",        "The Road"),
    ("Cormac McCarthy",        "Blood Meridian"),
    ("Ian McEwan",             "Atonement"),
    ("Salman Rushdie",         "Midnight's Children"),
    # Ciencia ficción
    ("Frank Herbert",          "Dune"),
    ("Isaac Asimov",           "Foundation"),
    ("Philip K. Dick",         "Do Androids Dream of Electric Sheep"),
    ("Arthur C. Clarke",       "2001 A Space Odyssey"),
    ("Ray Bradbury",           "Fahrenheit 451"),
    ("William Gibson",         "Neuromancer"),
    ("Douglas Adams",          "The Hitchhiker's Guide to the Galaxy"),
    ("Andy Weir",              "The Martian"),
    ("Ernest Cline",           "Ready Player One"),
    # Fantasía
    ("J.R.R. Tolkien",         "The Lord of the Rings"),
    ("J.R.R. Tolkien",         "The Hobbit"),
    ("J.K. Rowling",           "Harry Potter and the Philosopher's Stone"),
    ("George R.R. Martin",     "A Game of Thrones"),
    ("Brandon Sanderson",      "The Way of Kings"),
    ("Neil Gaiman",            "American Gods"),
    ("Patrick Rothfuss",       "The Name of the Wind"),
    # Thriller / Misterio
    ("Stieg Larsson",          "The Girl with the Dragon Tattoo"),
    ("Gillian Flynn",          "Gone Girl"),
    ("Tana French",            "In the Woods"),
    ("Agatha Christie",        "And Then There Were None"),
    ("Dennis Lehane",          "Mystic River"),
    # Bestsellers modernos
    ("Yuval Noah Harari",      "Sapiens"),
    ("Yuval Noah Harari",      "Homo Deus"),
    ("Malcolm Gladwell",       "The Tipping Point"),
    ("Malcolm Gladwell",       "Outliers"),
    ("Michelle Obama",         "Becoming"),
    ("Matthew McConaughey",    "Greenlights"),
    ("Atomic Habits",          "James Clear"),
    ("James Clear",            "Atomic Habits"),
    ("Mark Manson",            "The Subtle Art of Not Giving a Fuck"),
    ("Cal Newport",            "Deep Work"),
    ("Robert Greene",          "The 48 Laws of Power"),
    ("Ryan Holiday",           "The Obstacle Is the Way"),
    # No-ficción / Historia
    ("Yuval Noah Harari",      "21 Lessons for the 21st Century"),
    ("Steven Pinker",          "The Better Angels of Our Nature"),
    ("Nassim Taleb",           "The Black Swan"),
    ("Daniel Kahneman",        "Thinking Fast and Slow"),
    ("Walter Isaacson",        "Steve Jobs"),
    ("Michael Lewis",          "The Big Short"),
]

CURATED_ES = [
    # Literatura hispanoamericana — imprescindibles
    ("Gabriel García Márquez", "Cien años de soledad"),
    ("Gabriel García Márquez", "El amor en los tiempos del cólera"),
    ("Gabriel García Márquez", "Crónica de una muerte anunciada"),
    ("Jorge Luis Borges",      "Ficciones"),
    ("Jorge Luis Borges",      "El Aleph"),
    ("Julio Cortázar",         "Rayuela"),
    ("Julio Cortázar",         "Cuentos completos"),
    ("Mario Vargas Llosa",     "La ciudad y los perros"),
    ("Mario Vargas Llosa",     "La fiesta del chivo"),
    ("Mario Vargas Llosa",     "Conversación en La Catedral"),
    ("Carlos Fuentes",         "La muerte de Artemio Cruz"),
    ("Isabel Allende",         "La casa de los espíritus"),
    ("Isabel Allende",         "Eva Luna"),
    ("Pablo Neruda",           "Veinte poemas de amor"),
    ("Octavio Paz",            "El laberinto de la soledad"),
    ("Juan Rulfo",             "Pedro Páramo"),
    ("Alejo Carpentier",       "El siglo de las luces"),
    ("Roberto Bolaño",         "Los detectives salvajes"),
    ("Roberto Bolaño",         "2666"),
    ("Elena Poniatowska",      "La noche de Tlatelolco"),
    # Literatura española
    ("Miguel de Cervantes",    "Don Quijote de la Mancha"),
    ("Federico García Lorca",  "Romancero gitano"),
    ("Antonio Machado",        "Campos de Castilla"),
    ("Miguel Delibes",         "Los santos inocentes"),
    ("Camilo José Cela",       "La familia de Pascual Duarte"),
    ("Javier Marías",          "Tu rostro mañana"),
    ("Javier Cercas",          "Soldados de Salamina"),
    ("Arturo Pérez-Reverte",   "El capitán Alatriste"),
    ("Arturo Pérez-Reverte",   "La tabla de Flandes"),
    ("Carlos Ruiz Zafón",      "La sombra del viento"),
    ("Carlos Ruiz Zafón",      "El juego del ángel"),
    ("Ildefonso Falcones",     "La catedral del mar"),
    # Bestsellers modernos en español
    ("Ken Follett",            "Los pilares de la Tierra"),
    ("Ken Follett",            "Un mundo sin fin"),
    ("Dan Brown",              "El código Da Vinci"),
    ("Dan Brown",              "Inferno"),
    ("Haruki Murakami",        "Tokio blues"),
    ("Haruki Murakami",        "Kafka en la orilla"),
    ("Milan Kundera",          "La insoportable levedad del ser"),
    ("Albert Camus",           "El extranjero"),
    ("Antoine de Saint-Exupéry", "El principito"),
    ("Paulo Coelho",           "El alquimista"),
    ("Paulo Coelho",           "Once minutos"),
    # No-ficción en español
    ("Yuval Noah Harari",      "Sapiens de animales a dioses"),
    ("Yuval Noah Harari",      "Homo Deus"),
    ("Risto Mejide",           "El arte de presentar"),
    ("Walter Isaacson",        "Steve Jobs"),
    ("Viktor Frankl",          "El hombre en busca de sentido"),
    ("Dale Carnegie",          "Cómo ganar amigos e influir sobre las personas"),
    ("Nassim Taleb",           "El cisne negro"),
    ("Mark Manson",            "El sutil arte de que todo te importe una mierda"),
    ("James Clear",            "Hábitos atómicos"),
    ("Robin Sharma",           "El monje que vendió su Ferrari"),
    # Ciencia ficción / Fantasía traducida
    ("Frank Herbert",          "Dune"),
    ("George Orwell",          "1984"),
    ("Aldous Huxley",          "Un mundo feliz"),
    ("J.R.R. Tolkien",         "El señor de los anillos"),
    ("J.K. Rowling",           "Harry Potter y la piedra filosofal"),
    ("George R.R. Martin",     "Juego de tronos"),
    ("Stieg Larsson",          "Los hombres que no amaban a las mujeres"),
    ("Gillian Flynn",          "Perdida"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Open Library API
# ─────────────────────────────────────────────────────────────────────────────

def ol_get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ebooks-export/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"    [!] Open Library error: {e}")
        return {}


def fetch_ol_trending(limit=50):
    """Top libros trending de Open Library."""
    print("  → Open Library trending (inglés)...")
    data = ol_get(f"https://openlibrary.org/trending/yearly.json?limit={limit}")
    books = []
    for w in data.get("works", []):
        author = ""
        authors = w.get("author_name", [])
        if authors:
            author = authors[0]
        books.append({
            "title":    w.get("title", ""),
            "author":   author,
            "language": "en",
            "source":   "openlibrary_trending",
        })
    print(f"     {len(books)} libros")
    return books


def fetch_ol_trending_es(limit=30):
    """Libros trending en español de Open Library."""
    print("  → Open Library trending (español)...")
    url = "https://openlibrary.org/search.json?language=spa&sort=editions&limit=30&fields=title,author_name"
    data = ol_get(url)
    books = []
    for d in data.get("docs", []):
        author = ""
        authors = d.get("author_name", [])
        if authors:
            author = authors[0]
        title = d.get("title", "")
        if title:
            books.append({
                "title":    title,
                "author":   author,
                "language": "es",
                "source":   "openlibrary_es",
            })
    print(f"     {len(books)} libros")
    return books


def build_book_list(ol_en, ol_es):
    """Combina todas las fuentes y deduplica."""
    seen  = set()
    books = []

    def add(title, author, lang, source):
        key = (title.lower().strip(), author.lower().strip())
        if key in seen or not title:
            return
        seen.add(key)
        books.append({"title": title, "author": author, "language": lang, "source": source})

    for b in ol_en:
        add(b["title"], b["author"], "en", b["source"])
    for b in ol_es:
        add(b["title"], b["author"], "es", b["source"])
    for author, title in CURATED_EN:
        add(title, author, "en", "curated_en")
    for author, title in CURATED_ES:
        add(title, author, "es", "curated_es")

    return books


# ─────────────────────────────────────────────────────────────────────────────
# The Pirate Bay
# ─────────────────────────────────────────────────────────────────────────────

def tpb_search(query, category=601, max_results=3):
    """cat=601 = eBooks"""
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
        print(f"    [!] TPB error '{query}': {e}")
        return []


def best_format_result(results):
    """De la lista de resultados, prioriza el que tenga mejor formato Kindle."""
    order = {"azw3": 0, "mobi": 1, "epub": 2, "kindle": 3}
    def score(r):
        name = r.get("name", "").lower()
        for fmt, s in order.items():
            if fmt in name:
                return s
        return 99
    return sorted(results, key=score)


def search_book_tpb(title, author, lang):
    """
    Busca un libro en TPB con fallbacks:
      1. "Author Title EPUB/MOBI" en cat 601
      2. "Author Title" en cat 601
      3. "Author Title" en cat 0
    """
    base = f"{author} {title}".strip()
    lang_hint = "español" if lang == "es" else ""

    # Intenta con cada formato Kindle
    for fmt in KINDLE_FORMATS:
        query = f"{base} {fmt}"
        if lang_hint:
            query += f" {lang_hint}"
        results = tpb_search(query, category=601, max_results=3)
        if results:
            return best_format_result(results), f"{fmt.upper()}"

    # Sin formato específico, cat eBooks
    results = tpb_search(base, category=601, max_results=3)
    if results:
        return best_format_result(results), "eBook"

    # Fallback categoría general
    results = tpb_search(base, category=0, max_results=3)
    if results:
        return best_format_result(results), "general"

    # Solo título
    results = tpb_search(title, category=601, max_results=3)
    if results:
        return best_format_result(results), f"título"

    return [], None


def magnet_link(torrent):
    ih   = torrent.get("info_hash", "")
    name = urllib.parse.quote(torrent.get("name", ""))
    trackers = (
        "tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
        "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
    )
    return f"magnet:?xt=urn:btih:{ih}&dn={name}&{trackers}"


def tpb_web_url(query):
    return f"{TPB_WEB}?q={urllib.parse.quote(query)}&cat=601"


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


def safe_filename(name, max_len=80):
    keep = set(" ._-()[]")
    out  = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)
    return out[:max_len].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Descargar .torrent
# ─────────────────────────────────────────────────────────────────────────────

def download_torrent(info_hash, dest_path):
    ih = info_hash.upper()
    for tpl in TORRENT_SOURCES:
        url = tpl.format(ih=ih)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            if data and data[0:1] == b'd':
                with open(dest_path, "wb") as f:
                    f.write(data)
                return True
        except Exception:
            continue
    return False


# ─────────────────────────────────────────────────────────────────────────────
# HTML para uTorrent Web
# ─────────────────────────────────────────────────────────────────────────────

def build_html(rows_en, rows_es, not_found):
    def section(rows, lang_label, color):
        html = f'<h2 style="color:{color};margin-top:2rem">📚 {lang_label}</h2>\n<table>\n'
        html += '<thead><tr style="color:#888;font-size:.8rem"><th></th><th style="text-align:left">Libro</th><th style="text-align:left">Torrent</th><th>Fmt</th><th>Seeds</th><th>MB</th></tr></thead><tbody>\n'
        for r in rows:
            html += (
                f'<tr>'
                f'<td><a class="btn" href="{r["magnet"]}">▶ uTorrent</a></td>'
                f'<td><strong>{r["title"]}</strong><br><span class="auth">{r["author"]}</span></td>'
                f'<td style="font-size:.8rem">{r["torrent"]}</td>'
                f'<td class="center tag">{r["fmt"]}</td>'
                f'<td class="center">{r["seeds"]}</td>'
                f'<td class="center">{r["size"]}</td>'
                f'</tr>\n'
            )
        html += '</tbody></table>\n'
        return html

    nf_html = ""
    if not_found:
        nf_html = "<h2 style='color:#666'>Sin resultados en TPB</h2><ul style='color:#666'>" + \
                  "".join(f"<li>{b}</li>" for b in not_found) + "</ul>"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>uTorrent — Ebooks Kindle</title>
<style>
  body  {{ font-family: system-ui, sans-serif; background:#1a1a2e; color:#eee; margin:0; padding:20px }}
  h1   {{ color:#f5a623 }}
  table {{ width:100%; border-collapse:collapse; font-size:.85rem; margin-bottom:2rem }}
  thead th {{ text-align:center; padding:6px 8px; border-bottom:2px solid #333 }}
  tr:hover td {{ background:#0f3460 }}
  td   {{ padding:6px 8px; border-bottom:1px solid #222; vertical-align:middle }}
  td.center {{ text-align:center; white-space:nowrap }}
  .auth {{ color:#aaa; font-size:.8rem }}
  .tag  {{ background:#0f3460; border-radius:4px; font-size:.75rem; font-weight:bold; padding:2px 6px }}
  a.btn {{
    display:inline-block; padding:4px 10px; border-radius:4px;
    background:#f5a623; color:#000; text-decoration:none; font-size:.8rem; white-space:nowrap; font-weight:bold
  }}
  a.btn:hover {{ background:#d4891e }}
</style>
</head>
<body>
<h1>📚 Ebooks Kindle — uTorrent Web</h1>
<p style="color:#888">{len(rows_en)+len(rows_es)} libros encontrados &nbsp;|&nbsp;
Formatos: EPUB · MOBI · AZW3 · Kindle &nbsp;|&nbsp;
Haz clic en <strong>▶ uTorrent</strong> para descargar</p>

{section(rows_en, "Libros en Inglés", "#4fc3f7")}
{section(rows_es, "Libros en Español", "#a5d6a7")}
{nf_html}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run():
    print("\n📚  Ebooks Export → Torrent (Kindle)\n" + "=" * 40)

    # ── 1. Descargar listas ────────────────────────────────────────────────
    print("\n[1/4] Obteniendo listas de libros...")
    ol_en = fetch_ol_trending(limit=50)
    time.sleep(0.5)
    ol_es = fetch_ol_trending_es(limit=30)
    time.sleep(0.5)

    all_books = build_book_list(ol_en, ol_es)
    en_books  = [b for b in all_books if b["language"] == "en"]
    es_books  = [b for b in all_books if b["language"] == "es"]

    print(f"\n     Total libros únicos: {len(all_books)}")
    print(f"     Inglés: {len(en_books)} | Español: {len(es_books)}")

    with open(OUTPUT_DIR / "all_books.json", "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)

    # ── 2. Mostrar lista ───────────────────────────────────────────────────
    print(f"\n[2/4] Lista de libros (primeros 30 en inglés, 30 en español):")
    print(f"\n  {'#':<4} {'Autor':<30} {'Título'}")
    print("  " + "─" * 60)
    print("  -- INGLÉS --")
    for i, b in enumerate(en_books[:30], 1):
        print(f"  {i:<4} {b['author'][:28]:<30} {b['title'][:40]}")
    print("  -- ESPAÑOL --")
    for i, b in enumerate(es_books[:30], 1):
        print(f"  {i:<4} {b['author'][:28]:<30} {b['title'][:40]}")

    # ── 3. Buscar en TPB ───────────────────────────────────────────────────
    limit_per_lang = TOP_BOOKS_TPB // 2
    to_search = en_books[:limit_per_lang] + es_books[:limit_per_lang]

    print(f"\n[3/4] Buscando {len(to_search)} libros en The Pirate Bay (formato Kindle)...")

    report_lines = [
        f"# Ebooks Export — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Inglés: {len(en_books)} | Español: {len(es_books)}",
        "",
    ]
    html_rows_en  = []
    html_rows_es  = []
    magnet_lines  = []
    not_found     = []

    for i, book in enumerate(to_search, 1):
        title  = book["title"]
        author = book["author"]
        lang   = book["language"]
        flag   = "🇬🇧" if lang == "en" else "🇪🇸"

        print(f"  [{i}/{len(to_search)}] {flag} {author[:25]} — {title[:40]}", end=" ", flush=True)

        results, fmt_used = search_book_tpb(title, author, lang)

        if results:
            r     = results[0]
            seeds = r.get("seeders", "?")
            size  = size_human(r.get("size", 0))
            name  = r.get("name", "")
            mag   = magnet_link(r)
            ih    = r.get("info_hash", "")

            # Detecta formato real en el nombre del torrent
            fmt_detected = fmt_used
            for fmt in ["azw3", "mobi", "epub"]:
                if fmt in name.lower():
                    fmt_detected = fmt.upper()
                    break

            print(f"✓ [{seeds} seeds | {size} | {fmt_detected}]")
            report_lines.append(f"✓ {flag} [{fmt_detected}] {author} — {title}")
            report_lines.append(f"    [{seeds} seeds | {size}] {name}")
            report_lines.append(f"    {mag}")
            magnet_lines.append(f"# {author} — {title} [{fmt_detected}]")
            magnet_lines.append(mag)

            row = {
                "title":     title,
                "author":    author,
                "torrent":   name[:70],
                "fmt":       fmt_detected,
                "seeds":     seeds,
                "size":      size,
                "magnet":    mag,
                "info_hash": ih,
            }
            if lang == "en":
                html_rows_en.append(row)
            else:
                html_rows_es.append(row)
        else:
            print(f"✗")
            report_lines.append(f"✗ {flag} {author} — {title} — {tpb_web_url(title)}")
            not_found.append(f"{flag} {author} — {title}")

        time.sleep(1.2)

    # ── 4. Descargar .torrent ──────────────────────────────────────────────
    all_rows   = html_rows_en + html_rows_es
    print(f"\n[4/4] Descargando {len(all_rows)} ficheros .torrent...")
    ok_count  = 0
    fail_list = []

    for row in all_rows:
        ih    = row["info_hash"]
        fname = safe_filename(f"{row['author']} - {row['title']}") + ".torrent"
        dest  = TORRENTS_DIR / fname
        print(f"  ↓ {row['author'][:20]} — {row['title'][:30]}...", end=" ", flush=True)
        if download_torrent(ih, dest):
            print("✓")
            ok_count += 1
        else:
            print("✗")
            fail_list.append(f"{row['author']} — {row['title']}")
        time.sleep(0.8)

    # ── Guardar ────────────────────────────────────────────────────────────
    with open(OUTPUT_DIR / "reporte_ebooks.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    with open(OUTPUT_DIR / "magnets_ebooks.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(magnet_lines))
    with open(OUTPUT_DIR / "utorrent_ebooks.html", "w", encoding="utf-8") as f:
        f.write(build_html(html_rows_en, html_rows_es, not_found))

    print(f"\n{'='*40}")
    print(f"¡Listo! Archivos en: {OUTPUT_DIR.resolve()}")
    print(f"  📂 torrents/                — {ok_count} ficheros .torrent para uTorrent Web")
    print(f"     → uTorrent Web: botón '+' → 'Añadir fichero' → selecciona todos")
    print(f"  🌐 utorrent_ebooks.html     — vista web con botones (alternativa)")
    print(f"  📄 reporte_ebooks.txt       — resumen completo")
    print(f"  🧲 magnets_ebooks.txt       — magnet links")
    print(f"  📁 all_books.json           — lista completa de libros")
    if fail_list:
        print(f"\n  ⚠ .torrent no descargado ({len(fail_list)}) — usa el magnet como alternativa:")
        for b in fail_list[:10]:
            print(f"     - {b}")
    if not_found:
        print(f"\n  ✗ Sin resultados en TPB ({len(not_found)}):")
        for b in not_found[:10]:
            print(f"     - {b}")
    print()


if __name__ == "__main__":
    run()
