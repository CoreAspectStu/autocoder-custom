"""
FastAPI app module for uvicorn auto-reload

This module provides the app instance that uvicorn can import
for auto-reload functionality.
"""
from .server import create_app

# Create app instance with higher rate limits for testing
app = create_app(
    jwt_secret_key="test-secret-key",
    enable_auth=True,
    enable_rate_limiting=True,
    requests_per_minute=200,  # Increased from 60
    requests_per_hour=5000     # Increased from 1000
)
