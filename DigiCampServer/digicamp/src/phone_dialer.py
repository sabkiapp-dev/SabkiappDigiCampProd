import datetime
import os
import time
import django
from django.db.models import Q
from datetime import timedelta
from src.mytime import get_mytime
import requests
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'digicamp_server.settings')
django.setup()
from api.models import PhoneDialer, Campaign, SmsDialer, SmsCampaign
from django.db.models import F
import concurrent.futures
from api.models import ActiveCampaignHosts
from api.models import UserHosts
from api.models import SimInformation
from api.models import CallInfo
from api.views.gateway_status import merge_sim_information
from api.views.campaign import average_call_duration
import json
from django.core.exceptions import ObjectDoesNotExist
import threading
from django.conf import settings

from src.sabkiapp_server import get_name
from src.get_gateway_status import get_gateway_status
import os
import pickle
import time
from src.transliteration import transliterate_hindi 

# Get all PhoneDialer objects where sent_status equals 0
pickle_file_path_ms = 'gateway_status_fetch_time.pkl'
pickle_file_path_user_status = 'user_status.pkl'

def one_hour_ago():
    return get_mytime() - timedelta(hours=1)


def update_sim_information(host, sim_imsi):
    current_time = get_mytime()
    twenty_seconds_ago = current_time - timedelta(seconds=20)
    sim_information_obj = SimInformation.objects.filter(host=host, sim_imsi=sim_imsi).first()
    if sim_information_obj:
        last_call_actual_time = sim_information_obj.last_call_time
        sim_information_obj.last_call_time = current_time
        sim_information_obj.save()
        return last_call_actual_time
    else:
        return 0

def reupdate_sim_information(host, sim_imsi, updated_time):
    SimInformation.objects.filter(host=host, sim_imsi=sim_imsi).update(
        last_call_time=updated_time
    )



def process_response(response_list):
    number_of_sims_ready = response_list[0]['number_of_sims_ready'] if response_list else 0
    ready_sims = []
    if number_of_sims_ready > 0:
        ready_sims = [port for response in response_list for port in response['port_data'] if port['final_status'] == 'Ready']
        ready_sims = sorted(ready_sims, key=lambda x: x['call_time_today'])
    # print("number_of_sims_ready : ", number_of_sims_ready)
    # print("ready_sims : ", ready_sims)
    return number_of_sims_ready, ready_sims

def make_call_thread(final_dial_list: list[dict]) -> None:
    """
    Iterate over the dial list, transliterate dynamic fields to Hindi
    (using cached Gemini), and send /make_call request.
    """

    for dial in final_dial_list:
        # 0️⃣	Update sent_status → 'queued'
        PhoneDialer.objects.filter(id=dial["dial_id"]).update(sent_status=1)

        dial_id = dial["dial_id"]
        url = f"https://{dial['host']}.sabkiapp.com/make_call"
        headers = {"Content-Type": "application/json"}

        # -------------------------------------------
        # 1️⃣	Name fall-back lookup (if needed)
        name = dial["name"]
        if dial["name_spell"] != 0 and name is None:
            from digicamp_server.api.models import get_name  # local import avoids cycle
            names = get_name(dial["user_id"], [dial["phone_number"]])
            name = names.get(dial["phone_number"], "")

        # -------------------------------------------
        # 2️⃣	Transliteration (cached)
        name_hi       = transliterate_hindi(name)
        channel_hi    = transliterate_hindi(dial.get("channel_name"))
        surveyor_hi   = transliterate_hindi(dial.get("surveyor_name"))

        # -------------------------------------------
        # 3️⃣	Prepare payload
        data = {
            "host":          dial["host"],
            "system_password": dial["system_password"],
            "phone_number":  dial["phone_number"],
            "port":          dial["port"],
            "user_id":       dial["user_id"],
            "campaign_id":   dial["campaign_id"],
            "name":          name_hi,
            "name_spell":    dial["name_spell"],
            "channel_name":  channel_hi,
            "surveyor_name": surveyor_hi,
            "language":      Campaign.objects.get(id=dial["campaign_id"]).language,
        }
        # print("--data : ", data)
        # -------------------------------------------
        # 4️⃣	Send request & handle status
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=15)
        except Exception:
            response = None  # network error simulated

        if not response or response.status_code != 200:
            # reset sent_status so it can be retried
            PhoneDialer.objects.filter(id=dial_id, sent_status=1).update(sent_status=0)
        else:
            PhoneDialer.objects.filter(id=dial_id).update(sent_status=1)

    # Thread end
    return

