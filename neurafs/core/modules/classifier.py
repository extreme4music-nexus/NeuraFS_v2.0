"""NeuraFS File Type Classifier Module."""

import os
from pathlib import Path


class MediaClassifier:
    """Classifies incoming files for Neural Encoding vs Standard Compression."""

    AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".aac", ".m4a", ".wma", ".aiff"}

    @classmethod
    def is_neural_audio(cls, file_path: str) -> bool:
        """Returns True if the file is an audio media format requiring Neural Encoding."""
        ext = Path(file_path).suffix.lower()
        return ext in cls.AUDIO_EXTENSIONS