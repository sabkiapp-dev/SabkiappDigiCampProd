import datetime
import random
import time  # Import the time module for introducing a delay
import subprocess
import json
import re
import os
import zipfile
import shutil
import string
import pickle
import threading
import configparser

from django.http import JsonResponse, HttpResponse, HttpResponseNotFound, HttpResponseForbidden, FileResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.shortcuts import render
from rest_framework.decorators import api_view
from django.conf import settings
from django.core.files.storage import default_storage
from urllib.parse import unquote, urlencode

import jwt as pyjwt
from src.jwt_auth import verify_token, extract_bearer_token, require_jwt

# From custom modules
from src.sms_counter import SmsCounter
from src.final_status import FinalStatus
from src.gateway_status import GatewayStatus
from src.ussd_cache import UssdCache
from src.decode_message import extract_validity_and_phone_vodafone, extract_phone_airtel, extract_validity_airtel
from src.update_database import update_everywhere
from src.send_ussd import request_ussd, send_ussd
# from src.utils import read_api_credentials  # removed: JWT auth replaced password auth
from src.sms_sender import SmsSender
from src.disk_space import get_disk_space_info
from src.audio_manager import download_and_save_audio
from src.mytime import get_mytime
from src.call_maker import make_call as make_call_
from src.dialplan_creator import check_capmaign_exists, create_dialplan, check_or_download_audio
from src.voice_generator import generate_voice_female, generate_voice_male
from src.voip_client import client as voip_client



API_CREDENTIALS = getattr(settings, 'API_CREDENTIALS', {})



def get_disk_space_info_view(request):
    # Call the function from utils.py
    result = get_disk_space_info()

    # Return the information as JSON response
    return JsonResponse(result)

@csrf_exempt
def upload_audio(request):
    try:
        # Retrieve raw JSON data from the request body
        data = json.loads(request.body.decode('utf-8'))

        # Ensure the directory for saving audio files exists
        save_directory = '/home/pi/Documents/campaign-audios'  # Change this to your desired directory
        if not os.path.exists(save_directory):
            os.makedirs(save_directory)



        # Call the helper function to download and save audio file
        file_path = download_and_save_audio(data, save_directory)

        if file_path:
            # You can do further processing with the file_path
            # For now, let's return a JsonResponse with the downloaded file path
            return JsonResponse({'file_path': file_path})
        else:
            return JsonResponse({'error': 'Invalid payload or download failed'})
    except json.JSONDecodeError as e:
        return JsonResponse({'error': 'Invalid JSON format in the request body'})




@csrf_exempt
@api_view(['GET'])
def start_ssh_tunnel(request):
    return JsonResponse({'status': 'disabled', 'message': 'Tunnel management removed -- cloudflared handles connectivity'})

@csrf_exempt
@api_view(['GET'])
def start_eroll_tunnels(request):
    return JsonResponse({'status': 'disabled', 'message': 'Tunnel management removed -- cloudflared handles connectivity'})


def get_number_of_ports_with_no_sim(data_list):
    return sum(sim['final_status'] == 'No SIM' for sim in data_list)

def get_number_of_ports_with_no_signal(data_list):
    return sum(sim['final_status'] == 'No Signal' for sim in data_list)

def get_number_of_new_sims(data_list):
    return sum(sim['final_status'] == 'New SIM' for sim in data_list)

def get_number_of_sims_with_no_recharge(data_list):
    return sum(sim['final_status'] == 'Rechargeless' for sim in data_list)

def get_number_of_sims_ready(data_list):
    return sum(sim['final_status'] == 'Ready' for sim in data_list)

def get_number_of_sims_busy(data_list):
    return sum(sim['final_status'] == 'Busy' for sim in data_list)


def get_port_data(data_list):
    # Assuming you want to include the entire data_list for each port
    return data_list


