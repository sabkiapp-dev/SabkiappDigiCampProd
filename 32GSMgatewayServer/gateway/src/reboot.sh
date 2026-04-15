#!/bin/bash

# Correct path to settings.py
SETTINGS_PATH="/home/pi/Documents/32GSMgatewayServer/gateway/gsm_gateway/settings.py"

# Extract the SUDO_PASS value directly from settings.py using grep and awk
sudo_password=$(grep -oP "^SUDO_PASS\s*=\s*['\"]\K[^'\"]+" "$SETTINGS_PATH")

# Check if sudo_password is empty
if [ -z "$sudo_password" ]; then
  echo "Failed to retrieve sudo password from settings.py. Exiting."
  exit 1
fi

# Use echo to provide the password to sudo
echo "$sudo_password" | sudo -S reboot
