"""Audio encoding and format conversion utilities."""

import io
from typing import Literal

import numpy as np
import soundfile as sf
from scipy import signal

from app.utils.logging import get_logger

logger = get_logger(__name__)


class AudioEncoder:
    """Audio format conversion and encoding utilities."""

    @staticmethod
    def opus_to_pcm16(opus_data: bytes, sample_rate: int = 16000) -> bytes:
        """
        Convert Opus audio to PCM16.

        Args:
            opus_data: Opus-encoded audio bytes
            sample_rate: Target sample rate

        Returns:
            PCM16 audio bytes
        """
        try:
            # Read opus data
            audio_buffer = io.BytesIO(opus_data)
            data, sr = sf.read(audio_buffer, dtype="int16")

            # Resample if needed
            if sr != sample_rate:
                data = AudioEncoder.resample(data, sr, sample_rate)

            # Convert to mono if stereo
            if len(data.shape) > 1 and data.shape[1] > 1:
                data = AudioEncoder.stereo_to_mono(data)

            return data.tobytes()

        except Exception as e:
            logger.error("opus_to_pcm16_failed", error=str(e))
            raise ValueError(f"Failed to convert Opus to PCM16: {e}") from e

    @staticmethod
    def pcm16_to_float32(pcm_data: bytes) -> np.ndarray:
        """
        Convert PCM16 to float32 numpy array.

        Args:
            pcm_data: PCM16 audio bytes

        Returns:
            Float32 numpy array normalized to [-1, 1]
        """
        # Convert to int16 array
        audio_int16 = np.frombuffer(pcm_data, dtype=np.int16)

        # Normalize to [-1, 1]
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        return audio_float32

    @staticmethod
    def float32_to_pcm16(audio_float: np.ndarray) -> bytes:
        """
        Convert float32 numpy array to PCM16.

        Args:
            audio_float: Float32 audio array [-1, 1]

        Returns:
            PCM16 audio bytes
        """
        # Clip to [-1, 1] and convert to int16
        audio_clipped = np.clip(audio_float, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        return audio_int16.tobytes()

    @staticmethod
    def resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
        Resample audio to target sample rate.

        Args:
            audio: Audio data as numpy array
            orig_sr: Original sample rate
            target_sr: Target sample rate

        Returns:
            Resampled audio as numpy array
        """
        if orig_sr == target_sr:
            return audio

        # Calculate resampling ratio
        ratio = target_sr / orig_sr

        # Use scipy's resample_poly for high-quality resampling
        # Find appropriate up/down factors
        from fractions import Fraction

        frac = Fraction(target_sr, orig_sr).limit_denominator(1000)
        up = frac.numerator
        down = frac.denominator

        resampled = signal.resample_poly(audio, up, down)

        logger.debug(
            "audio_resampled",
            orig_sr=orig_sr,
            target_sr=target_sr,
            orig_samples=len(audio),
            new_samples=len(resampled),
        )

        return resampled.astype(audio.dtype)

    @staticmethod
    def stereo_to_mono(audio: np.ndarray) -> np.ndarray:
        """
        Convert stereo audio to mono by averaging channels.

        Args:
            audio: Stereo audio array (N, 2)

        Returns:
            Mono audio array (N,)
        """
        if len(audio.shape) == 1:
            return audio

        return np.mean(audio, axis=1)

    @staticmethod
    def adjust_channels(audio: np.ndarray, target_channels: int) -> np.ndarray:
        """
        Adjust number of audio channels.

        Args:
            audio: Audio array
            target_channels: Target number of channels (1 or 2)

        Returns:
            Audio with target number of channels
        """
        current_channels = 1 if len(audio.shape) == 1 else audio.shape[1]

        if current_channels == target_channels:
            return audio

        if target_channels == 1:
            # Convert to mono
            return AudioEncoder.stereo_to_mono(audio)
        else:
            # Convert to stereo (duplicate mono)
            return np.column_stack([audio, audio])

    @staticmethod
    def get_audio_format(
        format_type: Literal["opus", "pcm", "wav"]
    ) -> tuple[str, str]:
        """
        Get format parameters for audio encoding.

        Args:
            format_type: Audio format type

        Returns:
            Tuple of (format, subtype)
        """
        format_map = {
            "opus": ("OGG", "OPUS"),
            "pcm": ("RAW", "PCM_16"),
            "wav": ("WAV", "PCM_16"),
        }

        if format_type not in format_map:
            raise ValueError(f"Unsupported format: {format_type}")

        return format_map[format_type]

    @staticmethod
    def validate_audio_chunk(
        audio_chunk: bytes,
        expected_sample_rate: int = 16000,
        expected_channels: int = 1,
    ) -> bool:
        """
        Validate audio chunk properties.

        Args:
            audio_chunk: Audio data to validate
            expected_sample_rate: Expected sample rate
            expected_channels: Expected number of channels

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if chunk is not empty
            if not audio_chunk or len(audio_chunk) == 0:
                logger.warning("audio_validation_failed", reason="empty_chunk")
                return False

            # Check minimum size (at least 100ms of audio)
            min_size = (expected_sample_rate * expected_channels * 2) // 10  # 100ms
            if len(audio_chunk) < min_size:
                logger.warning(
                    "audio_validation_failed",
                    reason="chunk_too_small",
                    size=len(audio_chunk),
                    min_size=min_size,
                )
                return False

            # Check alignment (PCM16 is 2 bytes per sample)
            if len(audio_chunk) % 2 != 0:
                logger.warning("audio_validation_failed", reason="invalid_alignment")
                return False

            return True

        except Exception as e:
            logger.error("audio_validation_error", error=str(e))
            return False
