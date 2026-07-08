from abc import ABC, abstractmethod
import asyncio
from typing import Callable, Awaitable

class STTProvider(ABC):
    @abstractmethod
    async def process_audio_stream(
        self, 
        audio_queue: asyncio.Queue, 
        handler_callback: Callable[[str, bool], Awaitable[None]]
    ) -> None:
        """
        Process the audio queue and call handler_callback with raw transcribed text.
        handler_callback(text, is_final) — is_final=False for interim/partial results,
        is_final=True for finalized sentences.
        """
        pass
