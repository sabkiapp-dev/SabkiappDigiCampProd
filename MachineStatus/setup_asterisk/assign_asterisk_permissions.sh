#!/bin/bash

# 1. Ensure the script is run as root (using sudo)
if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run this script with sudo."
  echo "Usage: sudo ./fix_asterisk_perms.sh"
  exit 1
fi

echo "Starting Asterisk permissions fix..."

# 2. Check if the asterisk user exists; if not, create it securely
if ! id "asterisk" &>/dev/null; then
    echo "User 'asterisk' not found. Creating it now..."
    adduser --system --group --home /var/lib/asterisk --no-create-home --gecos "Asterisk PBX" asterisk
else
    echo "User 'asterisk' already exists."
fi

# 3. Add 'pi' user to the asterisk group
echo "Adding user 'pi' to 'asterisk' group..."
usermod -a -G asterisk pi

# 4. Apply Ownership
echo "Applying ownership (asterisk:asterisk)..."
chown -R asterisk:asterisk /etc/asterisk
chown -R asterisk:asterisk /var/lib/asterisk
chown -R asterisk:asterisk /var/log/asterisk
chown -R asterisk:asterisk /var/spool/asterisk

# Check if the modules folder exists before trying to change it
if [ -d "/usr/lib/asterisk/modules" ]; then
    chown -R asterisk:asterisk /usr/lib/asterisk/modules
fi

# 5. Apply Directory Permissions (755)
echo "Applying directory permissions (755)..."
find /etc/asterisk -type d -exec chmod 755 {} +
find /var/lib/asterisk -type d -exec chmod 755 {} +
find /var/spool/asterisk -type d -exec chmod 755 {} +

# 6. Apply File Permissions (644)
echo "Applying file permissions (644)..."
find /etc/asterisk -type f -exec chmod 644 {} +
find /var/lib/asterisk -type f -exec chmod 644 {} +

# 7. Apply Special Gateway Permissions (770)
echo "Applying special outgoing spool permissions (770)..."
if [ -d "/var/spool/asterisk/outgoing" ]; then
    chmod 770 /var/spool/asterisk/outgoing
else
    echo "Note: /var/spool/asterisk/outgoing does not exist. Skipping."
fi

echo "================================================="
echo "SUCCESS: Permissions have been updated."
echo "================================================="
echo "IMPORTANT REMINDER:"
echo "1. Verify AST_USER=\"asterisk\" and AST_GROUP=\"asterisk\" are uncommented in /etc/default/asterisk"
echo "2. Restart Asterisk by running: sudo systemctl restart asterisk"