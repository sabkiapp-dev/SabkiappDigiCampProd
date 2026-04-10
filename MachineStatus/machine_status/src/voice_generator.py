import os
import shutil
from gtts import gTTS
from pydub import AudioSegment
import requests
from django.conf import settings





name_directory = "/var/lib/asterisk/sounds/en/names"
main_directory = "/var/lib/asterisk/sounds/en"

def generate_voice_female(name, phone_number):
    filename = f"{name}_female.wav"
    name_filepath = os.path.join(name_directory, filename)
    main_filepath = os.path.join(main_directory, f"{phone_number}_2.wav")

    try:
        if not os.path.exists(name_filepath):
            os.makedirs(name_directory, exist_ok=True)
            tts = gTTS(text=name, lang='en-us')
            tts.save(name_filepath)
            sound = AudioSegment.from_mp3(name_filepath)
            sound = sound.set_frame_rate(8000)
            sound.export(name_filepath, format="wav")

        shutil.copy2(name_filepath, main_filepath)
        return main_filepath

    except Exception as e:
        print(f"Error generating female voice: {e}")
        return None

def generate_voice_male(name, phone_number, user_id, host, system_password):
    filename = f"{name}_male.wav16"
    name_filepath = os.path.join(name_directory, filename)
    main_filepath = os.path.join(main_directory, f"{phone_number}_1.wav16")

    try:
        if not os.path.exists(name_filepath):
            os.makedirs(name_directory, exist_ok=True)
            url = f"{settings.BASE_URL}/get_pronunciation?host={host}&system_password={system_password}&user_id={user_id}&name={name}"
            response = requests.get(url).json()
            pronunciation_url = response["pronunciation_url"]

            with requests.get(pronunciation_url, stream=True) as r:
                r.raise_for_status()
                with open(name_filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

        print(f"Copying file from {name_filepath} to {main_filepath}")
        shutil.copy2(name_filepath, main_filepath)
        return main_filepath

    except Exception as e:
        print(f"Error generating male voice: {e}")
        return None

if __name__ == "__main__":
    name = "Gopal"
    phone_number = "9934445076"
    user_id = "10000002"
    host = "host"
    system_password = "password"
    female_voice_path = generate_voice_female(name, phone_number)
    print("female_voice_path:", female_voice_path)
    male_voice_path = generate_voice_male(name, phone_number, user_id, host, system_password)   
    print("male_voice_path:", male_voice_path)