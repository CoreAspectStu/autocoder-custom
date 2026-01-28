"""
MSW Adapter Package

Generates Mock Service Worker (MSW) handlers for API endpoints.
"""

from .msw_adapter import (
    MSWAdapter,
    MSWHandler,
    MSWGenerationResult,
    validate_handler_syntax,
    verify_handler_matches_endpoint
)

__all__ = [
    "MSWAdapter",
    "MSWHandler",
    "MSWGenerationResult",
    "validate_handler_syntax",
    "verify_handler_matches_endpoint"
]
