#!/usr/bin/env python3
"""
AI Server — Runs on dev PC. WebSocket server that does STT → LLM → TTS.

Receives ulaw audio from RPi audio bridge, processes through:
  1. STT (faster-whisper, local GPU/CPU)
  2. LLM (Gemini API)
  3. TTS (piper-tts, local)

Sends ulaw audio response back to RPi.

Usage:
    python3 ai_server.py
    python3 ai_server.py --port 9090 --stt-model small --language hi
"""

import argparse
import asyncio
import audioop
import io
import json
import logging
import re
import socket
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("AI")


# ── STT: shared silence-detection mixin ───────────────────────────────────

class _STTBase:
    """Shared VAD/buffering logic. Subclasses implement _transcribe()."""

    def _init_vad(self):
        self._buffer = bytearray()
        self._silence_count = 0
        self._has_speech = False
        self.SILENCE_THRESHOLD = 800    # RMS threshold (ulaw noise floor ~588, speech >1000)
        self.SILENCE_FRAMES = 12000     # ~750ms at 16kHz — avoids cutting mid-sentence pauses
        self.MIN_SPEECH_BYTES = 3200    # ~100ms minimum speech

    def vad(self, pcm_16k: bytes) -> bytes | None:
        """VAD only — never blocks. Returns captured PCM when speech ends, else None."""
        samples = struct.unpack(f"<{len(pcm_16k)//2}h", pcm_16k)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5

        if rms > self.SILENCE_THRESHOLD:
            self._has_speech = True
            self._silence_count = 0
            self._buffer.extend(pcm_16k)
        elif self._has_speech:
            self._silence_count += len(samples)
            self._buffer.extend(pcm_16k)

            if self._silence_count >= self.SILENCE_FRAMES:
                if len(self._buffer) >= self.MIN_SPEECH_BYTES:
                    captured = bytes(self._buffer)
                    self._buffer.clear()
                    self._has_speech = False
                    self._silence_count = 0
                    return captured
                self._buffer.clear()
                self._has_speech = False
                self._silence_count = 0
        return None


# ── STT: faster-whisper (local) ────────────────────────────────────────────

class WhisperSTT(_STTBase):
    """Local STT using faster-whisper."""

    def __init__(self, model_size="base", language="hi", device="auto"):
        self.model_size = model_size
        self.language = language
        self.device = device
        self._model = None
        self._init_vad()

    def load(self):
        from faster_whisper import WhisperModel
        compute = "float16" if self.device == "cuda" else "int8"
        device = "cuda" if self.device in ("cuda", "auto") else "cpu"
        try:
            self._model = WhisperModel(self.model_size, device=device, compute_type=compute)
            log.info(f"STT loaded: faster-whisper {self.model_size} on {device}/{compute}")
        except Exception:
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            log.info(f"STT loaded: faster-whisper {self.model_size} on cpu/int8 (GPU fallback)")

    def _transcribe(self, pcm_data: bytes) -> str:
        import numpy as np
        audio = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
        t0 = time.time()
        segments, _ = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text for seg in segments).strip()
        elapsed = time.time() - t0
        if text:
            log.info(f"STT ({elapsed:.1f}s): \"{text}\"")
        return text


# ── STT: Sarvam AI (cloud API) ─────────────────────────────────────────────

class SarvamSTT(_STTBase):
    """Cloud STT using Sarvam AI saaras/saarika API."""

    def __init__(self, api_key, language="hi-IN", model="saaras:v3"):
        self.api_key = api_key
        self.language = language
        self.model = model
        self._init_vad()

    def load(self):
        log.info(f"STT loaded: Sarvam AI {self.model}, lang={self.language}")

    def _transcribe(self, pcm_data: bytes) -> str:
        import requests
        # Wrap raw 16kHz 16-bit mono PCM in a WAV container
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_data)
        wav_buf.seek(0)

        t0 = time.time()
        try:
            resp = requests.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": self.api_key},
                files={"file": ("audio.wav", wav_buf, "audio/wav")},
                data={"model": self.model, "language_code": self.language, "mode": "transcribe"},
                timeout=15,
            )
        except Exception as e:
            log.error(f"Sarvam STT request failed: {e}")
            return ""

        if resp.status_code != 200:
            log.error(f"Sarvam STT {resp.status_code}: {resp.text[:200]}")
            return ""

        elapsed = time.time() - t0
        result = resp.json()
        text = result.get("transcript", "").strip()
        if text:
            log.info(f"STT ({elapsed:.1f}s): \"{text}\"")
        else:
            log.info(f"STT ({elapsed:.1f}s): empty — raw={str(result)[:100]}")
        return text


