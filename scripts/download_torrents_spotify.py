#!/usr/bin/env python3
"""Descarga ficheros .torrent desde los magnet links del export de Spotify."""
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

MAGNETS_FILE  = Path(__file__).parent.parent / "output" / "magnets.txt"
TORRENTS_DIR  = Path(__file__).parent.parent / "output" / "torrents_spotify"
TORRENTS_DIR.mkdir(exist_ok=True)

TORRENT_SOURCES = [
    "https://itorrents.org/torrent/{ih}.torrent",
    "https://torcache.net/torrent/{ih}.torrent",
]

def safe_filename(name, max_len=80):
    keep = set(" ._-()[]")
    out  = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)
    return out[:max_len].strip()

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

lines    = MAGNETS_FILE.read_text().splitlines()
ok = fail = skip = 0
label    = ""

print(f"\n🎵  Descargando .torrent de tu Spotify personal")
print(f"    Origen : {MAGNETS_FILE}")
print(f"    Destino: {TORRENTS_DIR}")
print("=" * 60)

for line in lines:
    line = line.strip()
    if line.startswith("#"):
        label = line[1:].strip()
        continue
    if not line.startswith("magnet:"):
        continue

    # Extrae info_hash del magnet
    m = re.search(r"urn:btih:([A-Fa-f0-9]{40})", line)
    if not m:
        continue
    ih = m.group(1)

    # Nombre del fichero a partir del label
    fname = safe_filename(label) + ".torrent"
    dest  = TORRENTS_DIR / fname

    if dest.exists():
        print(f"  — Ya existe: {fname[:55]}")
        skip += 1
        continue

    print(f"  ↓ {label[:55]}...", end=" ", flush=True)
    if download_torrent(ih, dest):
        print("✓")
        ok += 1
    else:
        print("✗")
        fail += 1
    time.sleep(0.8)

print(f"\n{'='*60}")
print(f"  ✓ Descargados : {ok}")
print(f"  — Ya existían : {skip}")
print(f"  ✗ Fallaron    : {fail}")
print(f"\n  📂 Carpeta: {TORRENTS_DIR.resolve()}")
print(f"  → En uTorrent Web: '+' → Añadir fichero → selecciona todos\n")
