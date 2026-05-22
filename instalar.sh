#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  MediaHub — Script de instalación
#  Compatible con: macOS · Ubuntu/Debian · Fedora/RHEL · Arch
#  Uso: bash instalar.sh
# ═══════════════════════════════════════════════════════════════

set -e   # detiene el script si hay un error no manejado
cd "$(dirname "$0")"

# ── Colores ────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✅ $1${RESET}"; }
warn() { echo -e "  ${YELLOW}⚠️  $1${RESET}"; }
err()  { echo -e "  ${RED}❌ $1${RESET}"; }
info() { echo -e "  ${BLUE}ℹ️  $1${RESET}"; }
step() { echo -e "\n${BOLD}▶ $1${RESET}"; }

# ── Banner ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   🎵  MediaHub — Instalación            ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Detectar sistema operativo ─────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ -f /etc/os-release ]]; then
        source /etc/os-release
        case "$ID" in
            ubuntu|debian|linuxmint|pop|elementary) echo "debian" ;;
            fedora|rhel|centos|rocky|alma)          echo "fedora" ;;
            arch|manjaro|endeavouros)               echo "arch"   ;;
            opensuse*|sles)                         echo "suse"   ;;
            *)                                      echo "linux"  ;;
        esac
    elif [[ -n "$WINDIR" ]] || [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "cygwin"* ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)

case "$OS" in
    macos)   info "Sistema: macOS" ;;
    debian)  info "Sistema: Ubuntu / Debian / Mint" ;;
    fedora)  info "Sistema: Fedora / RHEL / CentOS" ;;
    arch)    info "Sistema: Arch Linux / Manjaro" ;;
    suse)    info "Sistema: openSUSE" ;;
    windows) info "Sistema: Windows (Git Bash / WSL)" ;;
    *)       info "Sistema: Linux (genérico)" ;;
esac

# ══════════════════════════════════════════════════════════════
# PASO 1 — Python 3
# ══════════════════════════════════════════════════════════════
step "Verificando Python 3..."

install_python() {
    echo ""
    warn "Python 3 no encontrado. Intentando instalar automáticamente..."
    echo ""

    case "$OS" in

        macos)
            # Intenta con Homebrew
            if command -v brew &>/dev/null; then
                info "Usando Homebrew para instalar Python 3..."
                brew install python3 && return 0
            fi
            # Instala Homebrew y luego Python
            info "Homebrew no encontrado. Instalando Homebrew primero..."
            echo ""
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Agrega Homebrew al PATH (Apple Silicon vs Intel)
            if [[ -f /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -f /usr/local/bin/brew ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            brew install python3 && return 0
            ;;

        debian)
            info "Usando apt para instalar Python 3..."
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-pip python3-venv && return 0
            ;;

        fedora)
            if command -v dnf &>/dev/null; then
                info "Usando dnf para instalar Python 3..."
                sudo dnf install -y python3 python3-pip && return 0
            elif command -v yum &>/dev/null; then
                info "Usando yum para instalar Python 3..."
                sudo yum install -y python3 python3-pip && return 0
            fi
            ;;

        arch)
            info "Usando pacman para instalar Python 3..."
            sudo pacman -Sy --noconfirm python python-pip && return 0
            ;;

        suse)
            info "Usando zypper para instalar Python 3..."
            sudo zypper install -y python3 python3-pip && return 0
            ;;

        windows)
            echo ""
            err "No se puede instalar Python automáticamente en Windows desde Git Bash."
            echo ""
            echo -e "  ${BOLD}Instálalo manualmente:${RESET}"
            echo "  1. Descarga Python desde: https://www.python.org/downloads/"
            echo "  2. Ejecuta el instalador"
            echo -e "  3. ${YELLOW}⚠️  Activa 'Add Python to PATH'${RESET} durante la instalación"
            echo "  4. Cierra y vuelve a abrir la terminal"
            echo "  5. Ejecuta nuevamente: bash instalar.sh"
            echo ""
            read -p "  Presiona Enter para salir..."
            exit 1
            ;;

        *)
            echo ""
            err "No se pudo instalar Python automáticamente."
            echo ""
            echo -e "  ${BOLD}Instálalo manualmente según tu sistema:${RESET}"
            echo "    Ubuntu/Debian : sudo apt install python3 python3-pip"
            echo "    Fedora        : sudo dnf install python3 python3-pip"
            echo "    Arch          : sudo pacman -S python python-pip"
            echo "    Otro          : https://www.python.org/downloads/"
            echo ""
            read -p "  Presiona Enter para salir..."
            exit 1
            ;;
    esac

    # Si llegó aquí, la instalación falló
    err "La instalación automática de Python falló."
    echo ""
    echo "  Instálalo manualmente desde: https://www.python.org/downloads/"
    read -p "  Presiona Enter para salir..."
    exit 1
}