# ── LLM: Gemini API ────────────────────────────────────────────────────────

class SarvamLLM:
    """Sarvam AI LLM via OpenAI-compatible chat completions API."""

    def __init__(self, api_key, model="sarvam-m", system_prompt=""):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.default_system_prompt = system_prompt  # reset target after task calls
        self._history = []

    def load(self):
        log.info(f"LLM loaded: Sarvam AI {self.model}")

    async def generate(self, text: str) -> str:
        """Non-streaming generate (fallback). Prefer stream_sentences() for low latency."""
        self._history.append({"role": "user", "content": text})
        messages = self._build_messages()
        loop = asyncio.get_event_loop()
        try:
            reply = await loop.run_in_executor(None, self._sync_generate, messages)
        except Exception:
            self._history.pop()
            raise
        if reply:
            self._history.append({"role": "assistant", "content": reply})
        return reply

    def _build_messages(self):
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self._history[-16:])
        return messages

    def stream_sentences(self, text: str, sentence_queue, loop, stop_event):
        """Blocking — run in executor. Streams LLM, pushes sentences into queue."""
        import requests
        # Snapshot history NOW — don't modify self._history until successful completion.
        # Prevents race condition: concurrent barge-in streams can each snapshot safely;
        # only the one that finishes without cancellation commits to history.
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(list(self._history)[-16:])  # snapshot, not a reference
        messages.append({"role": "user", "content": text})

        t0 = time.time()
        full_reply = ""
        buf = ""

        def push(s):
            s = s.strip()
            if len(s) > 2:
                asyncio.run_coroutine_threadsafe(sentence_queue.put(s), loop)

        try:
            resp = requests.post(
                "https://api.sarvam.ai/v1/chat/completions",
                headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages,
                      "reasoning_effort": None, "stream": True, "max_tokens": 100},
                stream=True, timeout=15,
            )
        except Exception as e:
            asyncio.run_coroutine_threadsafe(sentence_queue.put(None), loop)
            raise Exception(f"LLM request failed: {e}")

        if resp.status_code == 429:
            asyncio.run_coroutine_threadsafe(sentence_queue.put(None), loop)
            raise Exception(f"429 RESOURCE_EXHAUSTED")
        if resp.status_code not in (200, 201):
            asyncio.run_coroutine_threadsafe(sentence_queue.put(None), loop)
            raise Exception(f"{resp.status_code} {resp.text[:100]}")

        for raw in resp.iter_lines():
            if stop_event.is_set():
                break
            if not raw:
                continue
            line = raw.decode() if isinstance(raw, bytes) else raw
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                token = json.loads(data_str)["choices"][0]["delta"].get("content", "")
            except Exception:
                continue
            if not token:
                continue
            buf += token
            full_reply += token
            # Split on sentence boundaries (Hindi + Latin)
            while True:
                idx = -1
                for punct in ["।", ".", "!", "?"]:
                    p = buf.find(punct)
                    if p != -1 and (idx == -1 or p < idx):
                        idx = p
                if idx == -1:
                    break
                sentence = buf[:idx + 1]
                buf = buf[idx + 1:]
                push(sentence)

        if buf.strip() and not stop_event.is_set():
            push(buf)

        elapsed = time.time() - t0
        log.info(f"LLM ({elapsed:.1f}s): \"{full_reply[:80]}{'...' if len(full_reply)>80 else ''}\"")

        # Commit to history only if we got a full reply AND weren't cancelled.
        # A cancelled/empty turn is silently dropped — next turn builds from unchanged history.
        if full_reply and not stop_event.is_set():
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": full_reply})

        asyncio.run_coroutine_threadsafe(sentence_queue.put(None), loop)  # sentinel

    def _sync_generate(self, messages):
        import requests
        t0 = time.time()
        try:
            resp = requests.post(
                "https://api.sarvam.ai/v1/chat/completions",
                headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages,
                      "reasoning_effort": None, "max_tokens": 100},
                timeout=20,
            )
        except Exception as e:
            raise Exception(f"Sarvam LLM request failed: {e}")

        if resp.status_code == 429:
            raise Exception(f"429 RESOURCE_EXHAUSTED: {resp.text[:100]}")
        if resp.status_code == 503:
            raise Exception(f"503 UNAVAILABLE: {resp.text[:100]}")
        if resp.status_code != 200:
            raise Exception(f"{resp.status_code} {resp.text[:100]}")

        reply = resp.json()["choices"][0]["message"]["content"].strip()
        elapsed = time.time() - t0
        log.info(f"LLM ({elapsed:.1f}s): \"{reply[:80]}{'...' if len(reply)>80 else ''}\"")
        return reply


