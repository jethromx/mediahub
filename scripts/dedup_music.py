#!/usr/bin/env python3
"""
dedup_music.py — Gestiona duplicados en tu biblioteca MP3.

Modos:
  1. Copiar a carpeta limpia (por defecto):
       python3 dedup_music.py <origen> <destino> [--dry-run] [--limit-gb N]
  2. Borrar duplicados en la misma carpeta:
       python3 dedup_music.py <origen> --delete-dupes [--dry-run]

Criterios:
  - Identidad: tags ID3 (artista + título). Fallback: nombre de fichero.
  - Cuando hay varios iguales, conserva el de MAYOR TAMAÑO (mejor calidad).
  - Prioridad con --limit-gb: artistas con más escuchas en Spotify van primero.
"""

import sys
import re
import shutil
import unicodedata
import json
import argparse
from pathlib import Path

try:
    from mutagen.id3 import ID3
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_filename(name: str, max_len: int = 120) -> str:
    keep = set(" ._-")
    out = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)
    return out[:max_len].strip(" _")


def read_tags(path: Path):
    if not HAS_MUTAGEN:
        return "", ""
    try:
        tags = ID3(str(path))
        artist = str(tags.get("TPE1", tags.get("TPE2", ""))).strip()
        title  = str(tags.get("TIT2", "")).strip()
        return artist, title
    except Exception:
        return "", ""


def identity_key(artist: str, title: str, path: Path) -> str:
    a = normalize(artist)
    t = normalize(title)
    if len(a) >= 2 and len(t) >= 2:
        return f"tag|||{a}|||{t}"
    # Fallback: nombre de fichero
    stem = path.stem
    m = re.match(r"^(.+?)\s*[-–—]\s*(.+)$", stem)
    if m:
        fa = normalize(m.group(1))
        ft = normalize(m.group(2))
        if len(fa) >= 2 and len(ft) >= 2:
            return f"fn|||{fa}|||{ft}"
    return f"raw|||{normalize(stem)}"


def dest_filename(artist: str, title: str, path: Path) -> str:
    if artist and title:
        return safe_filename(f"{artist} - {title}") + ".mp3"
    return safe_filename(path.stem) + ".mp3"


def load_spotify_plays(json_path: Path) -> dict[str, int]:
    """Devuelve {normalize(artist): plays} desde top_artistas.json."""
    if not json_path or not json_path.exists():
        return {}
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        return {normalize(item["artist"]): item["plays"] for item in data if "artist" in item}
    except Exception:
        return {}


def priority_score(entry: dict, spotify_plays: dict) -> tuple:
    """Score para ordenar: (plays del artista, tamaño). Mayor = mejor."""
    artist_norm = normalize(entry.get("artist", ""))
    plays = spotify_plays.get(artist_norm, 0)
    return (plays, entry["size"])


# ─────────────────────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────────────────────