def make_call(final_dial_list):
    threading.Thread(target=make_call_thread, args=(final_dial_list,)).start()

def get_phone_dilaer_list(user_host, ready_sim_list):

    try:
        # Arrange the ready_sim_list in ascending order of last_call_time
        ready_sim_list = sorted(ready_sim_list, key=lambda x: x['last_call_time'])
 

        my_time = get_mytime()
        user_id = user_host.user_id.id
        status = 1  # Assuming status is 1

        # Create a dictionary to store user_id, status, and current_time
        data = {'user_id': user_id, 'status': status, 'current_time': my_time}

        # Check if the pickle file exists
        if not os.path.exists(pickle_file_path_user_status):
            # print("Creating pickle file")
            # If the pickle file does not exist, create it and write the data
            with open(pickle_file_path_user_status, 'wb') as f:
                pickle.dump(data, f)
        else:
            # print("Found pickle file")
            # If the pickle file exists, load the existing data, update it, and write it back to the file
            try:
                with open(pickle_file_path_user_status, 'rb') as f:
                    existing_data = pickle.load(f)
            except EOFError:
                print("EOFError")
                existing_data = {}
            
            if user_id in existing_data and status == 1:
                if 'current_time' not in existing_data:
                    existing_data['current_time'] = datetime.datetime(2024, 2, 3, 1, 12, 0)  # Set current_time if it doesn't exist
                time_diff = (get_mytime() - existing_data['current_time']).total_seconds()
                if time_diff < 5:
                    # print("User ID with status 1 already exists in pickle file")
                    return ready_sim_list
                
            existing_data[user_id] = data
            # print("Updating pickle file")
            with open(pickle_file_path_user_status, 'wb') as f:
                pickle.dump(existing_data, f)

        
    
        # Get active campaign ids from ActiveCampaignHosts
        active_campaign_ids = ActiveCampaignHosts.objects.filter(
            status=1,
            host=user_host
        ).values_list('campaign_id', flat=True)
        limit = len(ready_sim_list)
        call_through_numbers = [sim['phone_number'] for sim in ready_sim_list]
 
        phone_dialers = PhoneDialer.objects.filter(
            Q(user_id=user_id) &
            Q(campaign__status=1) &
            Q(campaign__start_time__lte=my_time, campaign__end_time__gte=my_time) &
            Q(campaign__start_date__lte=my_time.date(), campaign__end_date__gte=my_time.date()) &
            Q(sent_status=0) & 
            (Q(sent_datetime=None) | Q(sent_datetime__lt=get_mytime())) & 
            Q(campaign__allow_repeat__gte=F('trials')) &
            Q(campaign_id__in=active_campaign_ids) &
            (Q(call_through=None) | Q(call_through__in=call_through_numbers))
        ).order_by('-campaign__campaign_priority', 'id')
        unique_phone_dialers = []
        seen_call_through = set()
        for i, phone_dialer in enumerate(phone_dialers):
            if phone_dialer.call_through is None:
                phone_dialer.sent_status = 6
                phone_dialer.save()
                unique_phone_dialers.append(phone_dialer)
            elif(phone_dialer.call_through not in seen_call_through):
                phone_dialer.sent_status = 6
                phone_dialer.save()
                unique_phone_dialers.append(phone_dialer)
                seen_call_through.add(phone_dialer.call_through)

            if len(unique_phone_dialers) == limit:
                break

        phone_dialers = unique_phone_dialers


            
        #unbook the status of user_id in pickel file to 0
        try:
            with open(pickle_file_path_user_status, 'rb') as f:
                existing_data = pickle.load(f)
        except EOFError:
            print("EOFError")
            existing_data = {}
        existing_data[user_id]['status'] = 0
        with open(pickle_file_path_user_status, 'wb') as f:
            pickle.dump(existing_data, f)

        final_dial_list = []
        for phone_dialer in phone_dialers:
            if len(ready_sim_list) > 0:
                call_through = phone_dialer.call_through
                if call_through is not None:
                    # print("call_through-- : ", call_through)
                    for sim in ready_sim_list:
                        if sim["phone_number"] == call_through:
                            # Update the sent_status to 1
            

                            phone_dialer.sent_status = 1
                            phone_dialer.sent_datetime = get_mytime()
                            phone_dialer.save()

                            ready_sim_list.remove(sim)
                            final_dial_list.append({
                                "host": user_host.host,
                                "system_password": user_host.system_password,
                                "phone_number": phone_dialer.phone_number,
                                "port": sim["port"],
                                "user_id": user_host.user_id.id,
                                "campaign_id": phone_dialer.campaign_id,
                                "name": phone_dialer.name,
                                "name_spell": phone_dialer.campaign.name_spell,
                                "dial_id": phone_dialer.id,
                                "channel_name": phone_dialer.channel_name,
                                "surveyor_name": phone_dialer.surveyor_name,
                                "ref_no": phone_dialer.ref_no
                            })
                            break
                    
                    phone_dialer.sent_status = 0
                    phone_dialer.sent_datetime = None
                    phone_dialer.save()
                else:
                    # Update the sent_status to 1
                    phone_dialer.sent_status = 1
                    phone_dialer.call_through = ready_sim_list[0]["phone_number"]
                    phone_dialer.sent_datetime = get_mytime()
                    phone_dialer.save()
                    call_through = ready_sim_list[0]["phone_number"]
                    final_dial_list.append({
                        "host": user_host.host,
                        "system_password": user_host.system_password,
                        "phone_number": phone_dialer.phone_number,
                        "port": ready_sim_list[0]["port"],
                        "user_id": user_host.user_id.id,
                        "campaign_id": phone_dialer.campaign_id,
                        "name": phone_dialer.name,
                        "name_spell": phone_dialer.campaign.name_spell,
                        "dial_id": phone_dialer.id,
                        "channel_name": phone_dialer.channel_name,
                        "surveyor_name": phone_dialer.surveyor_name,
                        "ref_no": phone_dialer.ref_no
                    })
                    ready_sim_list.pop(0)
        # Get a list of IDs from the sliced queryset
        dialer_ids = [dialer.id for dialer in phone_dialers]
    
            
        PhoneDialer.objects.filter(id__in=dialer_ids, sent_status=6).update(sent_status=0)
     
        if(len(final_dial_list) > 0):
            make_call(final_dial_list)
    except Exception as e:
        print("Error occurred in get_phone_dilaer_list:", str(e))
    
    return ready_sim_list          


