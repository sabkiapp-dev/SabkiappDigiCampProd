"""
Provider Base Classes — Abstract interfaces for STT, LLM, TTS, and STS.

All audio is 16-bit signed linear PCM, 16kHz, mono, little-endian (slin16).
This matches ExternalMedia format directly — no resampling needed for most providers.

Providers that need different sample rates (e.g., OpenAI Realtime @ 24kHz)
handle resampling internally.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseSTT(ABC):
    """Speech-to-Text: stream audio chunks → yield text segments.

    Audio input: raw PCM bytes (slin16, 16kHz, 16-bit LE mono)
    Text output: partial/final transcription segments
    """

    @abstractmethod
    async def start(self):
        """Initialize connection to STT provider."""
        ...

    @abstractmethod
    async def stop(self):
        """Close connection."""
        ...

    @abstractmethod
    async def feed_audio(self, pcm_chunk: bytes):
        """Feed a chunk of PCM audio to the STT engine."""
        ...

    @abstractmethod
    async def transcriptions(self) -> AsyncIterator[str]:
        """Yield transcribed text segments as they become available.

        Yields partial results for responsiveness, then final result.
        """
        ...


class BaseLLM(ABC):
    """Large Language Model: text in → streaming text out.

    Maintains conversation context across turns.
    """

    @abstractmethod
    async def start(self, system_prompt: str = ""):
        """Initialize with system prompt."""
        ...

    @abstractmethod
    async def stop(self):
        """Close connection."""
        ...

    @abstractmethod
    async def generate_stream(self, text: str) -> AsyncIterator[str]:
        """Stream LLM response token by token.

        Args:
            text: user's transcribed speech
        Yields:
            text chunks suitable for TTS (sentence fragments)
        """
        ...


class BaseTTS(ABC):
    """Text-to-Speech: stream text → yield audio chunks.

    Text input: sentence fragments from LLM
    Audio output: raw PCM bytes (slin16, 16kHz, 16-bit LE mono)

    Provider must handle conversion to slin16 if its native format differs.
    """

    @abstractmethod
    async def start(self):
        """Initialize connection to TTS provider."""
        ...

    @abstractmethod
    async def stop(self):
        """Close connection."""
        ...

    @abstractmethod
    async def synthesize_stream(self, text_chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Convert streaming text to streaming audio.

        Args:
            text_chunks: async iterator of text fragments
        Yields:
            PCM audio chunks (slin16 format, ~20ms per chunk ideal)
        """
        ...


class BaseSTS(ABC):
    """Speech-to-Speech: bidirectional audio streaming (bypasses STT+LLM+TTS).

    Used for end-to-end models like Gemini Live API or OpenAI Realtime API.
    Audio format: raw PCM bytes (slin16, 16kHz, 16-bit LE mono)

    Provider handles any internal resampling.
    """

    @abstractmethod
    async def start(self, system_prompt: str = ""):
        """Initialize bidirectional session."""
        ...

    @abstractmethod
    async def stop(self):
        """Close session."""
        ...

    @abstractmethod
    async def feed_audio(self, pcm_chunk: bytes):
        """Feed caller's audio to the STS model."""
        ...

    @abstractmethod
    async def audio_responses(self) -> AsyncIterator[bytes]:
        """Yield AI response audio chunks as they're generated.

        Yields:
            PCM audio chunks (slin16 format)
        """
        ...
