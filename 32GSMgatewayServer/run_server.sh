#!/bin/bash

# Path to the settings.py file
SETTINGS_FILE="/home/pi/Documents/32GSMgatewayServer/gateway/gsm_gateway/settings.py"

# Path to the Django project directory
DJANGO_PROJECT_DIR="/home/pi/Documents/32GSMgatewayServer/gateway"

# Path to the Django manage.py file
MANAGE_PY="$DJANGO_PROJECT_DIR/manage.py"

# Activate the virtual environment
source /home/pi/Documents/32GSMgatewayServer/ms_env/bin/activate
# Ensure project packages are importable regardless of CWD
export PYTHONPATH=/home/pi/Documents/32GSMgatewayServer:/home/pi/Documents/32GSMgatewayServer/gateway:$PYTHONPATH
# Configure Django settings for standalone scripts
export DJANGO_SETTINGS_MODULE=gsm_gateway.settings

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
cd /home/pi/Documents/32GSMgatewayServer
nohup python ami_listener.py &
sleep 30
if pgrep -f "check_server.py" > /dev/null; then
    echo "check_server.py is already running."
else
    cd /home/pi/Documents/32GSMgatewayServer
    nohup python check_server.py &
fi
#