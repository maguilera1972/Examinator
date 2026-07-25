#!/usr/bin/env bash
# Examinator — installation from the public Git repository
# Reproduces a working instance comparable to the published repo.
#
# Usage (recommended):
#   git clone https://git.aguilera.ch/Aguilera_Lab/Examinator.git
#   cd Examinator
#   sudo ./scripts/install_examinator.sh
#
# Or install/clone directly into the target directory:
#   sudo ./scripts/install_examinator.sh --dir /opt/exam-simulator --clone
#
set -euo pipefail

REPO_URL_DEFAULT="https://git.aguilera.ch/Aguilera_Lab/Examinator.git"
INSTALL_DIR_DEFAULT="/opt/exam-simulator"

REPO_URL="$REPO_URL_DEFAULT"
INSTALL_DIR="$INSTALL_DIR_DEFAULT"
DO_CLONE=0
SKIP_SEED=0
SKIP_SYSTEMD=0
SKIP_MANUALS=0
SKIP_BRANDING=0
ADMIN_EMAIL=""
NON_INTERACTIVE=0

usage() {
  cat <<'EOF'
Examinator installer

Options:
  --dir PATH            Install directory (default: /opt/exam-simulator)
  --repo-url URL        Git clone URL (default: https://git.aguilera.ch/Aguilera_Lab/Examinator.git)
  --clone               Clone the repository into --dir (if missing)
  --admin-email EMAIL   Write ADMIN_EMAIL into .env
  --skip-seed           Do not run scripts/seed_data.py
  --skip-systemd        Do not install/enable the systemd service
  --skip-manuals        Do not generate PDF user manuals
  --skip-branding       Do not run scripts/install_branding.sh
  --non-interactive     Do not prompt; keep existing .env when present
  -h, --help            Show this help
EOF
}

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run this script as root (sudo)."
  fi
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) INSTALL_DIR="${2:-}"; shift 2 ;;
    --repo-url) REPO_URL="${2:-}"; shift 2 ;;
    --clone) DO_CLONE=1; shift ;;
    --admin-email) ADMIN_EMAIL="${2:-}"; shift 2 ;;
    --skip-seed) SKIP_SEED=1; shift ;;
    --skip-systemd) SKIP_SYSTEMD=1; shift ;;
    --skip-manuals) SKIP_MANUALS=1; shift ;;
    --skip-branding) SKIP_BRANDING=1; shift ;;
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (use --help)" ;;
  esac
done

[[ -n "$INSTALL_DIR" ]] || die "--dir cannot be empty"
[[ -n "$REPO_URL" ]] || die "--repo-url cannot be empty"

require_root

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# If invoked from an existing checkout and --clone was not requested,
# install from that checkout into INSTALL_DIR (copy/rsync or reuse path).
if [[ "$DO_CLONE" -eq 0 ]]; then
  if [[ "$SOURCE_ROOT" == "$INSTALL_DIR" ]]; then
    log "Using existing checkout at ${INSTALL_DIR}"
  elif [[ -f "${SOURCE_ROOT}/app/main.py" ]]; then
    log "Syncing sources from ${SOURCE_ROOT} → ${INSTALL_DIR}"
    mkdir -p "$INSTALL_DIR"
    if have_cmd rsync; then
      rsync -a --delete \
        --exclude '.git/' \
        --exclude 'venv/' \
        --exclude 'data/*.db' \
        --exclude 'data/*.db-*' \
        --exclude '.env' \
        --exclude '__pycache__/' \
        --exclude '.pytest_cache/' \
        "${SOURCE_ROOT}/" "${INSTALL_DIR}/"
    else
      # Fallback without deleting extras
      tar -C "$SOURCE_ROOT" \
        --exclude='.git' --exclude='venv' --exclude='.env' \
        --exclude='__pycache__' --exclude='.pytest_cache' \
        -cf - . | tar -C "$INSTALL_DIR" -xf -
    fi
  else
    die "Cannot find application sources. Run from a clone, or pass --clone."
  fi
fi

