"""
Pipeline — Orchestrates audio flow between RTP and AI providers.

Two modes:
  Mode A (stt_llm_tts): Audio → STT → LLM → TTS → Audio
  Mode B (sts):         Audio → STS (end-to-end) → Audio

The pipeline reads PCM from RTP audio_queue, processes through the configured
provider chain, and sends response audio back via RTP.
"""

import asyncio
import logging
from typing import AsyncIterator

from providers.base import BaseSTT, BaseLLM, BaseTTS, BaseSTS
from rtp_handler import RTPProtocol, BYTES_PER_FRAME

log = logging.getLogger(__name__)


class Pipeline:
    """Audio processing pipeline with swappable providers."""

    def __init__(self, mode: str, rtp: RTPProtocol, **providers):
        self.mode = mode  # "stt_llm_tts" or "sts"
        self.rtp = rtp
        self.running = False

        if mode == "stt_llm_tts":
            self.stt: BaseSTT = providers["stt"]
            self.llm: BaseLLM = providers["llm"]
            self.tts: BaseTTS = providers["tts"]
        elif mode == "sts":
            self.sts: BaseSTS = providers["sts"]
        else:
            raise ValueError(f"Unknown pipeline mode: {mode}")

    async def start(self, system_prompt: str = ""):
        """Initialize all providers."""
        self.running = True
        if self.mode == "stt_llm_tts":
            await self.stt.start()
            await self.llm.start(system_prompt)
            await self.tts.start()
            log.info("Pipeline started: STT -> LLM -> TTS")
        else:
            await self.sts.start(system_prompt)
            log.info("Pipeline started: STS (end-to-end)")

    async def stop(self):
        """Shutdown all providers."""
        self.running = False
        if self.mode == "stt_llm_tts":
            await self.stt.stop()
            await self.llm.stop()
            await self.tts.stop()
        else:
            await self.sts.stop()
        log.info("Pipeline stopped")

    async def run(self):
        """Main processing loop — read from RTP, process, write back to RTP."""
        if self.mode == "sts":
            await self._run_sts()
        else:
            await self._run_stt_llm_tts()

    # --- Mode B: Speech-to-Speech ---

    async def _run_sts(self):
        """Direct audio-to-audio via STS provider."""
        # Run feed and playback concurrently
        await asyncio.gather(
            self._sts_feed_loop(),
            self._sts_playback_loop(),
        )

    async def _sts_feed_loop(self):
        """Read PCM from RTP queue → feed to STS."""
        while self.running:
            try:
                pcm = await asyncio.wait_for(
                    self.rtp.audio_queue.get(), timeout=0.1)
                await self.sts.feed_audio(pcm)
            except asyncio.TimeoutError:
                continue

    async def _sts_playback_loop(self):
        """Read response audio from STS → send via RTP."""
        async for pcm_chunk in self.sts.audio_responses():
            if not self.running:
                break
            self.rtp.send_audio(pcm_chunk)

    # --- Mode A: STT → LLM → TTS ---

    async def _run_stt_llm_tts(self):
        """Pipeline: collect speech → transcribe → generate → speak back."""
        # Run STT feed and transcription processing concurrently
        await asyncio.gather(
            self._stt_feed_loop(),
            self._transcription_loop(),
        )

    async def _stt_feed_loop(self):
        """Read PCM from RTP queue → feed to STT."""
        while self.running:
            try:
                pcm = await asyncio.wait_for(
                    self.rtp.audio_queue.get(), timeout=0.1)
                await self.stt.feed_audio(pcm)
            except asyncio.TimeoutError:
                continue

    async def _transcription_loop(self):
        """Read transcriptions from STT → LLM → TTS → RTP."""
        async for transcript in self.stt.transcriptions():
            if not self.running:
                break
            if not transcript.strip():
                continue

            log.info("User said: %s", transcript)

            # Stream LLM response through TTS and out to RTP
            llm_stream = self.llm.generate_stream(transcript)
            tts_stream = self.tts.synthesize_stream(llm_stream)

            async for pcm_chunk in tts_stream:
                if not self.running:
                    break
                self.rtp.send_audio(pcm_chunk)


def build_pipeline(config: dict, rtp: RTPProtocol) -> Pipeline:
    """Factory: build Pipeline from config.yaml dict."""
    mode = config.get("mode", "sts")

    if mode == "stt_llm_tts":
        stt = _load_stt(config.get("stt", {}))
        llm = _load_llm(config.get("llm", {}))
        tts = _load_tts(config.get("tts", {}))
        return Pipeline(mode, rtp, stt=stt, llm=llm, tts=tts)
    elif mode == "sts":
        sts = _load_sts(config.get("sts", {}))
        return Pipeline(mode, rtp, sts=sts)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def _load_stt(cfg: dict) -> BaseSTT:
    provider = cfg.get("provider", "deepgram")
    if provider == "deepgram":
        from providers.stt_deepgram import DeepgramSTT
        return DeepgramSTT(cfg)
    elif provider == "google":
        from providers.stt_google import GoogleSTT
        return GoogleSTT(cfg)
    elif provider == "whisper":
        from providers.stt_whisper import WhisperSTT
        return WhisperSTT(cfg)
    raise ValueError(f"Unknown STT provider: {provider}")


def _load_llm(cfg: dict) -> BaseLLM:
    provider = cfg.get("provider", "gemini")
    if provider == "gemini":
        from providers.llm_gemini import GeminiLLM
        return GeminiLLM(cfg)
    elif provider == "openai":
        from providers.llm_openai import OpenAILLM
        return OpenAILLM(cfg)
    elif provider == "ollama":
        from providers.llm_ollama import OllamaLLM
        return OllamaLLM(cfg)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _load_tts(cfg: dict) -> BaseTTS:
    provider = cfg.get("provider", "elevenlabs")
    if provider == "elevenlabs":
        from providers.tts_elevenlabs import ElevenLabsTTS
        return ElevenLabsTTS(cfg)
    elif provider == "google":
        from providers.tts_google import GoogleTTS
        return GoogleTTS(cfg)
    elif provider == "openai":
        from providers.tts_openai import OpenAITTS
        return OpenAITTS(cfg)
    raise ValueError(f"Unknown TTS provider: {provider}")


def _load_sts(cfg: dict) -> BaseSTS:
    provider = cfg.get("provider", "gemini_live")
    if provider == "gemini_live":
        from providers.sts_gemini_live import GeminiLiveSTS
        return GeminiLiveSTS(cfg)
    elif provider == "openai_realtime":
        from providers.sts_openai_realtime import OpenAIRealtimeSTS
        return OpenAIRealtimeSTS(cfg)
    raise ValueError(f"Unknown STS provider: {provider}")
