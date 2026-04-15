from asterisk import manager
import time

# Define your AMI connection parameters
AMI_HOST = 'localhost'
AMI_PORT = 5038
AMI_USERNAME = '1001'
AMI_PASSWORD = '1001'

def make_call(mobile_number, dialplan, channel, user_id):
    originate_command = f'channel originate Local/{mobile_number}{channel}{user_id}{dialplan}@basic-context extension s'
    print("originate_command: ", originate_command)

    asterisk = manager.Manager()
    try:
        # Connect and log in to Asterisk AMI
        asterisk.connect(AMI_HOST, AMI_PORT)
        asterisk.login(AMI_USERNAME, AMI_PASSWORD)

        # Send the originate command
        response = asterisk.command(originate_command)
        print("AMI Response:", response)

    except Exception as e:
        print("Error making call:", str(e))
    finally:
        # Ensure the connection is properly closed
        try:
            asterisk.close()
        except Exception:
            pass

# Test call parameters
mobile_number = "9934445076"      # Replace with your actual number
dialplan = "1000000078"           # Dialplan ID (example)
channel = "1001"                  # Channel ID
user_id = "00000011"              # User ID (example)

# Initiate the call
make_call(mobile_number, dialplan, channel, user_id)

# Wait to observe the result
time.sleep(5)
