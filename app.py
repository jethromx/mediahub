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
    "tmdb_api_key":      "",
    "music_folder":      str(Path.home() / "Downloads" / "Musica"),
    "ebooks_folder":     str(Path.home() / "Downloads" / "Ebooks"),
    "movies_folder":     str(Path.home() / "Downloads" / "Peliculas"),
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
    cfg = load_config()

    # ── Hero ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="mh-hero">
        <div style="font-size:2.6rem;font-weight:900;background:linear-gradient(135deg,#a78bfa,#60a5fa,#34d399);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:8px;">
            🎵 MediaHub
        </div>
        <div style="color:#8888b0;font-size:1.05rem;max-width:560px;line-height:1.7;">
            Tu biblioteca de música, películas y ebooks, <strong style="color:#c4b5fd;">completamente local</strong> y sin suscripciones.
            Descarga, organiza y exporta — todo desde tu máquina.
        </div>
        <div style="margin-top:18px;display:flex;gap:10px;flex-wrap:wrap;">
            <span class="mh-badge mh-badge-purple">🔒 100% Local</span>
            <span class="mh-badge mh-badge-blue">🎵 Last.fm + TPB</span>
            <span class="mh-badge mh-badge-green">🎬 Películas Latino</span>
            <span class="mh-badge mh-badge-yellow">🔧 Fix Metadata</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Métricas rápidas ──────────────────────────────────────────────────────
    music_count = len(list(Path(cfg["music_folder"]).rglob("*.mp3"))) if Path(cfg["music_folder"]).exists() else 0
    t_music  = BASE_DIR / "output" / "torrents"
    t_ebooks = BASE_DIR / "output_ebooks" / "torrents"
    n_torrents_music  = len(list(t_music.glob("*.torrent")))  if t_music.exists()  else 0
    n_torrents_ebooks = len(list(t_ebooks.glob("*.torrent"))) if t_ebooks.exists() else 0

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("🎵 MP3s en biblioteca", f"{music_count:,}")
    with col_b:
        st.metric("🎵 Torrents música", n_torrents_music)
    with col_c:
        st.metric("📚 Torrents ebooks", n_torrents_ebooks)

    st.markdown('<div class="mh-section-title">Módulos disponibles</div>', unsafe_allow_html=True)

    # ── Tarjetas de módulos ───────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="mh-card">
            <span class="mh-card-icon">🎵</span>
            <div class="mh-card-title">Música</div>
            <div class="mh-card-desc">
                Obtiene el top de canciones de <strong>Last.fm</strong> por género
                y descarga torrents MP3 desde The Pirate Bay.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Música →", use_container_width=True, key="home_musica"):
            st.session_state.page = "🎵 Música"
            st.rerun()

    with col2:
        st.markdown("""
        <div class="mh-card">
            <span class="mh-card-icon">🎬</span>
            <div class="mh-card-title">Películas</div>
            <div class="mh-card-desc">
                Explora películas de los 70s hasta hoy vía <strong>TMDB</strong>,
                encuentra torrents en español <strong>latino</strong> y filtra calidad CAM/TS.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Películas →", use_container_width=True, key="home_movies"):
            st.session_state.page = "🎬 Películas"
            st.rerun()

    with col3:
        st.markdown("""
        <div class="mh-card">
            <span class="mh-card-icon">📚</span>
            <div class="mh-card-title">Ebooks</div>
            <div class="mh-card-desc">
                Lista los libros más leídos en inglés y español
                y descarga ficheros <strong>.torrent</strong> para Kindle.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Ebooks →", use_container_width=True, key="home_ebooks"):
            st.session_state.page = "📚 Ebooks"
            st.rerun()

    with col3:
        st.markdown("""
        <div class="mh-card">
            <span class="mh-card-icon">🟢</span>
            <div class="mh-card-title">Mi Spotify</div>
            <div class="mh-card-desc">
                Procesa tu historial personal de Spotify y busca
                los torrents de tus artistas más escuchados.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Mi Spotify →", use_container_width=True, key="home_spotify"):
            st.session_state.page = "🟢 Mi Spotify"
            st.rerun()

    col4, col5, col6 = st.columns(3)

    with col4:
        st.markdown("""
        <div class="mh-card">
            <span class="mh-card-icon">🔧</span>
            <div class="mh-card-title">Fix Metadata</div>
            <div class="mh-card-desc">
                Completa los tags ID3 de tus MP3s — artista, álbum,
                año, género y portada — automáticamente.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Fix Metadata →", use_container_width=True, key="home_meta"):
            st.session_state.page = "🔧 Fix Metadata"
            st.rerun()

    with col5:
        st.markdown("""
        <div class="mh-card">
            <span class="mh-card-icon">🧹</span>
            <div class="mh-card-title">Limpiar duplicados</div>
            <div class="mh-card-desc">
                Detecta y borra los duplicados <strong>directamente en tu biblioteca</strong>,
                liberando espacio sin crear carpetas extra.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Limpiar →", use_container_width=True, key="home_phone"):
            st.session_state.page = "🧹 Limpiar duplicados"
            st.rerun()

    with col6:
        st.markdown("""
        <div class="mh-card">
            <span class="mh-card-icon">📊</span>
            <div class="mh-card-title">Explorador</div>
            <div class="mh-card-desc">
                Visualiza qué carpetas ocupan más espacio, navega nivel a nivel
                y detecta dónde está el peso de tu biblioteca.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Ir a Explorador →", use_container_width=True, key="home_exp"):
            st.session_state.page = "📊 Explorador"
            st.rerun()


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
    st.title("🧹 Limpiar duplicados")
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
    tab_run, tab_dups, tab_export = st.tabs([
        "🧹 Limpiar duplicados",
        "🔁 Lista de duplicados",
        "📦 Exportar a carpeta",
    ])

    script = BASE_DIR / "scripts" / "dedup_music.py"

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

    col3, col4 = st.columns(2)
    with col3:
        tmdb_key = st.text_input("TMDB API Key (películas)", value=cfg.get("tmdb_api_key", ""),
                                 type="password",
                                 help="Necesaria para la sección 🎬 Películas")
    with col4:
        st.markdown("")
        st.markdown("")
        st.markdown("🔗 [Obtener key en TMDB](https://www.themoviedb.org/settings/api) · Gratis")

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
            "tmdb_api_key":   tmdb_key,
            "music_folder":   music_folder,
            "ebooks_folder":  ebooks_folder,
            "movies_folder":  movies_folder,
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


def page_peliculas():
    import urllib.request, urllib.parse, json as _json, re as _re, time as _time

    st.title("🎬 Películas")
    cfg = load_config()

    # ── Importar helpers del script ───────────────────────────────────────────
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        from movies_export import (
            tmdb_discover, tmdb_search, tmdb_popular, tmdb_trending,
            find_movie_torrents, find_movie_torrents_combined,
            yts_search, GENRE_IDS, _format_movie,
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

    # ─── Tabs principales ─────────────────────────────────────────────────────
    tab_buscar, tab_decadas, tab_resultados = st.tabs([
        "🔎 Buscar película",
        "📅 Explorar por época / género",
        "📂 Resultados guardados",
    ])

    movies_dir = BASE_DIR / "output" / "movies"
    movies_dir.mkdir(parents=True, exist_ok=True)

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
                movies = tmdb_search(tmdb_key, query, year=yr)

            if not movies:
                st.warning("Sin resultados en TMDB. Prueba con el título en inglés.")
            else:
                # Permite elegir la película correcta si hay varias
                opciones = [f"{m['title']} ({m['year']}) ⭐{m['rating']}" for m in movies]
                seleccion = st.selectbox("Selecciona la película correcta", opciones, key="mov_sel")
                idx = opciones.index(seleccion)
                movie = movies[idx]

                # Tarjeta de la película
                _render_movie_card(movie)

                st.markdown("---")
                st.markdown("#### 🏴‍☠️ Torrents disponibles")
                with st.spinner("Buscando en The Pirate Bay y YTS..."):
                    tpb_t, yts_t = find_movie_torrents_combined(
                        movie["title"], movie["year"], n=n_torrents
                    )

                _render_torrents(tpb_t, yts_t, movie, movies_dir, show_blocked,
                                 key_prefix="buscar")

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 2 — Explorar por épocas y géneros
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_decadas:
        st.markdown("Descubre las **películas más populares** de cada época.")

        col_d, col_g, col_lim = st.columns([2, 2, 1])
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
        with col_lim:
            limite = st.number_input("Películas", 5, 40, 15, 5, key="mov_limit")

        buscar_epoca = st.button("🚀 Explorar", type="primary",
                                 use_container_width=True, key="mov_explore_btn")

        if buscar_epoca:
            genre_key = None
            if genero_sel != "Todos los géneros":
                genre_key = genero_sel.lower().replace(" ", "_")

            with st.spinner("Consultando TMDB..."):
                if decada_label == "Tendencias semana":
                    movies = tmdb_trending(tmdb_key)[:limite]
                elif decada_label == "Populares ahora":
                    movies = tmdb_popular(tmdb_key)[:limite]
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
                    movies = tmdb_discover(tmdb_key, y_gte, y_lte,
                                          genre_id=genre_id, limit=limite)

            if not movies:
                st.warning("Sin resultados. Prueba con otro filtro.")
            else:
                st.success(f"✅ {len(movies)} películas encontradas")
                st.session_state["mov_epoch_results"] = movies

        # Muestra resultados guardados en session
        movies = st.session_state.get("mov_epoch_results", [])
        if movies:
            for i, movie in enumerate(movies):
                with st.expander(
                    f"{'⭐' if movie['rating'] >= 7 else '🎬'} "
                    f"{movie['title']} ({movie['year']})  ·  ⭐ {movie['rating']}",
                    expanded=False,
                ):
                    _render_movie_card(movie, compact=True)
                    st.markdown("##### 🏴‍☠️ Torrents")

                    key = f"epoch_{i}"
                    if st.button("🔍 Buscar torrents", key=f"btn_{key}",
                                 use_container_width=True):
                        with st.spinner("Buscando en TPB y YTS..."):
                            tpb_t, yts_t = find_movie_torrents_combined(
                                movie["title"], movie["year"]
                            )
                        st.session_state[f"tpb_{key}"] = tpb_t
                        st.session_state[f"yts_{key}"] = yts_t

                    tpb_t = st.session_state.get(f"tpb_{key}")
                    yts_t = st.session_state.get(f"yts_{key}")
                    if tpb_t is not None or yts_t is not None:
                        _render_torrents(tpb_t or [], yts_t or [], movie, movies_dir,
                                         show_blocked=False, key_prefix=key)

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 3 — Resultados guardados
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


def _render_torrents(tpb_torrents: list, yts_torrents: list,
                     movie: dict, movies_dir: Path,
                     show_blocked: bool, key_prefix: str):
    """
    Renderiza torrents de TPB (con detección de español/latino)
    y YTS (siempre buena calidad, sin CAM/TS).
    """
    import urllib.parse as _uparse

    mag_path    = movies_dir / "magnets_movies.txt"
    tpb_good    = [t for t in tpb_torrents if not t.get("blocked")]
    tpb_blocked = [t for t in tpb_torrents if t.get("blocked")]
    yts_good    = list(yts_torrents)

    total_good = tpb_good + yts_good

    if not total_good and not tpb_blocked:
        st.warning("Sin torrents encontrados. Intenta con el título en inglés.")
        return

    # ── Resumen disponibilidad ────────────────────────────────────────────────
    has_lat = any(t.get("s_score", 0) == 2 for t in tpb_good)
    has_esp = any(t.get("s_score", 0) >= 1 for t in tpb_good)
    has_hd  = any("1080p" in t.get("q_label","") or "720p" in t.get("q_label","")
                  for t in total_good)

    pills = []
    if has_lat:  pills.append('<span class="mh-badge mh-badge-green">🇲🇽 Latino en TPB</span>')
    elif has_esp:pills.append('<span class="mh-badge mh-badge-blue">🌎 Español en TPB</span>')
    if has_hd:   pills.append('<span class="mh-badge mh-badge-purple">🎥 HD disponible</span>')
    if yts_good: pills.append('<span class="mh-badge mh-badge-yellow">🎬 YTS disponible</span>')
    if pills:
        st.markdown(" ".join(pills) + "<br>", unsafe_allow_html=True)

    def _draw_torrent(t: dict, row_key: str, label_badge: str, border_color: str):
        """Dibuja una tarjeta de torrent. Sin funciones anidadas ni st.rerun()."""
        saved_key = f"saved_{row_key}"
        is_saved  = st.session_state.get(saved_key, False)
        mag       = t["magnet"]

        # Codifica el magnet para usarlo en un href HTML
        mag_encoded = _uparse.quote(mag, safe="")

        with st.container(border=True):
            # ── Nombre ───────────────────────────────────────────────────────
            st.markdown(
                f'<div style="font-weight:600;font-size:0.88rem;color:#e2e2f0;'
                f'border-left:3px solid {border_color};padding-left:8px;margin-bottom:4px;">'
                f'{t["name"][:105]}</div>',
                unsafe_allow_html=True,
            )

            col_meta, col_actions = st.columns([3, 3])

            with col_meta:
                st.markdown(
                    f'<div style="font-size:0.8rem;color:#8888b0;line-height:1.9;">'
                    f'<b style="color:#c4b5fd;">{label_badge}</b><br>'
                    f'<span class="mh-badge mh-badge-purple" style="font-size:0.68rem;">{t["q_label"]}</span>'
                    f'&nbsp; {t["seed_icon"]} <b style="color:#e2e2f0;">{t["seeds"]}</b> seeds'
                    f' · {t["leeches"]} leechers · 💾 {t["size"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            with col_actions:
                # ── Botón: Abrir en uTorrent Web ─────────────────────────────
                # Usa un link HTML con href="magnet:..." — el navegador lo pasa
                # a uTorrent Web si está configurado como cliente por defecto.
                st.markdown(
                    f'<a href="{mag}" target="_blank" rel="noopener" '
                    f'style="display:block;width:100%;text-align:center;'
                    f'background:linear-gradient(135deg,#7050ff,#a855f7);'
                    f'color:#fff;font-weight:700;font-size:0.84rem;'
                    f'border-radius:10px;padding:9px 0;text-decoration:none;'
                    f'margin-bottom:6px;letter-spacing:0.3px;">'
                    f'▶ Abrir en uTorrent Web</a>',
                    unsafe_allow_html=True,
                )

                # ── Botón: Guardar magnet en archivo ─────────────────────────
                save_label = "✅ Magnet guardado" if is_saved else "💾 Guardar magnet"
                if st.button(save_label, key=f"btn_save_{row_key}",
                             use_container_width=True, disabled=is_saved):
                    mag_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(mag_path, "a", encoding="utf-8") as fh:
                        fh.write(
                            f"# {movie.get('title','')} ({movie.get('year','')}) "
                            f"— {t['q_label']} — {label_badge}\n"
                            f"{mag}\n\n"
                        )
                    st.session_state[saved_key] = True
                    # Sin st.rerun() — Streamlit ya recarga tras el click

            # ── Magnet link expandible ────────────────────────────────────────
            with st.expander("🔗 Ver magnet link completo"):
                st.code(mag, language="")
                st.caption(
                    "Puedes pegar este link directamente en uTorrent Web → "
                    "botón ➕ → 'Agregar enlace de torrent'."
                )

    # ═════════════════════════════════════════════════════════════════
    # Sección TPB
    # ═════════════════════════════════════════════════════════════════
    if tpb_good:
        st.markdown(
            '<div class="mh-section-title">🏴‍☠️ The Pirate Bay — con detección de idioma</div>',
            unsafe_allow_html=True,
        )
        for i, t in enumerate(tpb_good):
            s = t.get("s_score", 0)
            if t.get("source") == "YTS":
                badge, color = "🎬 YTS", "rgba(251,191,36,0.4)"
            elif s == 2:
                badge, color = "🇲🇽 Latino", "rgba(52,211,153,0.45)"
            elif s == 1:
                badge, color = "🌎 Español", "rgba(96,165,250,0.4)"
            elif s == -1:
                badge, color = "🇪🇸 España", "rgba(120,80,255,0.2)"
            else:
                badge, color = "🔤 Sin info idioma", "rgba(100,100,130,0.2)"
            _draw_torrent(t, f"{key_prefix}_tpb_{i}", badge, color)

    # ═════════════════════════════════════════════════════════════════
    # Sección YTS
    # ═════════════════════════════════════════════════════════════════
    if yts_good:
        st.markdown(
            '<div class="mh-section-title" style="margin-top:18px;">'
            '🎬 YTS — Alta calidad garantizada · BluRay / WEB · Sin CAM/TS</div>',
            unsafe_allow_html=True,
        )
        st.info(
            "ℹ️ YTS no incluye audio en español. Para subtítulos en español latino "
            "descárgalos en [Subdivx.com](https://www.subdivx.com) u "
            "[OpenSubtitles.org](https://www.opensubtitles.org) después de descargar.",
            icon="🗒️",
        )
        for i, t in enumerate(yts_good):
            _draw_torrent(t, f"{key_prefix}_yts_{i}",
                          "🎬 YTS · Alta calidad", "rgba(251,191,36,0.35)")

    # ═════════════════════════════════════════════════════════════════
    # Bloqueados
    # ═════════════════════════════════════════════════════════════════
    if show_blocked and tpb_blocked:
        with st.expander(f"🚫 Filtrados por mala calidad — {len(tpb_blocked)} resultados"):
            st.caption("CAM, TS, HDCAM, DVDSCR, etc. — grabaciones de cine o calidad inaceptable.")
            for t in tpb_blocked:
                st.markdown(
                    f'<div style="color:#6b2020;font-size:0.8rem;padding:3px 0;">'
                    f'🚫 {t["name"][:95]}'
                    f'<span style="color:#55228a;"> · {t["seeds"]} seeds</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def page_explorador():
    import os

    st.title("📊 Explorador de carpetas")
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
   BASE & BACKGROUND
═══════════════════════════════════════════════ */
html, body, [data-testid="stAppViewContainer"] {
    background: #0d0d1a !important;
    color: #e2e2f0 !important;
}
[data-testid="stMain"] {
    background: transparent !important;
}

/* ═══════════════════════════════════════════════
   SIDEBAR
═══════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #12122a 0%, #0d0d1a 100%) !important;
    border-right: 1px solid rgba(120,80,255,0.18) !important;
}
[data-testid="stSidebar"] * { color: #d0d0f0 !important; }

/* Nav buttons — base */
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(120,80,255,0.15) !important;
    border-radius: 10px !important;
    color: #c5c5e8 !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    padding: 8px 12px !important;
    transition: all 0.2s ease !important;
    text-align: left !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(120,80,255,0.18) !important;
    border-color: rgba(120,80,255,0.5) !important;
    color: #fff !important;
    transform: translateX(3px) !important;
}
/* Active nav button (primary type) */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7050ff 0%, #a855f7 100%) !important;
    border-color: transparent !important;
    color: #fff !important;
    box-shadow: 0 4px 15px rgba(120,80,255,0.4) !important;
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
}
h2, h3 { color: #c4b5fd !important; font-weight: 700 !important; }
h4, h5 { color: #a5b4fc !important; }
p, .stMarkdown p { color: #b8b8d4 !important; line-height: 1.7 !important; }

/* ═══════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════ */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    transition: all 0.2s ease !important;
    border: 1px solid rgba(120,80,255,0.3) !important;
    background: rgba(120,80,255,0.1) !important;
    color: #c4b5fd !important;
}
.stButton > button:hover {
    background: rgba(120,80,255,0.25) !important;
    border-color: rgba(120,80,255,0.6) !important;
    color: #fff !important;
    box-shadow: 0 4px 12px rgba(120,80,255,0.3) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7050ff 0%, #a855f7 100%) !important;
    border-color: transparent !important;
    color: #fff !important;
    box-shadow: 0 4px 20px rgba(120,80,255,0.45) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 25px rgba(120,80,255,0.65) !important;
    transform: translateY(-2px) !important;
    filter: brightness(1.1) !important;
}

/* ═══════════════════════════════════════════════
   METRICS
═══════════════════════════════════════════════ */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(120,80,255,0.12) 0%, rgba(168,85,247,0.08) 100%) !important;
    border: 1px solid rgba(120,80,255,0.25) !important;
    border-radius: 14px !important;
    padding: 16px !important;
    backdrop-filter: blur(8px) !important;
}
[data-testid="stMetricValue"] {
    color: #c4b5fd !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
}
[data-testid="stMetricLabel"] { color: #8888b0 !important; font-size: 0.8rem !important; }

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
    color: #8888b0 !important;
    font-weight: 500 !important;
    font-size: 0.87rem !important;
    padding: 8px 16px !important;
    border: none !important;
    background: transparent !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: linear-gradient(135deg, #7050ff, #a855f7) !important;
    color: #fff !important;
    box-shadow: 0 2px 10px rgba(120,80,255,0.4) !important;
}

/* ═══════════════════════════════════════════════
   INPUTS & SELECTS
═══════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(120,80,255,0.25) !important;
    border-radius: 10px !important;
    color: #e2e2f0 !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: rgba(120,80,255,0.7) !important;
    box-shadow: 0 0 0 3px rgba(120,80,255,0.15) !important;
}
.stSlider [data-baseweb="slider"] { color: #7050ff !important; }
.stSlider [data-baseweb="thumb"] { background: #7050ff !important; }

/* ═══════════════════════════════════════════════
   CONTAINERS / CARDS
═══════════════════════════════════════════════ */
[data-testid="stContainer"] {
    border-radius: 14px !important;
}
div[data-testid="stVerticalBlock"] > div:has(> [data-testid="stContainer"][style*="border"]) {
    background: rgba(120,80,255,0.06) !important;
    border-radius: 14px !important;
}

/* ═══════════════════════════════════════════════
   EXPANDERS
═══════════════════════════════════════════════ */
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(120,80,255,0.2) !important;
    border-radius: 12px !important;
    margin-bottom: 8px !important;
}
[data-testid="stExpander"]:hover {
    border-color: rgba(120,80,255,0.4) !important;
}
[data-testid="stExpanderToggleIcon"] { color: #7050ff !important; }

/* ═══════════════════════════════════════════════
   CODE BLOCKS / LOGS
═══════════════════════════════════════════════ */
.stCode, pre, code {
    background: rgba(0,0,0,0.4) !important;
    border: 1px solid rgba(120,80,255,0.2) !important;
    border-radius: 10px !important;
    color: #a8d8a8 !important;
    font-size: 0.8rem !important;
}

/* ═══════════════════════════════════════════════
   ALERTS & STATUS
═══════════════════════════════════════════════ */
[data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
    background: rgba(96,165,250,0.1) !important;
    border: 1px solid rgba(96,165,250,0.3) !important;
    border-radius: 10px !important;
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
   DIVIDERS
═══════════════════════════════════════════════ */
hr {
    border: none !important;
    border-top: 1px solid rgba(120,80,255,0.2) !important;
    margin: 20px 0 !important;
}

/* ═══════════════════════════════════════════════
   CAPTIONS & LABELS
═══════════════════════════════════════════════ */
.stCaption, small, [data-testid="stCaption"] {
    color: #6666a0 !important;
    font-size: 0.78rem !important;
}

/* ═══════════════════════════════════════════════
   DOWNLOAD BUTTONS
═══════════════════════════════════════════════ */
[data-testid="stDownloadButton"] > button {
    background: rgba(52,211,153,0.12) !important;
    border: 1px solid rgba(52,211,153,0.3) !important;
    color: #6ee7b7 !important;
    border-radius: 10px !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: rgba(52,211,153,0.25) !important;
    box-shadow: 0 4px 12px rgba(52,211,153,0.25) !important;
    transform: translateY(-1px) !important;
}

/* ═══════════════════════════════════════════════
   MULTISELECT TAGS
═══════════════════════════════════════════════ */
[data-baseweb="tag"] {
    background: linear-gradient(135deg, rgba(120,80,255,0.4), rgba(168,85,247,0.4)) !important;
    border-radius: 6px !important;
    color: #e2e2f0 !important;
}

/* ═══════════════════════════════════════════════
   CUSTOM HELPER CLASSES (via st.markdown)
═══════════════════════════════════════════════ */
.mh-card {
    background: linear-gradient(135deg, rgba(120,80,255,0.1) 0%, rgba(168,85,247,0.07) 100%);
    border: 1px solid rgba(120,80,255,0.25);
    border-radius: 16px;
    padding: 24px 20px;
    margin-bottom: 12px;
    transition: all 0.25s ease;
}
.mh-card:hover {
    border-color: rgba(120,80,255,0.55);
    background: linear-gradient(135deg, rgba(120,80,255,0.18) 0%, rgba(168,85,247,0.12) 100%);
    box-shadow: 0 8px 32px rgba(120,80,255,0.2);
    transform: translateY(-2px);
}
.mh-card-icon { font-size: 2.2rem; margin-bottom: 12px; display: block; }
.mh-card-title { color: #c4b5fd; font-size: 1.15rem; font-weight: 700; margin-bottom: 6px; }
.mh-card-desc { color: #8888b0; font-size: 0.88rem; line-height: 1.6; }
.mh-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.mh-badge-green  { background: rgba(52,211,153,0.15); color: #6ee7b7; border: 1px solid rgba(52,211,153,0.3); }
.mh-badge-yellow { background: rgba(251,191,36,0.15);  color: #fcd34d; border: 1px solid rgba(251,191,36,0.3); }
.mh-badge-red    { background: rgba(248,113,113,0.15); color: #fca5a5; border: 1px solid rgba(248,113,113,0.3); }
.mh-badge-blue   { background: rgba(96,165,250,0.15);  color: #93c5fd; border: 1px solid rgba(96,165,250,0.3); }
.mh-badge-purple { background: rgba(120,80,255,0.15);  color: #c4b5fd; border: 1px solid rgba(120,80,255,0.3); }
.mh-stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0; }
.mh-stat {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(120,80,255,0.2);
    border-radius: 10px;
    padding: 10px 18px;
    text-align: center;
    min-width: 100px;
}
.mh-stat-val { font-size: 1.4rem; font-weight: 800; color: #c4b5fd; }
.mh-stat-lbl { font-size: 0.72rem; color: #6666a0; margin-top: 2px; }
.mh-hero {
    background: linear-gradient(135deg, rgba(120,80,255,0.15) 0%, rgba(59,130,246,0.1) 50%, rgba(52,211,153,0.08) 100%);
    border: 1px solid rgba(120,80,255,0.2);
    border-radius: 20px;
    padding: 32px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
}
.mh-hero::before {
    content: "";
    position: absolute;
    top: -60px; right: -60px;
    width: 200px; height: 200px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(120,80,255,0.15), transparent 70%);
    pointer-events: none;
}
.mh-section-title {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #5555a0;
    margin: 24px 0 12px;
}
</style>
""", unsafe_allow_html=True)

# Navegación sidebar
if "page" not in st.session_state:
    st.session_state.page = "🏠 Inicio"

with st.sidebar:
    st.markdown("""
    <div style="padding:16px 8px 4px;margin-bottom:4px;">
        <div style="font-size:1.55rem;font-weight:900;background:linear-gradient(135deg,#a78bfa,#60a5fa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
            🎵 MediaHub
        </div>
        <div style="font-size:0.72rem;color:#44448a;letter-spacing:0.5px;margin-top:2px;">
            Tu música · Local · Sin suscripciones
        </div>
    </div>
    <div style="height:1px;background:linear-gradient(90deg,rgba(120,80,255,0.4),transparent);margin:8px 0 16px;"></div>
    """, unsafe_allow_html=True)

    pages = [
        ("🏠 Inicio",            "🏠"),
        ("🎵 Música",            "🎵"),
        ("🎬 Películas",         "🎬"),
        ("📚 Ebooks",            "📚"),
        ("🟢 Mi Spotify",        "🟢"),
        ("🔧 Fix Metadata",      "🔧"),
        ("🧹 Limpiar duplicados","🧹"),
        ("📊 Explorador",        "📊"),
        ("⚙️ Configuración",     "⚙️"),
        ("📖 Ayuda",             "📖"),
    ]
    for p, _ in pages:
        if st.button(p, use_container_width=True, key=f"nav_{p}",
                     type="primary" if st.session_state.page == p else "secondary"):
            st.session_state.page = p
            st.rerun()

    st.markdown("""
    <div style="height:1px;background:linear-gradient(90deg,rgba(120,80,255,0.4),transparent);margin:16px 0 12px;"></div>
    <div style="font-size:0.7rem;color:#33335a;text-align:center;">v1.0 · MediaHub · MIT</div>
    """, unsafe_allow_html=True)

# Renderiza la página activa
{
    "🏠 Inicio":             page_inicio,
    "🎵 Música":             page_musica,
    "🎬 Películas":          page_peliculas,
    "📚 Ebooks":             page_ebooks,
    "🟢 Mi Spotify":         page_spotify,
    "🔧 Fix Metadata":       page_metadata,
    "🧹 Limpiar duplicados": page_phone,
    "📊 Explorador":         page_explorador,
    "⚙️ Configuración":      page_config,
    "📖 Ayuda":              page_ayuda,
}[st.session_state.page]()