@require_jwt
@api_view(['GET'])
def gateway_status(request):
    host = request.jwt_payload.get('host')
    ussd_forcefully = int(request.query_params.get('ussd_forcefully', 0))
    port_forcefully = int(request.query_params.get('port_forcefully', 1))


    # Continue processing if credentials are valid
    status = GatewayStatus(ussd_forcefully, port_forcefully)
    if not status:
        print("noesponse_ from siminformation, may be host not active")
        return HttpResponse("No response from siminformation, may be host not active", status=400)
    data_list = status.data_list
    final_data = {
        "host":host,
        "machine_power_status": status.is_machine_on,
        "number_of_ports_with_no_sim": get_number_of_ports_with_no_sim(data_list),
        "number_of_ports_with_no_signal": get_number_of_ports_with_no_signal(data_list),
        "number_of_new_sims": get_number_of_new_sims(data_list),
        "number_of_sims_with_no_recharge": get_number_of_sims_with_no_recharge(data_list),
        "number_of_sims_ready": get_number_of_sims_ready(data_list),
        "number_of_sims_busy": get_number_of_sims_busy(data_list),
        "total_sms_balance": status.total_sms_balance,
        "port_data": get_port_data(data_list),

    }

    # Return the final data as JSON response
    return JsonResponse(final_data)

def get_gateway_status():
        """Get gateway status by calling GatewayStatus directly (no HTTP self-call)."""
        status = GatewayStatus(0, 1)
        if not status:
            return {}
        host = settings.API_CREDENTIALS.get('HOST', '')
        return {
            "host": host,
            "machine_power_status": status.is_machine_on,
            "number_of_ports_with_no_sim": get_number_of_ports_with_no_sim(status.data_list),
            "number_of_ports_with_no_signal": get_number_of_ports_with_no_signal(status.data_list),
            "number_of_new_sims": get_number_of_new_sims(status.data_list),
            "number_of_sims_with_no_recharge": get_number_of_sims_with_no_recharge(status.data_list),
            "number_of_sims_ready": get_number_of_sims_ready(status.data_list),
            "number_of_sims_busy": get_number_of_sims_busy(status.data_list),
            "total_sms_balance": status.total_sms_balance,
            "port_data": get_port_data(status.data_list),
        }

@require_jwt
@api_view(['POST'])
@csrf_exempt
def send_sms(request):
    # Extract parameters from the request data
    host = request.jwt_payload.get('host')
    data = request.data.get('data')  # Get list of combined data

    responses = []
    gateway_status_response = get_gateway_status()
    if not gateway_status_response:
        return JsonResponse({"error": "Failed to get gateway status"}, status=500)

    for item in data:
        phone_no = item.get('phone_no')
        message = item.get('message')
        port = int(item.get('port'))
        sms_dialer_id = item.get('sms_dialer_id')  # Extract the sms_dialer_id

        # Find the port data for the given port
        port_data = next((pd for pd in gateway_status_response.get('port_data', []) if pd.get('port') == port), None)
        if port_data is None:
            print(f"No data found for port {port}")
            continue

        sim_imsi = port_data.get('sim_imsi')
        sms_balance = port_data.get('sms_balance')
        if not phone_no or not message or not port:
            responses.append(({"message": "Invalid data", "phone_no":phone_no, "sms_dialer_id": sms_dialer_id}, 421))
            continue
        # check if phone_number is indian and 10 digits and starts with greater than 5
        if not re.match(r'^[6-9]\d{9}$', phone_no):
            responses.append(({"message": "Invalid phone number", "phone_no":phone_no, "sms_dialer_id": sms_dialer_id}, 422))
            continue
        
        # char len of message should be less than 5
        sms_count = SmsCounter.count(message)['sms_count']
        if sms_count > 5:
            responses.append(({"message": "Message length exceeded", "phone_no":phone_no, "sms_dialer_id": sms_dialer_id}, 423))
            continue
        
        sms_balance = sms_balance - sms_count
        if sms_balance < 0:
            responses.append(({"message": "Insufficient SMS balance", "phone_no":phone_no, "sms_dialer_id": sms_dialer_id}, 424))
            continue
        
        # Perform your SMS sending logic here using the provided phone and message
        sms_sender = SmsSender(phone_no, message, port, sim_imsi, sms_balance)
        response = sms_sender.send_sms()

        if response == 1:
            responses.append(({"message": "SMS sent successfully", "phone_no": phone_no, "sms_dialer_id": sms_dialer_id}, 200))

    return JsonResponse(responses, safe=False)



def display_pickle_data():
    filename = 'ussd_cache.pkl'
    try:
        with open(filename, 'rb') as file:
            data = pickle.load(file)
            print("**Data in ussd_cache.pkl:")
            print(data)
    except FileNotFoundError:
        print(f"File '{filename}' not found.")


