#!/bin/bash
# ─────────────────────────────────────────────────────────────
# MediaHub — Script de inicio
# Uso: doble clic o ejecutar en terminal: bash iniciar.sh
# ─────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

echo ""
echo "🎵  MediaHub — Iniciando..."
echo ""

# Verifica Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no encontrado. Instálalo desde https://www.python.org"
    read -p "Presiona Enter para cerrar..."
    exit 1
fi

# Verifica Streamlit
if ! python3 -c "import streamlit" &> /dev/null; then
    echo "⚙️  Instalando dependencias por primera vez..."
    pip3 install streamlit mutagen requests --break-system-packages
fi

# Abre el navegador tras 3 segundos
sleep 3 && open http://localhost:8501 &

echo "✅  Abre tu navegador en: http://localhost:8501"
echo "    Para cerrar la app presiona Ctrl+C"
echo ""

# Inicia la app
streamlit run app.py
