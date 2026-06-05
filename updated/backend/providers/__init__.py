import os
from .open_ai import OpenAIProvider
from .deepgram import DeepgramProvider

def get_stt_provider(provider_name_override: str = None):
    provider_name = (provider_name_override or os.getenv("STT_PROVIDER", "openai")).lower()
    if provider_name == "deepgram":
        return DeepgramProvider()
    return OpenAIProvider()
