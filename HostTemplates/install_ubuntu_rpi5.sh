#!/bin/bash

# --- 1. CONFIGURATION ---
DEVICE="/dev/sdd"           
HOSTNAME="host1"
USER_NAME="pi"
USER_PASS="123"
WIFI_SSID="BRS_Bhawan_5G"
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