if [[ "$DO_CLONE" -eq 1 ]]; then
  have_cmd git || die "git is required for --clone"
  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log "Updating existing git checkout in ${INSTALL_DIR}"
    git -C "$INSTALL_DIR" fetch --all --prune
    git -C "$INSTALL_DIR" pull --ff-only || true
  elif [[ -e "$INSTALL_DIR" ]] && [[ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null || true)" ]]; then
    die "${INSTALL_DIR} exists and is not empty; refuse to clone into it"
  else
    log "Cloning ${REPO_URL} → ${INSTALL_DIR}"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
fi

[[ -f "${INSTALL_DIR}/app/main.py" ]] || die "Install failed: ${INSTALL_DIR}/app/main.py not found"
[[ -f "${INSTALL_DIR}/requirements.txt" ]] || die "Install failed: requirements.txt not found"

cd "$INSTALL_DIR"

log "Installing system packages (Python venv support + DejaVu fonts)"
if have_cmd apt-get; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    fonts-dejavu-core \
    ca-certificates \
    curl \
    rsync \
    git
else
  log "apt-get not found — ensure Python 3.13+, venv, pip and fonts-dejavu-core are installed"
fi

PYTHON_BIN="$(command -v python3.13 || command -v python3 || true)"
[[ -n "$PYTHON_BIN" ]] || die "python3 not found"
PY_VER="$("$PYTHON_BIN" -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
log "Using Python ${PY_VER} (${PYTHON_BIN})"

log "Creating virtualenv"
"$PYTHON_BIN" -m venv "${INSTALL_DIR}/venv"
# shellcheck disable=SC1091
source "${INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${INSTALL_DIR}/requirements.txt"

log "Preparing data directory and configuration"
mkdir -p "${INSTALL_DIR}/data"
ABS_DB="${INSTALL_DIR}/data/exams.db"
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
  SECRET="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  if [[ -z "$ADMIN_EMAIL" ]]; then
    if [[ "$NON_INTERACTIVE" -eq 0 ]]; then
      read -r -p "Admin e-mail (ADMIN_EMAIL) [admin@example.com]: " ADMIN_EMAIL_INPUT || true
      ADMIN_EMAIL="${ADMIN_EMAIL_INPUT:-admin@example.com}"
    else
      ADMIN_EMAIL="admin@example.com"
    fi
  fi
  # Absolute SQLite URLs need four slashes: sqlite:////path/to/db
  cat > "${INSTALL_DIR}/.env" <<EOF
APP_NAME=Examinator
DATABASE_URL=sqlite:////${ABS_DB#/}
SECRET_KEY=${SECRET}
QUESTIONS_PER_SESSION=50
SESSION_COOKIE=certsim_user_id
ADMIN_EMAIL=${ADMIN_EMAIL}
EOF
  log "Created ${INSTALL_DIR}/.env — review ADMIN_EMAIL / SECRET_KEY before production use"
else
  log "Keeping existing ${INSTALL_DIR}/.env"
fi

export PYTHONPATH="$INSTALL_DIR"

if [[ "$SKIP_BRANDING" -eq 0 && -x "${INSTALL_DIR}/scripts/install_branding.sh" ]]; then
  log "Installing branding assets"
  "${INSTALL_DIR}/scripts/install_branding.sh" || log "Branding script reported a non-fatal issue"
fi

if [[ "$SKIP_SEED" -eq 0 ]]; then
  log "Seeding catalog / question pools"
  "${INSTALL_DIR}/venv/bin/python" "${INSTALL_DIR}/scripts/seed_data.py"
else
  log "Skipping seed (--skip-seed)"
fi

if [[ "$SKIP_MANUALS" -eq 0 ]]; then
  log "Generating user manuals (PDF)"
  if "${INSTALL_DIR}/venv/bin/python" "${INSTALL_DIR}/scripts/generate_user_manuals.py"; then
    log "Manuals generated under app/static/docs/manuals/"
  else
    log "Manual generation failed (fonts missing?) — continuing; prebuilt manuals in the repo may still be available"
  fi
else
  log "Skipping manuals (--skip-manuals)"
fi

# Align systemd unit paths with INSTALL_DIR
UNIT_SRC="${INSTALL_DIR}/deploy/exam-simulator.service"
UNIT_WORK="${INSTALL_DIR}/deploy/exam-simulator.service.installed"
sed \
  -e "s|/opt/exam-simulator|${INSTALL_DIR}|g" \
  "$UNIT_SRC" > "$UNIT_WORK"

if [[ "$SKIP_SYSTEMD" -eq 0 ]]; then
  if have_cmd systemctl; then
    log "Installing systemd service"
    cp "$UNIT_WORK" /etc/systemd/system/exam-simulator.service
    systemctl daemon-reload
    systemctl enable exam-simulator.service
    systemctl restart exam-simulator.service
    systemctl --no-pager --full status exam-simulator.service || true
  else
    log "systemctl not available — start manually:"
    log "  PYTHONPATH=${INSTALL_DIR} ${INSTALL_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
  fi
else
  log "Skipping systemd (--skip-systemd)"
  log "Dev start: PYTHONPATH=${INSTALL_DIR} ${INSTALL_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
fi

cat <<EOF

Installation complete.

  Directory : ${INSTALL_DIR}
  Config    : ${INSTALL_DIR}/.env
  Database  : ${INSTALL_DIR}/data/exams.db
  Service   : exam-simulator.service $([ "$SKIP_SYSTEMD" -eq 0 ] && echo '(enabled)' || echo '(not installed)')

Next steps:
  1. Review ${INSTALL_DIR}/.env (ADMIN_EMAIL, SECRET_KEY)
  2. Open http://localhost:8000
  3. Register with the admin e-mail to access Administration
  4. Optional nginx sample: ${INSTALL_DIR}/deploy/nginx-exam-simulator.conf
  5. Excel question template: ${INSTALL_DIR}/docs/excel/

Documentation: ${INSTALL_DIR}/README.md
               ${INSTALL_DIR}/docs/DOCUMENTATION_TECHNIQUE.md
EOF
