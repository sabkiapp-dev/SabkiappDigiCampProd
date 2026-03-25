import errno
import os
import django
from django.db.models import Q, F
from datetime import timedelta
from src.mytime import get_mytime
import requests
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'voiceapi.settings')
django.setup()
from api.models import PhoneDialer, Campaign
import concurrent.futures
from api.models import ActiveCampaignHosts
from api.models import UserHosts
from api.models import SimInformation
from api.views.machine_status import merge_sim_information
from django.db.models import Max
import threading
from django.conf import settings
from api.models import SmsCampaign
from api.models import SmsDialer  # Import the SmsDialer class
import time
from src.sms_sender import SmsSender
import pickle
from datetime import datetime, timedelta
from src.get_machine_status import get_machine_status


def sms_dialers_list_to_send(host, system_password, sms_dialers_list, machine_status):
    # Flatten the list of lists
    sms_dialers_list = [item for sublist in sms_dialers_list for item in sublist]

    # Arrange the sms_dialers_list acc to the sms_count desc
    sms_dialers_list = sorted(sms_dialers_list, key=lambda sms_dialer: sms_dialer.sms_count, reverse=True)


    # Arrange the port data acc to the sms_balance descending
    port_data = sorted(machine_status['port_data'], key=lambda x: x['sms_balance'], reverse=True)

    # Remove port data where sms_balance is 0
    port_data = [port for port in port_data if port['sms_balance'] > 0]



    data = []
    # Now match or book each sms_dialer with the port_data
    for sms_dialer in sms_dialers_list:
        for port in port_data:
            if (port['final_status'] == "Ready" or port['final_status'] == "Busy") and (port['sms_balance'] > sms_dialer.sms_count):
                data.append({
                    'sms_dialer_id': sms_dialer.id,
                    'port': port['port'],
                    'message': sms_dialer.sms_sent,
                    'phone_no': sms_dialer.phone_number,
                })
                sms_dialer.sms_through = port['phone_number']
                # Remove the port from the port_data
                port_data.remove(port)  
                break          
            else:
                sms_dialer.sent_status = 0
                sms_dialer.sent_datetime = None
                sms_dialer.save()
    
    response = SmsSender().send_sms(host, system_password, data)
    return response




