import requests
import pandas as pd
from src.port_data import PortData
from src.port_data import PortData
from src.virtual_data import VirtualStorage
from datetime import datetime
from .final_status import FinalStatus
from .send_ussd import request_ussd
import time
import threading
from src.mytime import get_mytime, timedelta
from src.update_database import update_sms_everywhere

class MachineStatus:

    def __init__(self, ussd_forcefully, port_forcefully):
        port_data_obj = PortData()
        ports_data, is_machine_on = port_data_obj.fetch_and_populate_data()
        self.is_machine_on = is_machine_on
        self.total_sms_balance = 0

        if(is_machine_on == 0):
            self.data_list = []
            return
        # Create an instance of VirtualStorage
        storage = VirtualStorage()

        # Fetch data
        fetched_data = storage.fetch_data()
        if fetched_data != "Error":
            merged_data = self.merge_data(ports_data, fetched_data)
        else:
            merged_data = ports_data
        self.new_sims = []
        self.rechargeless_sims = []
        
        data_list = []
        for i, port_data in enumerate(merged_data):
            data = {
                "port": port_data.port,
                "status": port_data.status,
                "operator": port_data.operator,
                "signal": port_data.signal,
                "sim_imsi": port_data.sim_imsi,
                "state": port_data.state,
                "phone_number": port_data.phone_no,
                "sms_backup_date": port_data.sms_backup_date,
                "sms_balance": port_data.sms_balance,
                "validity": port_data.validity,
                "last_validity_check": port_data.last_validity_check,
                "final_status": port_data.final_status
            }
  

    
            
            data_list.append(data)
            

        self.data_list = data_list

        for data in data_list:
            final_status = self.set_final_status(data)
            data['final_status'] = final_status
            if final_status == FinalStatus.READY.value or final_status == FinalStatus.BUSY.value:
                self.total_sms_balance += int(data["sms_balance"])
            # print(f"**Final Status : {data['final_status']}, port : {data['port']}")

        # Return data_list immediately
        self.data_list = data_list
        if fetched_data != "Error":
            # Start a new thread to run the remaining part of the script
            background_thread = threading.Thread(target=self.run_background_tasks, args=(ussd_forcefully, port_forcefully))
            background_thread.start()

    def run_background_tasks(self, ussd_forcefully, port_forcefully):
        # Rest of the script after returning data_list
        if len(self.new_sims) > 0:
            for sim in self.new_sims:
                sim_imsi = sim['sim_imsi']
                port = sim['port']
                operator = sim['operator']
                print(f"requesting ussd for port {port}, sim_imsi {sim_imsi}, operator {operator}, type phone")
                request_ussd(port, sim_imsi, operator, type='phone')
                time.sleep(2)

        if len(self.rechargeless_sims) > 0:
            for sim in self.rechargeless_sims:
                sim_imsi = sim['sim_imsi']
                port = sim['port']
                operator = sim['operator']
                last_validity_check_str = sim['last_validity_check']
                last_validity_check_dt = get_mytime()
                if last_validity_check_str:
                    try:
                        last_validity_check_dt = datetime.fromisoformat(last_validity_check_str)
                        last_validity_check_dt = datetime.fromisoformat(last_validity_check_str)
                    except ValueError:
                        pass                

                mytime = get_mytime()

                # Check if difference is greater than 1 hour
                time_difference = mytime - last_validity_check_dt
                if (time_difference > timedelta(hours=24)) or (ussd_forcefully==1 and int(port)==port_forcefully):
                   
                    # print(f"Requesting USSD for validity {sim_imsi}, {port}, {operator}, {last_validity_check_str}")
                    request_ussd(port, sim_imsi, operator, type='validity')
                    time.sleep(2)
                # else:
                #     print(f"Skipping USSD request for {sim_imsi} as validity check was done within the last hour.")

                    




    def merge_data(self, ports_data, fetched_data):
        merged_ports_data = []
        if(not fetched_data):
            return ports_data
        for port_data in ports_data:
            for fetched_item in fetched_data:
                if port_data.sim_imsi == fetched_item['sim_imsi']:
                    # Update the port_data with fetched_data attributes
                    port_data.phone_no = fetched_item.get('phone_no', '')
                    port_data.sms_backup_date = fetched_item.get('sms_backup_date', '')
                    port_data.sms_balance = fetched_item.get('sms_balance', '')
                    port_data.validity = fetched_item.get('validity', '')
                    port_data.last_validity_check = fetched_item.get('last_validity_check', '')
                    break
            merged_ports_data.append(port_data)
        
        return merged_ports_data
        
    def update_sms_data_in_datalist(self, sim_imsi, sms_backup_date, sms_balance):
        for data in self.data_list:
            if(data['sim_imsi'] == sim_imsi):
                data['sms_backup_date'] = sms_backup_date
                data['sms_balance'] = sms_balance
    def set_final_status(self, port_item):
        signal = 0
        today = get_mytime().date().strftime('%Y-%m-%d')

        port_item["final_status"] = ""  # Set default final_status to an empty string

        try:
            signal = int(port_item.get("signal", 0))
        except ValueError:
            pass


        if "Undetected SIM Card" in port_item.get("status", ""):
            # print("No SIM")
            port_item["final_status"] = FinalStatus.NO_SIM.value
        elif "No Signal" in port_item.get("status", "") or ("Up" in port_item.get("status", "") and signal < 5):
            # print("No Signal")
            port_item["final_status"] = FinalStatus.NO_SIGNAL.value
        elif "Up" in port_item.get("status", "") and not port_item.get("phone_number"):
         
            port_item["final_status"] = FinalStatus.NEW_SIM.value   
            print("new sim : ", port_item)
            self.new_sims.append(port_item)
        elif  "Up" in port_item.get("status", ""):
            validity = port_item.get("validity", "")
            if validity:
                try:
    
                    # print(f"validity_date : {validity}, type : {type(validity)}")
                    # print(f"today : {today}, type : {type(today)}")
                    if validity < today:
                        # print("rechargeless")
                        port_item["final_status"] = FinalStatus.RECHARGELESS.value
                        self.rechargeless_sims.append(port_item)
                    else:
                        sim_imsi = port_item.get("sim_imsi", "")
                        sms_backup_date = port_item.get("sms_backup_date", "")
                        # print(f"sms_backup_date : {sms_backup_date}, type : {type(sms_backup_date)}")

    
                                    
                        if sms_backup_date < today:
                            default_sms_balance = 100
                            update_sms_everywhere(sim_imsi, today, default_sms_balance)
                            self.update_sms_data_in_datalist(sim_imsi, today, default_sms_balance)
                        if port_item.get("state", "") == "READY":
                            port_item["final_status"] = FinalStatus.READY.value
                        else:
                            port_item["final_status"] = FinalStatus.BUSY.value
                except ValueError as ve:
                    print("Error : ", ve)
            else:
                # Code for requesting mobile number and other operations
                pass

        return port_item.get("final_status")