def get_user_host_response_thread(user_host):

    if(user_host is None):
        return
    try:
        host_name = user_host.host
        current_time = get_mytime()
        data = {host_name: current_time}
        # Check if pickle file exists
        if not os.path.exists(pickle_file_path_ms):
            # If not, create a new dictionary with the host name and current time
            with open(pickle_file_path_ms, 'wb') as f:
                pickle.dump(data, f)
        else:
            try:
                with open(pickle_file_path_ms, 'rb') as f:
                    existing_data = pickle.load(f)
                    # print("user_id --: ", user_host.user_id.id)
                    # print("datetime --: ", current_time)
                    
                    # print("existing_data --: ", existing_data)
            except EOFError:
                print("EOFError1")
                existing_data = {}
            # Check if the host name is in the data
            if host_name in existing_data:
                # If it is, check if the time is within 5 seconds
                current_time = get_mytime()
                if (current_time - existing_data[host_name]).total_seconds() <= 5:
                    # If it is, wait for 5 seconds
                    time.sleep(5)
                    
                    # Update current time
                    
                    
                    # Reload the data from the pickle file
                    try:
                        with open(pickle_file_path_ms, 'rb') as f:
                            existing_data = pickle.load(f)

                    except EOFError:
                        print("EOFError2")
                        existing_data = {}
                    current_time = get_mytime()
                    if (current_time - existing_data[host_name]).total_seconds() <= 5:
                        # If the time is still within 5 seconds, return
                        return None, None, None
                current_time = get_mytime()
                data[host_name] = current_time
            
            else:
                # If the host name is not in the data, add it with the current time
                current_time = get_mytime()
                data[host_name] = current_time
            # Save the updated data
            existing_data.update(data)
            with open(pickle_file_path_ms, 'wb') as f:
                pickle.dump(existing_data, f)
                
        response = get_gateway_status(user_host)

        if response:
            #print("Step 5, merge_sim_information ", user_host.host)
            response = merge_sim_information([response])
            # print("Response : ", response)
            number_of_sims_ready, ready_sim_list = process_response(response)
            # If number of sims ready is greater than 0, then update the sim information for the list
            reupdate_sim_information_list = []
            for sim in ready_sim_list:
                updated = update_sim_information(user_host.host, sim["sim_imsi"])
                if updated == 0:
                    # remove the sim from ready_sim_list
                    ready_sim_list.remove(sim)
                else:
                    reupdate_sim_information_list.append((user_host.host, sim['sim_imsi'], updated))
            
            
            user_hosts = UserHosts.objects.filter(host=user_host.host, status=1).order_by('-priority')

            
            for user_host in user_hosts:
                # print("calling user_host : ", user_host.host, "user id : ", user_host.user_id.id)
                if len(ready_sim_list) > 0:
                    ready_sim_list = get_phone_dilaer_list(user_host, ready_sim_list)
                else:
                    break
            if len(ready_sim_list) > 0:
                for sim in ready_sim_list:
                    updated_time = next((item[2] for item in reupdate_sim_information_list if item[0] == user_host.host and item[1] == sim["sim_imsi"]), None)
                    reupdate_sim_information(user_host.host, sim["sim_imsi"], updated_time)
             

    except Exception as e:
        print("Error occurred in get_user_host_response_thread:", str(e))
        raise e




