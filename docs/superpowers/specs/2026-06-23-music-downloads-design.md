# Diseño — Descargas de música: registro, metadata/portada y mejores torrents

- **Fecha:** 2026-06-23
- **Rama:** `feature/music-downloads`
- **Proyecto:** mediahub (Streamlit, `app.py` + `scripts/`)

## Objetivo

Mejorar el flujo de descarga de música en tres frentes:

1. **Registro persistente de descargas** — al descargar, guardar qué se pidió para
   que futuras búsquedas sepan que ya se descargó (o que está en proceso).
2. **Fix de metadata + portada** — una vez los archivos están en la biblioteca,
   arreglar tags y carátula de los que estén incompletos.
3. **Mejores torrents** — evitar torrents que abren pero no completan por pocos
   seeds, eligiendo automáticamente el más sano.

## Decisiones tomadas (con el usuario)

| Tema | Decisión |
|---|---|
| Detección de descarga completada | Procesar carpeta (botón que escanea `music_folder`) — sin depender del cliente torrent |
| Alcance del fix de metadata | Todos los archivos con tags faltantes/pobres en todo el `music_folder` |
| Selección de torrent | Auto-elegir el más sano (scoring mejorado) |

## Contexto actual (cómo funciona hoy)

- Descargar = `subprocess.Popen(["open", magnet])`: se entrega al cliente torrent del
  SO. mediahub **no** sabe cuándo termina ni dónde cae el archivo.
- `_best_torrent(results)`: filtra `seeders>0`, prefiere nombres con `320`/`MP3`,
  devuelve el de más seeds. No considera tamaño ni mínimo de seeds.
- `_scan_music_library(folder)`: indexa la biblioteca por `artista|||título`
  (tags ID3 vía mutagen + nombre de archivo).
- `_is_downloaded(lib_keys, artist, track)`: marca "descargada" si está en el índice.
- `download_history.json`: log grueso de eventos (`_record_download`), no por canción.
- `dedup_music.py`: **lee** tags pero no los escribe ni maneja portadas.
- `mutagen` está disponible.

## Componente 1 — Ledger de descargas

**Archivo:** `output/downloads_ledger.json` (en `output/`, ya ignorado por git).

**Esquema** (dict keyed por `"artista — track"`):

```json
{
  "Bad Bunny — Tití Me Preguntó": {
    "artist": "Bad Bunny",
    "track": "Tití Me Preguntó",
    "info_hash": "…",
    "magnet": "magnet:?xt=…",
    "torrent_name": "Bad Bunny - Un Verano Sin Ti [FLAC]",
    "source": "Knaben",
    "seeds": 23,
    "size": "612 MB",
    "requested_at": "2026-06-23 16:00",
    "status": "requested",        // requested → completed
    "completed_at": null,
    "file_path": null,
    "tagged": false
  }
}
```

**Helpers (en `app.py`):**

- `_ledger_load() -> dict` / `_ledger_save(d)`
- `_ledger_record_request(song: dict, result: dict)` — al pulsar 🧲 Abrir; crea/actualiza
  con `status="requested"`.
- `_ledger_mark_completed(key, file_path)` — desde el procesado de carpeta.

**Estados en la UI** (Canciones, Tendencias, búsqueda individual):

- **✅ Descargada** — presente en la biblioteca (`_scan_music_library`) o `completed` en el ledger.
- **⬇️ Pedida** — `requested` en el ledger pero aún no aparece en la biblioteca (bajando).
- **⏳ Sin buscar / sin pedir**.

`_is_downloaded` se extiende para considerar también el ledger (`completed`).

## Componente 2 — Procesar descargas + fix de metadata/portada

**Nuevo script:** `scripts/tag_music.py` (CLI + importable, mismo patrón que `dedup_music.py`).

**Nueva UI:** pestaña **"🏷️ Metadata & Portadas"** en la página *Limpiar duplicados*
(`page_phone`), que ya gestiona la biblioteca.

**Flujo:**

