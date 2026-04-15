"""
OpenAI LLM Provider — Streaming text generation via OpenAI Chat API.

Used in STT → LLM → TTS pipeline (Mode A).
"""

import asyncio
import logging
from typing import AsyncIterator

from providers.base import BaseLLM

log = logging.getLogger(__name__)


class OpenAILLM(BaseLLM):

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.model_name = config.get("model", "gpt-4o-mini")
        self.system_prompt = config.get("system_prompt", "")
        self._client = None
        self._messages = []

    async def start(self, system_prompt: str = ""):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("Install: pip install openai")

        self._client = AsyncOpenAI(api_key=self.api_key)
        prompt = system_prompt or self.system_prompt or (
            "You are a helpful voice assistant. Keep responses short and conversational."
        )
        self._messages = [{"role": "system", "content": prompt}]
        log.info("OpenAI LLM started (model=%s)", self.model_name)

    async def stop(self):
        self._messages.clear()
        log.info("OpenAI LLM stopped")

    async def generate_stream(self, text: str) -> AsyncIterator[str]:
        self._messages.append({"role": "user", "content": text})

        buffer = ""
        full_response = ""

        try:
            stream = await self._client.chat.completions.create(
                model=self.model_name,
                messages=self._messages,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    buffer += delta.content
                    full_response += delta.content

                    # Yield at sentence boundaries
                    while any(p in buffer for p in [".", "!", "?", "।", "\n"]):
                        for i, ch in enumerate(buffer):
                            if ch in ".!?।\n":
                                sentence = buffer[:i + 1].strip()
                                buffer = buffer[i + 1:]
                                if sentence:
                                    yield sentence
                                break

            if buffer.strip():
                yield buffer.strip()

            self._messages.append({"role": "assistant", "content": full_response})

            # Keep history manageable
            if len(self._messages) > 21:
                self._messages = self._messages[:1] + self._messages[-20:]

        except Exception as e:
            log.error("OpenAI LLM error: %s", e)
            yield "Sorry, I encountered an error."
