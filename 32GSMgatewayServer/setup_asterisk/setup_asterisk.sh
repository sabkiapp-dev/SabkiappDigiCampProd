#!/bin/bash

# =================================================
#  RPi Post-Boot Setup: Asterisk + Cloudflare Tunnel
#  Run with: sudo ./setup_asterisk.sh
# =================================================

# --- CREDENTIALS (fill before running) ---
CLOUDFLARE_TOKEN=""

# =================================================

if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run this script with sudo."
  echo "Usage: sudo ./setup_asterisk.sh"
  exit 1
fi

# --- CHECK TOKEN BEFORE DOING ANYTHING ---
if [ -z "$CLOUDFLARE_TOKEN" ]; then
  echo "================================================="
  echo "  ERROR: CLOUDFLARE_TOKEN is not set.            "
  echo "  Edit this script and add your token:           "
  echo "    CLOUDFLARE_TOKEN=\"your-token-here\"           "
  echo "  Then run again.                                 "
  echo "================================================="
  exit 1
fi

set -e

echo "================================================="
echo "  ASTERISK + CLOUDFLARE SETUP - 32 GSM Gateway   "
echo "================================================="

# --- 1. FETCH 32GSMGATEWAYSERVER SOURCE FROM LOCAL PC ---
echo "--- Step 1: Copy 32GSMgatewayServer source from your PC ---"
echo ""
read -p "  Enter your PC's IP address       : " HOST_IP
read -p "  Enter your PC's username         : " HOST_USER
read -p "  Enter full path to 32GSMgatewayServer : " HOST_PATH
echo ""

echo "-> Copying from $HOST_USER@$HOST_IP:$HOST_PATH ..."
mkdir -p /home/pi/Documents
scp -r "$HOST_USER@$HOST_IP:$HOST_PATH" /home/pi/Documents/32GSMgatewayServer
chown -R pi:pi /home/pi/Documents/32GSMgatewayServer
echo "-> 32GSMgatewayServer copied to /home/pi/Documents/32GSMgatewayServer"

# --- 2. INSTALL CLOUDFLARE TUNNEL ---
echo "--- Step 2: Installing Cloudflare Tunnel ---"
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  | tee /etc/apt/sources.list.d/cloudflared.list
apt update && apt install -y cloudflared
cloudflared service install "$CLOUDFLARE_TOKEN"
systemctl enable cloudflared
systemctl start cloudflared
echo "-> Cloudflare Tunnel installed and running."

# --- 3. WIPE TOKEN FROM THIS FILE ---
echo "--- Step 3: Removing token from script for security ---"
SCRIPT_PATH="$(realpath "$0")"
sed -i 's/^CLOUDFLARE_TOKEN=".*/CLOUDFLARE_TOKEN=""/' "$SCRIPT_PATH"
echo "-> Token cleared from $SCRIPT_PATH"

# --- 4. SYSTEM UPDATE & INSTALL ASTERISK ---
echo "--- Step 4: Updating system and installing Asterisk ---"
apt upgrade -y
apt install -y asterisk

# --- 5. WRITE extensions.conf ---
echo "--- Step 5: Writing extensions.conf ---"
truncate -s 0 /etc/asterisk/extensions.conf
cat > /etc/asterisk/extensions.conf <<'EXTENSIONS_EOF'
[basic-context]
exten => _XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX,1,Verbose(1,"User dialed ${EXTEN}")
 same => n,Set(PHONE=${EXTEN:0:10})
 same => n,Set(CHANNEL_RAW=${EXTEN:10:4})
 same => n,Set(CALLERID_NUM=${CHANNEL_RAW})
 same => n,Set(USER_ID=${EXTEN:14:8})
 same => n,Set(DIALPLAN=${EXTEN:22:10})
 same => n,System(/home/pi/Documents/32GSMgatewayServer/dtmf.sh start_dialing ${PHONE} ${CALLERID_NUM} ${USER_ID} ${DIALPLAN} &)
 ; We removed the not_answered line from here because it is never reached
 same => n,Dial(PJSIP/${PHONE}@${CALLERID_NUM},${INTERNAL_DIAL_OPT},U(${DIALPLAN}^${DIALPLAN}^${PHONE}^${CALLERID_NUM}^${USER_ID}^${DIALPLAN}))
 same => n,Hangup()

