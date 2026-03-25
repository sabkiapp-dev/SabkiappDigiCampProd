import time
import logging
# logging.basicConfig(filename='machine_status.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework.response import Response
from django.http import JsonResponse
from ..models.sim_information import SimInformation
from ..models.user_hosts import UserHosts
import requests
import jwt
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from src.mytime import get_mytime
from datetime import timedelta
from django.forms.models import model_to_dict

def get_user_id_from_token(token):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        return payload.get('user_id')
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed('access_token expired')
    except IndexError:
        raise AuthenticationFailed('token malformed')




def merge_sim_information(machine_status):
    for status in machine_status:
        status["number_of_sims_waiting"] = 0
        status["number_of_sims_blocked"] = 0
        
        host = status['host']
        for port in status['port_data']:
            
            sim_imsi = port['sim_imsi']
            final_status = port['final_status']
            if(final_status == "No Signal"):
                print(f"Port {port['port']}: Changing signal from {port['signal']} to 0 due to No Signal status")
                port.update({"signal": "0"})
            if sim_imsi:
                sim_info_obj = SimInformation.objects.filter(host=host, sim_imsi=sim_imsi).first()
                if sim_info_obj:
                    today_block_status = sim_info_obj.today_block_status
                    # print("today_block_status : ", today_block_status)
                    last_call_time = sim_info_obj.last_call_time
                    if not last_call_time:
                        # create default last_call_time as datetime format
                        last_call_time = get_mytime()
                        sim_info_obj.last_call_time = last_call_time
                        sim_info_obj.save()
                    
                    last_call_date = sim_info_obj.last_call_time.strftime('%Y-%m-%d')
                    
                    if today_block_status != 0 and last_call_date != get_mytime().strftime('%Y-%m-%d'):
                        sim_info_obj.today_block_status = 0
                        sim_info_obj.save()
                    elif today_block_status > 4 and last_call_date == get_mytime().strftime('%Y-%m-%d'):
                        final_status = "Blocked"
                        if "number_of_sims_blocked" in status and "number_of_sims_ready" in status:
                            status["number_of_sims_ready"] = status["number_of_sims_ready"] - 1
                            status["number_of_sims_blocked"] = status["number_of_sims_blocked"] + 1

                    sim_info = model_to_dict(sim_info_obj)
                    sim_info['last_call_time'] = sim_info['last_call_time'].strftime('%Y-%m-%d %H:%M:%S')
                    sim_info['call_status_date'] = sim_info['call_status_date'].strftime('%Y-%m-%d')
                    # If last_call_date is not today, then reset the calls_made_today and call_time_today and update in database
                    if sim_info['call_status_date'] != get_mytime().strftime('%Y-%m-%d'):
                        sim_info['calls_made_today'] = 0
                        sim_info['call_time_today'] = 0
                        sim_info['call_status_date'] = get_mytime().strftime('%Y-%m-%d')
                        sim_info_obj.calls_made_today = 0
                        sim_info_obj.call_time_today = 0
                        sim_info_obj.call_status_date = get_mytime().strftime('%Y-%m-%d')
                        sim_info_obj.save()

                    # Check if last_call_time is within 10 seconds
                    call_after = sim_info_obj.call_after


                    time_difference = get_mytime() - sim_info_obj.last_call_time.replace(tzinfo=None)

                    final_status_changed = False
                    if time_difference <= timedelta(seconds=5) and final_status == "Ready":
                        final_status = "Busy"
                        final_status_changed = True

                    elif time_difference <= timedelta(seconds=call_after) and final_status == "Ready":
                        final_status = "Waiting"
                        final_status_changed = True

                    sim_info['final_status'] = final_status

                    if "number_of_sims_ready" in status and "number_of_sims_busy" in status and "number_of_sims_waiting" in status and final_status_changed:
                        status["number_of_sims_ready"] = status["number_of_sims_ready"] - 1
                        if final_status == "Busy":
                            status["number_of_sims_busy"] = status["number_of_sims_busy"] + 1
                        else:
                            status["number_of_sims_waiting"] = status["number_of_sims_waiting"] + 1

    
                else:
                    sim_info = {
                        "calls_made_total": 0,
                        "calls_made_today": 0,
                        "call_time_total": 0,
                        "call_time_today": 0,
                        "call_status_date": "2024-01-01",
                        "last_call_time": "2024-02-12 18:45:12"
                    }
                port.update(sim_info)
                port.update({"final_status": final_status})
            else:
                default_sim_info = {
                    "calls_made_total": 0,
                    "calls_made_today": 0,
                    "call_time_total": 0,
                    "call_time_today": 0,
                    "call_status_date": "2024-01-01",
                    "last_call_time": "2024-02-12 18:45:12"
                }
                port.update(default_sim_info)
    return machine_status

