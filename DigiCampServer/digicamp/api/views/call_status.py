from decimal import Decimal
import json
import logging
import os
import random
from django.http import JsonResponse
import requests
from rest_framework.decorators import api_view
from rest_framework.parsers import JSONParser
from ..models.call_status import CallStatus 
from ..models.call_dtmf_status import CallDtmfStatus
from ..models.campaign import Campaign
from ..models.user_hosts import UserHosts
from ..models.phone_dialer import PhoneDialer
from ..serializers import CallStatusSerializer
from django.utils import timezone
from src.mytime import get_mytime
from src.phone_dialer import get_all_active_hosts, update_final_call_status, get_user_host_response, update_phone_dialer_and_sim_info
from django.conf import settings
from datetime import timedelta
from ..views.sms_dialer import sms_dialer_bulk
from threading import Thread
from ..models.sim_information import SimInformation
from ..models.dial_plan import DialPlan
from ..models.error_verify_phone_dialer import ErrorVerifyPhoneDialer, now_ist_naive
from django.db.models import F
import datetime as dt
import pytz
from ..call_status_pusher import CallStatusPusher

IST = pytz.timezone("Asia/Kolkata")



def check_sim_block_call(user_host, port):

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
        print("make_call_reponse : ", response.json())



def push_call_status(phone_dialer, status: str):
    print("push_call_status: ", phone_dialer, status)
    """Push call status to SabkiApp for the given PhoneDialer."""
    ref_no = getattr(phone_dialer, 'ref_no', None)
    if not ref_no:
        print("push_call_status: Missing ref_no – skipping API call")
        return False

    payload = {
        "ref_no": ref_no,
        "status": status,
        "retry_count": phone_dialer.trials +1 or 1,
        "retry_at": dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }
    return CallStatusPusher.push(payload)


import datetime  # Added to handle standard UTC timezone



