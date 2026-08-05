"""NeuraFS Custom Exception Hierarchy."""


class NeuraFSError(Exception):
    """Base exception for all NeuraFS operations."""
    pass


class InvalidHCSHeaderError(NeuraFSError):
    """Raised when container magic header or flag bytes are invalid."""
    pass


class UnsupportedHCSVersionError(NeuraFSError):
    """Raised when encountering an unhandled HCS layout version."""
    pass


class CorruptedManifestError(NeuraFSError):
    """Raised when the JSON metadata manifest is unparseable or incomplete."""
    pass


class InvalidPrecisionModeError(NeuraFSError):
    """Raised when an unsupported precision mode is requested."""
    pass


class AudioAnalysisError(NeuraFSError):
    """Raised when automatic sample rate detection or complexity profiling fails."""
    pass


class NeuralResynthesisError(NeuraFSError):
    """Raised when PyTorch agent deserialization or resynthesis fails."""
    pass