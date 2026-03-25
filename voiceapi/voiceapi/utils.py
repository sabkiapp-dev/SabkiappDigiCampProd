from boto3 import session
import os
from api.models.name_pronunciation import NamePronunciation
import requests
import imageio_ffmpeg as ffmpeg
from pydub import AudioSegment
import tempfile
import os
from datetime import datetime, timedelta


# ─── BUNDLE IMAGEIO‑FFMPEG FOR PYDUB ─────────────────────────────────────────
# get the ffmpeg executable that imageio‑ffmpeg provides
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
# tell pydub to use it for both conversion and probing
AudioSegment.converter = ffmpeg_path
AudioSegment.ffprobe   = ffmpeg_path
# ─────────────────────────────────────────────────────────────────────────

# DigitalOcean Spaces credentials
ACCESS_ID = 'DO002FER8TXVU8UJJFCV'
SECRET_KEY = '0q0zbXHjRiTvefg7vleBK5js5eC2b2+EzmiAGcIEHsc'
SPACE_NAME = 'sabkiapp'
REGION_NAME = 'sgp1'
ENDPOINT_URL = 'https://sgp1.digitaloceanspaces.com'

def upload_file(file_path, user_id):
    # Extract file name and extension from path
    file_name = os.path.basename(file_path)
    file_ext = os.path.splitext(file_path)[1]
    print(f"File name: {file_name}, File extension: {file_ext}")
    # Convert the audio file to the desired format if necessary
    if file_ext == '.mp3':
        # Convert MP3 to WAV
        wav_path = convert_mp3_to_wav(file_path)
        # Convert WAV to 8kHz
        output_path = convert_wav_to_8khz(wav_path, wav_path)
    elif file_ext == '.wav':
        # Convert WAV to 8kHz
        output_path = convert_wav_to_8khz(file_path, file_path)
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

    # Define the key (path in the space) for the file
    key = f"Asterisk/Audios/{user_id}/{os.path.basename(output_path)}"

    # Upload the file
    try:
        client.upload_file(output_path, SPACE_NAME, key, ExtraArgs={'ACL': 'public-read', 'ContentType': 'audio/mpeg'})
        # Construct the URL of the uploaded file
        file_url = f"{ENDPOINT_URL}/{SPACE_NAME}/{key}"
        return file_url
    except Exception as e:
        print(f"Error uploading file: {e}")
        return None
    

def convert_wav_to_8khz(input_file, output_file):
    # Load the input file
    audio = AudioSegment.from_wav(input_file)

    # Convert the audio to the desired format
    audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)

    # Save the output file
    audio.export(output_file, format='wav')

    # Return the path of the output file
    return output_file

def convert_mp3_to_wav(input_mp3_path):
    # Check if the input file exists
    if not os.path.exists(input_mp3_path):
        raise FileNotFoundError(f"The file {input_mp3_path} does not exist.")

    # Construct the output file path
    base, ext = os.path.splitext(input_mp3_path)
    output_wav_path = f"{base}.wav"

    # Load the MP3 file
    audio = AudioSegment.from_file(input_mp3_path)

    # Convert to WAV and save
    audio.export(output_wav_path, format="wav")

    print(f"Audio file has been converted and saved at {output_wav_path}")

    return output_wav_path



def generate_name_pronunciation(name):
    # ElevenLabs API setup
    url = "https://api.elevenlabs.io/v1/text-to-speech/wViXBPUzp2ZZixB1xQuM"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": "06f8c5ab70e431fc77ce02984e55060f"
    }
    data = {
        "text": name,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    # Send request to ElevenLabs API
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to generate audio: {response.status_code}")

    # Save the MP3 audio to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_mp3_file:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                temp_mp3_file.write(chunk)
        temp_mp3_file_path = temp_mp3_file.name

    # Convert MP3 to WAV
    base, _ = os.path.splitext(temp_mp3_file_path)
    output_wav_path = f"{base}.wav"
    audio = AudioSegment.from_file(temp_mp3_file_path)
    audio.export(output_wav_path, format="wav")

    # Clean up the temporary MP3 file
    os.remove(temp_mp3_file_path)

    return output_wav_path

def get_or_create_pronunciation(name):
    # Check if the name already exists in the database
    pronunciation_obj, created = NamePronunciation.objects.get_or_create(name=name)

    if created:
        # If the name is new, generate pronunciation and upload it
        try:
            wav_file = generate_name_pronunciation(name)
            pronunciation_url = upload_file(wav_file)
            pronunciation_obj.pronunciation_url = pronunciation_url
            pronunciation_obj.save()
        except Exception as e:
            # Handle exceptions (e.g., generation or upload failures)
            return {'error': str(e)}

    return {'url': pronunciation_obj.pronunciation_url}