@api_view(['POST'])
def send_call_status(request):
    
    data = JSONParser().parse(request)
    print("data : ", data)
    host = data.get('host')
    system_password = data.get('system_password')
    campaign_id = data.get('campaign')
    # Validate campaign_id – must be numeric
    if not campaign_id or not str(campaign_id).isdigit():
        return JsonResponse({"message": "Invalid or missing campaign_id"}, status=400)
    # create a random 10 digit number for testing
    random_id = ''.join([str(random.randint(0, 9)) for _ in range(10)])
    
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        # Look up host+password WITHOUT user_id to see who owns it
        user_host_any = UserHosts.objects.filter(host=host, system_password=system_password).values('id','user_id').first()
       
        # If you still want the strict triple match, do it after logging:
        user_host = UserHosts.objects.get(host=host, system_password=system_password, user_id=campaign.user_id)
        user_id = campaign.user_id
        user_host = UserHosts.objects.get(host=host, system_password=system_password, user_id=user_id)
    except (Campaign.DoesNotExist, UserHosts.DoesNotExist):
        print(f"Host not matching with user_id or password not correct random id : {random_id}")
        return JsonResponse({"message": 'Host not matching with user_id or password not correct'}, status=400)


    current_time = get_mytime()
    phone = data.get('phone')
    port = data.get('port')
    sim_imsi = data.get('sim_imsi')
    data['host'] = user_host.id
    host = user_host.id
    campaign_id = data.get('campaign')  # Assuming campaign_id is in data

    
    if(data.get('event') == 'start_dialing'):
        dtmf_response = data.get('dtmf_response')
        if not dtmf_response or not dtmf_response.isdigit():
            print("Invalid dtmf_response")
            return JsonResponse({"message": 'Invalid dtmf_response'}, status=400)
        try:
            # We add 19800 to push the naive datetime forward by 5.5 hours (to match IST)
            adjusted_epoch = int(dtmf_response) + 19800
            dial_time = datetime.datetime.fromtimestamp(adjusted_epoch)
        except ValueError:
            print("Invalid time format in dtmf_response.")
            dial_time = None
        if not dial_time:
            print("Invalid dtmf_response1")
            return JsonResponse({"message": 'Invalid dtmf_response'}, status=400)
     

        phone_dialer = PhoneDialer.objects.filter(phone_number=phone, campaign_id=campaign_id, sent_status=1).order_by('-sent_datetime').first()
        if not phone_dialer:
            print("random id :", random_id,", Invalid start_dialing event, phone= ", phone, " campaign= ", campaign_id, "sim_imsi= ", sim_imsi)
            return JsonResponse({"message": 'Invalid start_dialing event'}, status=400)
        # print("radom_id ", random_id,"valid start_dialing event. phone= ", phone, " campaign= ", campaign_id, "sim_imsi= ", sim_imsi)
        phone_dialer.sent_datetime = dial_time
        phone_dialer.save()
        return JsonResponse({"message": 'Dial time updated successfully'}, status=201)
        
    elif data.get('event') == 'not_answered':
        
        # print("hereee")
        data['start_time'] = current_time
        data['end_time'] = current_time

        dtmf_response = data.get('dtmf_response')
        if not dtmf_response or not dtmf_response.isdigit():
            print("Invalid dtmf_response2")
            return JsonResponse({"message": 'Invalid timestamp'}, status=400)
        try:
            # We add 19800 to push the naive datetime forward by 5.5 hours (to match IST)
            adjusted_epoch = int(dtmf_response) + 19800
            dial_time = datetime.datetime.fromtimestamp(adjusted_epoch)
        except ValueError:
            print("Invalid time format in dtmf_response.")
            dial_time = None
        if not dial_time:
            print("Invalid dtmf_response3")
            return JsonResponse({"message": 'Invalid dtmf_response'}, status=400)
       
        # Retrieve the PhoneDialer instance
        phone_dialer = PhoneDialer.objects.filter(
            phone_number=phone,
            campaign_id=campaign_id,
            sent_status=1,
            # sent_datetime__gte removed (iter04 fix)
        ).order_by('-sent_datetime').first()

        if phone_dialer:

            # print("here ")
            # if dialtime - sent_datetime is less than 5 sec, print hello world
            if (dial_time - phone_dialer.sent_datetime).total_seconds() < 5:
                if phone_dialer.block_trials > 1:
                    phone_dialer.sent_status = 2
                    phone_dialer.save()
                    if user_id == 10006666:
                        # Push call status to SabkiApp
                        push_call_status(phone_dialer, 'not_answered')
                        
                    return JsonResponse({"message": 'Call not answered'}, status=201)
              
                update_phone_dialer_and_sim_info(phone_dialer, user_host, sim_imsi, port)
                
                get_user_host_response(user_host)
                print("Sim blocked")
                return JsonResponse({"message": 'Sim Blocked'}, status=400)
            
            

            # If phone_dialer.
            extension = data.get('extension')
            if (extension != 'CONGESTION' and extension != 'CHANUNAVAIL'):
            
                # Update sent_status in PhoneDialer table
                phone_dialer.sent_status = 2
                phone_dialer.save()
                sim_info = SimInformation.objects.filter(host=user_host.host, sim_imsi=sim_imsi).first()
                if sim_info:
                    if sim_info.today_block_status > 3:
                        print("user_host, port : ", user_host, port)
                        check_sim_block_call(user_host, port)
                    sim_info.calls_made_today += 1
                    sim_info.calls_made_total += 1
                    sim_info.today_block_status += Decimal('0.5')
                    sim_info.save()
                if user_id == 10006666:
                    # Push call status to SabkiApp
                    push_call_status(phone_dialer, 'not_answered')

                # Check if allow_repeat is greater than phone_dialer.trials
                if campaign.allow_repeat > phone_dialer.trials:
                    #if sent_status=0 and campaign_id=campaign_id is already present, return
                    if PhoneDialer.objects.filter(
                        phone_number=phone,
                        campaign_id=campaign_id,
                        sent_status=0
                    ).exists():
                        return JsonResponse({"message": 'Call not answered'}, status=201)
                    # also check sent_status=1
                    # Add a new entry to PhoneDialer with sent_status 0
                    new_phone_dialer = PhoneDialer.objects.create(
                        phone_number=phone,
                        user_id=user_id,
                        name=phone_dialer.name,
                        call_through=phone_dialer.call_through,
                        campaign_id=campaign_id,
                        sent_status=0,
                        sent_datetime=current_time + timedelta(hours=1),  # 1 hour after
                        trials=phone_dialer.trials + 1,  # Increment trials
                        channel_name=phone_dialer.channel_name,
                        surveyor_name=phone_dialer.surveyor_name
                    )
                    new_phone_dialer.save()
                else:
                    # Check if there are any contacts with status 0 or 1
                    has_contacts = PhoneDialer.objects.filter(
                        campaign_id=campaign_id,
                        sent_status__in=[0, 1, 3]  # Considering status 0 and 1
                    ).exists()

                    if not has_contacts and campaign.status==1 and user_id != 10006666:
                        # Update campaign status to 3 if there are no contacts with status 0 or 1
                        campaign.status = 3
                        campaign.save()

                get_user_host_response(user_host)
                return JsonResponse({"message": 'Call not answered'}, status=201)
            elif(extension == 'CONGESTION' or extension == 'CHANUNAVAIL'):
                # Assuming phone_dialer is defined here
                update_phone_dialer_and_sim_info(phone_dialer, user_host, sim_imsi, port)
                get_user_host_response(user_host)
                print("Sim blocked1")
                return JsonResponse({"message": 'Sim blocked'}, status=400)    
            
        else:
            return JsonResponse({"message": 'No contact found in phone_dialer'}, status=404)


    elif data.get('event') == 'answered':
        data['start_time'] = current_time
        print("answeeredd phone : ", phone, "campaign_id : ", campaign_id)
        print("")

        # Retrieve the PhoneDialer instance
        phone_dialer = PhoneDialer.objects.filter(
            phone_number=phone,
            campaign_id=campaign_id,
            sent_status=1,
            # sent_datetime__gte removed (iter04 fix)
        ).order_by('-sent_datetime').first()

        print("answered phone_dialer : ", phone_dialer)
        if phone_dialer:
            data['dial'] = phone_dialer.id  # Add the dial_id to the data
            # print("phone number in dialer : ", phone_dialer.phone_number)
            serializer = CallStatusSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                print("answered phone number in serializer ", phone_dialer.phone_number)
                # Update sent_status in PhoneDialer table
                phone_dialer.sent_status = 3
                phone_dialer.save()
                # print("phone number in dialer after save ", phone_dialer.phone_number)

                return JsonResponse(serializer.data, status=201)

            else:
                print("answeredSerializer not valid : ", serializer.errors)
                
                # FIX: Check if another thread already updated this record to status 3 before we downgrade it
                phone_dialer.refresh_from_db()
                if phone_dialer.sent_status != 3:
                    phone_dialer.sent_status = 2
                    phone_dialer.save()
                
                return JsonResponse({"message": "Serializer not valid", "errors": serializer.errors}, status=400)

        else:
            print("answered No contact found in phone_dialer")
            return JsonResponse({"message": 'No contact found in phone_dialer'}, status=404)

    elif data.get('event') == 'completed':
        timeout = campaign.call_cut_time if campaign.call_cut_time else 0
        start_time = current_time
        call_status = CallStatus.objects.filter(phone=phone, campaign=campaign, port=port, host=host, dial__sent_status=3).order_by('-id').first()
        if not call_status:
            print("Invalid event")
            return JsonResponse({"message": 'Invalid event'}, status=400)
        data['end_time'] = current_time 
        start_time = call_status.start_time
        end_time = data.get('end_time')
        data['duration'] = (end_time - start_time).seconds
        if(data['duration'] > timeout):
            data['duration'] = timeout
        duration = data['duration']
        
        # Retrieve the PhoneDialer instance
        phone_dialer = PhoneDialer.objects.filter(id=call_status.dial_id, sent_status=3).first()
        if phone_dialer:
            sim_info = SimInformation.objects.filter(host=user_host.host, sim_imsi=sim_imsi).first()

            if sim_info:
                sim_info.calls_made_today += 1
                sim_info.call_time_today += data['duration']
                sim_info.calls_made_total += 1
                sim_info.call_time_total += data['duration']
                sim_info.today_block_status = 0
                sim_info.save()

             # Update sent_status in PhoneDialer table
            phone_dialer.sent_status = 5
            phone_dialer.duration = duration
            phone_dialer.save()

            # ── If service user and no DTMF yet → push no_dtmf ───────────────
            if user_id == 10006666 and not CallDtmfStatus.objects.filter(call_id=phone_dialer.id, dtmf_response__in=["1", "2"]).exists():
                push_call_status(phone_dialer, "no_dtmf")
            
                
            get_user_host_response(user_host)


            # Check if there are any contacts with status 0 or 1
            has_contacts = PhoneDialer.objects.filter(
                campaign_id=campaign_id,
                sent_status__in=[0, 1, 3]  # Considering status 0 and 1
            ).exists()

            if not has_contacts and campaign.status == 1 and user_id != 10006666:
                # Update campaign status to 3 if there are no contacts with status 0 or 1
                campaign.status = 3
                campaign.save()
                

            # Delete the existing call_status instance
            call_status.delete()


            get_user_host_response(user_host)
            return JsonResponse({"message":"Event completed"}, status=201)
        else:
            return JsonResponse({"message": 'No contact found in phone_dialer with sent_status=3'}, status=404)


    elif data.get('event') == 'dtmf':
        extension = data.get('extension')
        # If extension is not present in data, return error
        if not extension:
            return JsonResponse({"message": 'Extension is required'}, status=400)
        dtmf_response = data.get('dtmf_response')
        if not dtmf_response or not dtmf_response.isdigit() or int(dtmf_response) not in range(0, 10):
            return JsonResponse({"message": 'Invalid dtmf_response'}, status=400)
        phone_dialer = PhoneDialer.objects.filter(phone_number=phone, campaign=campaign, sent_status__in=[3, 5]).order_by('-sent_datetime').first()
        if not phone_dialer:
            return JsonResponse({"message": 'Invalid dtmf event'}, status=400)
        # Check if the campaign_id has extension in it in dialplan
        # Get the dtmf field name
        dtmf_field = f"dtmf_{dtmf_response}"

        # Check if the DialPlan exists with the given campaign, extension and dtmf response
        dial_plan_exists = DialPlan.objects.filter(
            campaign=campaign,
            extension_id=extension,
            **{dtmf_field: F(dtmf_field)}
        ).exists()

        if not dial_plan_exists:
            return JsonResponse({"message": 'Invalid dtmf event'}, status=400)

        dial_id = phone_dialer.id
        print("dial_id : ", dial_id)
        # If call_id and extension already present in call_dtmf_status table, then update the dtmf_response 
        # else insert the new record
        call_dtmf_status = CallDtmfStatus.objects.filter(call_id=dial_id, extension=extension).first()
        print("call_dtmf_status : ", call_dtmf_status)
        if call_dtmf_status:
            call_dtmf_status.dtmf_response = dtmf_response
            call_dtmf_status.save()
            if user_id == 10006666 and (dtmf_response == '1' or dtmf_response == '2'):
                # Push call status to SabkiApp
                push_call_status(phone_dialer, 'accepted' if dtmf_response == '1' else 'rejected')
            return JsonResponse({'message': 'DTMF response updated successfully'}, status=201)
        else:
            call_dtmf_status = CallDtmfStatus(call_id=phone_dialer, extension=extension, dtmf_response=dtmf_response)
            call_dtmf_status.save()
            if user_id == 10006666 and (dtmf_response == '1' or dtmf_response == '2'):
                # Push call status to SabkiApp
                push_call_status(phone_dialer, 'accepted' if dtmf_response == '1' else 'rejected')
            return JsonResponse({'message': 'DTMF response saved successfully'}, status=201)
    else:
        return JsonResponse({"message": 'No event found'}, status=400)

    return JsonResponse({"message": 'Unexpected error occurred'}, status=500)






