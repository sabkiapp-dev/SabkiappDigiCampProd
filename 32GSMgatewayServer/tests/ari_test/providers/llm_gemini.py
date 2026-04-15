"""
Gemini LLM Provider — Streaming text generation via Google Gemini API.

Used in STT → LLM → TTS pipeline (Mode A).
Maintains conversation history for multi-turn dialogue.
"""

import asyncio
import logging
from typing import AsyncIterator

from providers.base import BaseLLM

log = logging.getLogger(__name__)


class GeminiLLM(BaseLLM):

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.model_name = config.get("model", "gemini-2.5-flash")
        self.system_prompt = config.get("system_prompt", "")
        self._client = None
        self._chat = None
        self._history = []

    async def start(self, system_prompt: str = ""):
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Install: pip install google-genai")

        self._client = genai.Client(api_key=self.api_key)
        prompt = system_prompt or self.system_prompt or (
            "You are a helpful voice assistant. Keep responses short and conversational. "
            "Respond in the same language the user speaks."
        )
        self._history = []
        self._system_prompt = prompt
        log.info("Gemini LLM started (model=%s)", self.model_name)

    async def stop(self):
        self._history.clear()
        log.info("Gemini LLM stopped")

    async def generate_stream(self, text: str) -> AsyncIterator[str]:
        from google.genai import types

        self._history.append({"role": "user", "parts": [{"text": text}]})

        contents = [
            types.Content(role="user", parts=[types.Part(text=self._system_prompt)]),
        ]
        for msg in self._history:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part(text=p["text"]) for p in msg["parts"]],
                )
            )

        full_response = ""
        buffer = ""

        try:
            response = await self._client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
            )

            async for chunk in response:
                if chunk.text:
                    buffer += chunk.text
                    full_response += chunk.text

                    # Yield at sentence boundaries for natural TTS
                    while any(p in buffer for p in [".", "!", "?", "।", "\n"]):
                        for i, ch in enumerate(buffer):
                            if ch in ".!?।\n":
                                sentence = buffer[:i + 1].strip()
                                buffer = buffer[i + 1:]
                                if sentence:
                                    yield sentence
                                break

            # Yield remaining buffer
            if buffer.strip():
                yield buffer.strip()

            # Store assistant response in history
            self._history.append({
                "role": "model",
                "parts": [{"text": full_response}],
            })

            # Keep history manageable (last 10 turns)
            if len(self._history) > 20:
                self._history = self._history[-20:]

        except Exception as e:
            log.error("Gemini LLM error: %s", e)
            yield "Sorry, I encountered an error."
