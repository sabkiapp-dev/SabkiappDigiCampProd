from api.models.contacts import Contacts
import requests
import json
from  src.phone_encrypter import encrypt
import voiceapi.settings as settings
import threading
import requests



import concurrent.futures
import time


def process_phone_number(phone_number, user_id, names, not_found_numbers):
    # Check if the phone number is in the contacts with status 1 for user_id
    contact = Contacts.objects.filter(user_id=user_id, phone_number=phone_number, status=1).first()
    if contact:
        names[phone_number] = contact.name
        # If name is empty, append not found numbers
        if not contact.name:
            not_found_numbers.append(phone_number) 
    else:
        not_found_numbers.append(phone_number)
    return names, not_found_numbers

def get_name(user_id, phone_numbers):
    try:
        not_found_numbers = []
        names = {}
        start_time = time.time()
        phone_numbers_processed = 0

        # Use a ThreadPoolExecutor to process the phone numbers in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(process_phone_number, phone_numbers, [user_id]*len(phone_numbers), [names]*len(phone_numbers), [not_found_numbers]*len(phone_numbers))

        # Update names and not_found_numbers with the results from the threads
        for result in results:
            names, not_found_numbers = result

        phone_numbers_processed += len(phone_numbers)
        elapsed_time = time.time() - start_time
        if elapsed_time >= 60:  # 60 seconds = 1 minute
            print(f"Processed {phone_numbers_processed} phone numbers in the last minute.")
            start_time = time.time()
            phone_numbers_processed = 0

        if not_found_numbers:
            # Call bankjaal api to get the names
            response = requests.post(
                settings.sabkiapp_base_url+'/get_names',
                headers={'Content-Type': 'application/json'},
                data=json.dumps({
                    "user_id": encrypt(str(user_id)),
                    "phone_no": not_found_numbers
                })
            )
            if response.status_code == 200:
                print("item : ", response.json())
                try:
                    names_from_bankjaal = {item['phoneNumber']: item['name'] for item in response.json() if 'phoneNumber' in item and 'name' in item}
                    names.update(names_from_bankjaal)
                except Exception as e:
                    print("Error occurred while parsing the response:", str(e))
                    
        return names
    except Exception as e:
        print("Error occurred:", str(e))
        return {}

def get_user_id(phone_no):
    en_phone_no = encrypt(phone_no)
    headers = {'Content-Type': 'application/json'}
    data = {"phone_no": str(en_phone_no)}
    url = settings.sabkiapp_base_url+'/get_userid'
    print("url : ", url)
    response = requests.post(url, headers=headers, data=json.dumps(data))
    # print the request data and response
    if response.status_code == 200:
        user_data = response.json()
        if 'userId' in user_data and user_data['userId'] not in (None, 'null'):
            return user_data['userId']

    return None




def store_misscall_on_sabkiapp(phone_number, management_id, operator, user_id, past=None, past_datetime=None):
    def make_api_call(phone_number, management_id, operator):
        if not past or not past_datetime:
            url = f"{settings.sabkiapp_base_url}/misscalls?phone_number={phone_number}&management_id={management_id}&password={settings.sabkiapp_misscall_password}&operator={operator}&user_id={user_id}"
        else:
            url = f"{settings.sabkiapp_base_url}/misscalls?phone_number={phone_number}&management_id={management_id}&password={settings.sabkiapp_misscall_password}&operator={operator}&user_id={user_id}&past={past}&past_datetime={past_datetime}"
        response = requests.get(url)

    # Create a thread that calls the API
    thread = threading.Thread(target=make_api_call, args=(phone_number, management_id, operator))
    thread.start()

    # Return a response
    return True