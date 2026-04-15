#!/bin/bash

# Wait for 5 seconds
sleep 5

# Check if the source directory exists
if [ ! -d "/home/pi/Documents/temp/32GSMgatewayServer" ]; then
  echo "Source directory /home/pi/Documents/temp/32GSMgatewayServer does not exist. Exiting."
  exit 1
fi

# Get the sudo password from settings.py using Python
sudo_password=$(python3 -c "import sys; sys.path.append('/home/pi/Documents/32GSMgatewayServer/gateway'); from gsm_gateway import settings; print(settings.SUDO_PASS)")
# echo "sudo_password is $sudo_password"

# Delete existing code
rm -rf /home/pi/Documents/32GSMgatewayServer

# Copy new code
cp -r /home/pi/Documents/temp/32GSMgatewayServer /home/pi/Documents/32GSMgatewayServer

rm -rf /home/pi/Documents/temp/32GSMgatewayServer

# Use echo to provide the password to sudo
echo "$sudo_password" | sudo -S chmod -R 777 /home/pi/Documents/32GSMgatewayServer

# Use echo to provide the password to sudo
echo "$sudo_password" | sudo -S reboot