def reboot_active_host():
    active_hosts = UserHosts.objects.filter().values('host').distinct()
    for host in active_hosts:
        host = host['host']
        system_password = UserHosts.objects.get(host=host, status=1).system_password    

        # call the api {host}.sabkiapp.com/tunnel_status
        response = requests.get(f'https://{host}.sabkiapp.com/tunnel_status')

        # if the response is not 200, leave else call the reboot api
        if response.status_code != 200:
            continue

        # call the reboot api
        reboot_response = requests.post(f'https://{host}.sabkiapp.com/reboot', data={
            'host': host,'password': system_password
            })

        # check the reboot response
        if reboot_response.status_code != 200:
            print(f'Failed to reboot {host}')
        

# @api_view(['GET'])
# def trigger_dialer(request):
#     api_key = request.GET.get('api_key')
#     if api_key != settings.API_KEY_CRONJOB:
#         return JsonResponse({'status': "message", 'message': 'Invalid API key'}, status=400)

#     # TEMPORARILY DISABLED — if get_my_time() is less than 7am and greater than 10pm, return message
#     if get_mytime().hour < 7 or get_mytime().hour > 22:
#         # If get_my_time hr is 5 and min is 30, call the reboot function
#         if get_mytime().hour == 5 and get_mytime().minute == 30:
#             Thread(target=reboot_active_host).start()
#         return JsonResponse({'status': "message", 'message': 'Dialer is not allowed to run between 10pm and 7am'}, status=400)

        

