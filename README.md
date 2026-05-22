<div align="center">

# 🎵 MediaHub

**Tu biblioteca de música y ebooks, completamente local y sin suscripciones.**

Descarga música por géneros, procesa tu historial de Spotify, completa los metadatos de tus MP3s, exporta al celular sin duplicados y descarga ebooks para Kindle — todo desde una app web que corre en tu propia máquina.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)](#instalación)

</div>

---

## ✨ ¿Qué hace MediaHub?

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   Last.fm  ──►  Top canciones por género  ──►  The Pirate Bay      │
│                                                    │                │
│   Spotify  ──►  Tus artistas más escuchados ───►   │  .torrent     │
│                                                    │   files        │
│   Open Library ──► Libros trending EN/ES  ──►      │               │
│                                                    ▼               │
│                                              uTorrent Web          │
│                                                    │               │
│                                                    ▼               │
│              ~/Downloads/Musica  ◄──────────  MP3s descargados     │
│                      │                                             │
│                      ├──► 🔧 Fix Metadata  (tags + portadas)       │
│                      │                                             │
│                      └──► 📱 Exportar al Móvil (sin duplicados)    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🗂️ Secciones de la app

| Sección | Qué hace |
|---|---|
| 🎵 **Música** | Descarga torrents MP3 de las canciones más populares de Last.fm por género |
| 📚 **Ebooks** | Busca los libros más leídos (EN/ES) en formato Kindle via The Pirate Bay |
| 🟢 **Mi Spotify** | Procesa tu historial personal de Spotify y busca tus artistas favoritos |
| 🔧 **Fix Metadata** | Completa los tags ID3 de tus MP3s (artista, álbum, año, género, portada) |
| 📱 **Exportar al Móvil** | Copia tu música al celular eliminando canciones repetidas |
| ⚙️ **Configuración** | API keys, carpetas y preferencias persistentes |
| 📖 **Ayuda** | Documentación completa integrada en la app |

---

## 🚀 Instalación rápida

### Requisitos previos

- **Python 3.10+** — [descargar aquí](https://www.python.org/downloads/)
- **uTorrent Web** — para gestionar las descargas
- Conexión a internet

### 3 pasos para empezar

```bash
# 1. Clona el repositorio
git clone git@github.com:jethromx/mediahub.git
cd mediahub

# 2. Ejecuta el instalador (una sola vez)
bash instalar.sh

# 3. Inicia la app
bash iniciar.sh
```

Abre tu navegador en **http://localhost:8501** 🎉

> **Windows:** instala [Git for Windows](https://gitforwindows.org/) para usar `bash`. Luego sigue los mismos pasos.

---

## 📦 Instalación detallada

<details>
<summary><b>Mac / Linux</b></summary>

```bash
# Verifica Python
python3 --version   # necesitas 3.10 o superior

# Clona e instala
git clone git@github.com:jethromx/mediahub.git
cd mediahub
bash instalar.sh

# Inicia
bash iniciar.sh
```

</details>

<details>
<summary><b>Windows (Git Bash)</b></summary>

1. Instala [Python 3](https://www.python.org/downloads/) — activa **"Add Python to PATH"**
2. Instala [Git for Windows](https://gitforwindows.org/)
3. Abre **Git Bash** y ejecuta:

```bash
git clone git@github.com:jethromx/mediahub.git
cd mediahub
bash instalar.sh
bash iniciar.sh
```

</details>

<details>
<summary><b>Instalación manual de dependencias</b></summary>

```bash
pip3 install streamlit mutagen requests
```

</details>

---

## 🎵 Módulo: Música

Obtiene el **top de canciones** de [Last.fm](https://www.last.fm/) por género y busca cada una en **The Pirate Bay** en formato MP3.

```
Last.fm Charts                 The Pirate Bay              Tu máquina
──────────────                 ──────────────              ──────────
Top global  ──┐                                            
Top por rock  ├──► consolida ──► busca MP3 ──► .torrent ──► output/torrents/
Top por metal ┘    y deduplica   con 4 niveles   descarga   
Top por latin      unique        de fallback                
...                tracks                                  
```

**4 niveles de búsqueda (fallback automático):**
1. `"artista canción mp3"` — categoría MP3
2. `"artista canción"` — todas las categorías
3. `"artista álbum mp3"` — busca el álbum completo
4. `"artista mp3"` — discografía del artista

**Anti-duplicados inteligente:**
- Las canciones ya encontradas se reutilizan del caché sin llamar a TPB
- Los `.torrent` ya descargados no se vuelven a descargar
- La pestaña de resultados marca cada canción como **🆕 Nueva** · **♻️ Ya existía** · **✗ No encontrada**

**Archivos generados:**
```
output/
├── torrents/              ← importar en uTorrent Web
├── magnets_lastfm.txt     ← magnet links alternativos
├── reporte_lastfm.txt     ← resumen completo
└── lastfm_search_log.json ← log de estados por canción
```

---

## 📚 Módulo: Ebooks

Busca los libros más leídos combinando **Open Library** con una lista curada de clásicos y premios literarios.

**Fuentes:**
- 📖 Open Library — trending anual en inglés y búsqueda en español
- 🏆 Lista curada — ~200 títulos: clásicos, Nobel, Booker, Pulitzer, bestsellers

**Formatos buscados** (en orden de preferencia): `EPUB` → `MOBI` → `AZW3` → `Kindle`

```
output_ebooks/
├── torrents/             ← importar en uTorrent Web
├── magnets_ebooks.txt    ← magnet links
└── utorrent_ebooks.html  ← página con botones de descarga directa
```

---

## 🟢 Módulo: Mi Spotify

Procesa tu **exportación personal de Spotify** y busca tus artistas más escuchados en The Pirate Bay.

**Cómo obtener tus datos de Spotify:**

```
1. spotify.com/account/privacy
         │
         ▼
2. "Descarga tus datos" → Historial de reproducción extendido
         │
         ▼  (puede tardar hasta 30 días)
3. Recibes un ZIP por email
         │
         ▼
4. Extrae el ZIP en:  mediahub/spotify_data/
         │
         ▼
5. App → "Mi Spotify" → Iniciar ✓
```

**Qué analiza:**
- Lee `Streaming_History_Audio_*.json` (busca en subcarpetas automáticamente)
- Mínimo 30 segundos de reproducción para contar
- Agrupa por artista y canción, ordena por reproducciones
- Busca discografías de los top 50 artistas en TPB

> El archivo `top_artistas.json` generado también lo usa **Exportar al Móvil** para priorizar qué canciones incluir cuando hay límite de espacio.

---

## 🔧 Módulo: Fix Metadata

Completa automáticamente los **tags ID3** de tus MP3s consultando bases de datos musicales gratuitas.

```
Tu carpeta de música
        │
        ▼
  Lee cada MP3
        │
        ├── ¿Tiene título, artista, álbum, año, género, portada?
        │         │ NO
        │         ▼
        │   MusicBrainz ──► busca por nombre de archivo / tags parciales
        │         │
        │         ▼
        │    Last.fm API ──► portada del álbum
        │         │
        │         ▼
        └──► Escribe los tags faltantes en el MP3 ✓
```

**Tags que completa:**

| Tag | Campo | Fuente |
|---|---|---|
| Título | `TIT2` | MusicBrainz |
| Artista | `TPE1` | MusicBrainz |
| Álbum | `TALB` | MusicBrainz |
| Año | `TDRC` | MusicBrainz |
| Género | `TCON` | MusicBrainz |
| Portada | `APIC` | Last.fm / Cover Art Archive |

**Tres modos:**

| Modo | Descripción |
|---|---|
| `Normal` | Rellena solo campos vacíos, no toca lo que ya existe |
| `Dry Run` | Muestra qué cambiaría sin modificar ningún fichero |
| `Force` | Sobreescribe todos los tags aunque ya existan datos |

> ⏱️ MusicBrainz limita a 1 req/segundo. Con 3,000 MP3s → ~55 minutos.

---

## 📱 Módulo: Exportar al Móvil

Genera una copia de tu biblioteca **sin canciones repetidas**, lista para transferir al celular.

**¿Cómo detecta duplicados?**

```
Para cada MP3:
    │
    ├── Tiene tags ID3? ──YES──► clave = normalize(artista) + normalize(título)
    │
    └── Sin tags ────────────► clave = normalize(nombre de fichero)

Cuando hay varias copias de la misma canción:
    └──► Conserva la de MAYOR TAMAÑO (= mejor calidad / bitrate)
         Renombra como "Artista - Título.mp3"
```

**Límite de tamaño con prioridad inteligente:**

Si tu celular tiene espacio limitado, activa el límite en GB. Las canciones se ordenan por **escuchas en Spotify** — los artistas que más escuchas van primero. Nada importante queda fuera.

```
Biblioteca completa (ej. 40 GB)
        │
        ▼ limite: 16 GB
        │
        ├── José José ──── 1,197 plays  ✓ entra
        ├── Metallica ──── 1,047 plays  ✓ entra
        ├── Luis Miguel ──   900 plays  ✓ entra
        ├── ...
        └── artistas con pocas escuchas ──► excluidos (sin espacio)
```

**Pestañas disponibles:**

| Pestaña | Contenido |
|---|---|
| `▶ Ejecutar` | Analizar (sin copiar) o Exportar (con copia) |
| `🔁 Lista de duplicados` | Qué se conserva y qué se omite, con buscador |
| `📊 Reporte` | Estadísticas y lista completa de canciones exportadas |

---

## ⚙️ Configuración

Todos los ajustes se guardan en `config.json` y persisten entre sesiones.

| Campo | Default | Descripción |
|---|---|---|
| Last.fm API Key | — | Gratis en [last.fm/api](https://www.last.fm/api/account/create) |
| Carpeta de música | `~/Downloads/Musica` | Dónde están tus MP3s |
| Carpeta de ebooks | `~/Downloads/Ebooks` | Dónde van los ebooks |
| Carpeta para el móvil | `~/Downloads/Musica_Movil` | Destino sin duplicados |
| Límite de tamaño | 32 GB | Máximo para exportar al móvil |
| Canciones top | 100 | Cuántas buscar en Last.fm |
| Géneros | rock, pop, metal... | Géneros para la búsqueda |
| Libros a buscar | 120 | Total de ebooks (mitad EN / mitad ES) |

---

## 🛠️ Tecnologías utilizadas

| Categoría | Tecnología | Uso |
|---|---|---|
| **UI** | [Streamlit](https://streamlit.io/) | Interfaz web completa en Python |
| **Música** | [Last.fm API](https://www.last.fm/api) | Charts globales y por género |
| **Metadatos** | [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) | Tags de MP3 (sin API key) |
| **Portadas** | [Cover Art Archive](https://coverartarchive.org/) | Imágenes de álbumes |
| **Libros** | [Open Library API](https://openlibrary.org/developers/api) | Libros trending |
| **Torrents** | [apibay.org](https://apibay.org/) | API JSON de The Pirate Bay |
| **Tags MP3** | [mutagen](https://mutagen.readthedocs.io/) | Leer y escribir ID3 |
| **HTTP** | `urllib` (stdlib) | Todas las peticiones de red |
| **Ficheros** | `pathlib`, `shutil` (stdlib) | Manejo de archivos y carpetas |

> Todo funciona sin bases de datos, sin Docker, sin servidores — solo Python en tu máquina.

---

## 📁 Estructura del proyecto

```
mediahub/
│
├── 🟢 instalar.sh          ← Ejecutar UNA VEZ en máquina nueva
├── ▶️  iniciar.sh           ← Ejecutar cada vez para abrir la app
├── app.py                  ← App principal (Streamlit)
├── requirements.txt        ← Dependencias Python
│
├── scripts/                ← Módulos de procesamiento
│   ├── lastfm_export.py       Música: Last.fm → TPB
│   ├── ebooks_export.py       Ebooks: Open Library → TPB
│   ├── spotify_export.py      Historial personal de Spotify
│   ├── fix_metadata.py        Metadatos y portadas de MP3s
│   └── dedup_music.py         Exportación al móvil sin duplicados
│
├── spotify_data/           ← Extrae aquí el ZIP de Spotify (no se sube a git)
│
├── output/                 ← Resultados de música (no se sube a git)
│   ├── torrents/
│   ├── torrents_spotify/
│   └── ...
│
└── output_ebooks/          ← Resultados de ebooks (no se sube a git)
    ├── torrents/
    └── ...
```

---

## ❓ Solución de problemas

<details>
<summary><b>La app no abre el navegador</b></summary>

Abre manualmente: [http://localhost:8501](http://localhost:8501)

</details>

<details>
<summary><b>Error "port already in use"</b></summary>

```bash
pkill -f "streamlit run"
bash iniciar.sh
```

</details>

<details>
<summary><b>pip3 no se encuentra</b></summary>

```bash
python3 -m pip install streamlit mutagen requests
```

</details>

<details>
<summary><b>Los torrents no descargan (sin seeds)</b></summary>

Normal en torrents antiguos. Busca otra versión en [thepiratebay.org](https://thepiratebay.org) o usa el magnet link del reporte.

</details>

<details>
<summary><b>Fix Metadata es muy lento</b></summary>

MusicBrainz limita a 1 petición/segundo para proteger su servicio gratuito. Con 3,000 MP3s tarda ~55 minutos — no se puede acelerar sin riesgo de bloqueo.

</details>

<details>
<summary><b>Los ebooks no aparecen en el Kindle</b></summary>

Transfiere los `.epub` o `.mobi` al Kindle por cable USB, o usa la app **Send to Kindle** de Amazon.

</details>

<details>
<summary><b>Duplicados no se detectan bien</b></summary>

Los MP3s sin tags ID3 se identifican por nombre de fichero. Ejecuta **Fix Metadata** primero para completar los tags, luego vuelve a exportar.

</details>

<details>
<summary><b>No tengo el ZIP de Spotify todavía</b></summary>

Puede tardar hasta 30 días. Mientras tanto usa la sección **🎵 Música** con Last.fm para descargar las canciones más populares por género.

</details>

---

## 📄 Licencia

MIT — úsalo, modifícalo y distribúyelo libremente.

---

<div align="center">

Hecho con 🎵 y Python · Sin suscripciones · Sin la nube · Todo tuyo

</div>