1. Escanea `music_folder` (mp3, flac, m4a en el MVP).
2. Para cada archivo con **tags pobres** (sin artista, sin título o sin portada):
   1. Deduce artista/título de tags existentes o del nombre (`Artista - Título`).
   2. Consulta **Shazam** (reusa `_shazam_lookup`/caché) → artista/título canónicos,
      álbum, año, género y **URL de portada**.
   3. Escribe tags con **mutagen**: artista, título, álbum, año, género.
   4. Descarga la portada y la **embebe** (APIC en MP3; `Picture` en FLAC; `covr` en M4A).
   5. Reconcilia con el ledger: si coincide con una entrada, marca `completed` + `tagged`
      y guarda `file_path`.
3. **Dry-run**, barra de progreso y reporte JSON (como dedup).

**Criterio "tags pobres":** falta artista **o** falta título **o** no tiene portada embebida.
(No reescribe archivos ya completos.)

## Componente 3 — Selección de torrents sana

Reescritura de `_best_torrent`:

```
_best_torrent(results, single_track=True, min_seeds=3)
```

- Descarta resultados con `seeders < min_seeds`.
- **Score de salud:** prioriza seeds; **penaliza tamaño** cuando `single_track`
  (una discografía de decenas de GB con pocos seeds es mala apuesta para una canción).
  Empuja hacia álbum/single con buena relación seeds/tamaño.
- Calidad (FLAC/320 en el nombre) como **desempate**, no como criterio principal.
- Si **nada** pasa `min_seeds`, devuelve el mejor disponible marcándolo con
  `low_seeds=True` para que la UI muestre **⚠️ pocos seeds**.

**Score (borrador):**

```
quality_bonus = 1.3 si nombre tiene FLAC/320/MP3, si no 1.0
size_gb       = size / 1e9
size_penalty  = 1.0 si !single_track o size_gb <= 1.5
                si single_track y size_gb > 1.5: 1 + (size_gb - 1.5) * 0.15
score = seeds * quality_bonus / size_penalty
```

(Valores afinables; la idea es que 30 seeds @ 600MB gane a 4 seeds @ 40GB.)

**Config:** nuevo ajuste `min_seeds` (default 3) en ⚙️ Configuración, leído por las
búsquedas de canciones.

## Flujo de datos

1. Búsqueda → `_search_song_torrent` → `_all_sources_search` (4 fuentes) →
   `_best_torrent` (sano) → resultado con seeds/size/source/low_seeds.
2. 🧲 Abrir → `open` magnet + `_ledger_record_request`.
3. Más tarde → "🏷️ Procesar descargas" → escanea, tagea, embebe portada, reconcilia ledger.
4. Las filas muestran ✅ / ⬇️ Pedida / ⏳ según biblioteca + ledger.

## Pruebas

- **Unit** `_best_torrent`: combinaciones seeds/tamaño/calidad → verifica que elige el sano
  y respeta `min_seeds`/`low_seeds`. Función pura, fácil.
- **Ledger**: round-trip load/save/record_request/mark_completed.
- **Tagger**: normalización y emparejado de archivos (dry-run sobre muestras); verificación
  de que detecta "tags pobres" correctamente.
- **Smoke**: `python -m py_compile`, la app carga (HTTP 200).

## Archivos afectados

- `app.py`: helpers de ledger; registrar al descargar (3 puntos de botón); extender
  `_is_downloaded`; reescribir `_best_torrent` + propagar `low_seeds` a la UI; pestaña
  "Metadata & Portadas"; config `min_seeds`.
- `scripts/tag_music.py`: **nuevo** (metadata + portadas, CLI + import).
- `docs/superpowers/specs/2026-06-23-music-downloads-design.md`: este documento.

## Fuera de alcance (YAGNI)

- Integración con cliente torrent (qBittorrent/Transmission) y watcher de carpeta:
  descartados a favor de "procesar carpeta".
- Formatos exóticos de audio en el tagger (solo MP3/FLAC/M4A en MVP).
- Búsqueda directa (tab2) — el preview/ledger aplican a Canciones y Tendencias.
