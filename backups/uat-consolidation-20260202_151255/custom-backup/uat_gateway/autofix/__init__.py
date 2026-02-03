"""
Auto-Fix Module - Automated fix suggestions for test failures

Phase 4 Advanced Feature: Auto-fix resolves 60% of selector failures

This module provides intelligent analysis and fix suggestions for common test failures.
"""

from uat_gateway.autofix.autofix_generator import (
    AutoFixGenerator,
    FixSuggestion,
    FixAnalysis,
    FixType,
    Confidence,
    generate_fix_suggestions
)

__all__ = [
    'AutoFixGenerator',
    'FixSuggestion',
    'FixAnalysis',
    'FixType',
    'Confidence',
    'generate_fix_suggestions'
]
