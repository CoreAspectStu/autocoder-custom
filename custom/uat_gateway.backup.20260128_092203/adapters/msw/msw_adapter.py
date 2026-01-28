"""
MSW Adapter - Generate Mock Service Worker handlers for API endpoints

This module is responsible for:
- Discovering API endpoints from backend code
- Generating MSW mock handlers for those endpoints
- Creating error scenarios
- Supporting dynamic responses
- Handling realistic delays
"""

import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.adapters.api.api_adapter import APIEndpoint, HTTPMethod, DiscoveryResult


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class MSWHandler:
    """Represents a generated MSW mock handler"""
    endpoint_path: str  # e.g., '/api/users'
    method: str  # 'GET', 'POST', etc.
    handler_code: str  # The generated TypeScript/JavaScript handler code
    response_status: int = 200  # Default response status
    response_body: Dict[str, Any] = field(default_factory=dict)  # Mock response data
    delay_ms: int = 0  # Simulated network delay
    scenario: str = "default"  # default, error, success, etc.
    description: str = ""  # Handler description


@dataclass
class MSWGenerationResult:
    """Result of MSW handler generation"""
    handlers: List[MSWHandler] = field(default_factory=list)
    endpoints_processed: int = 0
    handlers_generated: int = 0
    errors: List[str] = field(default_factory=list)
    output_files: List[str] = field(default_factory=list)  # Generated file paths


# ============================================================================
# MSW Handler Generator
# ============================================================================