def run_delete_dupes(source_dir: Path, dry_run: bool = False):
    """
    Modo borrar duplicados: detecta y elimina directamente de source_dir
    los ficheros duplicados, conservando el de mayor tamaño.
    """
    print(f"\n🧹  Limpieza de duplicados en carpeta")
    print(f"    Carpeta: {source_dir}")
    print(f"    Modo   : {'DRY RUN (nada se borrará)' if dry_run else '⚠️  BORRADO REAL'}")
    print("=" * 60)

    if not source_dir.exists():
        print(f"\n[!] La carpeta no existe: {source_dir}")
        sys.exit(1)

    # 1. Escanear
    print("\n[1/3] Escaneando MP3s...")
    all_mp3s = sorted(source_dir.rglob("*.mp3"))
    total = len(all_mp3s)
    print(f"      Encontrados: {total:,}")
    if total == 0:
        print("      No hay MP3s.")
        sys.exit(0)

    # 2. Agrupar por identidad
    print("\n[2/3] Detectando duplicados...")
    groups: dict[str, list[dict]] = {}
    for i, mp3 in enumerate(all_mp3s, 1):
        if i % 300 == 0 or i == total:
            print(f"      Procesados: {i:,}/{total:,}", end="\r", flush=True)
        artist, title = read_tags(mp3)
        key   = identity_key(artist, title, mp3)
        entry = {"path": mp3, "artist": artist, "title": title, "size": mp3.stat().st_size}
        groups.setdefault(key, []).append(entry)
    print()

    dup_groups = []
    for key, entries in groups.items():
        best       = max(entries, key=lambda e: e["size"])
        duplicates = [e for e in entries if e is not best]
        if duplicates:
            dup_groups.append({"best": best, "duplicates": duplicates})

    total_dup_files = sum(len(g["duplicates"]) for g in dup_groups)
    total_dup_size  = sum(d["size"] for g in dup_groups for d in g["duplicates"])

    print(f"      Grupos con dups   : {len(dup_groups):,}")
    print(f"      Ficheros a borrar : {total_dup_files:,}")
    print(f"      Espacio a liberar : {total_dup_size/1024**3:.2f} GB ({total_dup_size/1024**2:.0f} MB)")

    if not dup_groups:
        print("\n✅ ¡No hay duplicados! Tu carpeta ya está limpia.")
        # Guarda análisis vacío
        analysis_path = source_dir / "_dedup_analysis.json"
        report = {
            "mode": "delete_dupes", "source": str(source_dir), "dry_run": dry_run,
            "total_source": total, "duplicates_removed": 0, "freed_mb": 0,
            "duplicate_groups": [], "deleted_files": [],
        }
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return

    # Muestra la lista
    print(f"\n{'─'*60}")
    print(f"  DUPLICADOS ({len(dup_groups):,} grupos)")
    print(f"{'─'*60}")
    for g in sorted(dup_groups, key=lambda x: x["best"]["path"].name):
        best = g["best"]
        print(f"\n  🎵 {best['path'].name[:60]}  ({best['size']//1024:,} KB — CONSERVAR)")
        for d in g["duplicates"]:
            print(f"     {'[DRY] ' if dry_run else ''}✗ BORRAR: {d['path'].name[:60]}  ({d['size']//1024:,} KB)")

    # 3. Borrar
    print(f"\n[3/3] {'Simulando borrado' if dry_run else 'Borrando duplicados'}...")
    deleted = 0
    errors  = 0
    deleted_files = []

    for g in dup_groups:
        for d in g["duplicates"]:
            try:
                if not dry_run:
                    d["path"].unlink()
                deleted += 1
                deleted_files.append({
                    "deleted": str(d["path"]),
                    "kept":    str(g["best"]["path"]),
                    "size_kb": round(d["size"] / 1024),
                })
                print(f"  {'[DRY] ' if dry_run else ''}✗ {d['path'].name[:70]}")
            except Exception as ex:
                print(f"  ⚠️  Error borrando {d['path'].name}: {ex}")
                errors += 1

    freed_mb = round(total_dup_size / 1024**2, 1)
    print(f"\n{'='*60}")
    print(f"  {'[SIMULACIÓN] ' if dry_run else ''}Ficheros borrados : {deleted:,}")
    print(f"  Errores           : {errors}")
    print(f"  Espacio liberado  : {freed_mb} MB ({freed_mb/1024:.2f} GB)")
    if not dry_run:
        print(f"\n  ✅ ¡Carpeta limpia! {source_dir.resolve()}")

    # Guardar análisis
    analysis_path = source_dir / "_dedup_analysis.json"
    report = {
        "mode":             "delete_dupes",
        "source":           str(source_dir),
        "dry_run":          dry_run,
        "total_source":     total,
        "unique":           total - total_dup_files,
        "duplicates_removed": deleted,
        "freed_mb":         freed_mb,
        "errors":           errors,
        "duplicate_groups": [
            {
                "keep":   {"name": g["best"]["path"].name, "size_kb": round(g["best"]["size"]/1024)},
                "remove": [{"name": d["path"].name, "size_kb": round(d["size"]/1024)} for d in g["duplicates"]],
            }
            for g in dup_groups
        ],
        "deleted_files": deleted_files,
    }
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  📄 Reporte: {analysis_path}\n")


