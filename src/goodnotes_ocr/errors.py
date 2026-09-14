class GoodnotesOcrError(Exception):
    """Base error for this package."""


class DependencyError(GoodnotesOcrError):
    """A required optional runtime dependency is missing."""


class PageOutOfRangeError(GoodnotesOcrError):
    """The requested page is outside the document bounds."""


class PageDiscoveryError(GoodnotesOcrError):
    """The scraper could not discover or render the requested page."""


class VlmError(GoodnotesOcrError):
    """The VLM endpoint failed or returned an unusable response."""
