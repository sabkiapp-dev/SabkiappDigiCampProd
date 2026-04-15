import requests
import tempfile
import os
from api.models.name_pronunciation import NamePronunciation
import imageio_ffmpeg as ffmpeg
from pydub import AudioSegment
from src.voice_uploader import upload_file
from digicamp_server.mytime import get_mytime
import sys
sys.path.append('/usr/bin/ffmpeg')

# ─── BUNDLE IMAGEIO‑FFMPEG FOR PYDUB ─────────────────────────────────────────
# get the ffmpeg executable that imageio‑ffmpeg provides
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
# tell pydub to use it for both conversion and probing
AudioSegment.converter = ffmpeg_path
AudioSegment.ffprobe   = ffmpeg_path

def generate_name_pronunciation(name):
    print("Time for calling the function ", name, get_mytime())
    voice_ids = {
        'male':'wViXBPUzp2ZZixB1xQuM', 
        'female': 'S402tyB4EnjynGKAPwc5'
    }
    output_paths = []
    querystring = {"output_format":"ulaw_8000"}
    for voice_gender, voice_id in voice_ids.items():
        # ElevenLabs API setup
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
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
        response = requests.post(url, json=data, headers=headers, params=querystring)
        if response.status_code != 200:
            raise Exception(f"Failed to generate audio: {response.status_code}")

        # Save the MP3 audio to a temporary file
        temp_dir = tempfile.gettempdir()
        temp_mp3_file_path = os.path.join(temp_dir, f"{name}_{voice_gender}.mp3")
        with open(temp_mp3_file_path, 'wb') as temp_mp3_file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    temp_mp3_file.write(chunk)

        # Convert MP3 to WAV
        base, _ = os.path.splitext(temp_mp3_file_path)
        output_wav_path = f"{base}.wav"
        audio = AudioSegment.from_file(temp_mp3_file_path)
        audio.export(output_wav_path, format="wav")

        # Clean up the temporary MP3 file
        os.remove(temp_mp3_file_path)
        output_paths.append({voice_gender:output_wav_path})

    return output_paths
