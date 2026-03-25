import os
import requests

def download_and_save_audio(data, save_directory):
    try:
        audio_id = data.get('audio_id')
        audio_url = data.get('audio_url')
        print(f"audio_id : {audio_id}, audio_url : {audio_url}")

        if not audio_id or not audio_url:
            # Return None if required data is not present
            return None

        response = requests.get(audio_url)
        response.raise_for_status()  # Check if the request was successful

        # Extract the filename from the URL and include the audio_id
        filename = os.path.join(save_directory, f"{audio_id}_{os.path.basename(audio_url)}")

        # Save the audio file to the local directory
        with open(filename, 'wb') as file:
            file.write(response.content)

        return filename
    except requests.exceptions.RequestException as e:
        # Handle exceptions, log, or ignore based on your requirements
        print(f"Error downloading {audio_url}: {e}")
        return None