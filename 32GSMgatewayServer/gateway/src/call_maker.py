from asterisk import manager
import time
import socket
import pandas as pd
import threading
import requests
# Define your AMI connection parameters
AMI_HOST = 'localhost'
AMI_PORT = 5038
AMI_USERNAME = '1001'
AMI_PASSWORD = '1001'

# Define a global DataFrame
df_global = pd.DataFrame()
# Connect to Asterisk AMI
asterisk = manager.Manager()
asterisk.connect(AMI_HOST, AMI_PORT)
asterisk.login(AMI_USERNAME, AMI_PASSWORD)




def float_parse(a: str) -> float:
    if a is None:
        return None

    try:
        return float(a)
    except ValueError as error:
        print(error)
        return None


def make_call(mobile_number, dialplan, channel, user_id):
    originate_command = f'channel originate Local/{mobile_number}{channel}{user_id}{dialplan}@basic-context extension s'
    print("originate_command: ", originate_command)
    asterisk.command(originate_command)
    



    
