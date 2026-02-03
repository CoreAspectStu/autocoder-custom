"""
API Adapter Module

Provides API endpoint discovery and testing capabilities.
"""

from .api_adapter import (
    APIAdapter,
    APIEndpoint,
    DiscoveryResult,
    HTTPMethod,
    ErrorTestCase,
    ErrorTestResult,
    APIMeasurement,
    PerformanceStats,
    APITestResult,
    # Schema validation classes (Feature #128)
    SchemaDataType,
    SchemaProperty,
    ResponseSchema,
    ValidationResult,
)

__all__ = [
    'APIAdapter',
    'APIEndpoint',
    'DiscoveryResult',
    'HTTPMethod',
    'ErrorTestCase',
    'ErrorTestResult',
    'APIMeasurement',
    'PerformanceStats',
    'APITestResult',
    'SchemaDataType',
    'SchemaProperty',
    'ResponseSchema',
    'ValidationResult',
]
