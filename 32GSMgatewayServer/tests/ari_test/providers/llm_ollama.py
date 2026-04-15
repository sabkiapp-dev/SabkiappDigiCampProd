"""
Ollama LLM Provider — Local LLM via Ollama API.

Runs entirely on-device. Good for privacy/offline. Needs Ollama installed.
"""

import asyncio
import json
import logging
from typing import AsyncIterator

import requests as req

from providers.base import BaseLLM

log = logging.getLogger(__name__)


class OllamaLLM(BaseLLM):

    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model_name = config.get("model", "llama3.2")
        self.system_prompt = config.get("system_prompt", "")
        self._messages = []

    async def start(self, system_prompt: str = ""):
        prompt = system_prompt or self.system_prompt or (
            "You are a helpful voice assistant. Keep responses short and conversational."
        )
        self._messages = [{"role": "system", "content": prompt}]
        log.info("Ollama LLM started (model=%s, url=%s)", self.model_name, self.base_url)

    async def stop(self):
        self._messages.clear()
        log.info("Ollama LLM stopped")

    async def generate_stream(self, text: str) -> AsyncIterator[str]:
        self._messages.append({"role": "user", "content": text})

        buffer = ""
        full_response = ""

        try:
            # Ollama streaming via HTTP (run in thread to avoid blocking)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: req.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model_name,
                        "messages": self._messages,
                        "stream": True,
                    },
                    stream=True,
                    timeout=30,
                )
            )

            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                content = data.get("message", {}).get("content", "")
                if content:
                    buffer += content
                    full_response += content

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

            if len(self._messages) > 21:
                self._messages = self._messages[:1] + self._messages[-20:]

        except Exception as e:
            log.error("Ollama LLM error: %s", e)
            yield "Sorry, I encountered an error."
