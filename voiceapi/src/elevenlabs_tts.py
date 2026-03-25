from pathlib import Path
import hashlib
from typing import Dict, Tuple
from elevenlabs.client import ElevenLabs
from src.audio_converter import mp3_to_wav16

_CTX = {
    "name":    ("नमस्कार, ", ",जी,।"),
    "channel": ("यह कॉल आपको सबकी ऐप Platform के ", ",चैनल की ओर से"),
    "surveyor":("चैनल की ओर से ", " द्वारा किया गया है।"),
}

class VerificationCallTTS:
    """
    Thin wrapper around ElevenLabs that returns the absolute path
    of the freshly generated MP3 file. **No caching** on server side.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str,
        output_dir: str | Path = "./tts_out",
        seed: int | None = 12345,
    ) -> None:
        self.client = ElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        self.voice_settings = {
            "stability": 0.8,
            "similarity_boost": 0.8,
            "style": 0.2,
            "use_speaker_boost": True,
        }

    # ------------------------------------------------------------------ #
    def _hash(self, txt: str, length: int = 10) -> str:
        return hashlib.sha1(txt.encode()).hexdigest()[:length]

    def _filename(self, segment_type: str, text: str) -> Path:
        return self.output_dir / f"{segment_type}_{self._hash(text)}.mp3"

    # ------------------------------------------------------------------ #
    def generate(self, segment_type: str, text: str, prev: str, nxt: str) -> Path:
        """
        segment_type ∈ {"name", "channel", "surveyor"}
        Returns absolute **Path** to MP3.
        """
        chunks = self.client.text_to_speech.convert(
            voice_id=self.voice_id,
            text=text,
            model_id=self.model_id,
            output_format="mp3_44100_128",
            voice_settings=self.voice_settings,
            seed=self.seed,
            previous_text=prev,
            next_text=nxt,
        )
        mp3_path = self._filename(segment_type, text)
        mp3_path.write_bytes(b"".join(chunks))
        wav16_path = mp3_to_wav16(str(mp3_path))
        return Path(wav16_path)
