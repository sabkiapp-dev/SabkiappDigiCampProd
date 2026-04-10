#!/usr/bin/env python3
import sys
from pydub.generators import Sine

def generate_test_audio(output_path, duration_ms=1000):
    """
    Generates a 1-second test audio file (sine wave at 440 Hz) and saves it as an MP3.
    
    :param output_path: Path to store the generated test audio file.
    :param duration_ms: Duration of the generated audio in milliseconds.
    """
    # Generate a sine wave of 440Hz (A4 note)
    sine_wave = Sine(440).to_audio_segment(duration=duration_ms)
    sine_wave.export(output_path, format="mp3")
    print(f"Test audio generated at: {output_path}")

def main():
    if len(sys.argv) < 2:
        print("Usage: {} output_file".format(sys.argv[0]))
        sys.exit(1)
    
    output_path = sys.argv[1]
    generate_test_audio(output_path)

if __name__ == "__main__":
    main()