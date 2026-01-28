"""
Test Generator Module

Generates automated tests from Journey definitions.
"""

from .test_generator import (
    TestGenerator,
    TestConfig,
    GeneratedTest,
    create_test_generator
)

# Import git integration to monkey-patch TestGenerator with git methods
from . import git_integration  # noqa: F401

__all__ = [
    "TestGenerator",
    "TestConfig",
    "GeneratedTest",
    "create_test_generator",
]
