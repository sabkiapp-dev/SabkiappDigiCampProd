import os
import django
from django.db.models import Q

from datetime import timedelta
from voiceapi.mytime import get_mytime
import requests
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'voiceapi.settings')
django.setup()
from api.models import PhoneDialer, Campaign
from django.db.models import F
import concurrent.futures
from api.views.machine_status import fetch_machine_status
from api.models import ActiveCampaignHosts
from api.models import UserHosts
from api.models import SimInformation
from api.views.machine_status import merge_sim_information
# Get all PhoneDialer objects where sent_status equals 0
one_hour_ago = get_mytime() - timedelta(hours=1)

my_time = get_mytime()
print("My Time : ", my_time)

def get_machine_status(user_host):
    try:
        response = requests.get(f'https://{user_host.host}.sabkiapp.com/machine_status', params={'host': user_host.host, 'password': user_host.system_password}, timeout=10)
        return response.json()  # return the response from the server
    except requests.exceptions.RequestException as e:
        return None
    

def update_sim_information(host, sim_imsi):
    SimInformation.objects.filter(host=host, sim_imsi=sim_imsi).update(
        last_call_time= get_mytime()
    )


def process_response(response_list):
    number_of_sims_ready = response_list[0]['number_of_sims_ready'] if response_list else 0
    if number_of_sims_ready > 0:
        ready_sims = [port for response in response_list for port in response['port_data'] if port['final_status'] == 'Ready']
        sim_with_lowest_call_time_today = min(ready_sims, key=lambda port: port['call_time_today'])
    else:
        sim_with_lowest_call_time_today = None
    return ready_sims, sim_with_lowest_call_time_today

# Find all active hosts from the UserHosts table 
active_hosts = UserHosts.objects.filter(status=1).values_list('host', flat=True).distinct()

with concurrent.futures.ThreadPoolExecutor() as executor:
    user_hosts = [UserHosts.objects.filter(host=host).first() for host in active_hosts]
    user_hosts = [user_host for user_host in user_hosts if user_host]  # remove None values
    for user_host, response in zip(user_hosts, executor.map(get_machine_status, user_hosts)):
        if response:
            response = merge_sim_information([response])
            number_of_sims_ready, sim_with_lowest_call_time_today = process_response(response)
            if sim_with_lowest_call_time_today:
                update_sim_information(user_host.host, sim_with_lowest_call_time_today["sim_imsi"])
                # Find the user from userHost with highest priority using orderby priority desc
                user_hosts = UserHosts.objects.filter(host=user_host.host).order_by('-priority')
                for user_host in user_hosts:
                    print("User : ", user_host.user_id.id)
                    if(user_host.user_id.id == 10000002):
                        print("User is 10000002")
                        break
        else:
            print(f"No response for host {user_host.host}")