# Verifica si Python está disponible
if ! command -v python3 &>/dev/null; then
    install_python
fi

# Verifica versión mínima (3.10)
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 10 ]]; }; then
    warn "Tienes Python $PY_VER pero se necesita 3.10 o superior."
    info "Intentando instalar una versión más nueva..."
    install_python
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
fi

ok "Python $PY_VER"

# ══════════════════════════════════════════════════════════════
# PASO 2 — pip
# ══════════════════════════════════════════════════════════════
step "Verificando pip..."

install_pip() {
    warn "pip no encontrado. Instalando..."
    case "$OS" in
        macos)
            python3 -m ensurepip --upgrade 2>/dev/null \
            || brew install python3 2>/dev/null \
            || { err "No se pudo instalar pip"; exit 1; }
            ;;
        debian)
            sudo apt-get install -y python3-pip 2>/dev/null \
            || python3 -m ensurepip --upgrade 2>/dev/null \
            || { err "No se pudo instalar pip"; exit 1; }
            ;;
        fedora)
            sudo dnf install -y python3-pip 2>/dev/null \
            || python3 -m ensurepip --upgrade 2>/dev/null \
            || { err "No se pudo instalar pip"; exit 1; }
            ;;
        arch)
            sudo pacman -Sy --noconfirm python-pip 2>/dev/null \
            || { err "No se pudo instalar pip"; exit 1; }
            ;;
        *)
            python3 -m ensurepip --upgrade 2>/dev/null \
            || { err "No se pudo instalar pip. Instala manualmente: https://pip.pypa.io"; exit 1; }
            ;;
    esac
}

# Selecciona el comando pip disponible
PIP_CMD=""
if python3 -m pip --version &>/dev/null; then
    PIP_CMD="python3 -m pip"
elif command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
elif command -v pip &>/dev/null; then
    PIP_CMD="pip"
else
    install_pip
    PIP_CMD="python3 -m pip"
fi

PIP_VER=$($PIP_CMD --version 2>&1 | awk '{print $2}')
ok "pip $PIP_VER  (comando: $PIP_CMD)"

# ══════════════════════════════════════════════════════════════
# PASO 3 — Dependencias Python
# ══════════════════════════════════════════════════════════════
step "Instalando dependencias Python..."

install_deps() {
    local REQS="$1"   # archivo o paquetes
    local IS_FILE="$2"

    # Construye el comando base
    if [[ "$IS_FILE" == "yes" ]]; then
        CMD="$PIP_CMD install -r $REQS"
    else
        CMD="$PIP_CMD install $REQS"
    fi

    # Intento 1: instalación normal (silenciosa)
    if $CMD -q 2>/dev/null; then return 0; fi

    # Intento 2: --break-system-packages (macOS/Debian con Python administrado por el SO)
    if $CMD --break-system-packages -q 2>/dev/null; then return 0; fi

    # Intento 3: --user (sin permisos de administrador)
    if $CMD --user -q 2>/dev/null; then return 0; fi

    # Intento 4: crear y usar un entorno virtual
    warn "Instalación directa bloqueada por el sistema. Creando entorno virtual..."
    python3 -m venv .venv
    source .venv/bin/activate
    if [[ "$IS_FILE" == "yes" ]]; then
        pip install -r "$REQS" -q 2>/dev/null && return 0
    else
        pip install $REQS -q 2>/dev/null && return 0
    fi

    return 1
}

