#!/bin/bash
# ============================================================
# sync_to_rpi.sh — Sync MachineStatus code to Raspberry Pi
# ============================================================
# Config
RPI_HOST="192.168.8.49"
RPI_USER="pi"
RPI_DEST="/home/pi/Documents/MachineStatus/"  # sync INTO this subdirectory
RPI_PROJ="/home/pi/Documents/MachineStatus"   # where run_server.sh lives on the RPi
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

# Colour codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC}  $1"; }

# Resolve local source (project root = script dir)
LOCAL_SRC="$(cd "$(dirname "$0")" && pwd)"

# ---- Checks -------------------------------------------------------
if ! command -v rsync &>/dev/null; then
    err "rsync is not installed. Install with: sudo apt install rsync"
    exit 1
fi

if ! command -v ssh &>/dev/null; then
    err "ssh is not installed."
    exit 1
fi

# Test connectivity
log "Testing connection to ${RPI_USER}@${RPI_HOST}..."
if ! ssh $SSH_OPTS "${RPI_USER}@${RPI_HOST}" "echo 'ok'" &>/dev/null; then
    err "Cannot reach ${RPI_USER}@${RPI_HOST}. Check:"
    err "  1. RPi is powered on and reachable on the network"
    err "  2. SSH server is running on the RPi"
    err "  3. Hostname '${RPI_HOST}' resolves (or update RPI_HOST in this script)"
    err "  4. SSH key-based auth is set up (ssh-copy-id pi@${RPI_HOST})"
    exit 1
fi
log "Connection OK."

# ---- What will be synced ------------------------------------------
log "Files to be synced (top-level only):"
rsync -n --out-format='  %-12o %-10M %-10L %f' \
    -av --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '*.pyo' \
    --exclude '*.log' \
    --exclude 'ami.log' \
    --exclude 'dtmf.log' \
    --exclude 'django.log' \
    --exclude 'nohup.out' \
    --exclude 'ms_env/' \
    --exclude '.git/' \
    --exclude '*.pkl' \
    --exclude '*.sqlite3' \
    --exclude 'db.sqlite3' \
    --exclude 'voip_gateway_cookies.pkl' \
    --exclude 'password.pkl' \
    --exclude 'virtual_ram_data.pkl' \
    --exclude 'ussd_cache.pkl' \
    --exclude 'cloudflared/' \
    --exclude 'backups_*/' \
    --exclude 'logs/' \
    --exclude '*.zip' \
    --exclude '.DS_Store' \
    --exclude 'node_modules/' \
    --exclude 'package-lock.json' \
    "${LOCAL_SRC}/" "${RPI_USER}@${RPI_HOST}:${RPI_DEST}" | grep -v '^\.' | head -40
echo ""

# ---- Dry-run confirmation ----------------------------------------
read -p "Proceed with sync? [Y/n] " confirm
confirm="${confirm:-Y}"
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    log "Aborted."
    exit 0
fi

# ---- Sync -------------------------------------------------------
log "Syncing to ${RPI_USER}@${RPI_HOST}:${RPI_DEST} ..."
rsync -av --delete \
    -e "ssh $SSH_OPTS" \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '*.pyo' \
    --exclude '*.log' \
    --exclude 'ami.log' \
    --exclude 'dtmf.log' \
    --exclude 'django.log' \
    --exclude 'nohup.out' \
    --exclude 'ms_env/' \
    --exclude '.git/' \
    --exclude '*.pkl' \
    --exclude '*.sqlite3' \
    --exclude 'db.sqlite3' \
    --exclude 'voip_gateway_cookies.pkl' \
    --exclude 'password.pkl' \
    --exclude 'virtual_ram_data.pkl' \
    --exclude 'ussd_cache.pkl' \
    --exclude 'cloudflared/' \
    --exclude 'backups_*/' \
    --exclude 'logs/' \
    --exclude '*.zip' \
    --exclude '.DS_Store' \
    --exclude 'node_modules/' \
    --exclude 'package-lock.json' \
    "${LOCAL_SRC}/" "${RPI_USER}@${RPI_HOST}:${RPI_DEST}"

if [ $? -eq 0 ]; then
    log "Sync complete."
else
    err "Sync failed (rsync exit code $?)."
    exit 1
fi

# ---- Recreate venv on RPi ----------------------------------------
log "Recreating Python venv on RPi..."
ssh $SSH_OPTS "${RPI_USER}@${RPI_HOST}" "cd ${RPI_PROJ} && \
    rm -rf ms_env && \
    python3 -m venv ms_env && \
    ms_env/bin/pip install --upgrade pip -q && \
    ms_env/bin/pip install -q -r requirements.txt && \
    echo 'venv ready'" 2>&1
if [ $? -eq 0 ]; then
    log "Python venv ready."
else
    warn "venv setup had issues — check pip install errors above."
fi

# ---- Restart service on RPi -------------------------------------
log "Restarting MachineStatus service on RPi..."
ssh $SSH_OPTS "${RPI_USER}@${RPI_HOST}" << 'ENDSSH'
    cd ${RPI_PROJ} || { echo "Directory not found: ${RPI_PROJ}"; exit 1; }

    # Kill existing processes
    pkill -f "python.*run_server" 2>/dev/null
    pkill -f "python.*ami_listener" 2>/dev/null
    sleep 2

    # Restart
    bash run_server.sh > nohup.out 2>&1 &
    echo "Service restarted (PID $!)"
ENDSSH

if [ $? -eq 0 ]; then
    log "Service restarted on RPi."
    log "Check logs: ssh ${RPI_USER}@${RPI_HOST} 'tail -f ~/Documents/nohup.out'"
else
    warn "Could not restart service (ssh may have failed)."
fi

log "Done."
