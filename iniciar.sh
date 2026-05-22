#!/bin/bash
# ─────────────────────────────────────────────────────────────
# MediaHub — Script de inicio
# Uso: doble clic o ejecutar en terminal: bash iniciar.sh
# ─────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

echo ""
echo "🎵  MediaHub — Iniciando..."
echo ""

# ── Verifica Python ───────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 no encontrado."
    echo "   Ejecuta primero: bash instalar.sh"
    read -p "   Presiona Enter para cerrar..."
    exit 1
fi

# ── Activa entorno virtual si existe (creado por instalar.sh) ─
if [[ -d .venv ]]; then
    source .venv/bin/activate
    echo "   ✅ Entorno virtual activado (.venv)"
fi

# ── Verifica Streamlit — si falta, lanza el instalador ───────
if ! python3 -c "import streamlit" &>/dev/null; then
    echo "⚙️  Dependencias no encontradas. Ejecutando instalador..."
    bash instalar.sh
    [[ -d .venv ]] && source .venv/bin/activate
fi

# ── Abre el navegador tras 3 segundos (multiplataforma) ───────
if [[ "$OSTYPE" == "darwin"* ]]; then
    sleep 3 && open http://localhost:8501 &
elif command -v xdg-open &>/dev/null; then
    sleep 3 && xdg-open http://localhost:8501 &
elif command -v start &>/dev/null; then
    sleep 3 && start http://localhost:8501 &
fi

echo "✅  Abre tu navegador en: http://localhost:8501"
echo "    Para cerrar la app presiona Ctrl+C"
echo ""

# ── Inicia la app ─────────────────────────────────────────────
streamlit run app.py