def sms_dialer_instant():
    try:
        my_time = get_mytime()

        sms_dialers = SmsDialer.objects.filter(
            Q(sent_status=0) &
            Q(sms_campaign_id=None) 
        )
        if not sms_dialers:
            return None
        sms_dialer_user_ids = sms_dialers.values_list('user_id', flat=True).distinct()
        if not sms_dialer_user_ids:
            return None
        active_hosts = UserHosts.objects.filter(
            Q(status=1) &
            Q(allow_sms=1) &
            Q(user_id__in=sms_dialer_user_ids)
        ).distinct()

        if not active_hosts:
            return None
        try:
            # Convert the queryset to a list of dictionaries
            active_hosts_list = list(active_hosts.values('host').distinct())

            # Create a dictionary with host as the key and status and time as values
            active_hosts_dict = {item['host']: {'status': 1, 'time': get_mytime()} for item in active_hosts_list}

            booked_hosts = []
            # If the pickle file does not exist, create it and add all entries from active_hosts_dict
            if not os.path.exists('sms_active_hosts.pickle'):
                with open('sms_active_hosts.pickle', 'wb') as f:
                    pickle.dump(active_hosts_dict, f)
                booked_hosts.extend(active_hosts_dict.keys())########
            else:
                with open('sms_active_hosts.pickle', 'rb') as f:
                    saved_hosts_dict = pickle.load(f)

                # Check for each host
                for host, data in active_hosts_dict.items():
                    # If no entry for host, make an entry
                    if host not in saved_hosts_dict:
                        saved_hosts_dict[host] = data
                        # save in pickle
                        with open('sms_active_hosts.pickle', 'wb') as f:
                            pickle.dump(saved_hosts_dict, f)

                        booked_hosts.extend(saved_hosts_dict.keys())#########
                    else:
                        # If entry with status=1 and time < 5 seconds, wait for 5 sec for 6 times
                        for _ in range(15):
                            # Load the dictionary from the pickle file
                            with open('sms_active_hosts.pickle', 'rb') as f:
                                saved_hosts_dict = pickle.load(f)

                            # If the host is not in the dictionary or the status is not 1 or the time difference is 5 seconds or more, break the loop
                            if host not in saved_hosts_dict or saved_hosts_dict[host]['status'] != 1 or (get_mytime() - saved_hosts_dict[host]['time']).total_seconds() >= 30:
                                booked_hosts.extend(saved_hosts_dict.keys()) ###############
                                # Update the status and time in the dictionary to current time
                                saved_hosts_dict[host] = {'status': 1, 'time': get_mytime()}
                                # Save the dictionary in the pickle file
                                with open('sms_active_hosts.pickle', 'wb') as f:
                                    pickle.dump(saved_hosts_dict, f)
                                break
                            
                            time.sleep(3)



        except Exception as e:
            print(f"An error occurred: {e}")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for host in booked_hosts:
                
                user_hosts = UserHosts.objects.filter(host=host, status=1, allow_sms=1).order_by('-priority')
                if user_hosts:
                    machine_status = get_machine_status(user_hosts.first())
                    if machine_status and machine_status['machine_power_status'] == 1 and machine_status['total_sms_balance'] > 0:
                        # Find the maximum balance of the user hosts from the machine status
                        max_balance = 0
                        for port in machine_status['port_data']:
                            if port['sms_balance'] > max_balance:
                                max_balance = port['sms_balance']

                        

                        limit = machine_status['number_of_sims_ready'] + machine_status['number_of_sims_busy']
                        if limit > 0:
                            sms_dialers_list = []
                            for user_host in user_hosts:
                                if(limit < 1):
                                    break
                                
                                booked_users = {user_host.user_id.id: {'status': 1, 'time': get_mytime()} }
                                user_free = False
                                if not os.path.exists('sms_user_id.pickle'):
                                    # If the file does not exist, create it
                                    with open('sms_user_id.pickle', 'wb') as f:
                                        pickle.dump(booked_users, f)
                                    user_free = True
                                    

                                else:
                                    with open('sms_user_id.pickle', 'rb') as f:
                                        sms_user_ids = pickle.load(f)
                                        if user_host.user_id.id not in sms_user_ids:
                                            sms_user_ids[user_host.user_id.id] = {'status': 1, 'time': get_mytime()}
                                            with open('sms_user_id.pickle', 'wb') as f:
                                                pickle.dump(sms_user_ids, f)
                                            user_free = True
                                        else:
                                            for _ in range(2):
                                                with open('sms_user_id.pickle', 'rb') as f:
                                                    sms_user_ids = pickle.load(f)
                                                if user_host.user_id.id not in sms_user_ids or sms_user_ids[user_host.user_id.id]['status'] != 1 or (get_mytime() - sms_user_ids[user_host.user_id.id]['time']).total_seconds() >= 1:
                                                    booked_users[user_host.user_id.id] = {'status': 1, 'time': get_mytime()}
                                                    with open('sms_user_id.pickle', 'wb') as f:
                                                        pickle.dump(sms_user_ids, f)
                                                    user_free = True
                                                    break
                                                time.sleep(1)
                                if user_free:
                                    sms_dialers = SmsDialer.objects.filter(
                                        Q(user_id=user_host.user_id) &
                                        Q(sent_status=0) &
                                        Q(sms_campaign_id=None) & 
                                        Q(sms_count__lte=max_balance) &
                                        Q(sms_template__status=1) 
                                    ).order_by('id')[:limit]
                                    sms_dialers = list(sms_dialers)
                                    for sms_dialer in sms_dialers:
                                        sms_dialer.sent_status = 1
                                        sms_dialer.sent_datetime = my_time
                                        sms_dialer.save()
                                    # Make users free by changing status = 0
                                    booked_users[user_host.user_id.id] = {'status': 0, 'time': get_mytime()}
                                    with open('sms_user_id.pickle', 'wb') as f:
                                        pickle.dump(booked_users, f)
                                    sms_dialers_list.append(sms_dialers)
                                    limit = limit - len(sms_dialers)
                            if (len(sms_dialers_list) > 0):  
                                system_password = user_host.system_password
                                response = sms_dialers_list_to_send(host, system_password, sms_dialers_list, machine_status)
                                if(response):
                                    # Unbook the hosts to status 0 in pickle file
                                    with open('sms_active_hosts.pickle', 'rb') as f:
                                        saved_hosts_dict = pickle.load(f)
                                    for host in saved_hosts_dict:
                                        saved_hosts_dict[host] = {'status': 0, 'time': get_mytime()}
                                    with open('sms_active_hosts.pickle', 'wb') as f:
                                        pickle.dump(saved_hosts_dict, f)
                                    time.sleep(5)
                                    sms_dialer_instant()                           

    except Exception as e:
        print(f"An error occurred 2: {e}")
        raise e