class GeminiLLM:
    """Gemini LLM via google-genai SDK."""

    def __init__(self, api_key, model="gemini-2.5-flash", system_prompt=""):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self._client = None
        self._history = []

    def load(self):
        from google import genai
        self._client = genai.Client(api_key=self.api_key)
        log.info(f"LLM loaded: {self.model}")

    async def generate(self, text: str) -> str:
        """Send text to Gemini, return full response."""
        from google.genai import types

        self._history.append({"role": "user", "parts": [{"text": text}]})

        contents = []
        if self.system_prompt:
            contents.append(types.Content(
                role="user", parts=[types.Part(text=f"System: {self.system_prompt}")]))
            contents.append(types.Content(
                role="model", parts=[types.Part(text="Understood. I'll follow those instructions.")]))

        for msg in self._history[-16:]:  # last 8 turns
            contents.append(types.Content(
                role=msg["role"],
                parts=[types.Part(text=p["text"]) for p in msg["parts"]],
            ))

        t0 = time.time()
        response = await self._client.aio.models.generate_content(
            model=self.model,
            contents=contents,
        )
        reply = response.text.strip()
        elapsed = time.time() - t0
        log.info(f"LLM ({elapsed:.1f}s): \"{reply[:80]}{'...' if len(reply)>80 else ''}\"")

        self._history.append({"role": "model", "parts": [{"text": reply}]})
        return reply


# ── TTS: piper-tts ──────────────────────────────────────────────────────────

class PiperTTS:
    """Local TTS using piper-tts. Returns raw PCM audio."""

    def __init__(self, voice="en_US-lessac-medium", speaker_id=None):
        self.voice = voice
        self.speaker_id = speaker_id
        self._voice_obj = None

    def load(self):
        # piper-tts downloads voice models automatically on first use
        log.info(f"TTS: piper voice={self.voice} (will download on first use)")

    def synthesize(self, text: str) -> bytes:
        """Convert text to 16kHz 16-bit PCM."""
        t0 = time.time()
        # Use piper CLI-style via subprocess for reliability
        cmd = ["piper", "--model", self.voice, "--output_raw"]
        if self.speaker_id is not None:
            cmd.extend(["--speaker", str(self.speaker_id)])

        try:
            result = subprocess.run(
                cmd, input=text.encode(), capture_output=True, timeout=30)
            pcm_data = result.stdout
            if result.returncode != 0:
                log.error(f"Piper error: {result.stderr.decode()[:200]}")
                return b""

            # Piper outputs 16-bit PCM at the voice's sample rate (usually 22050Hz)
            # Resample to 16kHz for our pipeline
            if len(pcm_data) > 0:
                # Piper default is 22050Hz mono 16-bit
                pcm_16k, _ = audioop.ratecv(pcm_data, 2, 1, 22050, 16000, None)
                elapsed = time.time() - t0
                duration = len(pcm_16k) / (16000 * 2)
                log.info(f"TTS ({elapsed:.1f}s): {duration:.1f}s audio for \"{text[:40]}...\"")
                return pcm_16k
        except FileNotFoundError:
            log.error("Piper not found. Install: pip install piper-tts")
        except subprocess.TimeoutExpired:
            log.error("Piper timed out")
        except Exception as e:
            log.error(f"TTS error: {e}")
        return b""


# ── TTS: Sarvam AI API ─────────────────────────────────────────────────────