def get_user_host_response(user_host):
    # print("Step 2, get_user_host_response ", user_host.host)
    thread = threading.Thread(target=get_user_host_response_thread, args=(user_host,))
    thread.start()




def get_all_active_hosts():
    my_time = get_mytime()

    # Get active campaigns
    active_campaigns = Campaign.objects.filter(
        status=1,
        start_time__lte=my_time,
        end_time__gte=my_time,
        start_date__lte=my_time.date(),
        end_date__gte=my_time.date()
    )
    # Get active campaign hosts
    active_campaign_hosts = ActiveCampaignHosts.objects.filter(
        status=1,
        campaign__in=active_campaigns
    ).values_list('host_id', flat=True)

    # Get active hosts - use the full query to get correct UserHosts
    # FIX: Previously was getting distinct host names and then re-querying which returned wrong UserHosts
    # Now directly iterate over UserHosts matching all criteria (status, user_id from active campaigns, id in active_campaign_hosts)
    active_user_hosts = UserHosts.objects.filter(
        status=1,
        user_id__in=active_campaigns.values_list('user_id', flat=True),
        id__in=active_campaign_hosts
    )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for user_host in active_user_hosts:
            get_user_host_response(user_host)

##########################################################################
##########################################################################
            
##########################################################################
##########################################################################
            
def update_phone_dialer_and_sim_info(phone_dialer, user_host, sim_imsi, port):
    user_host_name = user_host.host
    sim_info = SimInformation.objects.filter(host=user_host_name)
    # get phone_no from sim_info list
    phone_numbers = [sim.phone_no for sim in sim_info]
    
    
    other_phone_dialer = PhoneDialer.objects.filter(sent_status=5, call_through__in=phone_numbers).exclude(call_through=phone_dialer.call_through).order_by('-sent_datetime').first()
    
    phone_dialer.sent_status = 0
    if other_phone_dialer:
        phone_dialer.call_through = other_phone_dialer.call_through
    else:
        phone_dialer.call_through = None
    
    phone_dialer.sent_datetime = None
    phone_dialer.block_trials = phone_dialer.block_trials + 1
    phone_dialer.save()

    sim_info = SimInformation.objects.filter(host=user_host.host, sim_imsi=sim_imsi).first()
    print("sim_info- : ", sim_info)
    if sim_info:
        sim_info.today_block_status = sim_info.today_block_status + 1
        sim_info.save()
        if sim_info.today_block_status > 4:
            # update all phone_dialer with call_through = None where sent_status = 0 and call_through = sim_info.phone_no
            PhoneDialer.objects.filter(sent_status=0, call_through=sim_info.phone_no).update(call_through=None)
        print("today_block_status ", sim_info.today_block_status, " sim_imsi ", sim_imsi)
        if(sim_info.today_block_status > 3):
            
            url = f"https://{user_host.host}.sabkiapp.com/make_call"
            headers = {
                'Content-Type': 'application/json',
            }
            data = {
                "host": user_host.host,
                "system_password": user_host.system_password,
                "phone_number": 8929897587,
                "port": port,
                "user_id": 10005055,
                "campaign_id": 1000000001,
                "name": "",
                "name_spell": 0
            }

            if port != 0:
                response = requests.post(url, headers=headers, data=json.dumps(data))
        

