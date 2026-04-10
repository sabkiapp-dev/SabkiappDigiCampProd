#!/bin/bash

# =================================================
#  Cloudflare Tunnel Setup
#  Run with: sudo ./setup_cloudflare_tunnel.sh
# =================================================

# --- CREDENTIALS ---
CLOUDFLARE_TOKEN="YOUR_CLOUDFLARE_TUNNEL_TOKEN_HERE"

# =================================================

if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run this script with sudo."
  echo "Usage: sudo ./setup_cloudflare_tunnel.sh"
  exit 1
fi

if [ "$CLOUDFLARE_TOKEN" = "YOUR_CLOUDFLARE_TUNNEL_TOKEN_HERE" ]; then
  echo "Error: Please set your CLOUDFLARE_TOKEN at the top of this script."
  exit 1
fi

set -e

echo "================================================="
echo "  CLOUDFLARE TUNNEL SETUP                        "
echo "================================================="

# --- 1. INSTALL CLOUDFLARED ---
echo "--- Step 1: Installing cloudflared ---"
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  | tee /etc/apt/sources.list.d/cloudflared.list
apt update && apt install -y cloudflared
echo "-> cloudflared installed."

# --- 2. INSTALL TUNNEL AS SYSTEMD SERVICE ---
echo "--- Step 2: Registering tunnel as a system service ---"
cloudflared service install "$CLOUDFLARE_TOKEN"
echo "-> Tunnel service installed."

# --- 3. ENABLE & START ON BOOT ---
echo "--- Step 3: Enabling and starting the tunnel ---"
systemctl enable cloudflared
systemctl start cloudflared

echo "================================================="
echo "  SUCCESS! Cloudflare Tunnel is running.          "
echo "  It will auto-start on every reboot.             "
echo "  Status: sudo systemctl status cloudflared       "
echo "================================================="
