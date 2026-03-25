"""Utility to convert MP3 -> 16-bit, 8 kHz, mono WAV.

The resulting file gets the same base name with `.wav16` extension.
Relies on pydub with the bundled `ffmpeg` binary from imageio-ffmpeg so that
no system-wide ffmpeg install is required.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydub import AudioSegment
import imageio_ffmpeg as ffmpeg

# ---------------------------------------------------------------------------
# Configure pydub so that it uses imageio-ffmpeg's static binary. This makes it
# work out-of-the-box on most deployments even if ffmpeg is not installed in
# the system path.
# ---------------------------------------------------------------------------
ffmpeg_bin = ffmpeg.get_ffmpeg_exe()
AudioSegment.converter = ffmpeg_bin  # type: ignore[attr-defined]
AudioSegment.ffprobe = ffmpeg_bin    # type: ignore[attr-defined]


def mp3_to_wav16(mp3_path: str | os.PathLike) -> str:
    """Convert *mp3_path* to 16-bit, 8 kHz, mono WAV and return new file path.

    The converted file is written alongside the original, with a `.wav16`
    extension replacing `.mp3` (or appended if the original extension differs).
    """
    mp3_path = os.fspath(mp3_path)
    if not os.path.exists(mp3_path):
        raise FileNotFoundError(mp3_path)

    base, _ = os.path.splitext(mp3_path)
    out_path = base + ".wav16"

    # Load and convert
    audio = AudioSegment.from_file(mp3_path)
    mono_8k = audio.set_frame_rate(16000).set_channels(1)

    # Export with 16-bit PCM encoding
    mono_8k.export(out_path, format="wav", parameters=["-acodec", "pcm_s16le"])

    return out_path
