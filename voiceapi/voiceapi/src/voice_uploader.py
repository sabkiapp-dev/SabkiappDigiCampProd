from boto3 import session
import os
from src.audio_utils import convert_mp3_to_wav, convert_wav_to_16khz

# DigitalOcean Spaces credentials
ACCESS_ID = 'DO002FER8TXVU8UJJFCV'
SECRET_KEY = '0q0zbXHjRiTvefg7vleBK5js5eC2b2+EzmiAGcIEHsc'
SPACE_NAME = 'sabkiapp'
REGION_NAME = 'sgp1'
ENDPOINT_URL = 'https://sgp1.digitaloceanspaces.com'

def upload_file(file_path, user_id=None, space_folder=None, word=None, voice_sample_gender=None):

    # Extract file name and extension from path
    file_name = os.path.basename(file_path)
    file_ext = os.path.splitext(file_path)[1]
    print(f"File name: {file_name}, File extension: {file_ext}")
    # Convert the audio file to the desired format if necessary
    if file_ext == '.mp3':
        # Convert MP3 to WAV
        print("Converting MP3 to WAV...")
        wav_path = convert_mp3_to_wav(file_path)
        # Convert WAV to 8kHz
        print("Converting WAV to 8kHz...")
        output_path = convert_wav_to_16khz(wav_path, wav_path)
        print("Converted WAV to 8kHz")
    elif file_ext == '.wav':
        # Convert WAV to 8kHz
        print("Converting WAV to 8kHz...")
        output_path = convert_wav_to_16khz(file_path, file_path)
        print("Converted WAV to 8kHz")
    else:
        print(f"Unsupported file format: {file_ext}, use only .mp3 or .wav")

        return None

    # Check if output_path is None
    if output_path is None:
        print("Error in audio conversion.")
        return None

    # Initiate session with DigitalOcean Spaces
    session_obj = session.Session()
    client = session_obj.client('s3',
                                region_name=REGION_NAME,
                                endpoint_url=ENDPOINT_URL,
                                aws_access_key_id=ACCESS_ID,
                                aws_secret_access_key=SECRET_KEY)
    
    print(f"Uploading file to {space_folder} folder...")

    # Define the key (path in the space) for the file
    if(space_folder == 'Pronunciations'):
        key = f"Asterisk/{space_folder}/{word}_{voice_sample_gender}.wav"
    elif (space_folder == 'Audios'):
        key = f"Asterisk/{space_folder}/{user_id}/{os.path.basename(output_path)}"

    print(f"Key: {key}")
    # Upload the file
    try:
        client.upload_file(output_path, SPACE_NAME, key, ExtraArgs={'ACL': 'public-read', 'ContentType': 'audio/mpeg'})
        # Construct the URL of the uploaded file
        file_url = f"{ENDPOINT_URL}/{SPACE_NAME}/{key}"
        # Delete the local file
        os.remove(output_path)
        print(f"File uploaded successfully: {file_url}")
        return file_url
    except Exception as e:
        print(f"Error uploading file: {e}")
        return None