def run(source_dir: Path, dest_dir: Path,
        dry_run: bool = False,
        limit_bytes: int = 0,
        spotify_data: Path = None):

    print(f"\n📱  Preparando música sin repetidos para el móvil")
    print(f"    Origen : {source_dir}")
    print(f"    Destino: {dest_dir}")
    if dry_run:
        print(f"    Modo   : DRY RUN (sin copiar nada)")
    if limit_bytes:
        gb = limit_bytes / (1024**3)
        print(f"    Límite : {gb:.1f} GB — prioridad por escuchas de Spotify")
    print("=" * 60)

    if not source_dir.exists():
        print(f"\n[!] La carpeta origen no existe: {source_dir}")
        sys.exit(1)

    # ── 1. Escanear ───────────────────────────────────────────────────────────
    print("\n[1/4] Escaneando MP3s...")
    all_mp3s = sorted(source_dir.rglob("*.mp3"))
    total = len(all_mp3s)
    print(f"      Encontrados: {total:,}")
    if total == 0:
        print("      No hay MP3s.")
        sys.exit(0)

    # ── 2. Cargar prioridades de Spotify ──────────────────────────────────────
    spotify_plays = load_spotify_plays(spotify_data)
    if spotify_plays:
        print(f"      Historial Spotify: {len(spotify_plays):,} artistas cargados")

    # ── 3. Agrupar por identidad (detectar duplicados) ────────────────────────
    print("\n[2/4] Detectando duplicados...")
    groups: dict[str, list[dict]] = {}

    for i, mp3 in enumerate(all_mp3s, 1):
        if i % 300 == 0 or i == total:
            print(f"      Procesados: {i:,}/{total:,}", end="\r", flush=True)

        artist, title = read_tags(mp3)
        key = identity_key(artist, title, mp3)
        entry = {
            "path":      mp3,
            "artist":    artist,
            "title":     title,
            "dest_name": dest_filename(artist, title, mp3),
            "size":      mp3.stat().st_size,
        }
        groups.setdefault(key, []).append(entry)

    print()

    # ── 4. Seleccionar mejor versión de cada grupo ────────────────────────────
    print("\n[3/4] Seleccionando versión preferida por grupo...")
    unique_songs = []          # [{best, duplicates}]
    dup_groups   = []          # solo los que tienen duplicados (para el reporte)

    for key, entries in groups.items():
        best       = max(entries, key=lambda e: e["size"])
        duplicates = [e for e in entries if e is not best]
        unique_songs.append({"best": best, "duplicates": duplicates})
        if duplicates:
            dup_groups.append({"best": best, "duplicates": duplicates})

    total_unique    = len(unique_songs)
    total_dup_files = sum(len(g["duplicates"]) for g in dup_groups)
    total_size_all  = sum(g["best"]["size"] for g in unique_songs)

    print(f"      Canciones únicas  : {total_unique:,}")
    print(f"      Grupos con dups   : {len(dup_groups):,}")
    print(f"      Ficheros a omitir : {total_dup_files:,}")
    gb_all = total_size_all / (1024**3)
    print(f"      Tamaño sin dups   : {gb_all:.2f} GB")

    # ── Aplicar límite de tamaño con prioridad ────────────────────────────────
    excluded_songs = []
    if limit_bytes and total_size_all > limit_bytes:
        # Ordena por (plays de Spotify, tamaño) descendente
        unique_songs.sort(key=lambda g: priority_score(g["best"], spotify_plays), reverse=True)

        included = []
        accumulated = 0
        for g in unique_songs:
            sz = g["best"]["size"]
            if accumulated + sz <= limit_bytes:
                included.append(g)
                accumulated += sz
            else:
                excluded_songs.append(g)

        unique_songs = included
        gb_included = accumulated / (1024**3)
        print(f"\n  ⚠️  Límite activo: {limit_bytes/(1024**3):.1f} GB")
        print(f"      Incluidas  : {len(included):,} canciones ({gb_included:.2f} GB)")
        print(f"      Excluidas  : {len(excluded_songs):,} canciones (no caben)")
        if excluded_songs:
            print(f"      → Las excluidas son artistas con MENOS escuchas en Spotify")
    else:
        unique_songs.sort(key=lambda g: g["best"]["dest_name"])

    # ── 5. Mostrar lista de duplicados ────────────────────────────────────────
    if dup_groups:
        print(f"\n{'─'*60}")
        print(f"  DUPLICADOS DETECTADOS ({len(dup_groups):,} grupos, {total_dup_files:,} ficheros a omitir)")
        print(f"{'─'*60}")
        for g in sorted(dup_groups, key=lambda x: x["best"]["dest_name"]):
            best = g["best"]
            label = best["dest_name"][:52] if best["dest_name"] else best["path"].name[:52]
            print(f"\n  🎵 {label}")
            print(f"     ✓ CONSERVAR : {best['path'].name[:60]}  ({best['size']//1024:,} KB)")
            for d in g["duplicates"]:
                print(f"     ✗ OMITIR    : {d['path'].name[:60]}  ({d['size']//1024:,} KB)")

    # ── Mostrar excluidas por límite ──────────────────────────────────────────
    if excluded_songs:
        print(f"\n{'─'*60}")
        print(f"  EXCLUIDAS POR LÍMITE DE TAMAÑO ({len(excluded_songs):,} canciones)")
        print(f"{'─'*60}")
        for g in excluded_songs[:50]:
            best = g["best"]
            artist_plays = spotify_plays.get(normalize(best.get("artist", "")), 0)
            label = best["dest_name"][:52] or best["path"].name[:52]
            plays_str = f"  [{artist_plays} plays]" if artist_plays else ""
            print(f"  ↷ {label}{plays_str}")
        if len(excluded_songs) > 50:
            print(f"  ... y {len(excluded_songs)-50} más")

    # ── 6. Copiar / simular ───────────────────────────────────────────────────
    print(f"\n[4/4] {'Simulando' if dry_run else 'Copiando'} {len(unique_songs):,} canciones...")

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    copied = errors = 0
    report_files = []

    for g in unique_songs:
        best = g["best"]
        dest_path = dest_dir / best["dest_name"]

        if not dry_run:
            # Resuelve colisiones de nombre
            counter = 1
            base_stem = dest_path.stem
            while dest_path.exists():
                dest_path = dest_dir / f"{base_stem}_{counter}.mp3"
                counter += 1

        try:
            if not dry_run:
                shutil.copy2(str(best["path"]), str(dest_path))
            copied += 1

            dup_count = len(g["duplicates"])
            dup_tag = f"  (+ {dup_count} dup{'s' if dup_count>1 else ''} omitido{'s' if dup_count>1 else ''})" if dup_count else ""
            label = best["dest_name"][:55]
            print(f"  ✓ {label}{dup_tag}")

            report_files.append({
                "dest":       best["dest_name"],
                "source":     str(best["path"]),
                "artist":     best["artist"],
                "title":      best["title"],
                "size_kb":    round(best["size"] / 1024),
                "spotify_plays": spotify_plays.get(normalize(best.get("artist", "")), 0),
                "duplicates": [
                    {"path": str(d["path"]), "size_kb": round(d["size"] / 1024)}
                    for d in g["duplicates"]
                ],
            })
        except Exception as ex:
            print(f"  ✗ {best['path'].name[:55]} — {ex}")
            errors += 1

    # ── Resumen final ─────────────────────────────────────────────────────────
    size_total_kb = sum(f["size_kb"] for f in report_files)
    size_str = (f"{size_total_kb/1024/1024:.2f} GB" if size_total_kb > 1024*1024
                else f"{size_total_kb/1024:.1f} MB")

    print(f"\n{'='*60}")
    print(f"  ✓ {'Simuladas' if dry_run else 'Copiadas'}  : {copied:,} canciones")
    print(f"  ✗ Errores      : {errors}")
    print(f"  ✂ Dups omitidos: {total_dup_files:,} ficheros ({len(dup_groups):,} grupos)")
    if excluded_songs:
        print(f"  ↷ Excluidas    : {len(excluded_songs):,} (por límite de tamaño)")
    print(f"  💾 Tamaño total : {size_str}")
    if not dry_run:
        print(f"\n  📂 Carpeta lista: {dest_dir.resolve()}")
        print(f"  → Conecta tu móvil y copia esa carpeta")

    # ── Guardar reporte ───────────────────────────────────────────────────────
    report_data = {
        "source":               str(source_dir),
        "dest":                 str(dest_dir),
        "dry_run":              dry_run,
        "limit_gb":             round(limit_bytes / (1024**3), 1) if limit_bytes else None,
        "total_source":         total,
        "unique":               copied,
        "duplicates_removed":   total_dup_files,
        "excluded_by_limit":    len(excluded_songs),
        "errors":               errors,
        "size_total_mb":        round(size_total_kb / 1024, 1),
        "files":                report_files,
        "duplicate_groups": [
            {
                "keep":   {"name": g["best"]["dest_name"], "size_kb": round(g["best"]["size"]/1024)},
                "remove": [{"name": d["path"].name, "size_kb": round(d["size"]/1024)} for d in g["duplicates"]],
            }
            for g in dup_groups
        ],
        "excluded_songs": [
            {
                "name":          g["best"]["dest_name"],
                "artist":        g["best"]["artist"],
                "spotify_plays": spotify_plays.get(normalize(g["best"].get("artist", "")), 0),
                "size_kb":       round(g["best"]["size"]/1024),
            }
            for g in excluded_songs
        ],
    }

    # Siempre guarda el análisis (dry-run también) para que la app pueda mostrarlo
    analysis_path = dest_dir.parent / "_dedup_analysis.json" if dry_run else dest_dir / "_dedup_report.json"
    if dry_run:
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        dest_dir.mkdir(parents=True, exist_ok=True)

    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    tag = "análisis" if dry_run else "reporte"
    print(f"  📄 {tag.capitalize()}: {analysis_path}\n")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gestiona duplicados en tu biblioteca MP3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modos:
  Borrar duplicados en la misma carpeta (recomendado para ahorrar espacio):
    python3 dedup_music.py /ruta/musica --delete-dupes [--dry-run]

  Copiar versión limpia a otra carpeta:
    python3 dedup_music.py /ruta/musica /ruta/destino [--dry-run] [--limit-gb 32]
""",
    )
    parser.add_argument("source", type=Path, help="Carpeta con tus MP3s")
    parser.add_argument("dest",   type=Path, nargs="?", default=None,
                        help="Carpeta destino (solo en modo copia)")
    parser.add_argument("--delete-dupes", action="store_true",
                        help="Borrar duplicados directamente en la carpeta origen")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Solo analiza, no borra ni copia nada")
    parser.add_argument("--limit-gb", type=float, default=0,
                        help="Límite en GB para modo copia (0 = sin límite)")
    parser.add_argument("--spotify-data", type=Path, default=None,
                        help="Ruta a top_artistas.json para priorizar por escuchas")
    args = parser.parse_args()

    if args.delete_dupes:
        run_delete_dupes(source_dir=args.source, dry_run=args.dry_run)
    else:
        if not args.dest:
            parser.error("Debes indicar la carpeta destino, o usar --delete-dupes")
        limit_bytes = int(args.limit_gb * 1024**3) if args.limit_gb else 0
        run(
            source_dir   = args.source,
            dest_dir     = args.dest,
            dry_run      = args.dry_run,
            limit_bytes  = limit_bytes,
            spotify_data = args.spotify_data,
        )
