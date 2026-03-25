import requests
from src.ussd_cache import UssdCache
from src.virtual_data import VirtualStorage
from datetime import datetime
from src.mytime import get_mytime, get_mytime_strftime
from django.conf import settings
import time
from threading import Thread
from src.utils import read_api_credentials
from django.conf import settings


# Function to update data to the API
def update_data_to_api(payload):
    api_credentials = read_api_credentials()
    url = f"{settings.BASE_URL}/sim_information"  # Use BASE_URL from settings

    try:
        response = requests.post(url, json=payload, auth=('username', api_credentials['system_password']))

        if response.status_code == 201:
            return "Data updated successfully."
        else:
            return f"Failed to update data. Status code: {response.status_code}, Message : {response.content}"
    except requests.RequestException as e:
        return f"An error occurred: {str(e)}"

    
def clear_ussd_pickle_for_port(port):
    ussd_cache = UssdCache(port)
    ussd_cache.clear()

def update_virtual_data(sim_imsi, phone_no, validity, last_validity_check, sms_backup_date, sms_balance):
    virtual_storage = VirtualStorage()
    if phone_no:
        virtual_storage.update_field_by_sim_imsi(sim_imsi, 'phone_no', phone_no)

    if validity:
        virtual_storage.update_field_by_sim_imsi(sim_imsi, 'validity', validity)

    print("last_validity_check_ : ", last_validity_check)
    if last_validity_check:
        virtual_storage.update_field_by_sim_imsi(sim_imsi, 'last_validity_check', last_validity_check)

    if sms_backup_date:
        virtual_storage.update_field_by_sim_imsi(sim_imsi, 'sms_backup_date', sms_backup_date)

    if sms_balance:
        virtual_storage.update_field_by_sim_imsi(sim_imsi, 'sms_balance', sms_balance)

    # print("phone number from vdata : ", virtual_storage.get_field_by_sim_imsi(sim_imsi, 'phone_no'))

    







def update_sms_everywhere(sim_imsi, sms_backup_date, sms_balance):


    payload = {
        "host": read_api_credentials()['host'],
        "sim_imsi": sim_imsi,
        "sms_backup_date": sms_backup_date,  # Convert to string
        "sms_balance": sms_balance,

        "system_password": read_api_credentials()['system_password'],
    }

    # Call the function to update data
    result = update_data_to_api(payload)
 

    update_virtual_data(sim_imsi, "", "", "", sms_backup_date, sms_balance)

    
    return "Update SMS request has been initiated. Check logs for details."

    # print(f"Updating SMS everywhere - sim_imsi: {sim_imsi}, sms_backup_date: {sms_backup_date_str}, sms_balance: {sms_balance}")


# Function to update everywhere
def update_everywhere(sim_imsi, port, phone_no, validity, request_type, operator):
    if(request_type=='validity'):
        phone_no = ''

    # Check if both phone_no and validity are empty, then skip update
    if not phone_no and not validity:
        return "Both phone number and validity are empty. Skipping update."

    # Construct payload conditionally without empty parameters
    payload = {
        "host": read_api_credentials()['host'],
        "sim_imsi": sim_imsi
    }

    if phone_no:
        payload["phone_no"] = phone_no

    
    if validity:
        payload["validity"] = validity
        payload["last_validity_check"] = get_mytime_strftime()

    payload["system_password"] = read_api_credentials()['system_password']

    # Call the function to update data
    result = update_data_to_api(payload)
  
    last_validity_check = None
    sms_backup_date = datetime.now().date().strftime("%Y-%m-%d")
    sms_balance = 100
    update_virtual_data(sim_imsi, phone_no, validity, last_validity_check, sms_backup_date, sms_balance)
    clear_ussd_pickle_for_port(port)

    return result