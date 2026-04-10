import threading
import time

import requests
from src.mytime import get_mytime
import json
from api.models import SmsDialer

class SmsSender:
    def __init__(self):
        pass

    def send_sms(self, host, password, data):
        # prepare the payload
        payload = {
            "host": host,
            "password": password,
            "data": data
        }
        

        # send the SMS
        url = f'https://{host}.sabkiapp.com/send_sms'
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, data=json.dumps(payload))

        # process the response
        response_data = response.json()
        for item in response_data:
            message_data, status_code = item
            sms_dialer_id = message_data['sms_dialer_id']

            # If status_code = 200, sent_status = 5, if status_code = 421, 422 or 423, sent_status = 6, if 424 or 5xx sent_status = 0 else sent_status = 7
            if status_code == 200:
                sent_status = 5
            elif status_code in [421, 422, 423]:
                sent_status = 7
            elif status_code in [424, 500, 501, 502, 503, 504]:
                sent_status = 0
            else:
                sent_status = 8

            
            # Update the sent_status in the SmsDialer table to 1 
            sms_dialer = SmsDialer.objects.get(id=sms_dialer_id)
            sms_dialer.sent_status = sent_status
            sms_dialer.sent_datetime = get_mytime()
            sms_dialer.save()
            
        return response_data
