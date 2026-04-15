#!/usr/bin/env python3
import os
import sys
import argparse
import imageio_ffmpeg as ffmpeg
from pydub import AudioSegment

# Grab the ffmpeg executable that imageio-ffmpeg downloaded
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
# Tell pydub to use it for both conversion and probing
AudioSegment.converter = ffmpeg_path
AudioSegment.ffprobe = ffmpeg_path

def convert_to_wav(input_file, output_file):
    """
    Converts an audio file to WAV format.
    
    :param input_file: Path to the input audio file.
    :param output_file: Path to store the output WAV file.
    :return: True if conversion was successful, False otherwise.
    """
    try:
        # Load the audio file
        audio = AudioSegment.from_file(input_file)
        # Export the audio as a WAV file
        audio.export(output_file, format="wav")
        return True
    except Exception as e:
        print(f"Error during conversion: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Convert an audio file to WAV format using pydub and ffmpeg"
    )
    parser.add_argument("input", help="Path to the input audio file")
    parser.add_argument(
        "output",
        nargs="?",
        help="Path for the output WAV file. If not provided, the input file basename will be used with a .wav extension."
    )
    args = parser.parse_args()

    input_file = args.input
    if not os.path.exists(input_file):
        print(f"Input file '{input_file}' does not exist.")
        sys.exit(1)

    output_file = args.output or f"{os.path.splitext(input_file)[0]}.wav"
    print(f"Converting '{input_file}' to '{output_file}'...")

    if convert_to_wav(input_file, output_file):
        print("Conversion successful!")
    else:
        print("Conversion failed.")

if __name__ == "__main__":
    main()