#!/bin/bash

# Path to the settings.py file
SETTINGS_FILE="/home/pi/Documents/MachineStatus/machine_status/machine_status/settings.py"

# Path to the Django project directory
DJANGO_PROJECT_DIR="/home/pi/Documents/MachineStatus/machine_status"

# Path to the Django manage.py file
MANAGE_PY="$DJANGO_PROJECT_DIR/manage.py"

# Activate the virtual environment
source /home/pi/Documents/MachineStatus/ms_env/bin/activate
# Ensure project packages are importable regardless of CWD
export PYTHONPATH=/home/pi/Documents/MachineStatus:/home/pi/Documents/MachineStatus/machine_status:$PYTHONPATH
# Configure Django settings for standalone scripts
export DJANGO_SETTINGS_MODULE=machine_status.settings

# Make sure log directories exist and are writable
mkdir -p logs
chmod 777 logs 2>/dev/null || true

# Read the host and port from the settings file
PORT=$(grep -oP "(?<=PORT = )\d+" "$SETTINGS_FILE")


# Construct the Django runserver command
DJANGO_COMMAND="python $MANAGE_PY runserver 0.0.0.0:${PORT}"

# Check the command line argument
if [ "$1" == "django" ]; then
    # Start Django server directly
    cd "$DJANGO_PROJECT_DIR"
    nohup python manage.py runserver 0.0.0.0:${PORT} &
else
    # Start Django server directly
    cd "$DJANGO_PROJECT_DIR"
    nohup python manage.py runserver 0.0.0.0:${PORT} &
fi

# Additional scripts
sleep 5
cd /home/pi/Documents/MachineStatus
nohup python ami_listener.py &
sleep 30
if pgrep -f "check_server.py" > /dev/null; then
    echo "check_server.py is already running."
else
    cd /home/pi/Documents/MachineStatus
    nohup python check_server.py &
fi
#