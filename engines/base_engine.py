from abc import ABC, abstractmethod


class BaseAudioEngine(ABC):
    """Abstract base class for all AI audio processing engines."""

    def __init__(self) -> None:
        self._is_loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @abstractmethod
    def load_model(self) -> bool:
        """Load and initialize model weights and tokenizer."""
        pass

    @abstractmethod
    def unload_model(self) -> None:
        """Release model resources."""
        pass