if [[ -f requirements.txt ]]; then
    if install_deps "requirements.txt" "yes"; then
        ok "Dependencias instaladas desde requirements.txt"
    else
        err "No se pudieron instalar las dependencias."
        echo ""
        echo "  Ejecuta manualmente:"
        echo "    $PIP_CMD install streamlit mutagen requests"
        read -p "  Presiona Enter para continuar de todas formas..."
    fi
else
    if install_deps "streamlit mutagen requests" "no"; then
        ok "Dependencias instaladas"
    else
        err "No se pudieron instalar las dependencias."
        read -p "  Presiona Enter para continuar de todas formas..."
    fi
fi

# ══════════════════════════════════════════════════════════════
# PASO 4 — Estructura de carpetas
# ══════════════════════════════════════════════════════════════
step "Creando estructura de carpetas..."

mkdir -p output/torrents output/torrents_spotify
mkdir -p output_ebooks/torrents
mkdir -p spotify_data scripts

ok "Carpetas listas"

# ══════════════════════════════════════════════════════════════
# PASO 5 — Configurar Streamlit
# ══════════════════════════════════════════════════════════════
step "Configurando Streamlit..."

STREAMLIT_DIR="$HOME/.streamlit"
mkdir -p "$STREAMLIT_DIR"

if [[ ! -f "$STREAMLIT_DIR/credentials.toml" ]]; then
    printf '[general]\nemail = ""\n' > "$STREAMLIT_DIR/credentials.toml"
fi
if [[ ! -f "$STREAMLIT_DIR/config.toml" ]]; then
    printf '[browser]\ngatherUsageStats = false\n\n[client]\ntoolbarMode = "minimal"\n' > "$STREAMLIT_DIR/config.toml"
fi

ok "Streamlit configurado (sin prompts de email)"

# ══════════════════════════════════════════════════════════════
# PASO 6 — Permisos de ejecución
# ══════════════════════════════════════════════════════════════
chmod +x instalar.sh iniciar.sh 2>/dev/null
ok "Permisos de ejecución aplicados"

# ══════════════════════════════════════════════════════════════
# PASO 7 — Verificación final
# ══════════════════════════════════════════════════════════════
step "Verificación final..."

ERRORS=0

check_import() {
    local PKG="$1"
    local NAME="${2:-$1}"
    if python3 -c "import $PKG" &>/dev/null \
    || ([[ -d .venv ]] && .venv/bin/python -c "import $PKG" &>/dev/null); then
        ok "$NAME instalado"
    else
        err "$NAME NO encontrado"
        ERRORS=$((ERRORS + 1))
    fi
}

check_import streamlit  "Streamlit"
check_import mutagen    "Mutagen"
check_import requests   "Requests"

# ══════════════════════════════════════════════════════════════
# Resultado final
# ══════════════════════════════════════════════════════════════
echo ""
if [[ $ERRORS -eq 0 ]]; then
    echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║  ${GREEN}✅  ¡Instalación completada con éxito!${RESET}${BOLD}               ║${RESET}"
    echo -e "${BOLD}║                                                          ║${RESET}"
    echo -e "${BOLD}║  Para iniciar la app:                                    ║${RESET}"
    echo -e "${BOLD}║    → Doble clic en  iniciar.sh                           ║${RESET}"
    echo -e "${BOLD}║    → O en terminal:  bash iniciar.sh                     ║${RESET}"
    echo -e "${BOLD}║                                                          ║${RESET}"
    echo -e "${BOLD}║  La app se abre en:  http://localhost:8501                ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${RESET}"
else
    echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║  ${YELLOW}⚠️   Instalación completada con advertencias${RESET}${BOLD}           ║${RESET}"
    echo -e "${BOLD}║                                                          ║${RESET}"
    echo -e "${BOLD}║  $ERRORS paquete(s) no se instalaron correctamente.          ║${RESET}"
    echo -e "${BOLD}║  Intenta manualmente:                                    ║${RESET}"
    echo -e "${BOLD}║    pip3 install streamlit mutagen requests                ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${RESET}"
fi

# Si se creó un venv, avisa cómo activarlo
if [[ -d .venv ]]; then
    echo ""
    echo -e "  ${YELLOW}Nota:${RESET} Las dependencias se instalaron en un entorno virtual (.venv)"
    echo -e "  El script ${BOLD}iniciar.sh${RESET} lo activará automáticamente."
fi

echo ""
