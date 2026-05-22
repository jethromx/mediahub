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
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
PYTHON      = sys.executable

DEFAULT_CONFIG = {
    "lastfm_api_key":    "7049ab07a1bbfce19db16bea7b004b29",
    "spotify_client_id": "25fedca142ec4de8b5663c330f9d21de",
    "spotify_secret":    "7a44614137a94523b4c5ab867400fe37",
    "music_folder":      str(Path.home() / "Downloads" / "Musica"),
    "ebooks_folder":     str(Path.home() / "Downloads" / "Ebooks"),
    "phone_folder":      str(Path.home() / "Downloads" / "Musica_Movil"),
    "phone_use_limit":   False,
    "phone_limit_gb":    32,
    "top_tracks":        100,
    "top_books":         120,
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
# Utilidades UI
# ─────────────────────────────────────────────────────────────────────────────

def stream_script(cmd, log_placeholder, status_placeholder):
    """Ejecuta un comando y muestra su salida en tiempo real."""
    log_lines = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
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
# Páginas
# ─────────────────────────────────────────────────────────────────────────────

def page_inicio():
    st.title("🎵 MediaHub")
    st.markdown("Descarga música y ebooks, y mantén tus metadatos siempre actualizados.")

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 🎵 Música")
        st.markdown(
            "Obtiene el top de canciones de **Last.fm** por género "
            "y busca sus torrents MP3 en The Pirate Bay."
        )
        if st.button("Ir a Música", use_container_width=True):
            st.session_state.page = "🎵 Música"
            st.rerun()

    with col2:
        st.markdown("### 📚 Ebooks")
        st.markdown(
            "Lista los libros más leídos en inglés y español "
            "y descarga ficheros .torrent para Kindle."
        )
        if st.button("Ir a Ebooks", use_container_width=True):
            st.session_state.page = "📚 Ebooks"
            st.rerun()

    with col3:
        st.markdown("### 🔧 Fix Metadata")
        st.markdown(
            "Analiza tus MP3s, completa los tags que faltan "
            "y descarga la portada de cada canción."
        )
        if st.button("Ir a Fix Metadata", use_container_width=True):
            st.session_state.page = "🔧 Fix Metadata"
            st.rerun()

    st.divider()

    col4, col5, _ = st.columns(3)
    with col4:
        st.markdown("### 📱 Exportar al Móvil")
        st.markdown(
            "Genera una copia de toda tu música **sin canciones repetidas**, "
            "lista para transferir al celular."
        )
        if st.button("Ir a Exportar al Móvil", use_container_width=True):
            st.session_state.page = "📱 Exportar al Móvil"
            st.rerun()

    st.divider()

    # Estado rápido
    cfg = load_config()
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        music_count = len(list(Path(cfg["music_folder"]).rglob("*.mp3"))) if Path(cfg["music_folder"]).exists() else 0
        st.metric("MP3s en tu biblioteca", music_count)
    with col_b:
        t_music = BASE_DIR / "output" / "torrents"
        st.metric("Torrents de música", len(list(t_music.glob("*.torrent"))) if t_music.exists() else 0)
    with col_c:
        t_ebooks = BASE_DIR / "output_ebooks" / "torrents"
        st.metric("Torrents de ebooks", len(list(t_ebooks.glob("*.torrent"))) if t_ebooks.exists() else 0)


def page_musica():
    st.title("🎵 Música — Last.fm → The Pirate Bay")
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

    tab1, tab2, tab3 = st.tabs(["▶ Ejecutar búsqueda", "🔎 Buscar artista / canción", "📂 Resultados anteriores"])

    with tab1:
        st.markdown(
            "Descarga el top de canciones de **Last.fm**, busca cada una en "
            "The Pirate Bay (MP3) y genera ficheros `.torrent` para uTorrent."
        )

        if st.button("🚀 Iniciar búsqueda", type="primary", use_container_width=True):
            # Actualiza config con valores del form
            cfg["top_tracks"] = top_tracks
            cfg["genres"]     = genres
            cfg["lastfm_api_key"] = cfg["lastfm_api_key"]
            save_config(cfg)

            # Parchea el script con los parámetros actuales
            script = BASE_DIR / "scripts" / "lastfm_export.py"
            code   = script.read_text()

            # Actualiza constantes en el script
            import re
            code = re.sub(r'LASTFM_API_KEY\s*=\s*"[^"]*"',
                          f'LASTFM_API_KEY = "{cfg["lastfm_api_key"]}"', code)
            code = re.sub(r'TOP_TRACKS_TPB\s*=\s*\d+',
                          f'TOP_TRACKS_TPB = {top_tracks}', code)
            genres_repr = repr(genres)
            code = re.sub(r'GENRES\s*=\s*\[.*?\]', f'GENRES = {genres_repr}', code, flags=re.DOTALL)
            script.write_text(code)

            status = st.empty()
            log    = st.empty()
            status.info("⏳ Ejecutando — puede tardar varios minutos...")
            ok = stream_script([PYTHON, "-u", str(script)], log, status)
            if ok:
                status.success("✅ ¡Listo!")
            else:
                status.error("❌ El script terminó con errores")

    # ── Tab 2: Búsqueda directa en TPB ───────────────────────────────────────
    with tab2:
        st.markdown("Busca cualquier artista o canción directamente en **The Pirate Bay** y descarga el `.torrent`.")

        col_q, col_cat = st.columns([3, 1])
        with col_q:
            query = st.text_input("🔎 Artista, canción o álbum",
                                  placeholder="ej: Metallica, Bohemian Rhapsody, The Wall...",
                                  key="tpb_query")
        with col_cat:
            categoria = st.selectbox("Categoría", ["MP3", "Música (todo)", "Todas"], key="tpb_cat")

        cat_map = {"MP3": 101, "Música (todo)": 100, "Todas": 0}
        n_resultados = st.slider("Número de resultados", 3, 20, 8, key="tpb_n")

        buscar = st.button("🔍 Buscar en The Pirate Bay", type="primary",
                           use_container_width=True, disabled=not query)

        if buscar and query:
            import urllib.request, urllib.parse, json as _json

            TPB_API = "https://apibay.org/q.php"
            TORRENT_SOURCES = [
                "https://itorrents.org/torrent/{ih}.torrent",
                "https://torcache.net/torrent/{ih}.torrent",
            ]

            def _tpb_search(q, cat, n):
                url = f"{TPB_API}?" + urllib.parse.urlencode({"q": q, "cat": cat})
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = _json.loads(r.read().decode())
                    if data and data[0].get("id") == "0":
                        return []
                    return data[:n]
                except Exception as e:
                    st.error(f"Error conectando con TPB: {e}")
                    return []

            def _size_human(b):
                try:
                    b = int(b)
                    for u in ("B","KB","MB","GB"):
                        if b < 1024: return f"{b:.0f} {u}"
                        b //= 1024
                    return f"{b:.1f} TB"
                except: return "?"

            def _magnet(r):
                ih   = r.get("info_hash","")
                name = urllib.parse.quote(r.get("name",""))
                tr   = ("tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
                        "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce")
                return f"magnet:?xt=urn:btih:{ih}&dn={name}&{tr}"

            with st.spinner(f"Buscando «{query}» en The Pirate Bay..."):
                resultados = _tpb_search(query, cat_map[categoria], n_resultados)

            if not resultados:
                st.warning("Sin resultados. Prueba con otra búsqueda o categoría.")
            else:
                st.success(f"✅ {len(resultados)} resultados para **{query}**")

                torrents_dir = BASE_DIR / "output" / "torrents"
                torrents_dir.mkdir(parents=True, exist_ok=True)

                for i, r in enumerate(resultados):
                    name  = r.get("name","")
                    seeds = int(r.get("seeders", 0))
                    leeches = int(r.get("leechers", 0))
                    size  = _size_human(r.get("size", 0))
                    ih    = r.get("info_hash","")
                    mag   = _magnet(r)

                    # Color según seeds
                    if seeds >= 20:   seed_color = "🟢"
                    elif seeds >= 5:  seed_color = "🟡"
                    else:             seed_color = "🔴"

                    with st.container(border=True):
                        col_info, col_meta, col_btns = st.columns([4, 2, 2])

                        with col_info:
                            st.markdown(f"**{name[:80]}**")

                        with col_meta:
                            st.caption(f"{seed_color} {seeds} seeds · {leeches} leechers")
                            st.caption(f"💾 {size}")

                        with col_btns:
                            # Botón descargar .torrent
                            keep  = set(" ._-()[]")
                            fname = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)[:80].strip() + ".torrent"
                            dest  = torrents_dir / fname

                            col_dl, col_mag = st.columns(2)
                            with col_dl:
                                if dest.exists():
                                    with open(dest, "rb") as fh:
                                        st.download_button("⬇ .torrent", fh.read(), fname,
                                                           key=f"dl_s_{i}", use_container_width=True,
                                                           help="Ya descargado — clic para guardar")
                                else:
                                    if st.button("⬇ Guardar", key=f"save_{i}",
                                                 use_container_width=True, help="Descargar .torrent"):
                                        try:
                                            ih_up = ih.upper()
                                            saved = False
                                            for tpl in TORRENT_SOURCES:
                                                try:
                                                    req = urllib.request.Request(
                                                        tpl.format(ih=ih_up),
                                                        headers={"User-Agent": "Mozilla/5.0"})
                                                    with urllib.request.urlopen(req, timeout=10) as resp:
                                                        data = resp.read()
                                                    if data and data[0:1] == b'd':
                                                        dest.write_bytes(data)
                                                        saved = True
                                                        break
                                                except: continue
                                            if saved:
                                                st.success("✅ Guardado")
                                            else:
                                                st.error("Sin servidor disponible")
                                        except Exception as ex:
                                            st.error(f"Error: {ex}")
                            with col_mag:
                                st.link_button("🧲 Magnet", mag,
                                               use_container_width=True,
                                               help="Abrir magnet link en uTorrent")

    # ── Tab 3: Resultados anteriores ─────────────────────────────────────────
    with tab3:
        out  = BASE_DIR / "output"
        torr = out / "torrents"
        log_path = out / "lastfm_search_log.json"

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

            # CSS inline para badges
            st.markdown("""
<style>
.badge-new    { background:#1a6b3c; color:#7dffb3; padding:2px 8px; border-radius:4px; font-size:.75rem; font-weight:600; }
.badge-cached { background:#1a3a5c; color:#7ec8ff; padding:2px 8px; border-radius:4px; font-size:.75rem; font-weight:600; }
.badge-nf     { background:#5c1a1a; color:#ffaaaa; padding:2px 8px; border-radius:4px; font-size:.75rem; font-weight:600; }
.song-row     { padding: 4px 0; border-bottom: 1px solid #222; }
</style>""", unsafe_allow_html=True)

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
    st.title("📚 Ebooks — Libros para Kindle")
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
            import re
            code = script.read_text()
            code = re.sub(r'TOP_BOOKS_TPB\s*=\s*\d+', f'TOP_BOOKS_TPB = {top_books}', code)
            script.write_text(code)
            status = st.empty()
            log    = st.empty()
            status.info("⏳ Ejecutando — puede tardar varios minutos...")
            ok = stream_script([PYTHON, "-u", str(script)], log, status)
            if ok:
                status.success("✅ ¡Listo!")
            else:
                status.error("❌ El script terminó con errores")

    # ── Tab 2: búsqueda directa ───────────────────────────────────────────────
    with tab2:
        st.markdown("Busca cualquier libro, autor o colección directamente en **The Pirate Bay**.")

        st.caption(SEED_LEGEND)
        st.markdown("---")

        col_q, col_cat = st.columns([3, 1])
        with col_q:
            query_eb = st.text_input(
                "📖 Título, autor o colección",
                placeholder="ej: Gabriel García Márquez, Harry Potter, Stephen King epub...",
                key="eb_query",
            )
        with col_cat:
            cat_eb = st.selectbox(
                "Categoría",
                ["Ebooks (601)", "Todas"],
                key="eb_cat",
                help="601 = categoría oficial de ebooks en TPB",
            )

        cat_map_eb = {"Ebooks (601)": 601, "Todas": 0}
        n_eb = st.slider("Número de resultados", 3, 20, 8, key="eb_n")

        buscar_eb = st.button("🔍 Buscar", type="primary",
                              use_container_width=True, disabled=not query_eb)

        if buscar_eb and query_eb:
            torrents_dir_eb = BASE_DIR / "output_ebooks" / "torrents"
            torrents_dir_eb.mkdir(parents=True, exist_ok=True)

            with st.spinner(f"Buscando «{query_eb}» en The Pirate Bay..."):
                res_eb = _eb_search(query_eb, cat_map_eb[cat_eb], n_eb)

            if not res_eb:
                st.warning("Sin resultados. Prueba con otro título, autor o en categoría **Todas**.")
            else:
                st.success(f"✅ {len(res_eb)} resultados para **{query_eb}**")

                for i, r in enumerate(res_eb):
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
                                            help="Ya descargado — clic para guardar en tu equipo",
                                        )
                                else:
                                    if st.button("⬇ Guardar", key=f"eb_save_{i}",
                                                 use_container_width=True,
                                                 help="Descarga el fichero .torrent a output_ebooks/torrents/"):
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
                                                st.success("✅ Guardado en output_ebooks/torrents/")
                                            else:
                                                st.error("No disponible en servidores de caché — usa el magnet")
                                        except Exception as ex:
                                            st.error(f"Error: {ex}")
                            with col_mag:
                                st.link_button(
                                    "🧲 Magnet", mag,
                                    use_container_width=True,
                                    help="Abre directamente en uTorrent sin guardar ningún fichero",
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
    st.title("🔧 Fix Metadata — MP3s")
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
    tab1, tab2 = st.tabs(["▶ Ejecutar", "📊 Último reporte"])

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
                ok = stream_script(cmd, log, status)
                if ok:
                    status.success("✅ ¡Análisis completado!")
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

            # Muestra los actualizados
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


def page_spotify():
    st.title("🟢 Spotify — Tu historial personal")
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
        tab1, tab2 = st.tabs(["▶ Ejecutar", "📂 Resultados"])
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


def page_phone():
    st.title("📱 Exportar al Móvil")
    cfg = load_config()

    st.markdown(
        "Escanea toda tu biblioteca de MP3s, elimina las canciones repetidas "
        "y copia una versión limpia a una carpeta lista para transferir al celular."
    )

    col1, col2 = st.columns(2)
    with col1:
        source_folder = st.text_input("📁 Carpeta origen (tus MP3s)", value=cfg["music_folder"])
    with col2:
        dest_folder = st.text_input("📱 Carpeta destino (para el móvil)", value=cfg["phone_folder"])

    source_path = Path(source_folder)
    dest_path   = Path(dest_folder)

    # ── Límite de tamaño ──────────────────────────────────────────────────────
    with st.expander("⚙️ Opciones avanzadas — Límite de tamaño", expanded=False):
        st.markdown(
            "Si tu celular o tarjeta SD tiene espacio limitado, activa el límite. "
            "Las canciones se ordenarán por **escuchas en Spotify** (los artistas "
            "que más escuchas van primero) para que nunca quede fuera lo que más te gusta."
        )
        col_lim1, col_lim2 = st.columns([1, 2])
        with col_lim1:
            use_limit = st.checkbox("Activar límite de tamaño",
                                    value=cfg.get("phone_use_limit", False))
        with col_lim2:
            limit_gb = st.slider(
                "Tamaño máximo (GB)", min_value=1, max_value=256,
                value=cfg.get("phone_limit_gb", 32), step=1, disabled=not use_limit,
                help="Solo se copiarán canciones hasta alcanzar este límite"
            )
        # Persiste los valores inmediatamente al cambiarlos
        if use_limit != cfg.get("phone_use_limit") or limit_gb != cfg.get("phone_limit_gb"):
            cfg["phone_use_limit"] = use_limit
            cfg["phone_limit_gb"]  = limit_gb
            save_config(cfg)

        # Info de Spotify para prioridad
        spotify_json = BASE_DIR / "output" / "top_artistas.json"
        if use_limit:
            if spotify_json.exists():
                with open(spotify_json) as f:
                    sp_data = json.load(f)
                st.success(
                    f"✅ Historial de Spotify disponible — {len(sp_data):,} artistas ordenados "
                    f"por escuchas. Se usará para priorizar."
                )
            else:
                st.warning(
                    "⚠️ No se encontró `output/top_artistas.json`. "
                    "Ejecuta primero **Mi Spotify** para generar el historial. "
                    "Sin él, la prioridad será por tamaño de fichero."
                )

    # Métricas rápidas
    st.markdown("---")
    if source_path.exists():
        mp3s = list(source_path.rglob("*.mp3"))
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("MP3s en origen", f"{len(mp3s):,}")

        # Lee último análisis o reporte
        analysis_path = dest_path.parent / "_dedup_analysis.json"
        report_path   = dest_path / "_dedup_report.json"
        last_report   = None
        if report_path.exists():
            with open(report_path) as f:
                last_report = json.load(f)
        elif analysis_path.exists():
            with open(analysis_path) as f:
                last_report = json.load(f)

        if last_report:
            col_b.metric("Únicas", f"{last_report.get('unique', 0):,}")
            col_c.metric("Duplicados a quitar", f"{last_report.get('duplicates_removed', 0):,}")
            excl = last_report.get("excluded_by_limit", 0)
            col_d.metric("Excluidas por límite", f"{excl:,}" if excl else "—")
        else:
            col_b.metric("Únicas", "—")
            col_c.metric("Duplicados", "—")
            col_d.metric("Tamaño est.", "—")
    else:
        st.warning("⚠️ La carpeta origen no existe. Verifica la ruta.")

    # ── Tabs principales ──────────────────────────────────────────────────────
    tab_run, tab_dups, tab_report = st.tabs(["▶ Ejecutar", "🔁 Lista de duplicados", "📊 Reporte"])

    with tab_run:
        st.markdown(
            "**Flujo recomendado:** primero *Analizar* para ver los duplicados, "
            "luego *Exportar* para copiar."
        )
        col_dry, col_run = st.columns(2)

        def build_cmd(dry: bool) -> list:
            script = BASE_DIR / "scripts" / "dedup_music.py"
            cmd = [PYTHON, "-u", str(script), source_folder, dest_folder]
            if dry:
                cmd.append("--dry-run")
            if use_limit and limit_gb:
                cmd += ["--limit-gb", str(limit_gb)]
            if spotify_json.exists():
                cmd += ["--spotify-data", str(spotify_json)]
            return cmd

        with col_dry:
            if st.button("🔍 Analizar (sin copiar)", use_container_width=True):
                if not source_path.exists():
                    st.error("La carpeta origen no existe.")
                else:
                    cfg["phone_folder"] = dest_folder
                    save_config(cfg)
                    status = st.empty()
                    log    = st.empty()
                    status.info("🔍 Analizando — detectando duplicados y calculando tamaño...")
                    ok = stream_script(build_cmd(dry=True), log, status)
                    if ok:
                        status.success("✅ Análisis listo. Ve a la pestaña **🔁 Lista de duplicados**.")
                    else:
                        status.error("❌ Error durante el análisis")

        with col_run:
            if st.button("🚀 Exportar al móvil", type="primary", use_container_width=True):
                if not source_path.exists():
                    st.error("La carpeta origen no existe.")
                else:
                    cfg["phone_folder"] = dest_folder
                    save_config(cfg)
                    status = st.empty()
                    log    = st.empty()
                    lim_txt = f" (límite {limit_gb} GB)" if use_limit else ""
                    status.info(f"⏳ Copiando música sin repetidos{lim_txt}...")
                    ok = stream_script(build_cmd(dry=False), log, status)
                    if ok:
                        status.success(f"✅ ¡Listo! Carpeta en: {dest_folder}")
                        st.balloons()
                    else:
                        status.error("❌ Terminó con errores")

        st.caption(
            "💡 Con el **límite de tamaño activo**, si no caben todas las canciones, "
            "se priorizan las de los artistas con más escuchas en tu historial de Spotify."
        )

    # ── Tab duplicados ────────────────────────────────────────────────────────
    with tab_dups:
        # Intenta cargar el análisis más reciente (dry-run o reporte real)
        analysis_path = dest_path.parent / "_dedup_analysis.json"
        report_path   = dest_path / "_dedup_report.json"
        data = None
        data_source = None

        if report_path.exists() and analysis_path.exists():
            # Usa el más reciente
            if report_path.stat().st_mtime >= analysis_path.stat().st_mtime:
                data = json.load(open(report_path))
                data_source = "reporte de exportación"
            else:
                data = json.load(open(analysis_path))
                data_source = "análisis (dry run)"
        elif report_path.exists():
            data = json.load(open(report_path))
            data_source = "reporte de exportación"
        elif analysis_path.exists():
            data = json.load(open(analysis_path))
            data_source = "análisis (dry run)"

        if not data:
            st.info("Ejecuta primero **🔍 Analizar** para ver la lista de duplicados.")
        else:
            dup_groups = data.get("duplicate_groups", [])
            excl       = data.get("excluded_songs", [])

            st.caption(f"Datos del último {data_source} · Origen: {data.get('source', '—')}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Grupos duplicados",   f"{len(dup_groups):,}")
            col2.metric("Ficheros a omitir",   f"{data.get('duplicates_removed', 0):,}")
            col3.metric("Excluidas por límite", f"{len(excl):,}" if excl else "—")

            # ── Lista de duplicados ───────────────────────────────────────────
            if dup_groups:
                st.markdown(f"#### 🔁 Canciones con duplicados ({len(dup_groups):,} grupos)")
                st.markdown(
                    "La versión marcada con ✅ es la que **se conserva** (mayor tamaño). "
                    "Las marcadas con ✗ se **omiten**."
                )

                search = st.text_input("🔎 Filtrar por nombre", placeholder="ej: metallica, enter sandman...")
                filtered = dup_groups
                if search:
                    q = search.lower()
                    filtered = [g for g in dup_groups
                                if q in g["keep"]["name"].lower()
                                or any(q in d["name"].lower() for d in g["remove"])]

                st.caption(f"Mostrando {min(len(filtered), 200):,} de {len(filtered):,} grupos")

                for g in filtered[:200]:
                    keep    = g["keep"]
                    remove  = g["remove"]
                    with st.container():
                        col_k, col_r = st.columns([3, 1])
                        with col_k:
                            st.markdown(f"**🎵 {keep['name'][:70]}**")
                            st.caption(f"  ✅ Conservar: `{keep['name'][:60]}`  —  {keep['size_kb']:,} KB")
                            for d in remove:
                                st.caption(f"  ✗ Omitir:    `{d['name'][:60]}`  —  {d['size_kb']:,} KB")
                        with col_r:
                            saved_kb = sum(d["size_kb"] for d in remove)
                            st.caption(f"Ahorra {saved_kb:,} KB")
                        st.divider()

                if len(filtered) > 200:
                    st.caption(f"... y {len(filtered)-200} grupos más (usa el filtro para buscar)")

            # ── Excluidas por límite ──────────────────────────────────────────
            if excl:
                with st.expander(f"↷ Canciones excluidas por límite de tamaño ({len(excl):,})"):
                    st.markdown(
                        "Estas canciones **no caben** dentro del límite configurado. "
                        "Son los artistas con menos escuchas en Spotify."
                    )
                    for e in excl:
                        plays = e.get("spotify_plays", 0)
                        plays_str = f"  [{plays:,} plays]" if plays else ""
                        st.caption(f"↷ {e.get('name', '?')[:70]}  —  {e.get('size_kb', 0):,} KB{plays_str}")

    # ── Tab reporte ───────────────────────────────────────────────────────────
    with tab_report:
        report_path = dest_path / "_dedup_report.json"
        if not report_path.exists():
            st.info("Aún no hay reporte de exportación. Ejecuta **🚀 Exportar al móvil** primero.")
        else:
            with open(report_path) as f:
                report = json.load(f)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total en origen",     f"{report.get('total_source', 0):,}")
            col2.metric("Copiadas al móvil",   f"{report.get('unique', 0):,}")
            col3.metric("Dups eliminados",      f"{report.get('duplicates_removed', 0):,}")
            col4.metric("Tamaño final",
                        f"{report.get('size_total_mb', 0)/1024:.2f} GB"
                        if report.get('size_total_mb', 0) > 1024
                        else f"{report.get('size_total_mb', 0):.0f} MB")

            if report.get("limit_gb"):
                st.info(f"📏 Límite aplicado: {report['limit_gb']} GB")

            pct = round(report.get('duplicates_removed', 0)
                        / max(report.get('total_source', 1), 1) * 100, 1)
            st.caption(f"Se redujo la biblioteca un {pct}% al eliminar duplicados")

            files = report.get("files", [])
            with st.expander(f"✅ Canciones exportadas ({len(files):,})"):
                search2 = st.text_input("🔎 Filtrar", key="rep_search",
                                        placeholder="ej: metallica...")
                show = [f for f in files
                        if not search2 or search2.lower() in f.get("dest","").lower()]
                for f in show[:300]:
                    plays = f.get("spotify_plays", 0)
                    plays_str = f"  ♪{plays:,}" if plays else ""
                    dups_n = len(f.get("duplicates", []))
                    dup_str = f"  [{dups_n} dup]" if dups_n else ""
                    st.caption(f"• {f['dest'][:70]}  —  {f.get('size_kb',0):,} KB{plays_str}{dup_str}")
                if len(show) > 300:
                    st.caption(f"... y {len(show)-300} más")


def page_ayuda():
    st.title("📖 Documentación — MediaHub")
    st.markdown("Guía completa de cada sección de la aplicación.")

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

> **Nota:** El fichero `top_artistas.json` también lo usa la sección **📱 Exportar al Móvil**
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
    with st.expander("📱 Exportar al Móvil — Sin canciones repetidas", expanded=False):
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
   ├─ 📱 Exportar al Móvil → Analizar (dry run) → ver duplicados
   └─ 📱 Exportar al Móvil → Exportar → copiar carpeta al celular
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


def page_config():
    st.title("⚙️ Configuración")
    cfg = load_config()

    st.markdown("### 🔑 APIs")
    col1, col2 = st.columns(2)
    with col1:
        lastfm_key = st.text_input("Last.fm API Key", value=cfg["lastfm_api_key"], type="password")
    with col2:
        st.markdown("")
        st.markdown("")
        st.markdown("🔗 [Obtener key en Last.fm](https://www.last.fm/api/account/create)")

    st.markdown("### 📁 Carpetas")
    music_folder  = st.text_input("Carpeta de música (MP3s)", value=cfg["music_folder"])
    ebooks_folder = st.text_input("Carpeta de ebooks", value=cfg["ebooks_folder"])
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

    genres_all = [
        "rock", "pop", "electronic", "hip-hop", "jazz", "metal",
        "classical", "reggae", "latin", "blues", "soul", "punk",
        "indie", "alternative", "r&b", "country", "folk",
    ]
    genres = st.multiselect("Géneros activos", genres_all, default=cfg.get("genres", genres_all[:10]))

    st.markdown("### 📚 Preferencias de ebooks")
    top_books = st.slider("Libros a buscar", 20, 300, cfg["top_books"], 10)

    st.markdown("---")
    if st.button("💾 Guardar configuración", type="primary"):
        new_cfg = {
            **cfg,
            "lastfm_api_key": lastfm_key,
            "music_folder":   music_folder,
            "ebooks_folder":  ebooks_folder,
            "phone_folder":      phone_folder,
            "phone_use_limit":   phone_use_limit,
            "phone_limit_gb":    phone_limit_gb,
            "top_tracks":     top_tracks,
            "top_books":      top_books,
            "genres":         genres,
        }
        save_config(new_cfg)

        # Actualiza los scripts con la nueva key
        for script_name, key_const in [("lastfm_export.py", "LASTFM_API_KEY"), ("fix_metadata.py", "LASTFM_API_KEY")]:
            script = BASE_DIR / "scripts" / script_name
            if script.exists():
                import re
                code = script.read_text()
                code = re.sub(rf'{key_const}\s*=\s*"[^"]*"', f'{key_const} = "{lastfm_key}"', code)
                script.write_text(code)

        st.success("✅ Configuración guardada")


# ─────────────────────────────────────────────────────────────────────────────
# Layout principal
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MediaHub",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS extra
st.markdown("""
<style>
    [data-testid="stSidebar"] { background-color: #1a1a2e; }
    [data-testid="stSidebar"] * { color: #eee !important; }
    .stButton > button { border-radius: 8px; }
    .stMetric { background: #0f0f23; border-radius: 8px; padding: 12px; }
</style>
""", unsafe_allow_html=True)

# Navegación sidebar
if "page" not in st.session_state:
    st.session_state.page = "🏠 Inicio"

with st.sidebar:
    st.markdown("## 🎵 MediaHub")
    st.markdown("---")
    pages = ["🏠 Inicio", "🎵 Música", "📚 Ebooks", "🟢 Mi Spotify", "🔧 Fix Metadata", "📱 Exportar al Móvil", "⚙️ Configuración", "📖 Ayuda"]
    for p in pages:
        if st.button(p, use_container_width=True, key=f"nav_{p}",
                     type="primary" if st.session_state.page == p else "secondary"):
            st.session_state.page = p
            st.rerun()
    st.markdown("---")
    st.caption("v1.0 — MediaHub")

# Renderiza la página activa
{
    "🏠 Inicio":           page_inicio,
    "🎵 Música":           page_musica,
    "📚 Ebooks":           page_ebooks,
    "🟢 Mi Spotify":       page_spotify,
    "🔧 Fix Metadata":     page_metadata,
    "📱 Exportar al Móvil": page_phone,
    "⚙️ Configuración":    page_config,
    "📖 Ayuda":            page_ayuda,
}[st.session_state.page]()
