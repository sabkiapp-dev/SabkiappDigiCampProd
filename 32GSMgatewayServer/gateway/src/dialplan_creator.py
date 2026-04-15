import os
import requests
import subprocess

def check_capmaign_exists(campaign):
    with open('/home/pi/Documents/32GSMgatewayServer/asterisk_dialplan.conf', 'r') as file:  # Path to your extensions.conf file
        for line in file:
            if line.strip() == f'[{campaign}]':
                return True
    return False


def check_or_download_audio(all_data):
    no_key_voice = all_data['no_key_voice']
    wrong_key_voice = all_data['wrong_key_voice']
    data = all_data['data']

    voices = [{'id': no_key_voice}, {'id': wrong_key_voice}] + [item['main_voice_id'] for item in data if item['main_voice_id'] is not None] + [item['option_voice_id'] for item in data if item['option_voice_id'] is not None]

    present_audios = []
    downloaded_audios = []

    # Check for present audios before downloading any new ones
    for voice in voices:
        file_path = f"/var/lib/asterisk/sounds/en/{voice['id']}.wav16"
        if os.path.exists(file_path):
            present_audios.append(file_path)
    print("Present audios: ", present_audios)
    

    # Download audios
    for voice in voices:
        file_path = f"/var/lib/asterisk/sounds/en/{voice['id']}.wav16"
        if not os.path.exists(file_path) and 'path' in voice:
            try:
                response = requests.get(voice['path'])
                response.raise_for_status()
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                downloaded_audios.append(file_path)
            except Exception as e:
                print(f"Failed to download {voice['path']}: {e}")


