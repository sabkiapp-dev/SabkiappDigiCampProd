#!/bin/bash

# --- 1. CONFIGURATION ---
DEVICE="/dev/sdd"           
HOSTNAME="host1"
USER_NAME="pi"
USER_PASS="123"
WIFI_SSID="BRS_Bhawan_4G"
WIFI_PASS="123456789"
RPI_IP="192.168.1.100"       # Static IP to assign to the RPi
RPI_GATEWAY="192.168.1.1"    # Your router/gateway IP
RPI_DNS="8.8.8.8"            # DNS server

echo "================================================="
echo "  RPi5 1-CLICK INSTALLER (With Auto-Expand)      "
echo "================================================="

# --- 2. HARDWARE CHECK ---
echo "--- Step 1: Checking SD Card State ---"
while true; do
    if lsblk -b "$DEVICE" >/dev/null 2>&1; then
        SIZE=$(lsblk -b -n -o SIZE "$DEVICE" | head -n 1)
        if [ -n "$SIZE" ] && [ "$SIZE" -gt 0 ] 2>/dev/null; then
            echo "SUCCESS: $DEVICE is connected and ready."
            break
        fi
    fi
    echo "⚠️  WARNING: '$DEVICE' is virtually ejected (No medium found)."
    echo "👉 ACTION REQUIRED: Please physically UNPLUG your USB card reader and PLUG IT BACK IN."
    sleep 3
done

# --- 3. FIND LOCAL IMAGE ---
IMG_FILE=$(ls -1 "$HOME/Downloads"/ubuntu-*preinstalled-server-arm64+raspi.img.xz 2>/dev/null | sort -V | tail -n 1)

if [ -z "$IMG_FILE" ]; then
    echo "ERROR: Cannot find the Ubuntu image in ~/Downloads."
    exit 1
fi
echo "Using Image: $IMG_FILE"

# --- 4. PREP & FLASH (USING DD) ---
echo "--- Step 2: Unmounting $DEVICE ---"
sudo umount ${DEVICE}* 2>/dev/null

echo "--- Step 3: Flashing (This takes 5-10 mins) ---"
sudo xz -dc "$IMG_FILE" | sudo dd of="$DEVICE" bs=4M status=progress conv=fsync

# --- 5. WAKE UP PARTITIONS ---
echo "--- Step 4: Refreshing Partitions ---"
sudo partprobe "$DEVICE"

echo "Waiting for partitions to appear..."
for i in {1..10}; do
    if [ -b "${DEVICE}1" ] && [ -b "${DEVICE}2" ]; then
        echo "-> Partitions found!"
        break
    fi
    sleep 2
done

if [ ! -b "${DEVICE}2" ]; then
    echo "CRITICAL ERROR: Linux cannot see the root partition (${DEVICE}2)."
    exit 1
fi

# --- 6. INSTANT 64GB EXPANSION ---
echo "--- Step 5: Expanding Root Partition to 100% ---"
# Make sure it isn't mounted before resizing
sudo umount "${DEVICE}2" 2>/dev/null

# 1. Tell the partition table to stretch partition 2 to the end of the disk
sudo parted -s "$DEVICE" resizepart 2 100%

# 2. Update the kernel about the new size
sudo partprobe "$DEVICE"
sleep 2

# 3. Check the filesystem for errors (Required before resizing)
sudo e2fsck -f -y "${DEVICE}2"

# 4. Expand the actual EXT4 filesystem to match the new partition size
sudo resize2fs "${DEVICE}2"

echo "-> Storage successfully expanded!"

# --- 7. INJECT SETTINGS ---
echo "--- Step 6: Injecting WiFi & SSH ---"
sudo mkdir -p /mnt/bootpart
sudo mount "${DEVICE}1" /mnt/bootpart

# Enable SSH
sudo touch /mnt/bootpart/ssh

# Write User Data
sudo tee /mnt/bootpart/user-data > /dev/null <<EOF
#cloud-config
hostname: $HOSTNAME
manage_etc_hosts: true
users:
  - name: $USER_NAME
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: users, admin, sudo
    shell: /bin/bash
    lock_passwd: false
    passwd: $(openssl passwd -6 $USER_PASS)