def sms_dialer_bulk():
    try:
        my_time = get_mytime()

        sms_dialers = SmsDialer.objects.filter(
                    Q(sent_status=0) &
                    Q(sms_campaign__status=1) &
                    Q(sms_campaign__start_time__lte=my_time, sms_campaign__end_time__gte=my_time) &
                    Q(sms_campaign__start_date__lte=my_time.date(), sms_campaign__end_date__gte=my_time.date())
                )
        if not sms_dialers:
            return None
        sms_dialer_user_ids = sms_dialers.values_list('user_id', flat=True).distinct()
        if not sms_dialer_user_ids:
            return None
        
        active_hosts = UserHosts.objects.filter(
            Q(status=1) &
            Q(allow_sms=1) &
            Q(user_id__in=sms_dialer_user_ids)
        ).distinct()

        if not active_hosts:
            return None
        try:
            # Convert the queryset to a list of dictionaries
            active_hosts_list = list(active_hosts.values('host').distinct())

            # Create a dictionary with host as the key and status and time as values
            active_hosts_dict = {item['host']: {'status': 1, 'time': get_mytime()} for item in active_hosts_list}

            booked_hosts = []
            # If the pickle file does not exist, create it and add all entries from active_hosts_dict
            if not os.path.exists('sms_active_hosts.pickle'):
                with open('sms_active_hosts.pickle', 'wb') as f:
                    pickle.dump(active_hosts_dict, f)
                booked_hosts.extend(active_hosts_dict.keys())########
            else:
                with open('sms_active_hosts.pickle', 'rb') as f:
                    saved_hosts_dict = pickle.load(f)

                # Check for each host
                for host, data in active_hosts_dict.items():
                    # If no entry for host, make an entry
                    if host not in saved_hosts_dict:
                        saved_hosts_dict[host] = data
                        # save in pickle
                        with open('sms_active_hosts.pickle', 'wb') as f:
                            pickle.dump(saved_hosts_dict, f)

                        booked_hosts.extend(saved_hosts_dict.keys())#########
                    else:
                        # If entry with status=1 and time < 5 seconds, wait for 5 sec for 6 times
                        for _ in range(15):
                            # Load the dictionary from the pickle file
                            with open('sms_active_hosts.pickle', 'rb') as f:
                                saved_hosts_dict = pickle.load(f)

                            # If the host is not in the dictionary or the status is not 1 or the time difference is 5 seconds or more, break the loop
                            if host not in saved_hosts_dict or saved_hosts_dict[host]['status'] != 1 or (get_mytime() - saved_hosts_dict[host]['time']).total_seconds() >= 30:
                                booked_hosts.extend(saved_hosts_dict.keys()) ###############
                                # Update the status and time in the dictionary to current time
                                saved_hosts_dict[host] = {'status': 1, 'time': get_mytime()}
                                # Save the dictionary in the pickle file
                                with open('sms_active_hosts.pickle', 'wb') as f:
                                    pickle.dump(saved_hosts_dict, f)
                                break
                            
                            time.sleep(3)



        except Exception as e:
            print(f"An error occurred: {e}")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for host in booked_hosts:
                
                user_hosts = UserHosts.objects.filter(host=host, status=1, allow_sms=1).order_by('-priority')
                if user_hosts:
                    machine_status = get_machine_status(user_hosts.first())
                    if machine_status and machine_status['machine_power_status'] == 1 and machine_status['total_sms_balance'] > 0:
                        # Find the maximum balance of the user hosts from the machine status
                        max_balance = 0
                        for port in machine_status['port_data']:
                            if port['sms_balance'] > max_balance:
                                max_balance = port['sms_balance']

                        

                        limit = machine_status['number_of_sims_ready'] + machine_status['number_of_sims_busy']
                        if limit > 0:
                            sms_dialers_list = []
                            for user_host in user_hosts:
                                if(limit < 1):
                                    break
                                
                                booked_users = {user_host.user_id.id: {'status': 1, 'time': get_mytime()} }
                                user_free = False
                                if not os.path.exists('sms_user_id.pickle'):
                                    # If the file does not exist, create it
                                    with open('sms_user_id.pickle', 'wb') as f:
                                        pickle.dump(booked_users, f)
                                    user_free = True
                                    

                                else:
                                    with open('sms_user_id.pickle', 'rb') as f:
                                        sms_user_ids = pickle.load(f)
                                        if user_host.user_id.id not in sms_user_ids:
                                            sms_user_ids[user_host.user_id.id] = {'status': 1, 'time': get_mytime()}
                                            with open('sms_user_id.pickle', 'wb') as f:
                                                pickle.dump(sms_user_ids, f)
                                            user_free = True
                                        else:
                                            for _ in range(2):
                                                with open('sms_user_id.pickle', 'rb') as f:
                                                    sms_user_ids = pickle.load(f)
                                                if user_host.user_id.id not in sms_user_ids or sms_user_ids[user_host.user_id.id]['status'] != 1 or (get_mytime() - sms_user_ids[user_host.user_id.id]['time']).total_seconds() >= 1:
                                                    booked_users[user_host.user_id.id] = {'status': 1, 'time': get_mytime()}
                                                    with open('sms_user_id.pickle', 'wb') as f:
                                                        pickle.dump(sms_user_ids, f)
                                                    user_free = True
                                                    break
                                                time.sleep(1)
                                if user_free:
                                    sms_dialers = SmsDialer.objects.filter(
                                        Q(user_id=user_host.user_id) &
                                        Q(sent_status=0) &
                                        Q(sms_campaign__status=1) &
                                        Q(sms_campaign__start_time__lte=my_time, sms_campaign__end_time__gte=my_time) &
                                        Q(sms_campaign__start_date__lte=my_time.date(), sms_campaign__end_date__gte=my_time.date()) &
                                        Q(sms_count__lte=max_balance) &
                                        Q(sms_template__status=1) 
                                    ).order_by('id')[:limit]

                                    sms_dialers = list(sms_dialers)
                                    for sms_dialer in sms_dialers:
                                        sms_dialer.sent_status = 1
                                        sms_dialer.sent_datetime = my_time
                                        sms_dialer.save()
                                    # Make users free by changing status = 0
                                    booked_users[user_host.user_id.id] = {'status': 0, 'time': get_mytime()}
                                    with open('sms_user_id.pickle', 'wb') as f:
                                        pickle.dump(booked_users, f)
                                    sms_dialers_list.append(sms_dialers)
                                    limit = limit - len(sms_dialers)
                            if (len(sms_dialers_list) > 0):  
                                system_password = user_host.system_password
                                response = sms_dialers_list_to_send(host, system_password, sms_dialers_list, machine_status)
                                if(response):
                                    # Unbook the hosts to status 0 in pickle file
                                    with open('sms_active_hosts.pickle', 'rb') as f:
                                        saved_hosts_dict = pickle.load(f)
                                    for host in saved_hosts_dict:
                                        saved_hosts_dict[host] = {'status': 0, 'time': get_mytime()}
                                    with open('sms_active_hosts.pickle', 'wb') as f:
                                        pickle.dump(saved_hosts_dict, f)
                                    time.sleep(5)
                                    sms_dialer_bulk()                           

    except Exception as e:
        print(f"An error occurred 2: {e}")
        raise e