class SarvamTTS:
    """Cloud TTS using Sarvam AI bulbul. Returns 16kHz PCM."""

    def __init__(self, api_key, language="hi-IN", speaker="anushka", model="bulbul:v3"):
        self.api_key = api_key
        self.language = language
        self.speaker = speaker
        self.model = model

    def load(self):
        log.info(f"TTS loaded: Sarvam AI {self.model}, speaker={self.speaker}, lang={self.language}")

    def synthesize(self, text: str) -> bytes:
        import requests, base64
        t0 = time.time()
        try:
            resp = requests.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                json={
                    "text": text,
                    "target_language_code": self.language,
                    "speaker": self.speaker,
                    "model": self.model,
                    "speech_sample_rate": 16000,
                    "output_audio_codec": "wav",
                },
                timeout=15,
            )
        except Exception as e:
            log.error(f"Sarvam TTS request failed: {e}")
            return b""

        if resp.status_code != 200:
            log.error(f"Sarvam TTS {resp.status_code}: {resp.text[:200]}")
            return b""

        audio_b64 = resp.json().get("audios", [""])[0]
        if not audio_b64:
            log.error("Sarvam TTS: empty audio in response")
            return b""

        wav_bytes = base64.b64decode(audio_b64)
        wav_buf = io.BytesIO(wav_bytes)
        with wave.open(wav_buf, "rb") as wf:
            pcm_16k = wf.readframes(wf.getnframes())
            src_rate = wf.getframerate()

        if src_rate != 16000:
            pcm_16k, _ = audioop.ratecv(pcm_16k, 2, 1, src_rate, 16000, None)

        elapsed = time.time() - t0
        duration = len(pcm_16k) / (16000 * 2)
        log.info(f"TTS ({elapsed:.1f}s): {duration:.1f}s audio for \"{text[:40]}\"")
        return pcm_16k


# ── TTS: ElevenLabs API ────────────────────────────────────────────────────

class ElevenLabsTTS:
    """Cloud TTS using ElevenLabs. Returns raw 16kHz PCM (no resampling needed)."""

    def __init__(self, api_key, voice_id="21m00Tcm4TlvDq8ikWAM", model="eleven_flash_v2_5"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model

    def load(self):
        log.info(f"TTS loaded: ElevenLabs {self.model}, voice={self.voice_id}")

    def synthesize(self, text: str) -> bytes:
        """Convert text to 16kHz 16-bit mono PCM (raw, no WAV header)."""
        import requests
        t0 = time.time()
        try:
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
                params={"output_format": "pcm_16000"},
                json={"text": text, "model_id": self.model,
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0}},
                timeout=30,
            )
        except Exception as e:
            log.error(f"ElevenLabs request failed: {e}")
            return b""

        if resp.status_code != 200:
            log.error(f"ElevenLabs TTS {resp.status_code}: {resp.text[:200]}")
            return b""

        pcm_16k = resp.content  # raw S16LE 16kHz mono — no resampling needed
        elapsed = time.time() - t0
        duration = len(pcm_16k) / (16000 * 2)
        log.info(f"TTS ({elapsed:.1f}s): {duration:.1f}s audio for \"{text[:40]}\"")
        return pcm_16k


# ── Task helpers ────────────────────────────────────────────────────────────

def _load_tasks_into_prompt(llm):
    """Append available tasks to LLM system prompt from tasks.json (if present)."""
    try:
        tasks_file = Path(__file__).parent / "tasks.json"
        tasks = json.loads(tasks_file.read_text()).get("tasks", [])
        if not tasks:
            return
        task_list = "\n".join(
            f'- "{t["name"]}" → id:{t["id"]} (calls {t["phone"]})' for t in tasks
        )
        llm.system_prompt = llm.default_system_prompt + (
            f"\n\nYou can execute these saved tasks for the user:\n{task_list}\n"
            "When the user asks to execute a task by name, respond naturally AND append "
            "EXECUTE_TASK:<id> at the very end of your sentence. "
            "Example: 'ठीक है, chai order कर रही हूँ EXECUTE_TASK:1'. "
            "Never say the token EXECUTE_TASK out loud — it is stripped before speaking."
        )
        log.info(f"Loaded {len(tasks)} tasks into prompt")
    except Exception:
        pass  # no tasks.json — fine


