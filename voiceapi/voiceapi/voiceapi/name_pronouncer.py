import requests
import imageio_ffmpeg as ffmpeg
from pydub import AudioSegment
import os
import uuid



# ─── BUNDLE IMAGEIO‑FFMPEG FOR PYDUB ─────────────────────────────────────────
# get the ffmpeg executable that imageio‑ffmpeg provides
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
# tell pydub to use it for both conversion and probing
AudioSegment.converter = ffmpeg_path
AudioSegment.ffprobe   = ffmpeg_path
# ─────────────────────────────────────────────────────────────────────────

def generate_name_pronunciation(name):
    # ElevenLabs API setup
    url = "https://api.elevenlabs.io/v1/text-to-speech/ljjBXNaMeKXpTHnguGA1"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": "7fb3272b3262bd3d11c98e3c962667ce"
    }
    data = {
        "text": name,
        "model_id": "eleven_monolingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "style": 0.1,
            "similarity_boost": 1
        }
    }

    # Send request to ElevenLabs API
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to generate audio: {response.status_code}")

    # Save the MP3 audio to a file in the current directory
    temp_mp3_file_path = f"{uuid.uuid4()}.mp3"
    with open(temp_mp3_file_path, 'wb') as temp_mp3_file:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                temp_mp3_file.write(chunk)

    # Convert MP3 to WAV
    base, _ = os.path.splitext(temp_mp3_file_path)
    output_wav_path = f"{base}.wav"
    audio = AudioSegment.from_file(temp_mp3_file_path)
    audio.export(output_wav_path, format="wav")

    # Clean up the MP3 file
    os.remove(temp_mp3_file_path)

    return output_wav_path


if __name__ == '__main__':
    file_path = generate_name_pronunciation("गौरव")
    print(file_path)




    # Expected output: 'C:\Users\user\AppData\Local\Temp\tmp3x9x6x4w.wav