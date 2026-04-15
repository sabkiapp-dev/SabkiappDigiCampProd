import json
from src.voip_client import client as voip_client
import time
class PortData:
    def __init__(self):
        self.port = None
        self.status = None
        self.operator = None
        self.signal = None
        self.sim_imsi = None
        self.state = None
        self.phone_no = None  # Add new attribute with an empty string
        self.sms_backup_date = None  # Add new attribute with an empty string
        self.sms_balance = 0 # Add new attribute with an empty string
        self.validity = None  # Add new attribute with an empty string
        self.last_validity_check = None  # Add new attribute with an empty string
        self.final_status = None

    def add_port_data(self, port_data):
        self.port = port_data.get('port')
        self.status = port_data.get('status')
        self.operator = port_data.get('operator')
        self.signal = port_data.get('signal')
        self.sim_imsi = port_data.get('sim_imsi')
        self.state = port_data.get('state')
        self.phone_no = None  # Add empty string assignment for new attribute
        self.sms_backup_date = None  # Add empty string assignment for new attribute
        self.sms_balance = 0  # Add empty string assignment for new attribute
        self.validity = None  # Add empty string assignment for new attribute
        self.last_validity_check = None  # Add empty string assignment for new attribute
        self.final_status = None

    def fetch_and_populate_data(self):
        # fetch via voip_client (handles login/cookies)
        data = voip_client.get_gsminfo()


        # if it failed, data will be {} or {"status": "error", "message": "..."}
        if not data or "status" in data:
            return None, 0

        port_data_list = []
        # print("data : ", data)
        for values in data.values():
            for entry in values:
                port = PortData()
                port.add_port_data(entry)
                port_data_list.append(port)

        return port_data_list, (1 if port_data_list else 0)

    def print_all_attributes(self):
        all_attributes = {
            key: value for key, value in vars(self).items() if not key.startswith('__')
        }
        for attribute, value in all_attributes.items():
            print(f"{attribute}: {value}")