def fetch_machine_status(user_id, host_forcefully, port_forcefully, ussd_forcefully, sms=False):
    # Fetch the hosts and system passwords for the user
    if(not sms):
        user_hosts = UserHosts.objects.filter(user_id=user_id, status=1, host=host_forcefully).values('host', 'system_password')
    else:
        user_hosts = UserHosts.objects.filter(user_id=user_id, status=1, allow_sms=1).values('host', 'system_password')

    # Iterate over the hosts and make a request to the API for each one
    responses = []
    for user_host in user_hosts:
        host = user_host['host']
        system_password = user_host['system_password']
        try:
            if ussd_forcefully == "1" and host_forcefully == host:
                
                response = requests.get(f'https://{host}.sabkiapp.com/machine_status', params={'host': host, 'password': system_password, 'port_forcefully': port_forcefully, 'ussd_forcefully': ussd_forcefully}, timeout=10)
            else:    
                response = requests.get(f'https://{host}.sabkiapp.com/machine_status', params={'host': host, 'password': system_password}, timeout=10)
                
            response.raise_for_status()  # Raises a HTTPError if the response status code is 4xx or 5xx

            response_data = response.json()

            responses.append(response_data)
        except (requests.exceptions.HTTPError, requests.exceptions.RequestException, requests.exceptions.JSONDecodeError, requests.exceptions.Timeout):
            error_response = {
                "host": host,
                "machine_power_status": 0,
                "number_of_ports_with_no_sim": 0,
                "number_of_ports_with_no_signal": 0,
                "number_of_new_sims": 0,
                "number_of_sims_with_no_recharge": 0,
                "number_of_sims_ready": 0,
                "number_of_sims_busy": 0,
                "total_sms_balance": 0,
                "port_data": [],
                "message": "Error fetching machine status",
            }
            responses.append(error_response)
    if(not sms):
        responses = merge_sim_information(responses)
    return responses


def get_all_machine_status(request):
    host = request.GET.get('host')
    # If no host is provided, return an error
    if not host:
        return JsonResponse({"message": "host is required"}, status=400)

    port_forcefully = request.GET.get('port_forcefully')
    ussd_forcefully = request.GET.get('ussd_forcefully')
    
    # get boolean sms
    sms = request.GET.get('sms')

    if sms == "true":
        sms = True
    else:
        sms = False
    # Get the Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header:
        # Extract the token
        token = auth_header.split(' ')[1]
        try:
            user_id = get_user_id_from_token(token)
            # Validate the token
            jwt_auth_class = JWTAuthentication()
            validated_token = jwt_auth_class.get_validated_token(token)
            # Get the user associated with the token
            user = jwt_auth_class.get_user(validated_token)

            # Check if the user_id in the URL matches the user_id associated with the token
            if str(user.id) != user_id:
                return JsonResponse({"message": "Unauthorized"}, status=401)

            responses = fetch_machine_status(user_id, host, port_forcefully, ussd_forcefully, sms)
            if responses and not sms:
                response = responses[0]
            elif responses and sms:
                response = responses
            else:
                response = {}

            return JsonResponse(response, safe=False)
        except InvalidToken as e:
            return JsonResponse({"message": "Invalid token, error "+str(e)}, status=401)
        except AuthenticationFailed as e:
            return JsonResponse({"message": str(e)}, status=401)
    else:
        return JsonResponse({"message": "Authorization header is required"}, status=401)