def _extract_opening(task_prompt: str):
    """Extract OPENING: line from task prompt. Returns (opening_text, cleaned_prompt)."""
    m = re.search(r'^OPENING:\s*(.+)$', task_prompt, re.MULTILINE)
    if m:
        opening = m.group(1).strip()
        cleaned = re.sub(r'^OPENING:.*\n?', '', task_prompt, flags=re.MULTILINE).strip()
        return opening, cleaned
    return None, task_prompt


# ── WebSocket Server ────────────────────────────────────────────────────────

MONITOR_PORT = 9091  # UDP port for admin live-listen
_mon_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_mon_dest = ("127.0.0.1", MONITOR_PORT)

def _mon_send(ulaw_data: bytes):
    """Send ulaw audio to admin monitor (best-effort, non-blocking)."""
    try:
        _mon_sock.sendto(ulaw_data, _mon_dest)
    except Exception:
        pass


async def handle_client(ws, stt, llm, tts):
    """Handle one RPi audio bridge connection."""
    log.info("RPi connected!")
    processing = False
    current_task = None
    stop_event = None   # signals current pipeline to abort (barge-in)
    pkt_count = 0
    is_speaking = False      # True while AI TTS audio is being sent
    speaking_until = 0.0     # monotonic deadline — suppress barge-in until here
    user_spoke = False       # set True the first time VAD fires (caller said something)

    try:
        async for message in ws:
            if isinstance(message, bytes):
                _mon_send(message)  # forward incoming ulaw to admin monitor
                pcm_8k = audioop.ulaw2lin(message, 2)
                pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)

                # Debug every ~2 seconds
                pkt_count += 1
                if pkt_count % 100 == 1:
                    samples = struct.unpack(f"<{len(pcm_16k)//2}h", pcm_16k)
                    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                    log.info(f"Audio: RMS={rms:.0f} has_speech={stt._has_speech} buf={len(stt._buffer)}")

                audio_chunk = stt.vad(pcm_16k)
                if audio_chunk:
                    user_spoke = True  # caller said something — suppress task purpose fallback
                    now = time.monotonic()
                    if is_speaking or now < speaking_until:
                        pass  # echo suppression — AI speaking, ignore incoming audio
                    elif processing and current_task and stop_event:
                        # Barge-in — user spoke while AI is responding
                        log.info("Barge-in detected — cancelling pipeline")
                        stop_event.set()
                        current_task.cancel()
                        processing = False

                    if not processing and not is_speaking and now >= speaking_until:
                        processing = True
                        stop_event = asyncio.Event()

                        async def _pipeline(chunk=audio_chunk, se=stop_event):
                            nonlocal processing, is_speaking, speaking_until
                            loop = asyncio.get_event_loop()
                            try:
                                # STT (non-blocking)
                                dur = len(chunk) / (16000 * 2)
                                log.info(f"STT: transcribing {dur:.2f}s...")
                                transcript = await loop.run_in_executor(None, stt._transcribe, chunk)
                                if not transcript or se.is_set():
                                    log.info("STT: empty or cancelled")
                                    return

                                # LLM streaming — sentences arrive via queue
                                sentence_q = asyncio.Queue()

                                def _stream():
                                    try:
                                        llm.stream_sentences(transcript, sentence_q, loop, se)
                                    except Exception as e:
                                        err = str(e)
                                        if "429" in err or "quota" in err.lower():
                                            asyncio.run_coroutine_threadsafe(
                                                sentence_q.put("माफ करें, अभी सेवा उपलब्ध नहीं है।"), loop)
                                        elif "503" in err:
                                            asyncio.run_coroutine_threadsafe(
                                                sentence_q.put("माफ करें, सेवा व्यस्त है।"), loop)
                                        else:
                                            log.error(f"LLM error: {e}")
                                        asyncio.run_coroutine_threadsafe(sentence_q.put(None), loop)

                                loop.run_in_executor(None, _stream)

                                # TTS each sentence as it arrives — overlap LLM + TTS
                                is_speaking = True
                                while not se.is_set():
                                    try:
                                        sentence = await asyncio.wait_for(sentence_q.get(), timeout=10.0)
                                    except asyncio.TimeoutError:
                                        log.warning("LLM sentence timeout")
                                        break
                                    if sentence is None:
                                        break
                                    if se.is_set():
                                        break

                                    # Strip task control tokens before TTS
                                    task_complete = "TASK_COMPLETE" in sentence
                                    sentence = sentence.replace("TASK_COMPLETE", "").strip()
                                    m_exec = re.search(r"EXECUTE_TASK:(\d+)", sentence)
                                    execute_task_id = None
                                    if m_exec:
                                        execute_task_id = m_exec.group(1)
                                        sentence = re.sub(r"EXECUTE_TASK:\d+", "", sentence).strip()
                                        log.info(f"[AI] TASK_TRIGGER: task_id={execute_task_id}")

                                    if not sentence:  # nothing left to speak
                                        if task_complete:
                                            await ws.send(json.dumps({"type": "hangup"}))
                                        break

                                    pcm = await loop.run_in_executor(None, tts.synthesize, sentence)
                                    if pcm and not se.is_set():
                                        pcm_8k_out, _ = audioop.ratecv(pcm, 2, 1, 16000, 8000, None)
                                        ulaw_out = audioop.lin2ulaw(pcm_8k_out, 2)
                                        await ws.send(ulaw_out)
                                        _mon_send(ulaw_out)  # forward AI TTS to admin monitor
                                        audio_secs = len(ulaw_out) / 8000  # ulaw: 8000 B/s
                                        speaking_until = time.monotonic() + audio_secs + 0.6  # +600ms echo tail
                                        log.info(f"Sent {len(ulaw_out)}B for: \"{sentence[:40]}\"")

                                    if task_complete and not se.is_set():
                                        # Wait for last audio to finish playing, then hang up
                                        await asyncio.sleep(audio_secs + 0.3)
                                        await ws.send(json.dumps({"type": "hangup"}))
                                        break

                            except asyncio.CancelledError:
                                pass
                            except Exception as e:
                                log.error(f"Pipeline error: {e}")
                            finally:
                                is_speaking = False
                                processing = False

                        current_task = asyncio.create_task(_pipeline())

            elif isinstance(message, str):
                data = json.loads(message)
                if data.get("type") == "call_start":
                    mode = data.get("mode", "outbound")
                    caller = data.get("caller", "?")
                    task_prompt = data.get("task_prompt")
                    log.info(f"Call {'incoming from ' + caller if mode == 'incoming' else 'started'}: {data.get('endpoint', '?')}")
                    stt._buffer.clear()
                    stt._has_speech = False
                    llm._history.clear()
                    user_spoke = False
                    task_opening = None
                    if task_prompt:
                        # Extract OPENING: line before building system prompt
                        task_opening, task_prompt_clean = _extract_opening(task_prompt)
                        llm.system_prompt = (
                            task_prompt_clean + "\n\n"
                            "When the task is successfully completed (order confirmed, info received, etc.), "
                            "append the exact token TASK_COMPLETE to your final response and stop talking. "
                            "Do not say TASK_COMPLETE out loud — it is stripped before speaking."
                        )
                        log.info(f"Task call — prompt loaded, opening={task_opening!r}")
                    else:
                        # Normal call — restore default + add task list for voice trigger
                        llm.system_prompt = llm.default_system_prompt
                        _load_tasks_into_prompt(llm)
                    if mode == "incoming":
                        # Auto-greet incoming caller
                        async def _greet():
                            nonlocal is_speaking, speaking_until
                            loop = asyncio.get_event_loop()
                            greeting = "नमस्ते! मैं भारती AI हूँ, आपकी कैसे मदद कर सकती हूँ?"
                            log.info(f"Sending greeting: {greeting}")
                            pcm = await loop.run_in_executor(None, tts.synthesize, greeting)
                            if pcm:
                                is_speaking = True
                                pcm_8k_out, _ = audioop.ratecv(pcm, 2, 1, 16000, 8000, None)
                                ulaw_out = audioop.lin2ulaw(pcm_8k_out, 2)
                                await ws.send(ulaw_out)
                                audio_secs = len(ulaw_out) / 8000
                                speaking_until = time.monotonic() + audio_secs + 0.6
                                is_speaking = False
                                log.info("Greeting sent")
                        asyncio.create_task(_greet())
                    elif task_opening:
                        # Outbound task call — two-step: greet first, state purpose after 3.5s if no response
                        _purpose = task_opening  # e.g. "मुझे Order Tea करना था।"
                        async def _task_open():
                            nonlocal is_speaking, speaking_until, user_spoke

                            async def _say(text, tail=0.4):
                                nonlocal is_speaking, speaking_until
                                loop = asyncio.get_event_loop()
                                pcm = await loop.run_in_executor(None, tts.synthesize, text)
                                if pcm:
                                    is_speaking = True
                                    pcm_8k, _ = audioop.ratecv(pcm, 2, 1, 16000, 8000, None)
                                    ulaw = audioop.lin2ulaw(pcm_8k, 2)
                                    await ws.send(ulaw)
                                    _mon_send(ulaw)  # forward opening TTS to admin monitor
                                    speaking_until = time.monotonic() + len(ulaw) / 8000 + tail
                                    is_speaking = False
                                    # NOTE: do NOT append to llm._history here —
                                    # pre-call TTS openings cause "First message must be
                                    # from user" errors since they put assistant turns
                                    # before any user turn. System prompt has full context.
                                    log.info(f"LLM (task): \"{text[:80]}\"")
                                    log.info(f"Task TTS sent: {text[:60]}")

                            # Step 1: short greeting (short suppression so "HI" response isn't dropped)
                            await _say("नमस्ते!", tail=0.3)

                            # Step 2: wait — if caller hasn't spoken in 3.5s, state purpose
                            await asyncio.sleep(3.5)
                            if not user_spoke and not is_speaking:
                                await _say(_purpose, tail=0.6)
                        asyncio.create_task(_task_open())
                elif data.get("type") == "call_end":
                    log.info("Call ended")
                    llm.system_prompt = llm.default_system_prompt  # reset after task calls

    except Exception as e:
        log.info(f"RPi disconnected: {e}")