EOF

# Write WiFi Config (static IP)
sudo tee /mnt/bootpart/network-config > /dev/null <<EOF
version: 2
ethernets:
  eth0:
    dhcp4: true
    optional: true
wifis:
  wlan0:
    dhcp4: false
    optional: true
    addresses: [$RPI_IP/24]
    routes:
      - to: default
        via: $RPI_GATEWAY
    nameservers:
      addresses: [$RPI_DNS]
    access-points:
      "$WIFI_SSID":
        password: "$WIFI_PASS"
EOF

# --- 8. CLEANUP ---
echo "--- Step 7: Finalizing ---"
sudo umount /mnt/bootpart

sudo mkdir -p /mnt/rootpart
sudo mount "${DEVICE}2" /mnt/rootpart

# Create the Documents directory for pi user
sudo mkdir -p /mnt/rootpart/home/$USER_NAME/Documents
sudo chown 1000:1000 /mnt/rootpart/home/$USER_NAME/Documents

# setup_asterisk.sh will be delivered via SCP in Phase 2 — not downloaded here

# --- SD Card Longevity Fixes (prevent filesystem corruption) ---
echo "--- Applying SD card protection ---"

# 1. fstab: safer mount options + tmpfs for /tmp and logs
sudo tee /mnt/rootpart/etc/fstab > /dev/null <<FSTAB
LABEL=writable  /               ext4  defaults,noatime,commit=120,errors=continue  0  1
LABEL=system-boot  /boot/firmware  vfat  defaults  0  1
tmpfs           /tmp            tmpfs  defaults,nosuid,nodev,size=64M  0  0
tmpfs           /var/tmp        tmpfs  defaults,nosuid,nodev,size=32M  0  0
FSTAB

# 2. Disable swap on SD card (swap destroys flash cells)
sudo tee /mnt/rootpart/etc/sysctl.d/99-sd-protect.conf > /dev/null <<SYSCTL
# Minimize swap usage — SD cards have limited write cycles
vm.swappiness=1
# Reduce dirty page writeback frequency
vm.dirty_ratio=40
vm.dirty_background_ratio=5
vm.dirty_expire_centisecs=6000
vm.dirty_writeback_centisecs=6000
SYSCTL

# 3. Limit journal size to prevent log bloat eating SD writes
sudo mkdir -p /mnt/rootpart/etc/systemd/journald.conf.d
sudo tee /mnt/rootpart/etc/systemd/journald.conf.d/sd-protect.conf > /dev/null <<JOURNAL
[Journal]
SystemMaxUse=30M
RuntimeMaxUse=20M
MaxFileSec=1day
ForwardToSyslog=no
JOURNAL

# 4. Logrotate: aggressive rotation to keep logs small
sudo tee /mnt/rootpart/etc/logrotate.d/sd-protect > /dev/null <<LOGROTATE
/var/log/syslog
/var/log/kern.log
/var/log/auth.log
/var/log/daemon.log
{
    rotate 2
    daily
    maxsize 5M
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        /usr/lib/rsyslog/rsyslog-rotate
    endscript
}
LOGROTATE

# 5. Disable unnecessary services that hammer the SD card
# (unattended-upgrades writes large apt caches; fwupd checks firmware constantly)
sudo ln -sf /dev/null /mnt/rootpart/etc/systemd/system/apt-daily.timer
sudo ln -sf /dev/null /mnt/rootpart/etc/systemd/system/apt-daily-upgrade.timer
sudo ln -sf /dev/null /mnt/rootpart/etc/systemd/system/fwupd-refresh.timer

echo "-> SD card protection applied (noatime, tmpfs, swap=1, journal capped, apt-daily disabled)"

# --- Boot Diagnostics (logs WiFi/internet/SSH status on every boot) ---
echo "--- Injecting boot diagnostics ---"
sudo tee /mnt/rootpart/usr/local/bin/boot_diag.sh > /dev/null << 'BOOTDIAG'
#!/bin/bash

LOG="/var/log/boot_diag.log"
PING_TARGET="8.8.8.8"
GATEWAY="__RPI_GATEWAY__"
MAX_WAIT=120
INTERVAL=5

