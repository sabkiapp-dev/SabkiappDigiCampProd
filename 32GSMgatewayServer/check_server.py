#!/usr/bin/env python3
import os
import re
import requests
import sys

# Fix import paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gateway'))
from src.mytime import get_mytime 
import time
import psutil
import threading

def check_script_status(script_path):
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if process.info['cmdline'] and script_path in process.info['cmdline']:
            return True
    print("Ami not running")
    return False

def run_script():
    result = os.system("python /home/pi/Documents/32GSMgatewayServer/ami_listener.py")
    if result == 0:
        print('Script started successfully.')
    else:
        print('Failed to start script.')

# Path to the settings.py file
SETTINGS_FILE = "/home/pi/Documents/32GSMgatewayServer/gateway/gsm_gateway/settings.py"

# Path to the lock file
LOCK_FILE = "/tmp/check_server.lock"

# Function to start run_server.sh
def start_run_server_django():
    import subprocess
    subprocess.Popen(['/bin/bash', '/home/pi/Documents/32GSMgatewayServer/run_server.sh', 'django'])

# Function to check if the process is already running
def is_process_running():
    return os.path.exists(LOCK_FILE)

# Function to create the lock file
def create_lock_file():
    with open(LOCK_FILE, 'w') as f:
        f.write("")

# Function to remove the lock file
def remove_lock_file():
    os.remove(LOCK_FILE)

# Function to check server status and start run_server.sh if necessary
def check_server():
    # Check if the process is already running
    if is_process_running():
        print("Another instance of the process is already running. Aborting.")
        return
    print("returned unsuccessful")
    while True:
        # Create the lock file to indicate that the process is running
        create_lock_file()

        try:
            print(f"Checking server... Time : {get_mytime()} | Host : {HOST}")

            # Check if Django is reachable
            try:
                response = requests.get(f"http://localhost:9000/tunnel_status", timeout=10)
                django_ok = (response.status_code == 200)
            except requests.exceptions.RequestException as e:
                print(f"\033[91mError reaching Django: {e}\033[0m")
                django_ok = False

            if not django_ok:
                print("\033[91mDjango not responding, restarting...\033[0m")
                start_run_server_django()
                time.sleep(60)
            else:
                is_ami_listener_running = check_script_status('/home/pi/Documents/32GSMgatewayServer/ami_listener.py')

                if not is_ami_listener_running:
                    print("AMI Listener Running: ", is_ami_listener_running)
                    # Run the script
                    # Create a thread that runs the run_script function
                    thread = threading.Thread(target=run_script)
                    # Start the thread
                    thread.start()

                time.sleep(60)  # Sleep for 1 minute before checking again

        except Exception as e:
            print(f"\033[91mUnexpected error: {e}\033[0m")

        finally:
            # Remove the lock file after the process completes
            remove_lock_file()

# Read the host and port from the settings file
with open(SETTINGS_FILE, 'r') as file:
    settings = file.read()
HOST = re.search(r"(?<='HOST': ')[^']+", settings).group(0)
PORT = re.search(r"(?<=PORT = )\d+", settings).group(0)

# Check server status
check_server()
