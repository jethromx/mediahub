#!/usr/bin/env python3
"""
export_m3u.py — Genera una playlist .m3u8 con todos los audios de una carpeta.

Uso:
  python3 export_m3u.py <carpeta> [--out ruta.m3u8]

Incluye duración y "Artista - Título" (#EXTINF) cuando hay tags (mutagen).
Las rutas se escriben relativas al archivo de playlist.
"""

import argparse
import sys
from pathlib import Path

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac", ".wma", ".alac"}

try:
    from mutagen import File as MutagenFile
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


def _meta(path: Path):
    """(duracion_seg, 'Artista - Título') desde tags; fallback al nombre."""
    dur, title = -1, path.stem
    if HAS_MUTAGEN:
        try:
            mf = MutagenFile(str(path), easy=True)
            if mf is not None:
                if mf.info and getattr(mf.info, "length", 0):
                    dur = int(mf.info.length)
                if mf.tags:
                    a = (mf.tags.get("artist") or [""])[0]
                    t = (mf.tags.get("title") or [""])[0]
                    if a and t:
                        title = f"{a} - {t}"
        except Exception:
            pass
    return dur, title


def run(folder: Path, out: Path = None) -> int:
    if not folder.exists():
        sys.exit(f"[!] La carpeta no existe: {folder}")
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in AUDIO_EXTS)
    if not files:
        sys.exit("[!] No se encontraron archivos de audio.")
    out = Path(out) if out else folder / "playlist.m3u8"

    lines = ["#EXTM3U"]
    for p in files:
        dur, title = _meta(p)
        try:
            rel = p.relative_to(out.parent)
        except ValueError:
            rel = p
        lines.append(f"#EXTINF:{dur},{title}")
        lines.append(str(rel))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✓ {len(files)} pistas → {out}")
    return len(files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera una playlist .m3u8 de una carpeta")
    parser.add_argument("source", type=Path, help="Carpeta con tu música")
    parser.add_argument("--out", type=Path, default=None, help="Ruta del .m3u8 de salida")
    args = parser.parse_args()
    run(args.source, args.out)
