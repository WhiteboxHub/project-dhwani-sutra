"""Configuration management for Dhwani Sutra."""

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AudioConfig(BaseSettings):
    """Audio processing configuration."""

    sample_rate: int = 16000
    chunk_duration_ms: int = 250
    format: Literal["opus", "pcm", "wav"] = "opus"
    channels: int = 1


class SessionConfig(BaseSettings):
    """Session management configuration."""

    max_duration_seconds: int = 14400
    idle_timeout_seconds: int = 3600
    max_concurrent: int = 100
    cleanup_interval_seconds: int = 60


class WebSocketConfig(BaseSettings):
    """WebSocket configuration."""

    ping_interval: int = 30
    ping_timeout: int = 10
    max_message_size: int = 1048576


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    level: Literal["debug", "info", "warning", "error"] = "info"
    format: Literal["json", "text"] = "json"
    include_correlation_id: bool = True


class RedisConfig(BaseSettings):
    """Redis configuration."""

    enabled: bool = False
    url: str | None = None
    session_ttl: int = 7200


class SecurityConfig(BaseSettings):
    """Security configuration."""

    require_auth: bool = False
    allowed_origins: list[str] = Field(default_factory=list)
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 100


class ProviderSettings(BaseSettings):
    """Provider-specific settings."""

    # OpenAI
    openai_model: str = "gpt-4o-realtime-preview-2024-10-01"
    openai_voice: str = "alloy"

    # Deepgram
    deepgram_model: str = "nova-2"
    deepgram_language: str = "en-US"
    deepgram_smart_format: bool = True
    deepgram_punctuate: bool = True

    # AssemblyAI
    assemblyai_language_code: str = "en_us"
    assemblyai_punctuate: bool = True
    assemblyai_format_text: bool = True

    # Google
    google_language_code: str = "en-US"
    google_model: str = "latest_long"
    google_use_enhanced: bool = True


class Config(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Provider
    provider: Literal["openai", "deepgram", "assemblyai", "google", "mock"] = "mock"
    test_mode: bool = False

    # API Keys
    openai_api_key: str | None = None
    deepgram_api_key: str | None = None
    assemblyai_api_key: str | None = None
    google_application_credentials: str | None = None

    # Redis
    redis_url: str | None = None

    # Logging
    log_level: str = "info"

    # Sub-configs
    audio: AudioConfig = Field(default_factory=AudioConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    providers: ProviderSettings = Field(default_factory=ProviderSettings)

    @classmethod
    def load_from_yaml(cls, yaml_path: str | Path = "config.yaml") -> "Config":
        """Load configuration from YAML file and merge with env vars."""
        config_path = Path(yaml_path)

        if not config_path.exists():
            # Use defaults if config file doesn't exist
            return cls()

        with open(config_path) as f:
            yaml_data = yaml.safe_load(f) or {}

        # Flatten nested config for Pydantic
        flat_config: dict[str, Any] = {}

        # Top-level settings
        if "provider" in yaml_data:
            flat_config["provider"] = yaml_data["provider"]

        # Audio settings
        if "audio" in yaml_data:
            audio = yaml_data["audio"]
            flat_config["audio"] = AudioConfig(**audio)

        # Session settings
        if "session" in yaml_data:
            session = yaml_data["session"]
            flat_config["session"] = SessionConfig(**session)

        # WebSocket settings
        if "websocket" in yaml_data:
            ws = yaml_data["websocket"]
            flat_config["websocket"] = WebSocketConfig(**ws)

        # Logging settings
        if "logging" in yaml_data:
            logging = yaml_data["logging"]
            flat_config["logging"] = LoggingConfig(**logging)

        # Redis settings
        if "redis" in yaml_data:
            redis = yaml_data["redis"]
            flat_config["redis"] = RedisConfig(**redis)

        # Security settings
        if "security" in yaml_data:
            security = yaml_data["security"]
            rate_limit = security.get("rate_limit", {})
            flat_config["security"] = SecurityConfig(
                require_auth=security.get("require_auth", False),
                allowed_origins=security.get("allowed_origins", []),
                rate_limit_enabled=rate_limit.get("enabled", True),
                rate_limit_requests_per_minute=rate_limit.get("requests_per_minute", 100),
            )

        # Provider-specific settings
        if "providers" in yaml_data:
            providers = yaml_data["providers"]
            provider_settings = {}

            if "openai" in providers:
                provider_settings["openai_model"] = providers["openai"].get("model")
                provider_settings["openai_voice"] = providers["openai"].get("voice")

            if "deepgram" in providers:
                provider_settings["deepgram_model"] = providers["deepgram"].get("model")
                provider_settings["deepgram_language"] = providers["deepgram"].get("language")
                provider_settings["deepgram_smart_format"] = providers["deepgram"].get(
                    "smart_format"
                )
                provider_settings["deepgram_punctuate"] = providers["deepgram"].get("punctuate")

            if "assemblyai" in providers:
                provider_settings["assemblyai_language_code"] = providers["assemblyai"].get(
                    "language_code"
                )
                provider_settings["assemblyai_punctuate"] = providers["assemblyai"].get("punctuate")
                provider_settings["assemblyai_format_text"] = providers["assemblyai"].get(
                    "format_text"
                )

            if "google" in providers:
                provider_settings["google_language_code"] = providers["google"].get("language_code")
                provider_settings["google_model"] = providers["google"].get("model")
                provider_settings["google_use_enhanced"] = providers["google"].get("use_enhanced")

            flat_config["providers"] = ProviderSettings(**provider_settings)

        # Create config instance (env vars will override)
        return cls(**flat_config)


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load_from_yaml()
    return _config


def reload_config() -> Config:
    """Reload configuration from file and environment."""
    global _config
    _config = Config.load_from_yaml()
    return _config
