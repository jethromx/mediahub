# Plan — Mejoras y features F1–F5

- **Fecha:** 2026-06-28
- **Rama:** `feature/music-downloads`
- Salido de la auditoría del proyecto.

## Alcance y estado de factibilidad

| ID | Feature | Estado | Verificable aquí |
|----|---------|--------|------------------|
| F1 | Panel de salud de fuentes | A implementar | Sí |
| F4 | Exportar playlist `.m3u` | A implementar | Sí |
| F5 | Paralelizar búsqueda directa | A implementar | Sí |
| F3 | Integrar qBittorrent | A implementar (build defensivo) | No (sin cliente corriendo) |
| F2 | Spotify Web API | **Diferida** | No — token OK pero API 403 (app en dev mode) |

Las 5 integran en `app.py`, por lo que se ejecutan **secuencialmente** (no en paralelo con agentes; se pisarían el archivo).

## F1 — Panel de salud de fuentes
- `_check_source(name, fn)` ejecuta un ping mínimo (query corta) por fuente y mide latencia/estado.
- `_sources_health()` corre todos los checks en paralelo (ThreadPoolExecutor) → lista de `{name, ok, ms, detail}`.
- Página nueva **"🩺 Salud de fuentes"** (grupo SISTEMA) con 🟢/🔴, latencia y último error; botón "Re-verificar".
- Fuentes: Knaben, SolidTorrents, BitSearch, TPB, Shazam, Apple charts, YouTube (yt-dlp), TMDB*, Last.fm* (*si hay key).
- Resuelve B1 (fallos silenciosos): da señal inmediata cuando una API cambia.

## F4 — Exportar playlist `.m3u`
- `scripts/export_m3u.py`: escanea una carpeta de audio y escribe un `.m3u8` (rutas relativas, con `#EXTINF` desde tags si hay mutagen).
- UI: sección/botón en la página *Limpiar duplicados* → genera `playlist.m3u8` en la carpeta de música.

## F5 — Paralelizar búsqueda directa
- En la pestaña *Buscar artista / canción* (tab2 de Música), las 4 fuentes se consultan en paralelo por variante (ThreadPoolExecutor) en vez de secuencial.
- Mantiene los límites por fuente y el dedupe existentes.

## F3 — Integrar qBittorrent
- `scripts/qbittorrent.py` (o módulo): `login()`, `add_magnet()`, `list_torrents()` contra la WebUI API v2.
- Config nueva: `qbit_url` (http://localhost:8080), `qbit_user`, `qbit_pass`.
- UI: ajustes en ⚙️ Configuración + página/sección **"🧲 Torrents"** que lista progreso/ETA; toggle para enviar magnets a qBittorrent en vez de `open`.
- Defensivo: si no conecta, muestra estado claro; no rompe el flujo `open` existente.

## F2 — Spotify Web API (diferida)
- Bloqueada: con las credenciales actuales el token se obtiene pero `/v1/search` responde **403** → app en *development mode* o restricción de la API.
- Acción del usuario: revisar el dashboard de Spotify (modo extendido / scopes). Se retoma luego.

## Pruebas
- F1: ejecutar `_sources_health()` y verificar estados reales.
- F4: generar `.m3u8` sobre una carpeta de prueba y validar contenido.
- F5: benchmark secuencial vs paralelo en la búsqueda directa.
- F3: pruebas de parsing/armado de requests; conexión real depende del cliente del usuario.
- Smoke: `py_compile` + app carga (HTTP 200, 0 tracebacks) tras cada feature.