@csrf_exempt
def receive_sms(request):
    if request.method == 'GET':
        # Extract query parameters from the request URL
        port = request.GET.get('port')
        message_raw = request.GET.get('msg')
        message = unquote(request.GET.get('msg'))
        time_value = request.GET.get('time')
        status_value = request.GET.get('status')
        code_value = request.GET.get('code')
        provided_id = request.GET.get('id')

        # Print the extracted information
        print(f"Received message: {message}")
        print(f"message_raw : {message_raw}")
        print(f"Port: {port}")
        print(f"Time: {time_value}")
        print(f"Status: {status_value}")
        print(f"Code: {code_value}")
        print(f"Provided ID: {provided_id}")

        ussd_cache = UssdCache(port)
        
        operator = ussd_cache.get_operator()
        request_type = ussd_cache.get_request_type()
        sim_imsi = ussd_cache.get_sim_imsi()
        if(operator == 'vodafone'):
            validity, phone_no = extract_validity_and_phone_vodafone(message)
            
            # print("sim_imsi to send to update_everywhere : ", sim_imsi)
            update_everywhere(sim_imsi, port, phone_no, validity, request_type, operator)
            print("Validity : {}, Phone : {}".format(validity, phone_no))
        if(operator == 'airtel' and request_type == 'phone'):
            phone_no = extract_phone_airtel(message)
            validity = ""
            print(f"--Sim Imsi : {sim_imsi}, Port : {port}, Operator : {operator}, request : {request_type}, phone_no : {phone_no}, message : {message}")
            update_everywhere(sim_imsi, port, phone_no, validity, request_type, operator)
            request_ussd(port, sim_imsi, operator, 'validity')

        if(operator == 'airtel' and request_type == 'validity'):
            validity = extract_validity_airtel(message)
            update_everywhere(sim_imsi, port, "", validity, request_type, operator)
            

        # print("Received ", str(ussd_cache))
        # display_pickle_data()

        # Return a simple HTTP response (optional)
        return HttpResponse("Received GET request successfully.")
    else:
        return HttpResponse("Method not allowed", status=405)
    


@csrf_exempt
def sms_response(request):
    if request.method == 'GET':
        # Extract query parameters from the request URL
        phone_no = request.GET.get('phone_no')
        port_no = request.GET.get('port_no')
        port_name = request.GET.get('port_name')
        message_raw = request.GET.get('msg')
        message = unquote(request.GET.get('msg'))
        time_value = request.GET.get('time')
        imsi = request.GET.get('imsi')
        status_value = request.GET.get('status')
        user_defined = request.GET.get('User Defined')

        # Print the extracted information
        print(f"Received message: {message}")
        print(f"message_raw: {message_raw}")
        print(f"Phone No: {phone_no}")
        print(f"Port No: {port_no}")
        print(f"Port Name: {port_name}")
        print(f"Time: {time_value}")
        print(f"IMSI: {imsi}")
        print(f"Status: {status_value}")
        print(f"User Defined: {user_defined}")

        # Return a simple HTTP response
        return HttpResponse("Received GET request successfully.")
    else:
        return HttpResponse("Method not allowed", status=405)


# A method get_tunnel_status just returs true always
def get_tunnel_status(request):
    from src.mytime import get_mytime

    return JsonResponse({'status': True, 'time':get_mytime()})

import json
import logging
import threading
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# --- LOGGER SETUP ---
# Define the exact path in your project root
LOG_FILE_PATH = '/home/pi/Documents/32GSMgatewayServer/dtmf_call_maker.log'

# Create a custom logger for this view
logger = logging.getLogger('dtmf_call_maker')
logger.setLevel(logging.INFO)

# Create file handler and set formatter
file_handler = logging.FileHandler(LOG_FILE_PATH)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Prevent adding multiple handlers if the module reloads
if not logger.handlers:
    logger.addHandler(file_handler)
# --------------------