def create_dialplan(all_data):
    data = all_data.get("data")
    campaign = all_data.get("campaign")
    
    # Check if dialplan already exists
    if check_capmaign_exists(campaign):
        print(f"Dialplan for campaign {campaign} already exists. Skipping creation.")
        return
        
    no_key_voice = all_data.get("no_key_voice")
    no_key_voice_id = no_key_voice.get("id") if no_key_voice is not None else None
    wrong_key_voice = all_data.get("wrong_key_voice") 
    wrong_key_voice_id = wrong_key_voice.get("id") if wrong_key_voice is not None else None
    timeout = all_data.get("timeout")
    sorted_data = sorted(data, key=lambda item: item['extension_id'])
    min_extension_id = sorted_data[0]['extension_id'] if sorted_data else None

    # Create a dictionary mapping ids to extension_ids
    id_to_extension = {item['id']: item['extension_id'] for item in data}

    try:
        with open('/home/pi/Documents/32GSMgatewayServer/asterisk_dialplan.conf', 'a') as file:  # Path to your extensions.conf file
            
            # FIX 1: Use ARG instead of CALLERID so it grabs the real dialed number, not the dongle's caller ID
            dialplan = f"""
[{campaign}]
exten => s,1,Verbose(1, "Call is answered ${{ARG1}}")
 same => n,Set(PHONE=${{ARG2}})
 same => n,Set(CALLERID_NUM=${{ARG3}})
 same => n,Set(USER_ID=${{ARG4}})
 same => n,Set(DIALPLAN=${{ARG5}})
 same => n, Set(TIMEOUT(absolute)={timeout})
 same => n, SYSTEM(/home/pi/Documents/32GSMgatewayServer/dtmf.sh answered ${{PHONE}} ${{CALLERID_NUM}} ${{USER_ID}} ${{DIALPLAN}} &)
 same => n, Playback(initial_wait)
 same => n, GoTo({campaign}-{min_extension_id},s,1)
            """
            file.write(dialplan)
            # Find the id of no_key_voice and wrong_key_voice

            for item in sorted_data:
                extension_id = item['extension_id']
                main_voice_id = item['main_voice_id']['id'] if item['main_voice_id'] is not None else None
                option_voice_id = item['option_voice_id']['id'] if item['option_voice_id'] is not None else None
                
                if item['sms_after'] is not None and item['template_id'] is not None:
                    send_sms_api = f"same => n, System(/home/pi/Documents/32GSMgatewayServer/dtmf.sh send_sms ${{PHONE}} ${{CALLERID_NUM}} ${{USER_ID}} ${{DIALPLAN}} {item['template_id']['id']} &)"
                
                if main_voice_id:
                    main_voice_template = f"same => n, Playback({main_voice_id})"
                    if item['sms_after'] == -1 and send_sms_api is not None:
                        main_voice_template = f"{send_sms_api}\n "+main_voice_template
                else:
                    main_voice_template = ""
                
                
                name_spell = item['name_spell'] if item['name_spell'] is not None else 0
        
                name_voice = None
                if name_spell == 1 or name_spell == 2:
                    name_voice = f"same => n, Background(${{PHONE}}_{name_spell})"
                    print("name_voice: ", name_voice)
                    main_voice_template += f"\n {name_voice}"
             

                continue_to_template = "" 

                # If continue_to is not None, directly go to the next extension and do not wait for dtmf
                if item['continue_to'] is not None:
                    continue_to_id = item['continue_to']
                    continue_to_extension = id_to_extension.get(continue_to_id) if continue_to_id is not None else None
                    if continue_to_extension is not None:
                        continue_to_template = f"same => n, Goto({campaign}-{continue_to_extension},s,1)" 
                        if option_voice_id:
                            option_voice_template = f"""same => n, Playback({option_voice_id})"""
                            option_voice_template += "\n "+continue_to_template
                            if item['sms_after'] == -2 and send_sms_api is not None:
                                option_voice_template = f"{send_sms_api}\n "+option_voice_template
                        
                        else:
                            option_voice_template = continue_to_template
                    print("option_voice_template: ", option_voice_template, "option_voice_id: ", option_voice_id, "extension : ", extension_id, "continue_to_id: ", continue_to_id, "continue_to_extension: ", continue_to_extension)

                else:
                    if item['continue_to'] is None and option_voice_id is not None:
                        option_voice_template = f"""same => n, Background({option_voice_id})\n same => n, Background(wait)"""
                        if no_key_voice_id is not None:
                            option_voice_template += f"""\n same => n, Playback({no_key_voice_id})"""
                        option_voice_template += f"""\n same => n, Background({option_voice_id})\n same => n, Background(wait)"""
                        print("option_voice_id2: ", option_voice_id, "extension : ", extension_id)
                        print("option_voice_template : ", option_voice_template)
                        if item['sms_after'] == -2 and send_sms_api is not None:
                            option_voice_template = f"{send_sms_api}\n "+option_voice_template
                    else:
                        option_voice_template = """same => n, Verbose(1, "Option Voice not available")"""
                
                # FIX 2: Removed duplicate completed script here
                dialplan = f"""
[{campaign}-{extension_id}]
exten => s,1,Verbose(1, "Started Extension {extension_id} of campaign {campaign}")
 same => n, set(current_extension={extension_id})
 {main_voice_template}
 {option_voice_template}
 same => n, Hangup()
"""

                # If continue_to is None, run for dtmf
                if item['continue_to'] is None and option_voice_id is not None:
                    
                    for dtmf in list(range(1, 10)) + [0]:  # This will iterate over the numbers 1 to 9 and then 0
                        new_extension_id = item[f'dtmf_{dtmf}']  # Get the new_extension from dtmf

                        # Get the extension_id corresponding to new_extension_id
                        new_extension = id_to_extension.get(new_extension_id) if new_extension_id is not None else None

                        if new_extension is not None or new_extension_id == 0:
                            dialplan += f"""
exten => {dtmf},1,Verbose(1, "Current Extension is ${{current_extension}}")
 same => n, System(/home/pi/Documents/32GSMgatewayServer/dtmf.sh dtmf ${{PHONE}} ${{CALLERID_NUM}} ${{USER_ID}} ${{DIALPLAN}} ${{current_extension}} ${{EXTEN}} &)"""
                            if new_extension_id != 0:
                                dialplan += f"""
 same => n, Goto({campaign}-{new_extension},s,1)"""
                        else:
                            dialplan += f"""
exten => {dtmf},1,Verbose(1, "Current Extension is ${{current_extension}}")"""
                            if wrong_key_voice_id is not None:
                                dialplan += f"""\n same => n, Playback({wrong_key_voice_id})"""
                            dialplan += f"\n same => n, Goto({campaign}-{extension_id},s,1)"   

                        if new_extension_id == 0:
                            # FIX 3: Removed duplicate completed script here
                            dialplan += "\n same => n, Hangup()\n"
                        else:
                            dialplan += "\n"
                file.write(dialplan)
        password = '123'  # Replace with your password
        command = 'asterisk -rx dialplan reload'
        args = ['sudo', '-S'] + command.split(' ', 2)
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        process.communicate(password.encode())
     
    except Exception as e:
        raise Exception("An error occurred while writing to the file: " + str(e))