#     Thread(target=get_all_active_hosts).start()
#     Thread(target=update_final_call_status).start()
#     Thread(target=sms_dialer_bulk).start()


#     return JsonResponse({'status': 'success'}, status=200)




# =================================
# ADDED CODE: LOGGING CONFIG (Absolute Path)
# =================================
LOG_FILE = '/tmp/dialer_debug.log' 
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# =================================

@api_view(['GET'])
def trigger_dialer(request):
    api_key = request.GET.get('api_key')
    
    # # =================================
    # # ADDED CODE: LOG REQUEST DATA
    # # =================================
    # t = get_mytime()
    # logging.info(f"API CALL RECEIVED - Key: {api_key[:5]}... Time: {t.hour}:{t.minute}")
    # # =================================

    if api_key != settings.API_KEY_CRONJOB:
        # # =================================
        # # ADDED CODE: LOG AUTH FAILURE
        # # =================================
        # logging.error(f"AUTH FAILED: Provided key does not match settings.API_KEY_CRONJOB")
        # # =================================
        return JsonResponse({'status': "message", 'message': 'Invalid API key'}, status=400)

    # TEMPORARILY DISABLED — if get_my_time() is less than 7am and greater than 10pm, return message
    if get_mytime().hour < 7 or get_mytime().hour >= 22:
        
        # # =================================
        # # ADDED CODE: LOG TIME BLOCK
        # # =================================
        # logging.warning(f"TIME BLOCK: Hour is {get_mytime().hour}. Allowed: 7-21.")
        # # =================================

        if get_mytime().hour == 5 and get_mytime().minute == 30:
            Thread(target=reboot_active_host).start()
        return JsonResponse({'status': "message", 'message': 'Dialer is not allowed to run between 10pm and 7am'}, status=400)

    Thread(target=get_all_active_hosts).start()
    Thread(target=update_final_call_status).start()
    Thread(target=sms_dialer_bulk).start()

    return JsonResponse({'status': 'success'}, status=200)