@require_jwt
@csrf_exempt
def make_call(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Log the entire incoming JSON payload
            logger.info(f"INCOMING REQUEST: {json.dumps(data)}")
        except json.JSONDecodeError:
            response_data = {'error': 'Invalid JSON body'}
            logger.error(f"RESPONSE 400: {response_data}")
            return JsonResponse(response_data, status=400)

        host = request.jwt_payload.get('host')
        system_password = data.get('system_password', '')
        user_id = data.get('user_id')
        port = int(data.get('port')) + 1000
        phone_number = data.get('phone_number')
        campaign_id = data.get('campaign_id')
        name = data.get('name')
        name_spell = int(data.get('name_spell', 0))

        male_voice_path = None
        female_voice_path = None
        
        if name_spell == 0 or name == '':
            # Do nothing
            pass
        elif name_spell == 1:
            male_voice_path = generate_voice_male(name, phone_number, user_id, host, system_password)
        elif name_spell == 2:
            female_voice_path = generate_voice_female(name, phone_number)
        elif name_spell == 3:
            female_voice_path = generate_voice_female(name, phone_number)
            male_voice_path = generate_voice_male(name, phone_number, user_id, host, system_password)

        # Start a new thread that runs the make_call_ function
        threading.Thread(target=make_call_, args=(phone_number, campaign_id, port, user_id)).start()
        
        response_data = {'status': 'OK'}
        logger.info(f"RESPONSE 200: {response_data} | Thread started for {phone_number}")
        return JsonResponse(response_data)
        
    else:
        response_data = {'error': 'Invalid Method'}
        logger.warning(f"RESPONSE 405: {response_data} | Method attempted: {request.method}")
        return JsonResponse(response_data, status=405)


@require_jwt
@csrf_exempt
def change_host_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        host = request.jwt_payload.get('host')
        new_system_password = data.get('new_system_password')

        # Update settings.py
        settings_file_path = os.path.join(settings.BASE_DIR, 'gsm_gateway', 'settings.py')
        with open(settings_file_path, 'r') as file:
            lines = file.readlines()

        with open(settings_file_path, 'w') as file:
            for line in lines:
                if "SYSTEM_PASSWORD" in line:
                    file.write(f"    'SYSTEM_PASSWORD': '{new_system_password}',\n")
                else:
                    file.write(line)

        # Update dtmf.sh
        dtmf_file_path = '/home/pi/Documents/32GSMgatewayServer/dtmf.sh'

        # Read the content of dtmf.sh
        with open(dtmf_file_path, 'r') as file:
            dtmf_content = file.read()

        # Define the pattern to match SYSTEM_PASSWORD="randompassword"
        pattern = r'SYSTEM_PASSWORD="([^"]+)"'

        # Replace the matched pattern with the new password
        updated_dtmf_content = re.sub(pattern, r'SYSTEM_PASSWORD="{}"'.format(new_system_password), dtmf_content)

        # Write the updated content back to dtmf.sh
        with open(dtmf_file_path, 'w') as file:
            file.write(updated_dtmf_content)

        return JsonResponse({'message': 'Host and password changed successfully'})

    else:
        return JsonResponse({'error': 'Invalid Method'}, status=405)




@require_jwt
@csrf_exempt
def save_dial_plan(request):
    print("[save_dial_plan] Method:", request.method)
    if request.method == 'POST':
        print("[save_dial_plan] Parsing request body...")
        all_data = json.loads(request.body)
        print("[save_dial_plan] Data:", all_data)
        host = request.jwt_payload.get('host')
        campaign = all_data.get('campaign')
        print(f"[save_dial_plan] Host={host}, Campaign={campaign}")
        print("[save_dial_plan] JWT Authentication succeeded")

        print(f"[save_dial_plan] Checking existence for campaign {campaign}...")
        dialplan_exists = check_capmaign_exists(campaign)
        print("[save_dial_plan] dialplan_exists =", dialplan_exists)
        if(dialplan_exists):
            print("[save_dial_plan] Dialplan exists; verifying audio...")
            check_or_download_audio(all_data)
            print("[save_dial_plan] Returning 'Dialplan Exists'")
            return JsonResponse({'message': 'Dialplan Exists'}, status=200)
        else:
            print("[save_dial_plan] Dialplan not found; processing audio and creation...")
            check_or_download_audio(all_data)
            print("[save_dial_plan] Creating dialplan...")
            create_dialplan(all_data)
            print("[save_dial_plan] Returning 'Dialplan Saved'")
            return JsonResponse({'message': 'Dialplan Saved'}, status=200)
    else:
        print(f"[save_dial_plan] Invalid method: {request.method}")
        return JsonResponse({'error': 'Invalid Method'}, status=405)
    


def check_data(port, sim_imsi, message):
    filename = 'ussd_cache.pkl'
    while True:
        try:
            with open(filename, 'rb') as file:
                data = pickle.load(file)
        except FileNotFoundError:
            data = {}

        found = False
        for key, value in data.items():
            if 'sim_imsi' in value and value['sim_imsi'] == sim_imsi:
                date_time_str = value['date_time']
                date_time_obj = datetime.datetime.strptime(date_time_str, "%Y-%m-%dT%H:%M:%S.%f")
                if (datetime.datetime.now() - date_time_obj).total_seconds() <= 30:
                    found = True
                    break

        if not found:
            print(f"Success: No data found for sim_imsi {port, sim_imsi, message}")
            send_ussd(port, sim_imsi, message)
            break
        else:
            print(f"Data for sim_imsi {sim_imsi} found, waiting for 30 seconds before retrying")
            time.sleep(30)



@require_jwt
@csrf_exempt
def reboot(request):
    if request.method == 'POST':

        # Execute the shell script to reboot the system
        try:
            script_path = '/home/pi/Documents/32GSMgatewayServer/gateway/src/reboot.sh'
            subprocess.run(['sh', script_path])
            return JsonResponse({'success': 'System reboot initiated successfully'})
        except Exception as e:
            return JsonResponse({'error': f'Failed to reboot system: {str(e)}'}, status=500)
    else:
        # Handle other request types (GET, PUT, DELETE, etc.)
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)