def update_final_call_status():
    # If we find sent_status =1 and sent_datetime is more than 1 hour ago, check for the entry of that id
    # in the call_status table, if not found, then update the sent_status to 0
    def five_mins_ago():
        return get_mytime() - timedelta(minutes=5)

    phone_dialers = PhoneDialer.objects.filter(
        Q(sent_status=1) &
        Q(sent_datetime__lte=five_mins_ago())
    )
    for phone_dialer in phone_dialers:
    
            try:
                call_status = phone_dialer.callstatus
                # print("call_status-- : ", call_status)

            except ObjectDoesNotExist:
                call_status = None

            if not call_status:
                call_through = phone_dialer.call_through
                user_id = phone_dialer.user_id
                if call_through is not None and user_id is not None:
                    sim_info = SimInformation.objects.filter(phone_no=call_through).order_by('-last_call_time').first()
                    if sim_info:
                        sim_imsi = sim_info.sim_imsi
                        host_name = sim_info.host
                        user_host = UserHosts.objects.filter(host=host_name, user_id=user_id).first()

                        if user_host:
                            gw_status = get_gateway_status(user_host)
                            if gw_status:
                                port = None
                                for item in gw_status['port_data']:
                                    if item['sim_imsi'] == sim_imsi:
                                        port = item['port']
                                        break
                                if port:
                                    update_phone_dialer_and_sim_info(phone_dialer, user_host, sim_imsi, port)
                                else:
                                    update_phone_dialer_and_sim_info(phone_dialer, user_host, sim_imsi, 0)

    # Also check for sent_status = 3 and sent_datetime is more than 1 hour ago, check for the entry of that id    
    # in the call_status table, if not found, then update the sent_status to 0
                
    phone_dialers = PhoneDialer.objects.filter(
        Q(sent_status=3) &
        Q(sent_datetime__lte=(one_hour_ago()))
    )


    for phone_dialer in phone_dialers:
        try:
            call_status = phone_dialer.callstatus
        except ObjectDoesNotExist:
            call_status = None

        if not call_status:
            phone_dialer.sent_status = 0
            phone_dialer.call_through = None
            phone_dialer.sent_datetime = None
            phone_dialer.save()
        else:
            # Update the endtime and duration in call_status table acc to call_cut_time from campaign
            phone_dialer.sent_status = 5
            phone_dialer.duration = int(average_call_duration(campaign_id=phone_dialer.campaign.id))
            phone_dialer.save()
            # delete callstatus
            call_status.delete()
            # Check if there are any contacts with status 0 or 1
            has_contacts = PhoneDialer.objects.filter(
                campaign_id=phone_dialer.campaign.id,
                sent_status__in=[0, 1, 3]  # Considering status 0 and 1
            ).exists()

            if not has_contacts and phone_dialer.campaign.status == 1:
                # Update campaign status to 3 if there are no contacts with status 0 or 1
                phone_dialer.campaign.status = 3
                phone_dialer.campaign.save()

    # If there is a contact with sent_status = 0 and call_through not None and sent_datetime is more than 1 day, update call_through to None
    phone_dialers = PhoneDialer.objects.filter(
        Q(sent_status=0) &
        Q(call_through__isnull=False) &
        Q(sent_datetime__lte=get_mytime()-timedelta(days=1))
    )
    for phone_dialer in phone_dialers:
        phone_dialer.call_through = None
        phone_dialer.save()

    # print("get_mytime min : ", get_mytime().time())
    # If get_mytime is bewteen 9:55pm and 9:56pm check all campaigns and all sms_campaigns with status 1 and if there is no contact with status 0 or 1, update the status to 3
    if get_mytime().time() >= get_mytime().replace(hour=21, minute=55).time() and get_mytime().time() <= get_mytime().replace(hour=21, minute=56).time():
        campaigns = Campaign.objects.filter(
            Q(status=1) 
        )
        for campaign in campaigns:
            has_contacts = PhoneDialer.objects.filter(
                campaign_id=campaign.id,
                sent_status=0 # Considering status 0
            ).exists()
            if not has_contacts:
                campaign.status = 3
                campaign.save()


        sms_campaigns = SmsCampaign.objects.filter(
            Q(status=1) 
        )
        for sms_campaign in sms_campaigns:
            has_contacts = SmsDialer.objects.filter(
                sms_campaign_id=sms_campaign.id,
                sent_status=0 # Considering status 0 
            ).exists()
            if not has_contacts:
                sms_campaign.status = 3
                sms_campaign.save()


    
