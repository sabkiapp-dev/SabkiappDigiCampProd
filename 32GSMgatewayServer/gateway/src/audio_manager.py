import os
import requests

def download_and_save_audio(data, save_directory):
    try:
        audio_id = data.get('audio_id')
        audio_url = data.get('audio_url')
        print(f"audio_id : {audio_id}, audio_url : {audio_url}")

        if not audio_id or not audio_url:
            return None

        response = requests.get(audio_url)
        response.raise_for_status()

        filename = os.path.join(save_directory, f"{audio_id}_{os.path.basename(audio_url)}")

        with open(filename, 'wb') as file:
            file.write(response.content)

        return filename
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {audio_url}: {e}")
        return None