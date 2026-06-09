# Spotify → Canciones + Torrents

**Fecha:** 2026-06-09
**Módulo:** `page_spotify` en `app.py`
**Tipo:** Nueva feature — tab interactivo de búsqueda de torrents por canción

---

## Objetivo

La página Mi Spotify ya importa el historial de Spotify y genera `top_canciones.json`. Lo que falta es una UI interactiva que muestre esa lista, busque torrents para cada canción, y permita abrir el magnet directamente en uTorrent con un clic.

---

## Estructura de datos

### Entrada (ya existe)
`output/top_canciones.json` — generado por `spotify_export.py`
```json
[{"artist": "Billie Eilish", "track": "BIRDS OF A FEATHER", "plays": 142, "ms": 852000}, ...]
```
Ordenado por plays descendente.

### Cache de resultados (nuevo)
`output/spotify_torrents_results.json` — creado y actualizado por la nueva feature
```json
{
  "Billie Eilish — BIRDS OF A FEATHER": {
    "status": "found",
    "name": "Billie Eilish - Happier Than Ever (Explicit)",
    "seeds": 87,
    "size": "320 MB",
    "info_hash": "abc123def456",
    "searched_at": "2026-06-09 12:00"
  },
  "Radiohead — Creep": {
    "status": "not_found",
    "searched_at": "2026-06-09 12:05"
  }
}
```

La cache persiste entre sesiones. El batch skip canciones que ya tienen entrada en la cache.

---

## UI

### Ubicación
Tercer tab en `page_spotify`: `🎵 Canciones`. Solo se muestra si `output/top_canciones.json` existe.

### Barra de métricas
```
Total: 847  |  ✅ Encontradas: 312  |  ❌ Sin resultado: 45  |  ⏳ Sin buscar: 490
```

### Botones de acción
- `🚀 Buscar todos` — busca en batch todas las canciones sin resultado en la cache
- `🔄 Re-buscar no encontradas` — reintenta solo las que tienen `status: not_found`

### Progreso del batch
Mientras corre el batch:
- Barra de progreso (`st.progress`)
- Texto en vivo: `"Buscando 47/847: Billie Eilish — BIRDS OF A FEATHER..."`
- Guarda a disco después de cada canción (tolerante a interrupciones)

### Filtro de tabla
Selector encima de la tabla: `Todos | ✅ Encontradas | ❌ Sin resultado | ⏳ Sin buscar`

### Tabla interactiva
Columnas: `#`, `Artista`, `Canción`, `Plays`, `Estado`, `Torrent (nombre · seeds · tamaño)`, `Acción`

Estados posibles por fila:
- `✅ Encontrado` → columna Torrent muestra nombre + seeds + tamaño, botón `🧲 Abrir`
- `❌ Sin resultado` → botón `🔄 Reintentar`
- `⏳ Sin buscar` → botón `🔍 Buscar`

### Botón magnet
Usa `st.link_button("🧲 Abrir", url="magnet:?xt=urn:btih:...")` — el navegador lo pasa a uTorrent/qBittorrent automáticamente.

---

## Lógica de búsqueda

### Fuentes en cascada
1. **Knaben DHT** (`knaben.eu/api/v1/search`, categoría `audio`) — primaria
2. **TPB apibay** (`apibay.org/q.php`, cat=101) — fallback si Knaben devuelve 0 con seeds

### Query principal
`"Artista Canción"` — ej. `"Billie Eilish BIRDS OF A FEATHER"`

### Variantes automáticas (si query principal falla)
1. Sin acentos — `unicodedata.normalize` + encode ASCII
2. Artista + discografía — `"Billie Eilish discography"`
3. Artista solo — `"Billie Eilish"`

Se prueban en orden; se para en la primera que devuelve al menos 1 torrent con seeds > 0.

### Criterio de selección del mejor torrent
1. Descartar torrents con `seeds == 0`
2. Del resto: elegir el de mayor `seeds`
3. Empate: preferir nombre que contenga `"320"` o `"MP3"` (case-insensitive)

### Rate limiting
1 segundo de pausa entre búsquedas en batch.

### Si no hay resultado tras todas las variantes
Guardar `status: not_found` en cache. El botón de esa fila muestra `🔄 Reintentar`.

---

## Cambios en el código

### `app.py` — `page_spotify`
- Agregar tab `🎵 Canciones` a los tabs existentes (`▶ Ejecutar`, `📂 Resultados`)
- Implementar toda la lógica del tab dentro de `page_spotify` (consistente con el patrón del resto de páginas)
- Reusar helpers de búsqueda: `_knaben_music` y `_tpb_search_cached` ya definidos en el scope de `page_musica` — extraer a funciones module-level para compartir, o reimplementar inline (patrón consistente con el resto del archivo)

### `scripts/spotify_export.py`
- Sin cambios — sigue generando `top_canciones.json` igual que hoy

---

## Fuera de alcance
- Búsqueda por artista (discografía) — queda para una iteración futura
- Deduplicación de canciones ya descargadas
- Integración directa con cliente torrent vía API
