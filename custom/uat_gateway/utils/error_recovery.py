"""
Error Recovery System for UAT Gateway

This module provides structured error recovery options for users
when errors occur during test execution.

Feature #228: UAT gateway provides error recovery options
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging


class RecoveryActionType(Enum):
    """Types of recovery actions available to users"""
    RETRY = "retry"              # Retry the failed operation
    SKIP = "skip"                # Skip and continue
    IGNORE = "ignore"            # Ignore this error type
    RERUN_CONFIG = "rerun_config"  # Rerun with different config
    SUPPORT = "support"          # Contact support
    VIEW_LOGS = "view_logs"      # View detailed logs
    CHECKPOINT = "checkpoint"    # Restore from checkpoint
    MANUAL_FIX = "manual_fix"    # Manual fix required


@dataclass
class RecoveryAction:
    """Represents a single recovery action option"""
    action_type: RecoveryActionType
    label: str                   # User-friendly label
    description: str             # What this action does
    enabled: bool = True         # Whether this action is available
    requires_user_input: bool = False  # Whether user needs to provide input
    confidence: float = 1.0      # Likelihood this will resolve the error (0-1)


@dataclass
class ErrorRecoveryContext:
    """
    Comprehensive error recovery information

    Provides users with actionable steps to recover from errors
    during UAT test execution.
    """
    error_id: str
    error_type: str
    error_message: str
    severity: str                # 'critical', 'high', 'medium', 'low'
    component: str               # Where the error occurred
    recovery_actions: List[RecoveryAction] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    documentation_link: Optional[str] = None
    support_link: Optional[str] = None
    related_errors: List[str] = field(default_factory=list)
    can_retry: bool = True
    estimated_recovery_time_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "error_id": self.error_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "severity": self.severity,
            "component": self.component,
            "recovery_actions": [
                {
                    "type": action.action_type.value,
                    "label": action.label,
                    "description": action.description,
                    "enabled": action.enabled,
                    "requires_user_input": action.requires_user_input,
                    "confidence": action.confidence
                }
                for action in self.recovery_actions
            ],
            "suggestions": self.suggestions,
            "documentation_link": self.documentation_link,
            "support_link": self.support_link,
            "related_errors": self.related_errors,
            "can_retry": self.can_retry,
            "estimated_recovery_time_ms": self.estimated_recovery_time_ms
        }


class ErrorRecoveryProvider:
    """
    Provides recovery options based on error type and context

    Analyzes errors and suggests appropriate recovery actions
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("uat_gateway.error_recovery")
        self._recovery_strategies = self._init_strategies()

    def _init_strategies(self) -> Dict[str, callable]:
        """Initialize recovery strategies for different error types"""
        return {
            # Test execution errors
            "TestExecutionError": self._test_execution_recovery,
            "TimeoutExpired": self._timeout_recovery,
            "BrowserCrashError": self._browser_crash_recovery,

            # Network errors
            "ConnectionError": self._connection_recovery,
            "URLError": self._url_error_recovery,

            # State management errors
            "StateManagementError": self._state_management_recovery,
            "CheckpointError": self._checkpoint_recovery,

            # Configuration errors
            "ConfigurationError": self._configuration_recovery,

            # Journey extraction errors
            "JourneyExtractionError": self._journey_extraction_recovery,

            # Test generation errors
            "TestGenerationError": self._test_generation_recovery,

            # Kanban integration errors
            "KanbanIntegrationError": self._kanban_recovery,

            # Generic fallback
            "UATGatewayError": self._generic_recovery,
        }

    def get_recovery_options(self,
                            error: Exception,
                            context: Optional[Dict[str, Any]] = None) -> ErrorRecoveryContext:
        """
        Get recovery options for an error

        Args:
            error: The exception that occurred
            context: Additional error context

        Returns:
            ErrorRecoveryContext with recovery options
        """
        error_type = type(error).__name__
        error_message = str(error)
        component = getattr(error, 'component', 'unknown') if hasattr(error, 'component') else context.get('component', 'unknown') if context else 'unknown'

        # Get recovery strategy
        strategy = self._recovery_strategies.get(
            error_type,
            self._recovery_strategies.get("UATGatewayError", self._generic_recovery)
        )

        # Generate error ID
        error_id = f"{error_type}_{hash(error_message) % 10000:04d}"

        # Build recovery context
        recovery_context = ErrorRecoveryContext(
            error_id=error_id,
            error_type=error_type,
            error_message=error_message,
            component=component,
            severity=self._determine_severity(error, context),
            recovery_actions=[],
            suggestions=[],
            documentation_link=self._get_documentation_link(error_type),
            support_link="https://github.com/CoreAspectStu/autocoder/issues"
        )

        # Apply strategy
        try:
            strategy(error, context, recovery_context)
        except Exception as e:
            self.logger.warning(f"Error applying recovery strategy: {e}")
            self._generic_recovery(error, context, recovery_context)

        return recovery_context

    def _determine_severity(self, error: Exception, context: Optional[Dict[str, Any]]) -> str:
        """Determine error severity based on type and context"""
        error_type = type(error).__name__

        # Critical errors
        if error_type in ["BrowserCrashError", "StateManagementError"]:
            return "critical"

        # High severity
        if error_type in ["TestExecutionError", "ConfigurationError"]:
            return "high"

        # Medium severity
        if error_type in ["ConnectionError", "TimeoutExpired"]:
            return "medium"

        # Low severity (informational)
        return "low"

    def _get_documentation_link(self, error_type: str) -> Optional[str]:
        """Get documentation link for error type"""
        docs_map = {
            "TestExecutionError": "https://docs.uat-gateway.dev/errors/test-execution",
            "ConfigurationError": "https://docs.uat-gateway.dev/errors/configuration",
            "StateManagementError": "https://docs.uat-gateway.dev/errors/state-management",
        }
        return docs_map.get(error_type)

    # ========================================================================
    # Recovery Strategies
    # ========================================================================

    def _test_execution_recovery(self,
                                 error: Exception,
                                 context: Optional[Dict[str, Any]],
                                 recovery: ErrorRecoveryContext):
        """Recovery options for test execution errors"""
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RETRY,
                label="Retry Test",
                description="Run the failed test again",
                confidence=0.7
            ),
            RecoveryAction(
                action_type=RecoveryActionType.VIEW_LOGS,
                label="View Console Logs",
                description="Check browser console for errors",
                confidence=0.9
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP,
                label="Skip Test",
                description="Skip this test and continue with remaining tests",
                confidence=0.5
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SUPPORT,
                label="Contact Support",
                description="Report this issue to the support team",
                confidence=0.3
            ),
        ]

        recovery.suggestions = [
            "Check if the application is still running",
            "Verify the test selector is correct",
            "Review browser console logs for JavaScript errors",
            "Ensure all test data is properly set up",
        ]

        recovery.can_retry = True
        recovery.estimated_recovery_time_ms = 5000

    def _timeout_recovery(self,
                         error: Exception,
                         context: Optional[Dict[str, Any]],
                         recovery: ErrorRecoveryContext):
        """Recovery options for timeout errors"""
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RERUN_CONFIG,
                label="Increase Timeout",
                description="Rerun with a longer timeout duration",
                confidence=0.8,
                requires_user_input=True
            ),
            RecoveryAction(
                action_type=RecoveryActionType.RETRY,
                label="Retry Immediately",
                description="Try running the test again with the same timeout",
                confidence=0.4
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP,
                label="Skip and Continue",
                description="Skip this slow test",
                confidence=0.6
            ),
        ]

        recovery.suggestions = [
            "The test may be waiting for a slow element",
            "Consider using more specific selectors",
            "Check if network conditions are slow",
            "Verify the application isn't hanging",
        ]

        recovery.can_retry = True
        recovery.estimated_recovery_time_ms = 10000

    def _browser_crash_recovery(self,
                                error: Exception,
                                context: Optional[Dict[str, Any]],
                                recovery: ErrorRecoveryContext):
        """Recovery options for browser crashes"""
        recovery.severity = "critical"
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RETRY,
                label="Restart Browser and Retry",
                description="Restart the browser and run the test again",
                confidence=0.8
            ),
            RecoveryAction(
                action_type=RecoveryActionType.CHECKPOINT,
                label="Restore from Checkpoint",
                description="Restore state from last checkpoint",
                confidence=0.7
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SUPPORT,
                label="Report Crash",
                description="This browser crash should be investigated",
                confidence=0.5
            ),
        ]

        recovery.suggestions = [
            "Browser crashes are often due to memory issues",
            "Check system memory availability",
            "Try running tests in headless mode",
            "Report this crash if it persists",
        ]

        recovery.can_retry = True
        recovery.estimated_recovery_time_ms = 15000

    def _connection_recovery(self,
                             error: Exception,
                             context: Optional[Dict[str, Any]],
                             recovery: ErrorRecoveryContext):
        """Recovery options for connection errors"""
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RETRY,
                label="Retry Connection",
                description="Attempt to connect again",
                confidence=0.8
            ),
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Start Application",
                description="Ensure the application is running",
                confidence=0.9,
                requires_user_input=True
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP,
                label="Skip Tests",
                description="Skip tests until application is available",
                confidence=0.3
            ),
        ]

        recovery.suggestions = [
            "Ensure the application server is running",
            "Check that the URL is correct",
            "Verify network connectivity",
            "Check if the application is on the correct port",
        ]

        recovery.can_retry = True
        recovery.estimated_recovery_time_ms = 3000

    def _url_error_recovery(self,
                           error: Exception,
                           context: Optional[Dict[str, Any]],
                           recovery: ErrorRecoveryContext):
        """Recovery options for URL errors"""
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RERUN_CONFIG,
                label="Update URL",
                description="Run tests with the correct application URL",
                confidence=0.9,
                requires_user_input=True
            ),
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Fix Configuration",
                description="Update the base_url in configuration",
                confidence=0.9
            ),
        ]

        recovery.suggestions = [
            "Check the base_url in your configuration",
            "Ensure the application is accessible",
            "Verify the URL format (include http:// or https://)",
        ]

        recovery.can_retry = False

    def _state_management_recovery(self,
                                  error: Exception,
                                  context: Optional[Dict[str, Any]],
                                  recovery: ErrorRecoveryContext):
        """Recovery options for state management errors"""
        recovery.severity = "critical"
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.CHECKPOINT,
                label="Restore from Last Checkpoint",
                description="Restore state from last successful checkpoint",
                confidence=0.8
            ),
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Reset State",
                description="Clear state and start fresh",
                confidence=0.7,
                requires_user_input=True
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SUPPORT,
                label="Contact Support",
                description="State management errors need investigation",
                confidence=0.5
            ),
        ]

        recovery.suggestions = [
            "State files may be corrupted",
            "Try clearing the state directory",
            "Restore from a previous checkpoint if available",
        ]

        recovery.can_retry = True
        recovery.estimated_recovery_time_ms = 5000

    def _checkpoint_recovery(self,
                             error: Exception,
                             context: Optional[Dict[str, Any]],
                             recovery: ErrorRecoveryContext):
        """Recovery options for checkpoint errors"""
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.IGNORE,
                label="Continue Without Checkpoint",
                description="Skip checkpoint restoration and continue",
                confidence=0.6
            ),
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Create New Checkpoint",
                description="Create a fresh checkpoint",
                confidence=0.7
            ),
        ]

        recovery.suggestions = [
            "Checkpoint file may be corrupted or missing",
            "Consider running without checkpoints",
            "Ensure state directory has write permissions",
        ]

        recovery.can_retry = True

    def _configuration_recovery(self,
                               error: Exception,
                               context: Optional[Dict[str, Any]],
                               recovery: ErrorRecoveryContext):
        """Recovery options for configuration errors"""
        recovery.can_retry = False
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Fix Configuration",
                description="Correct the configuration error",
                confidence=0.9,
                requires_user_input=True
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SUPPORT,
                label="View Documentation",
                description="Check configuration documentation",
                confidence=0.8
            ),
        ]

        recovery.suggestions = [
            "Review the configuration file",
            "Check for required fields",
            "Validate data types and formats",
            "Refer to the configuration documentation",
        ]

        recovery.documentation_link = "https://docs.uat-gateway.dev/configuration"

    def _journey_extraction_recovery(self,
                                     error: Exception,
                                     context: Optional[Dict[str, Any]],
                                     recovery: ErrorRecoveryContext):
        """Recovery options for journey extraction errors"""
        recovery.can_retry = False
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Fix Spec File",
                description="Correct the specification file",
                confidence=0.9,
                requires_user_input=True
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SUPPORT,
                label="View Documentation",
                description="Check spec file format documentation",
                confidence=0.8
            ),
        ]

        recovery.suggestions = [
            "Check the spec file syntax",
            "Ensure all required fields are present",
            "Validate journey definitions",
            "Check for circular references",
        ]

        recovery.documentation_link = "https://docs.uat-gateway.dev/specification"

    def _test_generation_recovery(self,
                                  error: Exception,
                                  context: Optional[Dict[str, Any]],
                                  recovery: ErrorRecoveryContext):
        """Recovery options for test generation errors"""
        recovery.can_retry = True
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RETRY,
                label="Retry Generation",
                description="Attempt to generate tests again",
                confidence=0.6
            ),
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Fix Journey Definition",
                description="Correct the journey causing issues",
                confidence=0.8,
                requires_user_input=True
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP,
                label="Skip Problematic Journey",
                description="Generate tests for other journeys",
                confidence=0.5
            ),
        ]

        recovery.suggestions = [
            "Journey definitions may have issues",
            "Check for missing or invalid steps",
            "Ensure all actions are supported",
        ]

    def _kanban_recovery(self,
                        error: Exception,
                        context: Optional[Dict[str, Any]],
                        recovery: ErrorRecoveryContext):
        """Recovery options for Kanban integration errors"""
        recovery.can_retry = True
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RETRY,
                label="Retry Kanban Update",
                description="Attempt to update Kanban board again",
                confidence=0.7
            ),
            RecoveryAction(
                action_type=RecoveryActionType.IGNORE,
                label="Skip Kanban Update",
                description="Continue without updating Kanban",
                confidence=0.6
            ),
            RecoveryAction(
                action_type=RecoveryActionType.MANUAL_FIX,
                label="Check API Configuration",
                description="Verify Kanban API credentials",
                confidence=0.8,
                requires_user_input=True
            ),
        ]

        recovery.suggestions = [
            "Check Kanban API token and URL",
            "Verify the board exists and is accessible",
            "Check network connectivity to Kanban service",
            "API credentials may have expired",
        ]

    def _generic_recovery(self,
                         error: Exception,
                         context: Optional[Dict[str, Any]],
                         recovery: ErrorRecoveryContext):
        """Generic recovery options for unknown errors"""
        recovery.recovery_actions = [
            RecoveryAction(
                action_type=RecoveryActionType.RETRY,
                label="Retry",
                description="Try the operation again",
                confidence=0.5
            ),
            RecoveryAction(
                action_type=RecoveryActionType.VIEW_LOGS,
                label="View Logs",
                description="Check detailed logs for more information",
                confidence=0.9
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SKIP,
                label="Skip",
                description="Skip this operation and continue",
                confidence=0.3
            ),
            RecoveryAction(
                action_type=RecoveryActionType.SUPPORT,
                label="Contact Support",
                description="Report this issue",
                confidence=0.4
            ),
        ]

        recovery.suggestions = [
            "An unexpected error occurred",
            "Check the logs for more details",
            "Try restarting if the error persists",
        ]

        recovery.can_retry = True
        recovery.estimated_recovery_time_ms = 5000


# ============================================================================
# Global Provider Instance
# ============================================================================

_global_provider: Optional[ErrorRecoveryProvider] = None


def get_error_recovery_provider() -> ErrorRecoveryProvider:
    """Get the global error recovery provider instance"""
    global _global_provider
    if _global_provider is None:
        _global_provider = ErrorRecoveryProvider()
    return _global_provider


__all__ = [
    "RecoveryActionType",
    "RecoveryAction",
    "ErrorRecoveryContext",
    "ErrorRecoveryProvider",
    "get_error_recovery_provider",
]
