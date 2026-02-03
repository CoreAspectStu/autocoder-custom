"""
Blocker Detection Service

Detects potential blockers for UAT test execution by analyzing:
- app_spec.txt for external service dependencies
- .env files for missing configuration
- package.json for installed dependencies
- Common API patterns in source code
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class BlockerType(str, Enum):
    """Types of blockers that can prevent test execution"""
    API_KEY_MISSING = "api_key"  # API key required but not provided
    SERVICE_UNAVAILABLE = "service_unavailable"  # External service down
    ENV_VAR_MISSING = "env_var"  # Environment variable not set
    CONFIG_DECISION = "config_decision"  # User choice needed (enable/disable/mock)
    RESOURCE_MISSING = "resource_missing"  # Required resource (file, DB) unavailable
    AUTH_PROVIDER = "auth_provider"  # Auth service not reachable


class BlockerAction(str, Enum):
    """Actions user can take to resolve a blocker"""
    PROVIDVE_KEY = "provide_key"  # Supply API key
    SKIP = "skip"  # Skip affected tests
    MOCK = "mock"  # Use mock service instead
    WAIT = "wait"  # Wait for service to become available
    ENABLE = "enable"  # Enable a feature
    DISABLE = "disable"  # Disable a feature


@dataclass
class Blocker:
    """A single blocker that prevents test execution"""
    id: str  # Unique identifier
    type: BlockerType
    service: str  # Service name (stripe, twilio, etc.)
    description: str  # Human-readable description
    key_name: Optional[str] = None  # Specific key/variable name
    affected_tests: List[str] = field(default_factory=list)  # Test IDs affected
    suggested_actions: List[BlockerAction] = field(default_factory=list)
    priority: str = "medium"  # critical, high, medium, low
    context: Dict[str, Any] = field(default_factory=dict)  # Additional context


class BlockerDetector:
    """Detects blockers by analyzing project configuration and code"""

    # Common API key patterns
    API_KEY_PATTERNS = {
        'stripe': ['STRIPE_SECRET_KEY', 'STRIPE_PUBLISHABLE_KEY', 'STRIPE_API_KEY'],
        'twilio': ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'],
        'sendgrid': ['SENDGRID_API_KEY'],
        'aws': ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
        'openai': ['OPENAI_API_KEY'],
        'google': ['GOOGLE_APPLICATION_CREDENTIALS', 'GOOGLE_API_KEY'],
        'github': ['GITHUB_TOKEN', 'GITHUB_CLIENT_SECRET'],
        'firebase': ['FIREBASE_SERVICE_ACCOUNT_KEY'],
        'mailgun': ['MAILGUN_API_KEY'],
        'redis': ['REDIS_URL'],
        'database': ['DATABASE_URL', 'DB_HOST', 'DB_PORT'],
    }

    # Service endpoint patterns
    SERVICE_PATTERNS = {
        'stripe': r'(stripe\.com|api\.stripe\.com)',
        'twilio': r'(twilio\.com|api\.twilio\.com)',
        'sendgrid': r'(sendgrid\.com|api\.sendgrid\.com)',
        'auth0': r'(auth0\.com|\.auth0\.com)',
        'firebase': r'(firebaseio\.com|firebase\.googleapis\.com)',
        'aws': r'(amazonaws\.com|\.amazonaws\.com)',
    }

    # Email/SMS services requiring special handling
    COMMUNICATION_SERVICES = ['stripe', 'twilio', 'sendgrid', 'mailgun', 'postal']

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def detect_all_blockers(self) -> List[Blocker]:
        """
        Detect all potential blockers for this project.

        Returns a list of Blocker objects sorted by priority.
        """
        blockers = []

        # 1. Check for missing API keys from app_spec.txt
        blockers.extend(self._detect_api_key_blockers())

        # 2. Check for missing environment variables
        blockers.extend(self._detect_env_var_blockers())

        # 3. Check for communication services (need special test setup)
        blockers.extend(self._detect_communication_blockers())

        # 4. Check for external services requiring mocking
        blockers.extend(self._detect_external_service_blockers())

        # Sort by priority (critical > high > medium > low)
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        blockers.sort(key=lambda b: priority_order.get(b.priority, 2))

        return blockers

    def _detect_api_key_blockers(self) -> List[Blocker]:
        """Detect API keys that are required but not provided"""
        blockers = []

        # Parse app_spec.txt if it exists
        app_spec = self.project_path / "prompts" / "app_spec.txt"
        if not app_spec.exists():
            app_spec = self.project_path / "app_spec.txt"
        if not app_spec.exists():
            return blockers

        spec_content = app_spec.read_text().lower()

        # Check for service dependencies (simplified - just text matching)
        for service, keys in self.API_KEY_PATTERNS.items():
            # Check if service is mentioned in spec
            if service in spec_content:
                # Check if any keys are provided
                for key in keys:
                    # Check if key exists in environment or .env
                    if not self._env_var_exists(key):
                        blockers.append(Blocker(
                            id=f"api_key_{service}_{key}",
                            type=BlockerType.API_KEY_MISSING,
                            service=service,
                            description=f"{service.title()} API key '{key}' is required but not provided",
                            key_name=key,
                            affected_tests=[f"Any tests using {service}"],
                            suggested_actions=[BlockerAction.PROVIDVE_KEY, BlockerAction.SKIP, BlockerAction.MOCK],
                            priority="critical" if service in ['stripe', 'twilio'] else "high"
                        ))

        return blockers

    def _detect_env_var_blockers(self) -> List[Blocker]:
        """Detect required environment variables that are missing"""
        blockers = []

        # Check for common required vars
        required_vars = [
            ('DATABASE_URL', 'Database connection string', BlockerType.RESOURCE_MISSING),
            ('REDIS_URL', 'Redis connection string', BlockerType.RESOURCE_MISSING),
            ('API_BASE_URL', 'API base URL', BlockerType.CONFIG_DECISION),
        ]

        for var, description, blocker_type in required_vars:
            if not self._env_var_exists(var):
                blockers.append(Blocker(
                    id=f"env_var_{var}",
                    type=blocker_type,
                    service=var.lower(),
                    key_name=var,
                    description=f"Environment variable '{var}' is required but not set",
                    affected_tests=["Tests requiring database/external services"],
                    suggested_actions=[BlockerAction.WAIT, BlockerAction.MOCK, BlockerAction.SKIP],
                    priority="high"
                ))

        return blockers

    def _detect_communication_blockers(self) -> List[Blocker]:
        """Detect email/SMS services that require special handling during tests"""
        blockers = []

        app_spec = self.project_path / "prompts" / "app_spec.txt"
        if not app_spec.exists():
            app_spec = self.project_path / "app_spec.txt"

        if not app_spec.exists():
            return blockers

        spec_content = app_spec.read_text()

        # Check for communication services
        for service in self.COMMUNICATION_SERVICES:
            if service in spec_content.lower():
                blockers.append(Blocker(
                    id=f"comm_{service}",
                    type=BlockerType.CONFIG_DECISION,
                    service=service,
                    description=f"{service.title()} integration detected. During tests, do you want to:",
                    affected_tests=[f"{service.title()} related tests"],
                    suggested_actions=[BlockerAction.MOCK, BlockerAction.SKIP, BlockerAction.ENABLE],
                    priority="medium",
                    context={
                        'service_type': 'communication',
                        'requires_real_credentials': True
                    }
                ))

        return blockers

    def _detect_external_service_blockers(self) -> List[Blocker]:
        """Detect external API dependencies that might need mocking"""
        blockers = []

        # Check for external API patterns in source
        src_dirs = ['src', 'app', 'lib']
        for src_dir in src_dirs:
            src_path = self.project_path / src_dir
            if not src_path.exists():
                continue

            # Search for fetch/axios calls to external APIs
            for file_path in src_path.rglob('*.ts'):
                try:
                    content = file_path.read_text()
                    self._check_for_api_calls(content, str(file_path), blockers)
                except:
                    pass

        return blockers

    def _check_for_api_calls(self, content: str, file_path: str, blockers: List[Blocker]):
        """Check source code for external API calls"""
        # Look for fetch/axios patterns
        patterns = [
            r"fetch\s*\(\s*[\"']https?://[^\"']+",
            r"axios\.(get|post|put|delete)\s*\(\s*[\"']https?://[^\"']+",
            r'https?://api\.[^"\']+',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                url = match.group(0)
                # Extract service name from URL
                if 'stripe' in url.lower():
                    blockers.append(Blocker(
                        id=f"external_api_{file_path}_{match.start()}",
                        type=BlockerType.SERVICE_UNAVAILABLE,
                        service="stripe",
                        description=f"External API call to Stripe detected in {file_path}",
                        affected_tests=["Tests making external API calls"],
                        suggested_actions=[BlockerAction.MOCK, BlockerAction.SKIP],
                        priority="low"
                    ))

    def _env_var_exists(self, var_name: str) -> bool:
        """Check if an environment variable exists"""
        import os
        return os.getenv(var_name) is not None

    def generate_blocker_summary(self, blockers: List[Blocker]) -> str:
        """Generate a human-readable summary of blockers"""
        if not blockers:
            return "✅ No blockers detected - ready for UAT testing"

        lines = [f"⚠️  {len(blockers)} blocker(s) detected:", ""]

        for i, blocker in enumerate(blockers, 1):
            lines.append(f"{i}. {blocker.service.title()}: {blocker.description}")
            lines.append(f"   Priority: {blocker.priority.upper()}")
            lines.append(f"   Options: {', '.join([a.value for a in blocker.suggested_actions])}")
            lines.append("")

        return "\n".join(lines)


# Convenience function for quick blocker detection
def detect_project_blockers(project_path: str) -> Dict[str, Any]:
    """
    Detect blockers for a project and return a structured response.

    Args:
        project_path: Path to the project directory

    Returns:
        Dict with blockers_detected, blockers list, and summary
    """
    detector = BlockerDetector(project_path)
    blockers = detector.detect_all_blockers()

    return {
        "blockers_detected": len(blockers) > 0,
        "blockers": [
            {
                "id": b.id,
                "blocker_type": b.type.value,
                "service": b.service,
                "key_name": b.key_name,
                "description": b.description,
                "affected_tests": b.affected_tests,
                "suggested_actions": [a.value for a in b.suggested_actions],
                "priority": b.priority,
                "context": b.context
            }
            for b in blockers
        ],
        "summary": detector.generate_blocker_summary(blockers)
    }
