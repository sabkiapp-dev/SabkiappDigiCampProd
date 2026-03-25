import requests
from django.conf import settings
from enum import Enum
from datetime import datetime
from src.final_status import FinalStatus
from src.update_database import update_sms_everywhere
from src.sms_counter import SmsCounter
from src.mytime import get_mytime
import json 

class SmsSender:
    def __init__(self, phone_no, message, port, sim_imsi, remaining_sms_balance):
        self.phone_no = phone_no
        self.message = message
        self.port =port
        self.sim_imsi = sim_imsi
        self.remaining_sms_balance = remaining_sms_balance
        

    def send_sms(self):
        # print("Response Content:", response.content)
        phone_no = self.phone_no
        message = self.message
        preferred_port = self.port
        sim_imsi = self.sim_imsi
        remaining_sms_balance = self.remaining_sms_balance


        today = get_mytime().date().strftime('%Y-%m-%d')
        update_sms_everywhere(sim_imsi, today, remaining_sms_balance)
        response = self.send_sms_to_selected_port(preferred_port)
        
        return 1

    


    def send_sms_to_selected_port(self, selected_port):
        try:
            sms_api_url = f"{settings.MACHINE_URL}:80/sendsms"
            sms_api_params = {
                'username': 'smsuser',
                'password': 'smspwd',
                'phonenumber': self.phone_no,
                'message': self.message,
                'port': selected_port,
            }
            print("selected_port : ", selected_port)
            # print("sms_api_url : ", sms_api_url)
            # Create a prepared request to get the final URL
            prepared_request = requests.Request('GET', sms_api_url, params=sms_api_params).prepare()

            # Print the final URL
            final_url = prepared_request.url
            print(f"Final SMS API URL: {final_url}")

            # Make an HTTP GET request to the SMS API
            response = requests.get(final_url)
        except Exception as e:
            print("An error occurred: ", str(e))