async def run_server(args):
    import websockets

    # Load STT
    if args.stt_provider == "sarvam":
        stt = SarvamSTT(
            api_key=args.sarvam_key,
            language=args.language,
            model=args.sarvam_model,
        )
    else:
        stt = WhisperSTT(model_size=args.stt_model, language=args.language, device=args.device)
    stt.load()

    if args.llm_provider == "sarvam":
        llm = SarvamLLM(
            api_key=args.sarvam_key,
            model=args.sarvam_llm_model,
            system_prompt=args.system_prompt,
        )
    else:
        llm = GeminiLLM(
            api_key=args.api_key,
            model=args.llm_model,
            system_prompt=args.system_prompt,
        )
    llm.load()

    if args.tts_provider == "sarvam":
        tts = SarvamTTS(
            api_key=args.sarvam_key,
            language=args.language,
            speaker=args.sarvam_tts_speaker,
            model=args.sarvam_tts_model,
        )
    elif args.tts_provider == "elevenlabs":
        tts = ElevenLabsTTS(
            api_key=args.elevenlabs_key,
            voice_id=args.elevenlabs_voice,
            model=args.elevenlabs_model,
        )
    else:
        tts = PiperTTS(voice=args.tts_voice)
    tts.load()

    log.info(f"AI Server listening on 0.0.0.0:{args.port}")
    log.info("Waiting for RPi audio bridge to connect...")

    async with websockets.serve(
        lambda ws: handle_client(ws, stt, llm, tts),
        "0.0.0.0", args.port,
        max_size=2**20,
    ):
        await asyncio.Future()  # run forever


