#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  MediaHub — Script de instalación
#  Ejecutar UNA SOLA VEZ en una máquina nueva:
#    bash instalar.sh
# ═══════════════════════════════════════════════════════════════

cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   🎵  MediaHub — Instalación        ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Verificar Python 3 ────────────────────────────────────────
echo "▶ Verificando Python 3..."

if ! command -v python3 &>/dev/null; then
    echo ""
    echo "  ❌ Python 3 no está instalado."
    echo ""
    echo "  Instálalo desde: https://www.python.org/downloads/"
    echo "  (descarga la versión 3.10 o superior)"
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  En Mac también puedes instalarlo con Homebrew:"
        echo "    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo "    brew install python3"
    fi
    echo ""
    read -p "  Presiona Enter para cerrar..."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "  ✅ $PYTHON_VERSION"

# ── 2. Instalar dependencias ─────────────────────────────────────
echo ""
echo "▶ Instalando dependencias..."

# Intenta pip3 normal primero, si falla usa --break-system-packages (macOS moderno)
if pip3 install -r requirements.txt -q 2>/dev/null; then
    echo "  ✅ Dependencias instaladas"
elif pip3 install -r requirements.txt --break-system-packages -q 2>/dev/null; then
    echo "  ✅ Dependencias instaladas"
elif pip3 install streamlit mutagen requests -q 2>/dev/null; then
    echo "  ✅ Dependencias instaladas"
elif pip3 install streamlit mutagen requests --break-system-packages -q 2>/dev/null; then
    echo "  ✅ Dependencias instaladas"
else
    echo "  ⚠️  No se pudieron instalar las dependencias automáticamente."
    echo "  Ejecuta manualmente:"
    echo "    pip3 install streamlit mutagen requests"
    read -p "  Presiona Enter para continuar de todas formas..."
fi

# ── 3. Crear carpetas necesarias ──────────────────────────────────
echo ""
echo "▶ Creando estructura de carpetas..."

mkdir -p output/torrents
mkdir -p output/torrents_spotify
mkdir -p output_ebooks/torrents
mkdir -p spotify_data
mkdir -p scripts

echo "  ✅ Carpetas listas"

# ── 4. Configurar Streamlit (evitar prompts de email/estadísticas) ─
echo ""
echo "▶ Configurando Streamlit..."

STREAMLIT_DIR="$HOME/.streamlit"
mkdir -p "$STREAMLIT_DIR"

if [ ! -f "$STREAMLIT_DIR/credentials.toml" ]; then
    echo '[general]' > "$STREAMLIT_DIR/credentials.toml"
    echo 'email = ""' >> "$STREAMLIT_DIR/credentials.toml"
fi

if [ ! -f "$STREAMLIT_DIR/config.toml" ]; then
    echo '[browser]' > "$STREAMLIT_DIR/config.toml"
    echo 'gatherUsageStats = false' >> "$STREAMLIT_DIR/config.toml"
fi

echo "  ✅ Streamlit configurado"

# ── 5. Hacer ejecutables los scripts de inicio ───────────────────
chmod +x instalar.sh iniciar.sh 2>/dev/null

# ── 6. Verificar instalación ──────────────────────────────────────
echo ""
echo "▶ Verificando instalación..."

MISSING=""

if ! python3 -c "import streamlit" &>/dev/null; then
    MISSING="$MISSING streamlit"
fi
if ! python3 -c "import mutagen" &>/dev/null; then
    MISSING="$MISSING mutagen"
fi

if [ -n "$MISSING" ]; then
    echo ""
    echo "  ⚠️  Faltan paquetes:$MISSING"
    echo "  Ejecuta manualmente:"
    echo "    pip3 install$MISSING"
    echo ""
else
    echo "  ✅ Todo instalado correctamente"
fi

# ── 7. Resumen final ──────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  ¡Instalación completada!                           ║"
echo "║                                                          ║"
echo "║  Para iniciar la app:                                    ║"
echo "║    → Doble clic en  iniciar.sh                          ║"
echo "║    → O en terminal:  bash iniciar.sh                    ║"
echo "║                                                          ║"
echo "║  La app se abre en:  http://localhost:8501               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
