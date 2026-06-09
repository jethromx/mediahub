# Spotify → Canciones + Torrents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un tab `🎵 Canciones` a la página Mi Spotify que muestra el listado completo de canciones importadas de Spotify y permite buscar torrents — tanto en batch como individualmente por fila — con botón de magnet para abrir en uTorrent.

**Architecture:** Se agregan helpers a nivel de módulo en `app.py` (después de `_tpb_search_cached`) para búsqueda Knaben + TPB y manejo de la cache de resultados en `output/spotify_torrents_results.json`. La función `page_spotify` se extiende con un tercer tab que lee `top_canciones.json`, muestra métricas, y renderiza filas con botones de búsqueda individual y magnet.

**Tech Stack:** Python 3, Streamlit, urllib (ya en uso), JSON file cache, Knaben DHT API, apibay.org (TPB)

---

## File Map

| Archivo | Cambio |
|---------|--------|
| `app.py:100-120` | Agregar helpers de módulo: `_size_human`, `_build_magnet`, `_knaben_search_music`, `_expand_music_queries`, `_best_torrent` |
| `app.py:83-99` | Agregar después de la sección watchlist: `SPOTIFY_RESULTS_FILE`, `_spotify_load_results`, `_spotify_save_results`, `_search_song_torrent` |
| `app.py:1635` | Cambiar `tab1, tab2` → `tab1, tab2, tab3` y agregar bloque `with tab3:` |

---

## Task 1: Helpers de módulo compartidos

**Files:**
- Modify: `app.py:119` (insertar después de `_tpb_search_cached`)

- [ ] **Step 1: Insertar los 5 helpers de módulo**

En `app.py`, después de la línea 119 (el cierre de `_tpb_search_cached`), insertar:

```python

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


def _knaben_search_music(q: str, n: int = 12) -> list:
    try:
        url = "https://knaben.eu/api/v1/search?" + _uparse_mod.urlencode({
            "search": q, "categories": "audio",
            "orderBy": "seeders", "orderType": "desc", "size": n,
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
            size_b = int(h.get("bytes") or 0)
            if not ih or not name:
                continue
            out.append({"name": name, "seeders": seeds, "size": size_b, "info_hash": ih})
        return out[:n]
    except Exception:
        return []


def _expand_music_queries(q: str) -> list:
    import unicodedata as _ud
    variants = [q]
    no_acc = "".join(c for c in _ud.normalize("NFKD", q) if _ud.category(c) != "Mn")
    if no_acc.lower() != q.lower():
        variants.append(no_acc)
    base = no_acc if no_acc.lower() != q.lower() else q
    variants.append(base + " discography")
    words = q.strip().split()
    if len(words) >= 2:
        variants.append(words[0])
    return list(dict.fromkeys(v.strip() for v in variants if v.strip()))


def _best_torrent(results: list):
    with_seeds = [r for r in results if int(r.get("seeders", 0)) > 0]
    if not with_seeds:
        return None
    quality = [r for r in with_seeds
               if any(k in r.get("name", "").upper() for k in ("320", "MP3"))]
    pool = quality if quality else with_seeds
    return max(pool, key=lambda r: int(r.get("seeders", 0)))
```

- [ ] **Step 2: Verificar que el app carga sin errores**

```bash
cd /Users/jethro/Documents/projects/mediahub
python -c "import ast; ast.parse(open('app.py').read()); print('OK — sin errores de sintaxis')"
```
Resultado esperado: `OK — sin errores de sintaxis`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat(spotify): add module-level music search helpers"
```

---

## Task 2: Cache de resultados de Spotify

**Files:**
- Modify: `app.py:98` (insertar después del bloque watchlist, antes del bloque TPB cache)

- [ ] **Step 1: Insertar la sección de cache y función de búsqueda por canción**

En `app.py`, después de la línea 98 (el cierre de `_save_watchlist`) e inmediatamente antes del comentario `# Búsqueda TPB cacheada`, insertar:

```python

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


def _search_song_torrent(artist: str, track: str) -> dict:
    """Busca el mejor torrent para una canción. Devuelve dict con status found/not_found."""
    queries = _expand_music_queries(f"{artist} {track}")
    for q in queries:
        results = _knaben_search_music(q, 10)
        best = _best_torrent(results)
        if best:
            return {
                "status": "found",
                "name": best["name"],
                "seeds": int(best.get("seeders", 0)),
                "size": _size_human(best.get("size", 0)),
                "info_hash": best.get("info_hash", ""),
                "searched_at": time.strftime("%Y-%m-%d %H:%M"),
            }
        tpb_results = _tpb_search_cached(q, 101, 10)
        tpb_normalized = [
            {
                "name": r.get("name", ""),
                "seeders": int(r.get("seeders", 0)),
                "size": int(r.get("size", 0)),
                "info_hash": r.get("info_hash", ""),
            }
            for r in tpb_results
        ]
        best = _best_torrent(tpb_normalized)
        if best:
            return {
                "status": "found",
                "name": best["name"],
                "seeds": int(best.get("seeders", 0)),
                "size": _size_human(best.get("size", 0)),
                "info_hash": best.get("info_hash", ""),
                "searched_at": time.strftime("%Y-%m-%d %H:%M"),
            }
    return {"status": "not_found", "searched_at": time.strftime("%Y-%m-%d %H:%M")}
```

**Nota importante:** `_search_song_torrent` llama a `_build_magnet`, `_knaben_search_music`, `_expand_music_queries`, `_best_torrent`, y `_size_human` — todas deben estar definidas antes en el archivo (Task 1). `_tpb_search_cached` ya está a nivel de módulo en la línea ~108.

- [ ] **Step 2: Verificar sintaxis**

```bash
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```
Resultado esperado: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat(spotify): add results cache and per-song torrent search"
```

---

## Task 3: Tab Canciones en page_spotify

**Files:**
- Modify: `app.py:1635` (dentro de `page_spotify`)

- [ ] **Step 1: Cambiar la línea de tabs**

Localizar en `page_spotify` (línea ~1635):
```python
        tab1, tab2 = st.tabs(["▶ Ejecutar", "📂 Resultados"])
```

Reemplazar con:
```python
        tab1, tab2, tab3 = st.tabs(["▶ Ejecutar", "📂 Resultados", "🎵 Canciones"])
```

- [ ] **Step 2: Agregar el bloque `with tab3:` después del bloque `with tab2:`**

Localizar el cierre del bloque `with tab2:` (línea ~1650):
```python
        with tab2:
            out = BASE_DIR / "output"
            if (out / "reporte.txt").exists():
                output_files_section(out, extensions=[".txt", ".json"])