class MSWAdapter:
    """
    Generates MSW (Mock Service Worker) handlers for API endpoints.

    This adapter:
    1. Uses APIEndpoint discovery from APIAdapter
    2. Generates TypeScript/JavaScript MSW handlers
    3. Supports multiple scenarios (success, error, etc.)
    4. Outputs complete MSW setup files
    """

    def __init__(self, base_url: str = "http://localhost:4001", default_delay_ms: int = 200):
        """
        Initialize the MSW adapter

        Args:
            base_url: The base URL for API endpoints
            default_delay_ms: Default simulated network delay in milliseconds (default: 200ms)
        """
        self.base_url = base_url
        self.default_delay_ms = default_delay_ms
        self.logger = get_logger(__name__)
        self.handlers: List[MSWHandler] = []

    def generate_handlers(
        self,
        endpoints: List[APIEndpoint],
        output_dir: Optional[Path] = None,
        scenarios: List[str] = None,
        auto_start_worker: bool = True
    ) -> MSWGenerationResult:
        """
        Generate MSW handlers for discovered API endpoints

        Args:
            endpoints: List of discovered API endpoints
            output_dir: Directory to write handler files (optional)
            scenarios: List of scenarios to generate (default, error, etc.)
            auto_start_worker: Whether to auto-start the worker (default: True).
                              Set to False for integration tests where real API is needed.

        Returns:
            MSWGenerationResult with generated handlers
        """
        if scenarios is None:
            scenarios = ["default", "error"]

        result = MSWGenerationResult()
        result.endpoints_processed = len(endpoints)

        self.logger.info(f"Generating MSW handlers for {len(endpoints)} endpoints")

        for endpoint in endpoints:
            try:
                # Generate handlers for each scenario
                for scenario in scenarios:
                    handler = self._generate_handler_for_endpoint(endpoint, scenario)
                    if handler:
                        result.handlers.append(handler)
                        result.handlers_generated += 1
                        self.logger.debug(
                            f"Generated {scenario} handler for {endpoint.method} {endpoint.path}"
                        )

            except Exception as e:
                error_msg = f"Failed to generate handler for {endpoint.path}: {str(e)}"
                result.errors.append(error_msg)
                self.logger.error(error_msg)

        # Write handlers to file if output directory specified
        if output_dir:
            self._write_handlers_to_file(result.handlers, output_dir, auto_start_worker)
            result.output_files = [str(output_dir / "msw-handlers.ts")]

        return result

    def _generate_handler_for_endpoint(
        self,
        endpoint: APIEndpoint,
        scenario: str = "default",
        delay_ms: int = None
    ) -> Optional[MSWHandler]:
        """
        Generate a single MSW handler for an endpoint

        Args:
            endpoint: The API endpoint to generate a handler for
            scenario: The scenario type (default, error, etc.)
            delay_ms: Simulated network delay in milliseconds (optional)

        Returns:
            MSWHandler object or None if generation fails
        """
        # Determine response status based on scenario
        if scenario == "error":
            status_code = 500
            response_body = {"error": "Internal server error", "message": "Mock error response"}
        elif scenario == "not_found":
            status_code = 404
            response_body = {"error": "Not found", "message": "Resource not found"}
        elif scenario == "unauthorized":
            status_code = 401
            response_body = {"error": "Unauthorized", "message": "Authentication required"}
        else:  # default
            status_code = 200
            response_body = self._generate_mock_response_body(endpoint)

        # Determine delay - use provided delay_ms or fall back to realistic defaults
        if delay_ms is None:
            # Auto-generate realistic delays based on scenario
            if scenario == "error":
                delay_ms = 1000  # Errors take longer
            elif scenario == "not_found":
                delay_ms = 200
            elif scenario == "unauthorized":
                delay_ms = 300
            else:
                delay_ms = self.default_delay_ms

        # Generate handler code with delay
        handler_code = self._generate_handler_code(endpoint, status_code, response_body, scenario, delay_ms)

        return MSWHandler(
            endpoint_path=endpoint.path,
            method=endpoint.method.value,
            handler_code=handler_code,
            response_status=status_code,
            response_body=response_body,
            delay_ms=delay_ms,
            scenario=scenario,
            description=f"MSW handler for {endpoint.method} {endpoint.path} ({scenario})"
        )

    def _generate_handler_code(
        self,
        endpoint: APIEndpoint,
        status_code: int,
        response_body: Dict[str, Any],
        scenario: str,
        delay_ms: int = 0
    ) -> str:
        """
        Generate TypeScript MSW handler code

        Args:
            endpoint: The API endpoint
            status_code: Response status code
            response_body: Mock response body
            scenario: Scenario type
            delay_ms: Simulated network delay in milliseconds

        Returns:
            TypeScript code string for the handler
        """
        # Format response body as JSON
        response_json = json.dumps(response_body, indent=2)

        # Generate handler code
        method = endpoint.method.value.lower()

        # Build delay instruction if delay > 0
        delay_instruction = ""
        if delay_ms > 0:
            delay_instruction = f"\n    // Simulate realistic network delay: {delay_ms}ms\n    await new Promise(resolve => setTimeout(resolve, {delay_ms}));"

        # Build the handler
        handler = f"""  // {endpoint.method.value} {endpoint.path} - {scenario}
  rest.{method}('{endpoint.path}', async (req, res, ctx) => {{
    // Response status: {status_code}{delay_instruction}
    return res(
      ctx.status({status_code}),
      ctx.json({response_json})
    );
  }})"""

        return handler

    def _extract_resource_name(self, path: str) -> str:
        """
        Extract the resource name from a path, ignoring path parameters.

        Handles various parameter styles:
        - Express/Koa: /api/users/:id → users
        - FastAPI: /api/users/{user_id} → users
        - Flask: /api/users/<int:id> → users

        Args:
            path: The endpoint path (e.g., '/api/users/:id' or '/api/users')

        Returns:
            The resource name (e.g., 'users') or 'data' if not found
        """
        import re

        # Remove leading/trailing slashes and split
        path_parts = path.strip('/').split('/')

        if not path_parts:
            return "data"

        # Get the last non-empty part
        last_part = path_parts[-1]

        # Check if it's a parameter (starts with : or is wrapped in {} or <>)
        # :param style (Express/Koa)
        if last_part.startswith(':'):
            param_name = last_part[1:]  # Remove the colon
            # Get the resource name from the previous part
            if len(path_parts) >= 2:
                return path_parts[-2]
            return "data"

        # {param} style (FastAPI)
        match = re.match(r'^\{(.+)\}$', last_part)
        if match:
            # It's a parameter, get resource from previous part
            if len(path_parts) >= 2:
                return path_parts[-2]
            return "data"

        # <param> or <type:param> style (Flask)
        match = re.match(r'^<(.+)>$', last_part)
        if match:
            # It's a parameter, get resource from previous part
            if len(path_parts) >= 2:
                return path_parts[-2]
            return "data"

        # Not a parameter, this is the resource name
        return last_part

    def _generate_mock_response_body(self, endpoint: APIEndpoint) -> Dict[str, Any]:
        """
        Generate mock response data based on endpoint characteristics

        Args:
            endpoint: The API endpoint

        Returns:
            Mock response data dictionary
        """
        # Extract resource name from path, ignoring parameters
        # Handles: /api/users/:id, /api/users/{id}, /api/users/<int:id>
        resource_name = self._extract_resource_name(endpoint.path)

        # Generate response based on HTTP method
        if endpoint.method == HTTPMethod.GET:
            # Return list of items or single item
            if endpoint.parameters:  # Has path params (e.g., /users/:id)
                return {
                    "id": "1",
                    "type": resource_name,
                    "attributes": {
                        "name": f"Mock {resource_name}",
                        "createdAt": "2025-01-26T00:00:00Z"
                    }
                }
            else:  # List endpoint
                return {
                    "data": [
                        {
                            "id": "1",
                            "type": resource_name,
                            "attributes": {
                                "name": f"Mock {resource_name} 1"
                            }
                        },
                        {
                            "id": "2",
                            "type": resource_name,
                            "attributes": {
                                "name": f"Mock {resource_name} 2"
                            }
                        }
                    ],
                    "meta": {
                        "total": 2,
                        "page": 1
                    }
                }

        elif endpoint.method == HTTPMethod.POST:
            # Return created resource
            return {
                "id": "new-id-123",
                "type": resource_name,
                "attributes": {
                    "name": f"Created {resource_name}",
                    "createdAt": "2025-01-26T00:00:00Z"
                }
            }

        elif endpoint.method in [HTTPMethod.PUT, HTTPMethod.PATCH]:
            # Return updated resource
            return {
                "id": "1",
                "type": resource_name,
                "attributes": {
                    "name": f"Updated {resource_name}",
                    "updatedAt": "2025-01-26T00:00:00Z"
                }
            }

        elif endpoint.method == HTTPMethod.DELETE:
            # Return success message
            return {
                "success": True,
                "message": f"{resource_name.capitalize()} deleted successfully"
            }

        else:
            # Default response
            return {
                "message": f"Mock response for {endpoint.method.value} {endpoint.path}"
            }

    def _write_handlers_to_file(
        self,
        handlers: List[MSWHandler],
        output_dir: Path,
        auto_start_worker: bool = True
    ) -> None:
        """
        Write generated handlers to a TypeScript file

        Args:
            handlers: List of MSW handlers
            output_dir: Output directory path
            auto_start_worker: Whether to auto-start the worker (default: True)
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "msw-handlers.ts"

        # Generate the complete handlers file
        file_content = self._generate_handlers_file(handlers, auto_start_worker)

        with open(output_file, 'w') as f:
            f.write(file_content)

        self.logger.info(f"Written {len(handlers)} handlers to {output_file}")

    def _generate_handlers_file(self, handlers: List[MSWHandler], auto_start_worker: bool = True) -> str:
        """
        Generate complete MSW handlers TypeScript file

        Args:
            handlers: List of MSW handlers
            auto_start_worker: Whether to auto-start the worker (default: True)

        Returns:
            Complete TypeScript file content
        """
        lines = [
            "// Auto-generated MSW (Mock Service Worker) handlers",
            "// Generated by UAT Gateway MSW Adapter",
            f"// Generated at: {self._get_timestamp()}",
            "",
            "import { http } from 'msw';",
            "import { setupWorker } from 'msw/browser';",
            "",
            "// ===================================================",
            "// MSW Mock Handlers",
            "// ===================================================",
            "//",
            "// This file contains MSW handlers for API endpoint mocking.",
            "//",
            "// USAGE:",
            "//",
            "// For Unit Tests (with mocks):",
            "//   import { worker, startMSW } from './msw-handlers';",
            "//   startMSW();  // Enable mocking",
            "//   // Your test code here - requests will be mocked",
            "//",
            "// For Integration Tests (real API):",
            "//   import { worker } from './msw-handlers';",
            "//   // DO NOT call startMSW() - requests will go to real API",
            "//   // Or call stopMSW() to disable mocking if already started",
            "//",
            "// ===================================================",
            "",
            "",
            "// MSW mock handlers for API endpoints",
            "export const handlers = [",
        ]

        # Add each handler
        for handler in handlers:
            lines.append(handler.handler_code + ",")

        lines.extend([
            "];",
            "",
            "",
            "// ===================================================",
            "// MSW Worker Setup",
            "// ===================================================",
            "",
            "// Setup MSW worker with handlers",
            "export const worker = setupWorker(...handlers);",
            "",
        ])

        # Add start/stop functions and optional auto-start
        if auto_start_worker:
            # Auto-start version (default, for unit tests)
            lines.extend([
                "// ===================================================",
                "// Auto-Start (for unit tests)",
                "// ===================================================",
                "",
                "// Start MSW worker automatically",
                "// This will intercept all matching HTTP requests",
                "worker.start({",
                "  onUnhandledRequest: 'bypass',",
                "});",
                "",
                "",
                "// ===================================================",
                "// Manual Control Functions (for integration tests)",
                "// ===================================================",
                "",
                "// Start MSW manually (if not already started)",
                "export function startMSW() {",
                "  // Worker is already started above, but this function",
                "  // is provided for API compatibility with non-auto-start mode",
                "  return worker;",
                "}",
                "",
                "// Stop MSW to use real API",
                "export function stopMSW() {",
                "  // Note: Once stopped, MSW cannot be restarted in the same session",
                "  // You'll need to reload the page to restart MSW",
                "  return worker.stop();",
                "}",
                "",
                "export default handlers;"
            ])
        else:
            # Manual-start version (for integration tests)
            lines.extend([
                "// ===================================================",
                "// Manual Control Functions",
                "// ===================================================",
                "",
                "// Start MSW to enable mocking",
                "export function startMSW() {",
                "  return worker.start({",
                "    onUnhandledRequest: 'bypass',",
                "  });",
                "}",
                "",
                "// Stop MSW to use real API",
                "export function stopMSW() {",
                "  // Note: Once stopped, MSW cannot be restarted in the same session",
                "  // You'll need to reload the page to restart MSW",
                "  return worker.stop();",
                "}",
                "",
                "",
                "// ===================================================",
                "// Usage Notes",
                "// ===================================================",
                "//",
                "// This file was generated with auto_start_worker=False",
                "// to support integration testing with the real API.",
                "//",
                "// To use mocks in unit tests:",
                "//   import { startMSW } from './msw-handlers';",
                "//   startMSW();  // Call this before your tests",
                "//",
                "// To use real API in integration tests:",
                "//   import { worker } from './msw-handlers';",
                "//   // Don't call startMSW() - requests will go to real API",
                "//",
                "// ===================================================",
                "",
                "export default handlers;"
            ])

        return "\n".join(lines)

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string"""
        from datetime import datetime
        return datetime.now().isoformat()


# ============================================================================
# Utility Functions
# ============================================================================

def validate_handler_syntax(handler_code: str) -> bool:
    """
    Validate that generated handler code has correct syntax

    Args:
        handler_code: The handler code to validate

    Returns:
        True if syntax is valid, False otherwise
    """
    try:
        # Basic syntax check - ensure balanced parentheses and braces
        if handler_code.count('(') != handler_code.count(')'):
            return False
        if handler_code.count('{') != handler_code.count('}'):
            return False
        return True
    except Exception:
        return False


def verify_handler_matches_endpoint(handler: MSWHandler, endpoint: APIEndpoint) -> bool:
    """
    Verify that a handler matches its endpoint

    Args:
        handler: The MSW handler
        endpoint: The API endpoint

    Returns:
        True if handler matches endpoint, False otherwise
    """
    # Check method matches
    if handler.method.lower() != endpoint.method.value.lower():
        return False

    # Check path matches (normalize for comparison)
    handler_path = handler.endpoint_path.strip().lower()
    endpoint_path = endpoint.path.strip().lower()

    if handler_path != endpoint_path:
        return False

    return True