import magic

@require_jwt
@csrf_exempt
def update_code(request):
    if request.method == 'POST':
        host = request.jwt_payload.get('host')
        system_password = request.GET.get('system_password', '')
        print("JWT Authentication verified")

        # Get the zip file URL from the URL
        zip_file_url = request.GET.get('zip_file_url')

        # Create temp dir
        temp_dir = '/home/pi/Documents/temp'
        temp_dir_gateway = '/home/pi/Documents/temp/32GSMgatewayServer'


        os.makedirs(temp_dir, exist_ok=True)

        response = requests.get(zip_file_url, stream=True)
        if response.status_code == 200:
            file_name = os.path.join(temp_dir, '32GSMgatewayServer.zip')
            with open(file_name, 'wb') as out_file:
                for chunk in response.iter_content(chunk_size=128):
                    out_file.write(chunk)
            print("Zip file downloaded successfully")
        # if True:
        #     file_name = os.path.join(temp_dir, '32GSMgatewayServer.zip')
            # Check the file type of the downloaded file
            file_type = magic.from_file(file_name)
            print(f"File type: {file_type}")

            # Extract the zip file
            try:
                with zipfile.ZipFile(file_name, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir_gateway)
                print("Zip file extracted successfully")

                # Change password and host in settings.py
                settings_file_path = os.path.join(temp_dir_gateway, 'gateway/gsm_gateway/settings.py')
                with open(settings_file_path, 'r') as file:
                    lines = file.readlines()
                
                print("settings_file_path : ", settings_file_path)
                print("len lines ", len(lines))
                # Find the lines with the host and system password and replace them
                for i, line in enumerate(lines):
                    if "SYSTEM_PASSWORD" in line:
                        lines[i] = f"    'SYSTEM_PASSWORD': '{system_password}',\n"
                    elif "'HOST':" in line:
                        lines[i] = f"    'HOST': '{host}',\n"
                    elif "UPDATED_TIME" in line:
                        # Get the current time plus 5 hours and 30 minutes
                        updated_time = get_mytime()
                        # Format the updated time as a string
                        updated_time_str = updated_time.strftime("%Y-%m-%d %H:%M:%S")
                        lines[i] = f'UPDATED_TIME = "{updated_time_str}"\n'

                

                # Write the modified lines back to the file
                with open(settings_file_path, 'w') as file:
                    file.writelines(lines)
                    
                # Run update.sh script
                script_path = '/home/pi/Documents/32GSMgatewayServer/update.sh'
                subprocess.run(['sh', script_path])

                return JsonResponse({"message": "Code updated successfully"}, status=200)
            except zipfile.BadZipFile:
                print("Error: The downloaded file is not a zip file")
                return JsonResponse({"error": "The downloaded file is not a zip file"}, status=500)
        else:
            print(f"Error: Failed to download the zip file (status code: {response.status_code})")
            return JsonResponse({"error": f"Failed to download the zip file (status code: {response.status_code})"}, status=500)