```

Inmediatamente después (antes del doble salto de línea que separa de `page_phone`), agregar:

```python

        with tab3:
            canciones_path = BASE_DIR / "output" / "top_canciones.json"
            if not canciones_path.exists():
                st.info("Primero ejecuta el análisis en **▶ Ejecutar** para generar el listado de canciones.")
            else:
                canciones = json.loads(canciones_path.read_text(encoding="utf-8"))
                results   = _spotify_load_results()

                # ── Métricas ──────────────────────────────────────────────────
                n_total     = len(canciones)
                n_found     = sum(1 for c in canciones
                                  if results.get(f"{c['artist']} — {c['track']}", {}).get("status") == "found")
                n_not_found = sum(1 for c in canciones
                                  if results.get(f"{c['artist']} — {c['track']}", {}).get("status") == "not_found")
                n_pending   = n_total - n_found - n_not_found

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total canciones", n_total)
                m2.metric("✅ Encontradas",  n_found)
                m3.metric("❌ Sin resultado", n_not_found)
                m4.metric("⏳ Sin buscar",    n_pending)

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

                if run_all or retry_nf:
                    to_search = [
                        c for c in canciones
                        if (run_all and f"{c['artist']} — {c['track']}" not in results)
                        or (retry_nf and results.get(f"{c['artist']} — {c['track']}", {}).get("status") == "not_found")
                    ]
                    prog_bar  = st.progress(0.0)
                    prog_text = st.empty()
                    total_s   = len(to_search)
                    for idx, c in enumerate(to_search):
                        label = f"{c['artist']} — {c['track']}"
                        prog_text.text(f"Buscando {idx + 1}/{total_s}: {label}…")
                        prog_bar.progress((idx + 1) / total_s)
                        results[label] = _search_song_torrent(c["artist"], c["track"])
                        if idx % 5 == 0:
                            _spotify_save_results(results)
                        time.sleep(1.0)
                    _spotify_save_results(results)
                    prog_text.success(f"✅ Listo — {total_s} canciones buscadas.")
                    st.rerun()

                st.markdown("---")

                # ── Filtro ────────────────────────────────────────────────────
                filtro = st.radio(
                    "Filtrar",
                    ["Todas", "✅ Encontradas", "❌ Sin resultado", "⏳ Sin buscar"],
                    horizontal=True,
                    key="spo_filtro",
                )

                def _filtrar(c):
                    key    = f"{c['artist']} — {c['track']}"
                    status = results.get(key, {}).get("status")
                    if filtro == "✅ Encontradas":   return status == "found"
                    if filtro == "❌ Sin resultado":  return status == "not_found"
                    if filtro == "⏳ Sin buscar":     return status is None
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
                    cache_key = f"{c['artist']} — {c['track']}"
                    res       = results.get(cache_key, {})
                    status    = res.get("status")
                    plays     = c.get("plays", 0)

                    with st.container(border=True):
                        col_info, col_status, col_action = st.columns([4, 2, 2])

                        with col_info:
                            st.markdown(f"**{c['artist']}** — {c['track']}")
                            st.caption(f"🔁 {plays} plays")

                        with col_status:
                            if status == "found":
                                name_t = res.get("name", "")[:60]
                                seeds  = res.get("seeds", 0)
                                size   = res.get("size", "?")
                                seed_icon = "🟢" if seeds >= 20 else ("🟡" if seeds >= 5 else "🔴")
                                st.caption(f"✅ {name_t}")
                                st.caption(f"{seed_icon} {seeds} seeds · {size}")
                            elif status == "not_found":
                                st.caption("❌ Sin resultado")
                            else:
                                st.caption("⏳ Sin buscar")

                        with col_action:
                            if status == "found":
                                ih  = res.get("info_hash", "")
                                mag = _build_magnet(ih, res.get("name", ""))
                                st.link_button("🧲 Abrir", mag,
                                               use_container_width=True,
                                               help="Abrir en uTorrent / qBittorrent")
                            else:
                                btn_label = "🔄 Reintentar" if status == "not_found" else "🔍 Buscar"
                                if st.button(btn_label, key=f"spo_search_{i}",
                                             use_container_width=True):
                                    with st.spinner(f"Buscando {c['artist']} — {c['track']}…"):
                                        results[cache_key] = _search_song_torrent(c["artist"], c["track"])
                                        _spotify_save_results(results)
                                    st.rerun()
```

- [ ] **Step 3: Verificar sintaxis**

```bash
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```
Resultado esperado: `OK`

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat(spotify): add Canciones tab with batch + per-row torrent search"
```

---

## Task 4: Verificación manual en el navegador

- [ ] **Step 1: Reiniciar la app**

Si la app está corriendo, detenerla (Ctrl+C) y volver a iniciar:
```bash
streamlit run app.py --server.port 8501
```

- [ ] **Step 2: Navegar a Mi Spotify**

Abrir http://localhost:8501 → sidebar → **🟢 Mi Spotify**

Verificar que aparecen **tres tabs**: `▶ Ejecutar`, `📂 Resultados`, `🎵 Canciones`

- [ ] **Step 3: Verificar tab Canciones sin datos**

Si no hay `output/top_canciones.json`, el tab debe mostrar:
> "Primero ejecuta el análisis en ▶ Ejecutar para generar el listado de canciones."

- [ ] **Step 4: Verificar tab Canciones con datos existentes**

Si ya existe `output/top_canciones.json` (el usuario ya ejecutó el análisis):
- Las 4 métricas deben mostrar números correctos
- El botón "🚀 Buscar todas las pendientes" debe estar activo si hay canciones sin buscar
- Las filas deben renderizar sin errores — cada una con info, estado y botón de acción

- [ ] **Step 5: Probar búsqueda individual**

Hacer clic en "🔍 Buscar" en cualquier fila con estado `⏳ Sin buscar`.
- Debe mostrar spinner con el nombre de la canción
- Al terminar, el botón cambia a `🧲 Abrir` (si encontró resultado) o `🔄 Reintentar` (si no encontró)
- El resultado persiste al cambiar de página y volver

- [ ] **Step 6: Probar botón magnet**

Hacer clic en `🧲 Abrir` en una fila con resultado encontrado.
- El navegador debe intentar abrir el magnet link
- uTorrent / qBittorrent debe recibir la descarga si está configurado como handler de `magnet:`

- [ ] **Step 7: Commit final si todo OK**

```bash
git add -p  # confirmar que no hay cambios pendientes
git log --oneline -4
```
