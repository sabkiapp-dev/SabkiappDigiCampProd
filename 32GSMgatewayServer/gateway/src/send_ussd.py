import requests
from .ussd_cache import UssdCache
from datetime import datetime
from django.conf import settings

def send_ussd(port, sim_imsi, message):
    username = "ussduser"
    password = "ussdpwd"
    base_url = f"{settings.MACHINE_URL}:80/sendussd"
    
    params = {
        'username': username,
        'password': password,
        'message': message,
        'port': port,
        'id': sim_imsi  # corrected the value from 'sim_imsi' to sim_imsi
    }
    
    try:
        print("sending ussd to port : ", port)
        response = requests.get(base_url, params=params)
        # print the request with params
        print(response.url)
        print("response : ", response.text)
        return response.text
    except requests.RequestException as e:
        return f"Failed to send USSD: {str(e)}"



def request_ussd(port, sim_imsi, operator, type):
    ussd_cache = UssdCache(port)
    if(ussd_cache.get_status == 'processing' and (datetime.now() - ussd_cache.get_date_time()).total_seconds() < 20):
        return
    print("Time while sending ussd for port {} is {}".format(port, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    # Check if operator contains 'vodafone' (case insensitive)
    if 'vodafone' in operator.lower():
        send_ussd(port, sim_imsi, '*199#')
    
        ussd_cache.update_operator("vodafone")
        
    # Check if operator contains 'airtel' (case insensitive)
    elif 'airtel' in operator.lower():
        if(type == 'phone'):
            send_ussd(port, sim_imsi, '*282#')
        else:
            send_ussd(port, sim_imsi, '*123#')
        ussd_cache.update_operator("airtel")


    ussd_cache.update_request_type(type)
    ussd_cache.update_status("processing")
    ussd_cache.update_trials(1)
    ussd_cache.update_phone_no("")
    ussd_cache.update_sim_imsi(sim_imsi)

    # print("ussd_cache : ", str(ussd_cache))