@require_jwt
def zip_entire_code(request):
    host = request.jwt_payload.get('host')
    system_password = settings.API_CREDENTIALS.get('SYSTEM_PASSWORD', '')
    print("JWT Authentication verified")

    # Define the source and destination paths
    gateway_path = '/home/pi/Documents/32GSMgatewayServer'
    temp_path_root = '/home/pi/Documents/temp'
    temp_path = '/home/pi/Documents/temp/32GSMgatewayServer'  # Update the path as needed

    # Create the temp directory if it does not exist
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    print("temp directory created")

    zip_file_path = '/home/pi/Documents/32GSMgatewayServer.zip'  # Update the path
    # Copy the entire directory to a new temporary host
    shutil.copytree(gateway_path, temp_path, symlinks=True)

    print("Code copied successfully")
    # Update host and system password in settings.py to empty strings
    settings_file_path = os.path.join(temp_path, 'gateway/gsm_gateway/settings.py')

    print("settings_file_path : ", settings_file_path)
    with open(settings_file_path, 'r') as file:
        lines = file.readlines()

    # Find the lines with the host and system password and replace them
    for i, line in enumerate(lines):
        if "SYSTEM_PASSWORD" in line:
            lines[i] = f"    'SYSTEM_PASSWORD': '1',\n"
        elif "'HOST':" in line:
            lines[i] = f"    'HOST': '1',\n"
        elif "COPY_TIME" in line:
            # Get the current time plus 5 hours and 30 minutes
            updated_time = get_mytime()
            # Format the updated time as a string
            updated_time_str = updated_time.strftime("%Y-%m-%d %H:%M:%S")
            lines[i] = f'COPY_TIME = "{updated_time_str}"\n'

    # Write the modified lines back to the file
    with open(settings_file_path, 'w') as file:
        file.writelines(lines)

    # Create the directory if it does not exist
    os.makedirs(os.path.dirname(zip_file_path), exist_ok=True)

    # Create a zip file of the temporary directory
    with zipfile.ZipFile(zip_file_path, 'w') as zip_ref:
        for root, _, files in os.walk(temp_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_ref.write(file_path, os.path.relpath(file_path, temp_path))
    print("Code zipped successfully")

    # Delete the temporary directory
    shutil.rmtree(temp_path_root)

    # Generate a random password
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

    # Store the password in a pickle file
    with open('password.pkl', 'wb') as f:
        pickle.dump(password, f)

    # Create the URL with the password as a query parameter
    url = request.build_absolute_uri('/Documents/32GSMgatewayServer.zip')
    url += '?' + urlencode({'password': password})

    # Return the URL
    return JsonResponse({
        'url': url,
    })




def download_zip(request):
    file_path = '/home/pi/Documents/32GSMgatewayServer.zip'
    password_file_path = 'password.pkl'

    # Get the password from the URL
    url_password = request.GET.get('password')

    # Load the password from the pickle file
    with open(password_file_path, 'rb') as f:
        real_password = pickle.load(f)

    # Check if the passwords match
    if url_password != real_password:
        return HttpResponseForbidden('<h1>Invalid password</h1>')
    
    print("password verified")

    # Check if the file exists
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), content_type='application/zip')
    else:
        return HttpResponseNotFound('<h1>File not found</h1>')


@csrf_exempt
@api_view(['GET'])
def gsm_info_view(request):
    try:
        data = voip_client.get_gsminfo()
        return JsonResponse(data)
    except Exception as e:
        print(f"Error in gsm_info_view: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@api_view(["POST"])
def authenticate(request):
    token = extract_bearer_token(request)
    if not token:
        return JsonResponse({"authenticated": False, "error": "Missing Authorization header"}, status=401)
    try:
        payload = verify_token(token)
        return JsonResponse({"authenticated": True, "payload": payload})
    except pyjwt.ExpiredSignatureError:
        return JsonResponse({"authenticated": False, "error": "Token expired"}, status=401)
    except pyjwt.InvalidTokenError as e:
        return JsonResponse({"authenticated": False, "error": str(e)}, status=401)
