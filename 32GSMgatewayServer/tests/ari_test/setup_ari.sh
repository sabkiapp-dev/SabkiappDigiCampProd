#!/bin/bash
# ============================================================
# setup_ari.sh — Enable ARI on Asterisk (run on RPi with sudo)
# Usage: sudo bash setup_ari.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC}   $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC}  $1"; }

if [ "$EUID" -ne 0 ]; then
    err "Run with sudo: sudo bash setup_ari.sh"
    exit 1
fi

echo "================================================="
echo "  ARI Setup for Asterisk                         "
echo "================================================="

# --- 1. Copy ARI config files ---
echo ""
echo "--- Step 1: Copying ARI config files ---"

# Backup existing configs if present
for f in http.conf ari.conf; do
    if [ -f "/etc/asterisk/$f" ]; then
        cp "/etc/asterisk/$f" "/etc/asterisk/${f}.bak.$(date +%Y%m%d%H%M%S)"
        warn "Backed up existing /etc/asterisk/$f"
    fi
done

cp "$SCRIPT_DIR/http.conf" /etc/asterisk/http.conf
cp "$SCRIPT_DIR/ari.conf" /etc/asterisk/ari.conf
chown asterisk:asterisk /etc/asterisk/http.conf /etc/asterisk/ari.conf
chmod 644 /etc/asterisk/http.conf /etc/asterisk/ari.conf
log "Config files copied to /etc/asterisk/"

# --- 2. Add stasis-test context if not present ---
echo ""
echo "--- Step 2: Adding stasis-test context to extensions.conf ---"

if grep -q '\[stasis-test\]' /etc/asterisk/extensions.conf 2>/dev/null; then
    warn "[stasis-test] context already exists — skipping"
else
    cat >> /etc/asterisk/extensions.conf <<'EOF'

; --- ARI Test Context (added by setup_ari.sh) ---
[stasis-test]
exten => s,1,Stasis(ai-call-app)
 same => n,Hangup()
EOF
    chown asterisk:asterisk /etc/asterisk/extensions.conf
    log "Added [stasis-test] context to extensions.conf"
fi

# --- 3. Reload Asterisk modules ---
echo ""
echo "--- Step 3: Reloading Asterisk ---"

asterisk -rx "module reload http" 2>/dev/null || warn "http module reload failed"
asterisk -rx "module reload res_ari" 2>/dev/null || warn "res_ari module reload failed"
asterisk -rx "module reload res_ari_channels" 2>/dev/null || true
asterisk -rx "module reload res_stasis" 2>/dev/null || true
asterisk -rx "dialplan reload" 2>/dev/null || warn "dialplan reload failed"

sleep 1

# --- 4. Verify ---
echo ""
echo "--- Step 4: Verifying ---"

echo ""
echo "HTTP status:"
asterisk -rx "http show status" 2>/dev/null || err "Could not query HTTP status"

echo ""
echo "ARI users:"
asterisk -rx "ari show users" 2>/dev/null || err "Could not query ARI users"

echo ""
echo "Dialplan check (stasis-test):"
asterisk -rx "dialplan show stasis-test" 2>/dev/null || err "stasis-test context not found"

echo ""
echo "================================================="
echo "  ARI Setup Complete                              "
echo "================================================="
echo ""
echo "  Test with:"
echo "    curl -u ari_user:ari_pass http://localhost:8088/ari/asterisk/info"
echo ""
echo "  Or run:"
echo "    python3 test_01_ping.py"
echo ""
