from django.http import JsonResponse
from rest_framework.decorators import api_view
from ..models.users import Users
from ..models.user_hosts import UserHosts
from ..models.name_pronunciation import NamePronunciation
from src.voice_uploader import upload_file
import os
from pydub import AudioSegment
import imageio_ffmpeg as ffmpeg
from src.mytime import get_mytime
from gtts import gTTS
import io
from google.cloud import texttospeech

# ─── BUNDLE IMAGEIO‑FFMPEG FOR PYDUB ───────────────────────────────────────
# get the ffmpeg executable that imageio‑ffmpeg provides
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
# tell pydub to use it for both conversion and probing
AudioSegment.converter = ffmpeg_path
AudioSegment.ffprobe   = ffmpeg_path
# ─────────────────────────────────────────────────────────────────────────

def generate_name_pronunciation(name):
    # Create a client
    client = texttospeech.TextToSpeechClient.from_service_account_json('../sabkiapp_google.json')

    # Set the text input to be synthesized
    text_input = texttospeech.SynthesisInput(text=name)

    # Set the voice configuration
    voice = texttospeech.VoiceSelectionParams(
        language_code='hi-IN',
        name='hi-IN-Standard-B',
    )

    # Set the audio configuration
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        effects_profile_id=['headphone-class-device'],
        pitch=0, 
        speaking_rate=0.85,
    )

    # Synthesize the speech
    response = client.synthesize_speech(
        input=text_input, voice=voice, audio_config=audio_config
    )

    # Save the audio to a temporary MP3 file
    temp_mp3_file_path = f"{name}_male.mp3"
    with io.open(temp_mp3_file_path, 'wb') as out:
        out.write(response.audio_content)

    # Convert MP3 to WAV
    wav_path = temp_mp3_file_path.replace(".mp3", ".wav")
    audio = AudioSegment.from_file(temp_mp3_file_path)
    audio.export(wav_path, format="wav")
    # delete the mp3 file
    os.remove(temp_mp3_file_path)

    return wav_path

@api_view(['GET'])
def get_pronunciation(request):
    # Extract name from query parameters
    name = request.query_params.get('name')
    host = request.query_params.get('host')
    system_password = request.query_params.get('system_password')
    user_id          = request.query_params.get('user_id')
    # name should be less than 50 characters else return with error
    if len(name) > 50:
        return JsonResponse({"message": 'Name should be less than 50 characters'}, status=400)
    name = name.lower()
    # Verify if the host and system_password are valid and for the user
    try:
        UserHosts.objects.get(host=host, system_password=system_password, user_id=user_id, status=1)
    except UserHosts.DoesNotExist:
        return JsonResponse({"message": 'Host not matching with user_id or password not correct'}, status=400)

    try:
        _ = NamePronunciation.objects.get(name=name)
        print("NamePronunciation.objects.get(name=name) : ",_)
    except NamePronunciation.DoesNotExist:
        # If the name does not exist, generate the pronunciation and save it to the database
        file_path = generate_name_pronunciation(name)
        print("file_path : ",file_path)
        #upload_file(file_path, user_id=None, space_folder=None, word=None, voice_sample_gender=None):
        file_url = upload_file(file_path, None, 'Pronunciations', name, voice_sample_gender='male')
        print("file_url : ",file_url)
        if(not file_url):
            return JsonResponse({"message": 'Pronunciation could not be generated'}, status=500)
        

        try:
            if file_path:
                # Retrieve the user
                try:
                    user = Users.objects.get(id=user_id)
                except Users.DoesNotExist:
                    print(f"User with id {user_id} does not exist.")
                    return

                print("create name_pronunciation")
                NamePronunciation.objects.create(name=name, user=user)
                print("created name_pronunciation")
        except Exception as e:
            print("Error during name pronunciation creation: ", e)

        else:
            return JsonResponse({"message": 'Pronunciation could not be generated'}, status=500)


    if not name:
        return JsonResponse({"message": 'Name is required'}, status=400)

    pronunciation_url = f"https://sabkiapp.sgp1.cdn.digitaloceanspaces.com/Asterisk/Pronunciations/{name}_male.wav"



    # If the name exists, return the pronunciation URL
    return JsonResponse({'name': name, 'pronunciation_url': pronunciation_url})
