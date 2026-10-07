"""core/fetch/__init__.py — Universal Fetch & Extraction Engine."""

from core.fetch.cache import FetchCache
from core.fetch.engine import UniversalFetchEngine
from core.fetch.extractor import SimpleContentExtractor
from core.fetch.fallback import CircuitBreaker, ErrorClassifier, FailureMemory, FetchErrorKind
from core.fetch.normalizer import FetchResult
from core.fetch.planner import FetchPlanner
from core.fetch.reddit import RedditFetcher

__all__ = [
    "UniversalFetchEngine",
    "FetchResult",
    "FetchCache",
    "FetchPlanner",
    "RedditFetcher",
    "SimpleContentExtractor",
    "ErrorClassifier",
    "FailureMemory",
    "CircuitBreaker",
    "FetchErrorKind",
]
