import os
import imageio_ffmpeg as ffmpeg
from pydub import AudioSegment
import soundfile as sf
import numpy as np
import librosa

# ─── BUNDLE IMAGEIO‑FFMPEG FOR PYDUB ─────────────────────────────────────────
# get the ffmpeg executable that imageio‑ffmpeg provides
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
# tell pydub to use it for both conversion and probing
AudioSegment.converter = ffmpeg_path
AudioSegment.ffprobe   = ffmpeg_path
# ─────────────────────────────────────────────────────────────────────────

def convert_wav_to_16khz(input_file, output_file):
    # Load the input file
    data, samplerate = sf.read(input_file)
    print(f"Data shape: {data.shape}, Samplerate: {samplerate}")
    # Check if the audio is stereo (2 channels)
    if len(data.shape) > 1 and data.shape[1] == 2:
        print("Converting stereo to mono...")
        data = np.mean(data, axis=1)  # convert to mono

    print(f"Data shape: {data.shape}")
    # Resample the audio to 16kHz
    try:
        

        data_16khz = librosa.resample(data, orig_sr=samplerate, target_sr=16000)
    except Exception as e:
        print(f"Error resampling audio: {e}")
        return None
    except:
        print("An unexpected error occurred")
        return None
    print(f"Data shape after resampling: {data_16khz.shape}")
    # Save the output file
    sf.write(output_file, data_16khz, 16000, subtype='PCM_16')
    print(f"Audio file has been converted and saved at {output_file}")
    # Rename the output file to .wav16
    base, ext = os.path.splitext(output_file)
    new_output_file = f"{base}.wav16"
    os.rename(output_file, new_output_file)
    print(f"Audio file has been converted and saved at {new_output_file}")
    # Return the path of the new output file
    return new_output_file



def convert_mp3_to_wav(input_mp3_path):
    # Check if the input file exists
    if not os.path.exists(input_mp3_path):
        raise FileNotFoundError(f"The file {input_mp3_path} does not exist.")

    # Construct the output file path
    base, ext = os.path.splitext(input_mp3_path)
    output_wav_path = f"{base}.wav"
    output_16khz_path = f"{base}_16khz.wav"

    # Load the MP3 file
    audio = AudioSegment.from_file(input_mp3_path)

    # Convert audio to WAV and save
    audio.export(output_wav_path, format="wav")

    print(f"Audio file has been converted and saved at {output_wav_path}")

    # Convert to 16kHz mono
    audio_16khz = audio.set_frame_rate(16000).set_channels(1)

    # Convert to numpy array
    samples = np.array(audio_16khz.get_array_of_samples())

    # Save as 16-bit PCM WAV
    sf.write(output_16khz_path, samples, 16000, subtype='PCM_16')

    # Rename the output file to .wav16
    base, ext = os.path.splitext(output_16khz_path)
    new_output_file = f"{base}.wav16"
    os.rename(output_16khz_path, new_output_file)


    print(f"Audio file has been converted to 16kHz 16-bit PCM and saved at {output_16khz_path}")

    return output_wav_path, output_16khz_path

if __name__ == "__main__":
    # Test convert_wav_to_16khz
    input_mp3 = 'edit audio 03.mp3'
    base_name = os.path.splitext(input_mp3)[0]  # Remove the extension
    output_wav = f'{base_name}.wav'  # Append new extension

    try:
        output_wav_path, output_16khz_path = convert_mp3_to_wav(input_mp3)
        print(f'Successfully converted {input_mp3} to WAV file at {output_wav_path}')
    except Exception as e:
        print(f'Failed to convert {input_mp3} to WAV file. Error: {e}')