exten => h,1,NoOp(Final Dial Status: ${DIALSTATUS})
 ; If the call was answered, run the completed script
 same => n,ExecIf($["${DIALSTATUS}" = "ANSWER"]?System(/home/pi/Documents/32GSMgatewayServer/dtmf.sh completed ${PHONE} ${CALLERID_NUM} ${USER_ID} ${DIALPLAN} &))
 ; If the call was NOT answered (BUSY, NOANSWER, CONGESTION, etc.), run the not_answered script
 same => n,ExecIf($["${DIALSTATUS}" != "ANSWER"]?System(/home/pi/Documents/32GSMgatewayServer/dtmf.sh not_answered ${PHONE} ${CALLERID_NUM} ${USER_ID} ${DIALPLAN} ${DIALSTATUS} &))
 same => n,Hangup()

; Include the rest of the dialplan here:
#include /home/pi/Documents/32GSMgatewayServer/asterisk_dialplan.conf
EXTENSIONS_EOF
echo "-> extensions.conf written."

# --- 6. WRITE pjsip.conf ---
echo "--- Step 6: Writing pjsip.conf ---"
truncate -s 0 /etc/asterisk/pjsip.conf
cat > /etc/asterisk/pjsip.conf <<'PJSIP_EOF'
[global]
type=global
default_entity_id=asterisk

[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060

;============================================

PJSIP_EOF

for i in $(seq 1001 1032); do
cat >> /etc/asterisk/pjsip.conf <<PJSIP_ENDPOINT
; SIP Trunk to Dinstar GSM Gateway
[$i]
type=endpoint
transport=transport-udp
context=basic-context
disallow=all
allow=ulaw
aors=$i
outbound_auth=$i
direct_media=no
from_user=$i
from_domain=192.168.8.50
callerid=$i <$i>

[$i]
type=auth
auth_type=userpass
username=$i
password=$i  ; match Dinstar SIP settings

[$i]
type=aor
contact=sip:192.168.8.50

[$i]
type=identify
endpoint=$i
match=192.168.8.50

PJSIP_ENDPOINT
done
echo "-> pjsip.conf written with 32 endpoints (1001-1032)."

# --- 7. ASSIGN ASTERISK PERMISSIONS ---
echo "--- Step 7: Assigning Asterisk permissions ---"

if ! id "asterisk" &>/dev/null; then
    echo "Creating 'asterisk' user..."
    adduser --system --group --home /var/lib/asterisk --no-create-home --gecos "Asterisk PBX" asterisk
else
    echo "User 'asterisk' already exists."
fi

usermod -a -G asterisk pi

chown -R asterisk:asterisk /etc/asterisk
chown -R asterisk:asterisk /var/lib/asterisk
chown -R asterisk:asterisk /var/log/asterisk
chown -R asterisk:asterisk /var/spool/asterisk
if [ -d "/usr/lib/asterisk/modules" ]; then
    chown -R asterisk:asterisk /usr/lib/asterisk/modules
fi

find /etc/asterisk -type d -exec chmod 755 {} +
find /var/lib/asterisk -type d -exec chmod 755 {} +
find /var/spool/asterisk -type d -exec chmod 755 {} +
find /etc/asterisk -type f -exec chmod 644 {} +
find /var/lib/asterisk -type f -exec chmod 644 {} +

if [ -d "/var/spool/asterisk/outgoing" ]; then
    chmod 770 /var/spool/asterisk/outgoing
fi

# --- 8. CONFIGURE /etc/default/asterisk ---
echo "--- Step 8: Configuring /etc/default/asterisk ---"
if [ -f /etc/default/asterisk ]; then
    sed -i 's/^#*AST_USER=.*/AST_USER="asterisk"/' /etc/default/asterisk
    sed -i 's/^#*AST_GROUP=.*/AST_GROUP="asterisk"/' /etc/default/asterisk
else
    cat > /etc/default/asterisk <<'DEFAULT_EOF'
AST_USER="asterisk"
AST_GROUP="asterisk"
DEFAULT_EOF
fi

# --- 9. RESTART ASTERISK ---
echo "--- Step 9: Enabling and restarting Asterisk ---"
systemctl enable asterisk
systemctl restart asterisk

echo "================================================="
echo "  SUCCESS!                                        "
echo "  - 32GSMgatewayServer: copied to ~/Documents          "
echo "  - Cloudflare Tunnel: running, auto-starts        "
echo "  - Token: wiped from script                       "
echo "  - Asterisk: running as 'asterisk' user           "
echo "  - extensions.conf: 32-char dialplan              "
echo "  - pjsip.conf: 32 endpoints (1001-1032)           "
echo "================================================="
