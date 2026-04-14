"""Provider factory for dependency injection."""

from typing import Literal

from app.config import Config
from app.providers.base import STTProvider
from app.providers.mock import MockSTTProvider
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ProviderFactory:
    """Factory for creating STT provider instances."""

    @staticmethod
    def create_provider(
        provider_type: Literal["openai", "deepgram", "assemblyai", "google", "mock"],
        config: Config,
    ) -> STTProvider:
        """
        Create an STT provider instance.

        Args:
            provider_type: Type of provider to create
            config: Application configuration

        Returns:
            STTProvider: Initialized provider instance

        Raises:
            ValueError: If provider type is unknown or configuration is invalid
        """
        logger.info("creating_provider", provider_type=provider_type)

        if provider_type == "mock" or config.test_mode:
            logger.info("using_mock_provider")
            return MockSTTProvider()

        if provider_type == "openai":
            if not config.openai_api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            # Import here to avoid loading heavy dependencies unless needed
            from app.providers.openai import OpenAISTTProvider

            return OpenAISTTProvider(
                api_key=config.openai_api_key,
                model=config.providers.openai_model,
                voice=config.providers.openai_voice,
            )

        if provider_type == "deepgram":
            if not config.deepgram_api_key:
                raise ValueError("DEEPGRAM_API_KEY not configured")
            from app.providers.deepgram import DeepgramSTTProvider

            return DeepgramSTTProvider(
                api_key=config.deepgram_api_key,
                model=config.providers.deepgram_model,
                language=config.providers.deepgram_language,
                smart_format=config.providers.deepgram_smart_format,
                punctuate=config.providers.deepgram_punctuate,
            )

        if provider_type == "assemblyai":
            if not config.assemblyai_api_key:
                raise ValueError("ASSEMBLYAI_API_KEY not configured")
            from app.providers.assemblyai import AssemblyAISTTProvider

            return AssemblyAISTTProvider(
                api_key=config.assemblyai_api_key,
                language_code=config.providers.assemblyai_language_code,
                punctuate=config.providers.assemblyai_punctuate,
                format_text=config.providers.assemblyai_format_text,
            )

        if provider_type == "google":
            if not config.google_application_credentials:
                raise ValueError("GOOGLE_APPLICATION_CREDENTIALS not configured")
            from app.providers.google import GoogleSTTProvider

            return GoogleSTTProvider(
                credentials_path=config.google_application_credentials,
                language_code=config.providers.google_language_code,
                model=config.providers.google_model,
                use_enhanced=config.providers.google_use_enhanced,
            )

        raise ValueError(f"Unknown provider type: {provider_type}")


def get_provider(config: Config | None = None) -> STTProvider:
    """
    Get an STT provider instance based on configuration.

    Args:
        config: Application configuration (uses global if None)

    Returns:
        STTProvider: Configured provider instance
    """
    if config is None:
        from app.config import get_config

        config = get_config()

    return ProviderFactory.create_provider(config.provider, config)