def main():
    parser = argparse.ArgumentParser(description="AI Voice Server")
    parser.add_argument("--port", default=9090, type=int, help="WebSocket port")

    # STT provider
    parser.add_argument("--stt-provider", default="sarvam",
                        choices=["sarvam", "whisper"], help="STT backend")
    # Sarvam STT
    parser.add_argument("--sarvam-key", default="sk_8mditejo_dzkogXLt9ra7JAZf0ANgvuC1",
                        help="Sarvam AI API key")
    parser.add_argument("--sarvam-model", default="saaras:v3",
                        help="Sarvam model: saaras:v3, saarika:v2.5")
    parser.add_argument("--language", default="hi-IN",
                        help="STT language (BCP-47 for sarvam e.g. hi-IN, en-IN; ISO for whisper e.g. hi)")
    # Whisper STT (used when --stt-provider whisper)
    parser.add_argument("--stt-model", default="base",
                        help="Whisper model: tiny, base, small, medium")
    parser.add_argument("--device", default="auto", help="cuda, cpu, or auto (whisper only)")

    # LLM provider
    parser.add_argument("--llm-provider", default="sarvam",
                        choices=["sarvam", "gemini"], help="LLM backend")
    # Sarvam LLM (reuses --sarvam-key)
    parser.add_argument("--sarvam-llm-model", default="sarvam-m",
                        help="Sarvam LLM model: sarvam-m, sarvam-30b, sarvam-105b")
    # Gemini LLM (used when --llm-provider gemini)
    parser.add_argument("--api-key", default="AIzaSyDxQ4yME9ChXywqmm-6qry_W5RcjhANmnM")
    parser.add_argument("--llm-model", default="gemini-2.5-flash")
    parser.add_argument("--system-prompt", default=(
        "Your name is Bharti AI. You are a friendly and helpful female voice assistant on a phone call. "
        "You are here to help callers with any kind of information or support they need. "
        "Keep responses short and to the point (1-2 sentences max) — this is a phone call. "
        "Always respond in the same language the caller speaks. "
        "If they speak Hindi, respond in Hindi. If English, respond in English. "
        "IMPORTANT: You are female. When speaking Hindi, always use feminine verb forms and grammar — "
        "use 'sakti hun' (not 'sakta hun'), 'karti hun' (not 'karta hun'), 'hoon' with feminine agreement, etc. "
        "Never use masculine Hindi grammar."
    ))

    # TTS provider
    parser.add_argument("--tts-provider", default="sarvam",
                        choices=["sarvam", "elevenlabs", "piper"], help="TTS backend")
    # Sarvam TTS (reuses --sarvam-key)
    parser.add_argument("--sarvam-tts-speaker", default="priya",
                        help="Sarvam TTS speaker (anushka, manisha, arya, karun, etc.)")
    parser.add_argument("--sarvam-tts-model", default="bulbul:v3",
                        help="Sarvam TTS model: bulbul:v3, bulbul:v2")
    # ElevenLabs TTS
    parser.add_argument("--elevenlabs-key", default="sk_fc5af11ca70e42dd477928efa94c19052c2f54f2efa74342",
                        help="ElevenLabs API key")
    parser.add_argument("--elevenlabs-voice", default="21m00Tcm4TlvDq8ikWAM",
                        help="ElevenLabs voice ID (default: Rachel)")
    parser.add_argument("--elevenlabs-model", default="eleven_flash_v2_5",
                        help="ElevenLabs model (eleven_flash_v2_5 for low latency)")
    # Piper TTS (used when --tts-provider piper)
    parser.add_argument("--tts-voice",
                        default="/home/ubuntu/.local/share/piper-voices/en_US-lessac-medium.onnx",
                        help="Piper voice model path or name")

    args = parser.parse_args()

    stt_label = (f"sarvam ({args.sarvam_model})" if args.stt_provider == "sarvam"
                 else f"whisper ({args.stt_model})")
    if args.tts_provider == "sarvam":
        tts_label = f"sarvam ({args.sarvam_tts_model}, speaker={args.sarvam_tts_speaker})"
    elif args.tts_provider == "elevenlabs":
        tts_label = f"elevenlabs ({args.elevenlabs_model}, voice={args.elevenlabs_voice})"
    else:
        tts_label = f"piper ({args.tts_voice})"
    print("=" * 55)
    print("  AI VOICE SERVER")
    print("=" * 55)
    print(f"  Port       : {args.port}")
    print(f"  STT        : {stt_label}")
    llm_label = (f"sarvam ({args.sarvam_llm_model})" if args.llm_provider == "sarvam"
                 else f"gemini ({args.llm_model})")
    print(f"  LLM        : {llm_label}")
    print(f"  TTS        : {tts_label}")
    print(f"  Language   : {args.language}")
    print("=" * 55)
    print()

    asyncio.run(run_server(args))


if __name__ == "__main__":
    main()