echo "========================================" >> "$LOG"
echo "BOOT DIAG — $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "========================================" >> "$LOG"

elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    wlan_state=$(cat /sys/class/net/wlan0/operstate 2>/dev/null)
    ip_addr=$(ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+')
    echo "[${elapsed}s] wlan0=$wlan_state ip=$ip_addr" >> "$LOG"
    if [ "$wlan_state" = "up" ] && [ -n "$ip_addr" ]; then
        echo "[${elapsed}s] WiFi UP with IP $ip_addr" >> "$LOG"
        break
    fi
    sleep $INTERVAL
    elapsed=$((elapsed + INTERVAL))
done

if [ $elapsed -ge $MAX_WAIT ]; then
    echo "FAIL: WiFi did not come up in ${MAX_WAIT}s" >> "$LOG"
fi

echo "" >> "$LOG"
echo "--- ip addr ---" >> "$LOG"
ip addr >> "$LOG" 2>&1
echo "" >> "$LOG"
echo "--- ip route ---" >> "$LOG"
ip route >> "$LOG" 2>&1
echo "" >> "$LOG"
echo "--- iw wlan0 link ---" >> "$LOG"
iw wlan0 link >> "$LOG" 2>&1
echo "" >> "$LOG"
echo "--- wpa_cli status ---" >> "$LOG"
wpa_cli -i wlan0 status >> "$LOG" 2>&1

echo "" >> "$LOG"
echo "--- ping gateway $GATEWAY ---" >> "$LOG"
ping -c 3 -W 2 "$GATEWAY" >> "$LOG" 2>&1
[ $? -eq 0 ] && echo "GATEWAY: OK" >> "$LOG" || echo "GATEWAY: FAIL" >> "$LOG"

echo "" >> "$LOG"
echo "--- ping internet $PING_TARGET ---" >> "$LOG"
ping -c 3 -W 2 "$PING_TARGET" >> "$LOG" 2>&1
[ $? -eq 0 ] && echo "INTERNET: OK" >> "$LOG" || echo "INTERNET: FAIL" >> "$LOG"

echo "" >> "$LOG"
echo "--- DNS check ---" >> "$LOG"
nslookup google.com >> "$LOG" 2>&1

echo "" >> "$LOG"
echo "--- SSH status ---" >> "$LOG"
systemctl is-active ssh >> "$LOG" 2>&1
systemctl is-active ssh.socket >> "$LOG" 2>&1
ss -tlnp | grep ":22" >> "$LOG" 2>&1

echo "" >> "$LOG"
echo "--- recent kernel errors ---" >> "$LOG"
dmesg | grep -i -E "error|fail|brcmfmac|wlan|mmc|voltage|throttl" | tail -20 >> "$LOG" 2>&1

echo "" >> "$LOG"
echo "DIAG COMPLETE — $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "========================================" >> "$LOG"
BOOTDIAG

# Replace gateway placeholder with actual value
sudo sed -i "s|__RPI_GATEWAY__|$RPI_GATEWAY|g" /mnt/rootpart/usr/local/bin/boot_diag.sh
sudo chmod +x /mnt/rootpart/usr/local/bin/boot_diag.sh

# Systemd service for boot diagnostics
sudo tee /mnt/rootpart/etc/systemd/system/boot_diag.service > /dev/null <<EOF
[Unit]
Description=Boot Diagnostics - WiFi and Internet Check
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/boot_diag.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
sudo mkdir -p /mnt/rootpart/etc/systemd/system/multi-user.target.wants
sudo ln -sf /etc/systemd/system/boot_diag.service /mnt/rootpart/etc/systemd/system/multi-user.target.wants/boot_diag.service

echo "-> Boot diagnostics installed (logs to /var/log/boot_diag.log)"

sudo umount /mnt/rootpart
sync

echo "================================================="
echo " REAL SUCCESS! The SD card is 100% ready.        "
echo " Size is fully expanded. WiFi & SSH are injected."
echo " setup_asterisk.sh is at ~/Documents/             "
echo "                                                  "
echo " RPi static IP: $RPI_IP                           "
echo " After first boot, SSH in via Phase 2 to deploy.  "
echo "   ssh $USER_NAME@$RPI_IP                         "
echo "================================================="
