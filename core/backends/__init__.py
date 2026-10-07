"""core/backends — Browser backend adapters for Muse 3.0."""

from core.backends.chrome_backend import ChromeBackend
from core.backends.obscura_backend import ObscuraBackend
from core.backends.playwright_backend import PlaywrightBackend

__all__ = ["ChromeBackend", "ObscuraBackend", "PlaywrightBackend"]
