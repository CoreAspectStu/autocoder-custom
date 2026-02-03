"""
API Adapter - Discover and test API endpoints from backend code

This module is responsible for:
- Scanning backend code to discover API endpoints
- Extracting HTTP methods, routes, and parameters
- Validating response schemas
- Testing authentication
- Testing error handling
- Measuring response times
"""

import ast
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import sys
import json
import requests
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger


# ============================================================================
# Data Models
# ============================================================================

class HTTPMethod(Enum):
    """HTTP methods"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


@dataclass
class APIEndpoint:
    """Represents a discovered API endpoint"""
    path: str  # e.g., '/api/users/:id'
    method: HTTPMethod  # GET, POST, etc.
    route: str  # The base route (e.g., '/api/users')
    parameters: List[str] = field(default_factory=list)  # ['id', 'name']
    query_params: List[str] = field(default_factory=list)  # ['page', 'limit']
    body_params: List[str] = field(default_factory=list)  # ['email', 'password']
    file: str = ""  # Source file where endpoint was found
    line: int = 0  # Line number in source file
    middleware: List[str] = field(default_factory=list)  # ['auth', 'validate']
    description: str = ""  # Description from comments


@dataclass
class DiscoveryResult:
    """Result of endpoint discovery"""
    endpoints: List[APIEndpoint] = field(default_factory=list)
    files_scanned: int = 0
    endpoints_found: int = 0
    errors: List[str] = field(default_factory=list)
    frameworks_detected: List[str] = field(default_factory=list)


@dataclass
class APIMeasurement:
    """Represents a single API response time measurement"""
    endpoint_path: str  # e.g., '/api/users'
    method: str  # 'GET', 'POST', etc.
    response_time_ms: float  # Response time in milliseconds
    status_code: int  # HTTP status code
    timestamp: datetime  # When the measurement was taken
    success: bool  # Whether the request succeeded
    error: Optional[str] = None  # Error message if failed
    response_size: int = 0  # Size of response in bytes


@dataclass
class PerformanceStats:
    """Performance statistics for API endpoints"""
    endpoint_path: str
    method: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time_ms: float = 0.0
    min_response_time_ms: float = float('inf')
    max_response_time_ms: float = 0.0
    slow_requests_count: int = 0  # Requests exceeding threshold
    last_measurement: Optional[datetime] = None


@dataclass
class APITestResult:
    """Result of testing an API endpoint"""
    endpoint: APIEndpoint
    success: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
    response_body: Optional[str] = None


@dataclass
class ErrorTestCase:
    """Represents a single error test case"""
    endpoint: APIEndpoint
    invalid_data: Dict[str, Any]  # Invalid payload to send
    expected_status: Optional[int] = None  # Expected error status code
    description: str = ""  # Description of what's being tested


@dataclass
class ErrorTestResult:
    """Result of testing error handling"""
    endpoint: APIEndpoint
    test_case: ErrorTestCase
    success: bool  # True if error was properly returned
    status_code: int  # Actual status code received
    response_body: Dict[str, Any]  # Response data
    error_message: str  # Error message from response
    is_helpful: bool  # True if error message is helpful
    documentation: str = ""  # Documentation of the error response
    timestamp: str = ""
    duration_ms: float = 0.0


# ============================================================================
# Schema Validation Data Models (Feature #128)
# ============================================================================

class SchemaDataType(Enum):
    """JSON Schema data types"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


@dataclass
class SchemaProperty:
    """Definition of a property in a schema"""
    name: str
    type: SchemaDataType
    required: bool = False
    description: str = ""
    properties: Optional[Dict[str, 'SchemaProperty']] = None  # For nested objects
    items: Optional['SchemaProperty'] = None  # For array items


@dataclass
class ResponseSchema:
    """Schema definition for API response"""
    status_code: int
    content_type: str = "application/json"
    properties: Dict[str, SchemaProperty] = None
    array_items: Optional[SchemaProperty] = None  # If response is an array
    description: str = ""

    def __post_init__(self):
        if self.properties is None:
            self.properties = {}


@dataclass
class ValidationResult:
    """Result of schema validation"""
    is_valid: bool
    errors: List[str] = None
    warnings: List[str] = None
    missing_fields: List[str] = None
    type_errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.missing_fields is None:
            self.missing_fields = []
        if self.type_errors is None:
            self.type_errors = []


# ============================================================================
# API Adapter
# ============================================================================

class APIAdapter:
    """
    Discover API endpoints from backend code

    Supports:
    - Express.js (app.get, router.post, etc.)
    - Fastify (fastify.get, fastify.post, etc.)
    - Koa (router.get, router.post, etc.)
    - Python Flask (@app.route)
    - Python FastAPI (@app.get, @router.post)
    """

    def __init__(
        self,
        backend_path: Optional[str] = None,
        frameworks: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ):
        """
        Initialize the API adapter

        Args:
            backend_path: Path to backend code directory
            frameworks: List of frameworks to detect (default: auto-detect)
            exclude_patterns: Patterns to exclude (e.g., ['node_modules', 'test'])
        """
        self.logger = get_logger(__name__)
        self.backend_path = Path(backend_path) if backend_path else None
        self.frameworks = frameworks or []
        self.exclude_patterns = exclude_patterns or ['node_modules', '__pycache__', '.git', 'dist', 'build']

        # Framework detection patterns
        self.framework_patterns = {
            'express': [
                (r'app\.(get|post|put|delete|patch)\(', 'Express app'),
                (r'router\.(get|post|put|delete|patch)\(', 'Express router'),
                (r'express\(\)', 'Express'),
            ],
            'fastify': [
                (r'fastify\.(get|post|put|delete|patch)\(', 'Fastify'),
                (r'fastify\.route\(', 'Fastify route'),
            ],
            'koa': [
                (r'router\.(get|post|put|delete|patch)\(', 'Koa Router'),
                (r'koa-router', 'Koa Router'),
            ],
            'flask': [
                (r'@app\.route', 'Flask'),
                (r'@.*\.route\(', 'Flask blueprint'),
                (r'flask\.', 'Flask'),
            ],
            'fastapi': [
                (r'@app\.(get|post|put|delete|patch)', 'FastAPI'),
                (r'@router\.(get|post|put|delete|patch)', 'FastAPI router'),
                (r'from fastapi import', 'FastAPI'),
            ],
        }

        # HTTP method patterns
        self.method_patterns = {
            'get': HTTPMethod.GET,
            'post': HTTPMethod.POST,
            'put': HTTPMethod.PUT,
            'delete': HTTPMethod.DELETE,
            'patch': HTTPMethod.PATCH,
            'head': HTTPMethod.HEAD,
            'options': HTTPMethod.OPTIONS,
        }

    def discover_endpoints(self, backend_path: Optional[str] = None) -> DiscoveryResult:
        """
        Scan backend code and discover API endpoints

        Args:
            backend_path: Path to backend code (overrides init value)

        Returns:
            DiscoveryResult with discovered endpoints
        """
        result = DiscoveryResult()

        # Use provided path or default
        scan_path = Path(backend_path) if backend_path else self.backend_path

        if not scan_path or not scan_path.exists():
            result.errors.append(f"Backend path not found: {scan_path}")
            self.logger.error(f"Backend path not found: {scan_path}")
            return result

        self.logger.info(f"Scanning backend code in: {scan_path}")

        # Detect frameworks if not specified
        if not self.frameworks:
            self.frameworks = self._detect_frameworks(scan_path)
            result.frameworks_detected = self.frameworks

        if not self.frameworks:
            result.errors.append("No supported frameworks detected")
            self.logger.warning("No supported frameworks detected")
            return result

        self.logger.info(f"Detected frameworks: {', '.join(self.frameworks)}")

        # Scan files based on framework
        for framework in self.frameworks:
            if framework in ['express', 'fastify', 'koa']:
                endpoints = self._scan_javascript_files(scan_path, framework)
            elif framework in ['flask', 'fastapi']:
                endpoints = self._scan_python_files(scan_path, framework)
            else:
                self.logger.warning(f"Unsupported framework: {framework}")
                continue

            result.endpoints.extend(endpoints)

        # Update statistics
        result.files_scanned = len(list(scan_path.rglob('*')))
        result.endpoints_found = len(result.endpoints)

        self.logger.info(
            f"Discovery complete: {result.endpoints_found} endpoints "
            f"found in {result.files_scanned} files"
        )

        return result

    def _detect_frameworks(self, scan_path: Path) -> List[str]:
        """
        Detect which backend frameworks are used

        Args:
            scan_path: Path to scan

        Returns:
            List of detected framework names
        """
        detected = set()

        # Check package.json for Node.js frameworks
        package_json = scan_path / 'package.json'
        if package_json.exists():
            content = package_json.read_text()
            if 'express' in content.lower():
                detected.add('express')
            if 'fastify' in content.lower():
                detected.add('fastify')
            if 'koa' in content.lower() or 'koa-router' in content:
                detected.add('koa')

        # Check requirements.txt or pyproject.toml for Python frameworks
        requirements_txt = scan_path / 'requirements.txt'
        pyproject_toml = scan_path / 'pyproject.toml'

        for dep_file in [requirements_txt, pyproject_toml]:
            if dep_file.exists():
                content = dep_file.read_text()
                if 'flask' in content.lower():
                    detected.add('flask')
                if 'fastapi' in content.lower():
                    detected.add('fastapi')

        # Scan source files for framework imports
        for js_file in scan_path.rglob('*.js'):
            if self._should_exclude_file(js_file):
                continue
            try:
                content = js_file.read_text()
                if 'express' in content:
                    detected.add('express')
                if 'fastify' in content:
                    detected.add('fastify')
                if 'koa' in content:
                    detected.add('koa')
            except Exception:
                pass

        for py_file in scan_path.rglob('*.py'):
            if self._should_exclude_file(py_file):
                continue
            try:
                content = py_file.read_text()
                if 'flask' in content:
                    detected.add('flask')
                if 'fastapi' in content:
                    detected.add('fastapi')
            except Exception:
                pass

        return list(detected)

    def _scan_javascript_files(
        self,
        scan_path: Path,
        framework: str
    ) -> List[APIEndpoint]:
        """
        Scan JavaScript files for API endpoints

        Args:
            scan_path: Path to scan
            framework: Framework name (express, fastify, koa)

        Returns:
            List of discovered endpoints
        """
        endpoints = []

        for js_file in scan_path.rglob('*.js'):
            if self._should_exclude_file(js_file):
                continue

            try:
                file_endpoints = self._extract_from_javascript(js_file, framework, scan_path)
                endpoints.extend(file_endpoints)
            except Exception as e:
                self.logger.warning(f"Error scanning {js_file}: {e}")

        return endpoints

    def _extract_from_javascript(
        self,
        js_file: Path,
        framework: str,
        scan_path: Path
    ) -> List[APIEndpoint]:
        """
        Extract endpoints from a JavaScript file

        Args:
            js_file: Path to JavaScript file
            framework: Framework name
            scan_path: Base path for relative file paths

        Returns:
            List of endpoints found in file
        """
        endpoints = []

        try:
            content = js_file.read_text()
            lines = content.split('\n')

            # Try to make path relative to scan_path
            try:
                file_path = str(js_file.relative_to(scan_path))
            except ValueError:
                # If files are on different drives on Windows, use absolute path
                file_path = str(js_file)

            for line_num, line in enumerate(lines, 1):
                # Match patterns like: app.get('/path', handler)
                # or: router.post('/path', handler)
                if framework == 'express':
                    matches = re.finditer(
                        r'(app|router)\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']',
                        line
                    )
                elif framework == 'fastify':
                    matches = re.finditer(
                        r'(fastify|app)\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']',
                        line
                    )
                elif framework == 'koa':
                    matches = re.finditer(
                        r'router\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']',
                        line
                    )
                else:
                    continue

                for match in matches:
                    method_str = match.group(2).lower()
                    path = match.group(3)

                    # Extract parameters from path
                    parameters = self._extract_path_parameters(path)

                    # Extract query parameters for pagination detection
                    query_params = self._extract_query_params_from_comments(lines, line_num)

                    endpoint = APIEndpoint(
                        path=path,
                        method=self.method_patterns.get(method_str, HTTPMethod.GET),
                        route=self._extract_base_route(path),
                        parameters=parameters,
                        query_params=query_params,
                        file=file_path,
                        line=line_num,
                    )

                    endpoints.append(endpoint)

        except Exception as e:
            self.logger.warning(f"Error parsing {js_file}: {e}")

        return endpoints

    def _scan_python_files(
        self,
        scan_path: Path,
        framework: str
    ) -> List[APIEndpoint]:
        """
        Scan Python files for API endpoints

        Args:
            scan_path: Path to scan
            framework: Framework name (flask, fastapi)

        Returns:
            List of discovered endpoints
        """
        endpoints = []

        for py_file in scan_path.rglob('*.py'):
            if self._should_exclude_file(py_file):
                continue

            try:
                file_endpoints = self._extract_from_python(py_file, framework)
                endpoints.extend(file_endpoints)
            except Exception as e:
                self.logger.warning(f"Error scanning {py_file}: {e}")

        return endpoints

    def _extract_from_python(
        self,
        py_file: Path,
        framework: str,
        scan_path: Path
    ) -> List[APIEndpoint]:
        """
        Extract endpoints from a Python file

        Args:
            py_file: Path to Python file
            framework: Framework name
            scan_path: Base path for relative file paths

        Returns:
            List of endpoints found in file
        """
        endpoints = []

        try:
            content = py_file.read_text()
            lines = content.split('\n')

            # Try to make path relative to scan_path
            try:
                file_path = str(py_file.relative_to(scan_path))
            except ValueError:
                file_path = str(py_file)

            # Look for decorator patterns
            for line_num, line in enumerate(lines, 1):
                if framework == 'flask':
                    # Match: @app.route('/path', methods=['GET'])
                    matches = re.finditer(
                        r'@.*\.route\s*\(\s*["\']([^"\']+)["\'][^)]*\)',
                        line
                    )
                elif framework == 'fastapi':
                    # Match: @app.get('/path') or @router.post('/path')
                    matches = re.finditer(
                        r'@.*\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']',
                        line
                    )
                else:
                    continue

                for match in matches:
                    if framework == 'flask':
                        path = match.group(1)
                        # Look ahead for methods parameter
                        methods_line = ' '.join(lines[max(0, line_num-2):line_num+2])
                        methods_match = re.search(r'methods\s*=\s*\[([^\]]+)\]', methods_line)
                        if methods_match:
                            methods_str = methods_match.group(1)
                            method_names = re.findall(r'["\'](GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)["\']', methods_str)
                        else:
                            method_names = ['GET']  # Default for Flask
                    else:  # fastapi
                        method_str = match.group(1).lower()
                        path = match.group(2)
                        method_names = [method_str]

                    # Extract parameters from path
                    parameters = self._extract_path_parameters(path)

                    # Extract query parameters for pagination detection
                    query_params = self._extract_query_params_from_comments(lines, line_num)

                    for method_name in method_names:
                        endpoint = APIEndpoint(
                            path=path,
                            method=self.method_patterns.get(method_name.lower(), HTTPMethod.GET),
                            route=self._extract_base_route(path),
                            parameters=parameters,
                            query_params=query_params,
                            file=file_path,
                            line=line_num,
                        )

                        endpoints.append(endpoint)

        except Exception as e:
            self.logger.warning(f"Error parsing {py_file}: {e}")

        return endpoints

    def _extract_path_parameters(self, path: str) -> List[str]:
        """
        Extract parameter names from route path

        Examples:
            '/users/:id' -> ['id']
            '/posts/:postId/comments/:commentId' -> ['postId', 'commentId']
            '/api/users/<int:user_id>' -> ['user_id']

        Args:
            path: Route path

        Returns:
            List of parameter names
        """
        parameters = []

        # Express/Koa style: /users/:id
        if ':' in path:
            parameters = re.findall(r':(\w+)', path)

        # Flask style: /users/<int:id> or /users/<user_id>
        elif '<' in path and '>' in path:
            parameters = re.findall(r'<(?:\w+:)?(\w+)>', path)

        # FastAPI style: /users/{user_id}
        elif '{' in path and '}' in path:
            parameters = re.findall(r'\{(\w+)\}', path)

        return parameters

    def _extract_query_params_from_comments(
        self,
        lines: List[str],
        line_num: int
    ) -> List[str]:
        """
        Extract query parameters from nearby comments or code

        Looks for common pagination parameters like page, limit, offset, cursor
        in comments within 3 lines above the route definition.

        Args:
            lines: All lines in the file
            line_num: Current line number (1-indexed)

        Returns:
            List of query parameter names found
        """
        query_params = []

        # Look at lines above the current line
        start_line = max(0, line_num - 4)
        context_lines = lines[start_line:line_num]

        # Join lines and search for pagination-related terms
        context = '\n'.join(context_lines).lower()

        # Common pagination parameter names
        pagination_params = ['page', 'limit', 'offset', 'cursor', 'per_page', 'pagesize']

        for param in pagination_params:
            if param in context:
                query_params.append(param)

        return list(set(query_params))  # Remove duplicates

    def _extract_base_route(self, path: str) -> str:
        """
        Extract base route from path (without parameters)

        Examples:
            '/users/:id' -> '/users'
            '/api/v1/posts/:postId/comments' -> '/api/v1/posts/comments'
            '/users/{id}' -> '/users'
            '/users/<int:id>' -> '/users'

        Args:
            path: Full route path

        Returns:
            Base route
        """
        # Remove Express/Koa style parameters: /:id, /:postId
        base = re.sub(r'/:[\w]+', '', path)

        # Remove FastAPI style parameters: /{id}, /{postId}
        base = re.sub(r'/\{[\w]+\}', '', base)

        # Remove Flask style parameters: /<int:id>, /<id>
        base = re.sub(r'/<[^>]+>', '', base)

        # Ensure leading slash
        if not base.startswith('/'):
            base = '/' + base

        return base

    def _should_exclude_file(self, file_path: Path) -> bool:
        """
        Check if file should be excluded from scanning

        Args:
            file_path: File path to check

        Returns:
            True if file should be excluded
        """
        # Check against exclude patterns
        for pattern in self.exclude_patterns:
            if pattern in str(file_path):
                return True

        return False

    def get_endpoint_summary(self, endpoints: List[APIEndpoint]) -> Dict[str, Any]:
        """
        Generate summary statistics for discovered endpoints

        Args:
            endpoints: List of discovered endpoints

        Returns:
            Summary statistics
        """
        if not endpoints:
            return {
                'total': 0,
                'by_method': {},
                'by_route': {},
                'unique_parameters': set(),
            }

        by_method = {}
        by_route = {}
        all_params = set()

        for endpoint in endpoints:
            # Count by method
            method_name = endpoint.method.value
            by_method[method_name] = by_method.get(method_name, 0) + 1

            # Count by route
            by_route[endpoint.route] = by_route.get(endpoint.route, 0) + 1

            # Collect parameters
            all_params.update(endpoint.parameters)

        return {
            'total': len(endpoints),
            'by_method': by_method,
            'by_route': by_route,
            'unique_parameters': list(all_params),
        }

    # ========================================================================
    # API Testing and Response Time Measurement
    # ========================================================================

    def test_endpoint(
        self,
        endpoint: APIEndpoint,
        base_url: str,
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
        auth: Optional[Tuple[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None
    ) -> APITestResult:
        """
        Test an API endpoint and measure response time

        Args:
            endpoint: The endpoint to test
            base_url: Base URL for the API (e.g., 'http://localhost:4001')
            timeout: Request timeout in seconds
            headers: HTTP headers to include
            auth: Basic auth tuple (username, password)
            params: Query parameters
            body: Request body for POST/PUT/PATCH

        Returns:
            APITestResult with timing and status information
        """
        result = APITestResult(endpoint=endpoint, success=False)

        # Construct full URL
        url = f"{base_url.rstrip('/')}{endpoint.path}"

        try:
            # Prepare request arguments
            request_kwargs = {
                'timeout': timeout,
                'headers': headers or {},
            }

            if auth:
                request_kwargs['auth'] = auth
            if params:
                request_kwargs['params'] = params
            if body and endpoint.method in [HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH]:
                request_kwargs['json'] = body

            # Measure response time
            start_time = time.time()

            response = requests.request(
                method=endpoint.method.value,
                url=url,
                **request_kwargs
            )

            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000

            # Update result
            result.success = response.status_code < 400
            result.status_code = response.status_code
            result.response_time_ms = response_time_ms

            try:
                result.response_body = response.text
            except Exception:
                result.response_body = None

            self.logger.info(
                f"{endpoint.method.value} {endpoint.path} - "
                f"Status: {response.status_code}, "
                f"Time: {response_time_ms:.2f}ms"
            )

        except requests.exceptions.Timeout:
            result.error = f"Request timeout after {timeout}s"
            self.logger.warning(f"Timeout: {endpoint.method.value} {endpoint.path}")

        except requests.exceptions.ConnectionError as e:
            result.error = f"Connection error: {str(e)}"
            self.logger.warning(f"Connection error: {endpoint.method.value} {endpoint.path}")

        except Exception as e:
            result.error = f"Request failed: {str(e)}"
            self.logger.error(f"Request failed: {endpoint.method.value} {endpoint.path}: {e}")

        return result

    def measure_endpoint(
        self,
        endpoint: APIEndpoint,
        base_url: str,
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[APIMeasurement]:
        """
        Measure response time for an endpoint

        Args:
            endpoint: The endpoint to measure
            base_url: Base URL for the API
            timeout: Request timeout in seconds
            headers: HTTP headers to include
            params: Query parameters

        Returns:
            APIMeasurement with timing data, or None if request failed
        """
        # Construct full URL
        url = f"{base_url.rstrip('/')}{endpoint.path}"

        try:
            # Measure response time
            start_time = time.time()

            response = requests.get(
                url,
                timeout=timeout,
                headers=headers or {},
                params=params
            )

            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000

            # Create measurement
            measurement = APIMeasurement(
                endpoint_path=endpoint.path,
                method=endpoint.method.value,
                response_time_ms=response_time_ms,
                status_code=response.status_code,
                timestamp=datetime.now(),
                success=response.status_code < 400,
                error=None if response.status_code < 400 else f"HTTP {response.status_code}",
                response_size=len(response.content)
            )

            self.logger.debug(
                f"Measured {endpoint.method.value} {endpoint.path}: "
                f"{response_time_ms:.2f}ms (Status: {response.status_code})"
            )

            return measurement

        except Exception as e:
            self.logger.error(f"Failed to measure {endpoint.path}: {e}")
            return None

    def track_performance(
        self,
        measurements: List[APIMeasurement],
        slow_threshold_ms: float = 1000.0
    ) -> Dict[str, PerformanceStats]:
        """
        Track performance statistics from measurements

        Args:
            measurements: List of API measurements
            slow_threshold_ms: Threshold for flagging slow requests (ms)

        Returns:
            Dictionary mapping endpoint paths to PerformanceStats
        """
        stats_by_endpoint: Dict[str, PerformanceStats] = {}

        for measurement in measurements:
            key = f"{measurement.method} {measurement.endpoint_path}"

            if key not in stats_by_endpoint:
                stats_by_endpoint[key] = PerformanceStats(
                    endpoint_path=measurement.endpoint_path,
                    method=measurement.method
                )

            stats = stats_by_endpoint[key]

            # Update counters
            stats.total_requests += 1
            if measurement.success:
                stats.successful_requests += 1
            else:
                stats.failed_requests += 1

            # Update response time statistics
            rt = measurement.response_time_ms
            stats.avg_response_time_ms = (
                (stats.avg_response_time_ms * (stats.total_requests - 1) + rt)
                / stats.total_requests
            )

            if rt < stats.min_response_time_ms:
                stats.min_response_time_ms = rt
            if rt > stats.max_response_time_ms:
                stats.max_response_time_ms = rt

            # Flag slow requests
            if rt > slow_threshold_ms:
                stats.slow_requests_count += 1

            # Update last measurement timestamp
            if stats.last_measurement is None or measurement.timestamp > stats.last_measurement:
                stats.last_measurement = measurement.timestamp

        return stats_by_endpoint

    def get_slow_requests(
        self,
        measurements: List[APIMeasurement],
        threshold_ms: float = 1000.0
    ) -> List[APIMeasurement]:
        """
        Get list of slow requests exceeding threshold

        Args:
            measurements: List of API measurements
            threshold_ms: Response time threshold in milliseconds

        Returns:
            List of measurements exceeding threshold
        """
        slow_requests = [
            m for m in measurements
            if m.response_time_ms > threshold_ms
        ]

        # Sort by response time (slowest first)
        slow_requests.sort(key=lambda m: m.response_time_ms, reverse=True)

        return slow_requests

    def generate_performance_report(
        self,
        stats: Dict[str, PerformanceStats]
    ) -> str:
        """
        Generate a human-readable performance report

        Args:
            stats: Performance statistics by endpoint

        Returns:
            Formatted report string
        """
        if not stats:
            return "No performance data available."

        lines = [
            "=" * 70,
            "API Performance Report",
            "=" * 70,
            ""
        ]

        for key, stat in stats.items():
            lines.append(f"{stat.method} {stat.endpoint_path}")
            lines.append("-" * 70)
            lines.append(f"  Total Requests:     {stat.total_requests}")
            lines.append(f"  Successful:         {stat.successful_requests}")
            lines.append(f"  Failed:             {stat.failed_requests}")
            lines.append(f"  Avg Response Time:  {stat.avg_response_time_ms:.2f}ms")
            lines.append(f"  Min Response Time:  {stat.min_response_time_ms:.2f}ms")
            lines.append(f"  Max Response Time:  {stat.max_response_time_ms:.2f}ms")
            lines.append(f"  Slow Requests:      {stat.slow_requests_count}")

            if stat.last_measurement:
                lines.append(f"  Last Measurement:   {stat.last_measurement.strftime('%Y-%m-%d %H:%M:%S')}")

            # Calculate success rate
            if stat.total_requests > 0:
                success_rate = (stat.successful_requests / stat.total_requests) * 100
                lines.append(f"  Success Rate:       {success_rate:.1f}%")

            lines.append("")

        return "\n".join(lines)

    # ========================================================================
    # Schema Validation (Feature #128)
    # ========================================================================

    def validate_response(
        self,
        response_data: Dict[str, Any],
        schema: ResponseSchema
    ) -> ValidationResult:
        """
        Validate API response against a schema

        Args:
            response_data: Response body as dictionary
            schema: Expected response schema

        Returns:
            ValidationResult with validation status and errors
        """
        result = ValidationResult(is_valid=True)

        # Handle array responses
        if schema.array_items is not None:
            if not isinstance(response_data, list):
                result.is_valid = False
                result.type_errors.append(
                    f"Response should be an array, got {type(response_data).__name__}"
                )
                return result

            # Validate each item in the array
            for idx, item in enumerate(response_data):
                if isinstance(item, dict):
                    item_result = self._validate_object_against_properties(
                        item,
                        {"item": schema.array_items}
                    )
                    if not item_result.is_valid:
                        result.is_valid = False
                        result.errors.extend([
                            f"Array item {idx}: {err}"
                            for err in item_result.errors
                        ])
                        result.type_errors.extend([
                            f"Array item {idx}: {err}"
                            for err in item_result.type_errors
                        ])
                        result.missing_fields.extend([
                            f"Array item {idx}: {field}"
                            for field in item_result.missing_fields
                        ])
                else:
                    result.is_valid = False
                    result.type_errors.append(
                        f"Array item {idx} should be object, got {type(item).__name__}"
                    )

            return result

        # Handle object responses
        if not isinstance(response_data, dict):
            result.is_valid = False
            result.type_errors.append(
                f"Response should be an object, got {type(response_data).__name__}"
            )
            return result

        # Validate object properties
        return self._validate_object_against_properties(response_data, schema.properties)

    def _validate_object_against_properties(
        self,
        data: Dict[str, Any],
        properties: Dict[str, SchemaProperty]
    ) -> ValidationResult:
        """
        Validate an object against property definitions

        Args:
            data: Object to validate
            properties: Property definitions

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        # Check required fields
        for prop_name, prop_def in properties.items():
            if prop_def.required and prop_name not in data:
                result.is_valid = False
                result.missing_fields.append(prop_name)
                result.errors.append(f"Missing required field: {prop_name}")

        # Validate present fields
        for field_name, field_value in data.items():
            if field_name not in properties:
                # Unknown field - add warning but don't fail
                result.warnings.append(f"Unknown field: {field_name}")
                continue

            prop_def = properties[field_name]

            # Check data type
            if not self._check_type(field_value, prop_def.type):
                result.is_valid = False
                result.type_errors.append(
                    f"Type mismatch for '{field_name}': expected {prop_def.type.value}, got {type(field_value).__name__}"
                )
                result.errors.append(
                    f"Type mismatch for '{field_name}': expected {prop_def.type.value}, got {type(field_value).__name__}"
                )

            # Validate nested objects
            if prop_def.type == SchemaDataType.OBJECT and prop_def.properties:
                if isinstance(field_value, dict):
                    nested_result = self._validate_object_against_properties(
                        field_value,
                        prop_def.properties
                    )
                    if not nested_result.is_valid:
                        result.is_valid = False
                        result.errors.extend([
                            f"Nested object '{field_name}': {err}"
                            for err in nested_result.errors
                        ])
                        result.type_errors.extend([
                            f"Nested object '{field_name}': {err}"
                            for err in nested_result.type_errors
                        ])
                        result.missing_fields.extend([
                            f"Nested object '{field_name}': {field}"
                            for field in nested_result.missing_fields
                        ])

            # Validate array items
            if prop_def.type == SchemaDataType.ARRAY and prop_def.items:
                if isinstance(field_value, list):
                    for idx, item in enumerate(field_value):
                        if not self._check_type(item, prop_def.items.type):
                            result.is_valid = False
                            result.type_errors.append(
                                f"Array '{field_name}' item {idx}: expected {prop_def.items.type.value}, got {type(item).__name__}"
                            )

        return result

    def _check_type(self, value: Any, expected_type: SchemaDataType) -> bool:
        """
        Check if a value matches the expected type

        Args:
            value: Value to check
            expected_type: Expected data type

        Returns:
            True if type matches
        """
        if value is None:
            # Null is valid for non-required fields
            return True

        type_checks = {
            SchemaDataType.STRING: lambda v: isinstance(v, str),
            SchemaDataType.INTEGER: lambda v: isinstance(v, int) and not isinstance(v, bool),
            SchemaDataType.NUMBER: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            SchemaDataType.BOOLEAN: lambda v: isinstance(v, bool),
            SchemaDataType.ARRAY: lambda v: isinstance(v, list),
            SchemaDataType.OBJECT: lambda v: isinstance(v, dict),
            SchemaDataType.NULL: lambda v: v is None,
        }

        checker = type_checks.get(expected_type)
        if checker:
            return checker(value)

        return False

    # ========================================================================
    # Error Handling Testing (Feature #130)
    # ========================================================================

    def generate_error_test_cases(
        self,
        endpoints: List[APIEndpoint],
        base_url: str
    ) -> List[ErrorTestCase]:
        """
        Generate error test cases for discovered endpoints

        Args:
            endpoints: List of discovered endpoints
            base_url: Base URL for the API (e.g., 'http://localhost:4000')

        Returns:
            List of error test cases
        """
        test_cases = []

        for endpoint in endpoints:
            # Generate test cases based on HTTP method and parameters
            if endpoint.method in [HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH]:
                # Test with invalid JSON
                test_cases.append(ErrorTestCase(
                    endpoint=endpoint,
                    invalid_data={"invalid": "data that should fail"},
                    expected_status=400,
                    description=f"Send malformed data to {endpoint.path}"
                ))

                # Test with missing required fields
                test_cases.append(ErrorTestCase(
                    endpoint=endpoint,
                    invalid_data={},
                    expected_status=400,
                    description=f"Send empty payload to {endpoint.path}"
                ))

                # Test with wrong data types
                test_cases.append(ErrorTestCase(
                    endpoint=endpoint,
                    invalid_data={"field": 123},  # Should be string
                    expected_status=400,
                    description=f"Send wrong data types to {endpoint.path}"
                ))

            elif endpoint.method == HTTPMethod.GET:
                # Test with invalid query parameters
                test_cases.append(ErrorTestCase(
                    endpoint=endpoint,
                    invalid_data={"invalid_param": "value"},
                    expected_status=400,
                    description=f"Send invalid query params to {endpoint.path}"
                ))

            # Test with invalid path parameters
            if endpoint.parameters:
                test_cases.append(ErrorTestCase(
                    endpoint=endpoint,
                    invalid_data={"invalid": "params"},
                    expected_status=404,
                    description=f"Send invalid path parameters to {endpoint.path}"
                ))

        return test_cases

    def test_error_handling(
        self,
        test_case: ErrorTestCase,
        base_url: str
    ) -> ErrorTestResult:
        """
        Test error handling for a specific endpoint

        Args:
            test_case: Error test case to execute
            base_url: Base URL for the API

        Returns:
            ErrorTestResult with test outcome
        """
        start_time = datetime.now()
        url = f"{base_url}{test_case.endpoint.path}"

        try:
            # Prepare request based on HTTP method
            method = test_case.endpoint.method.value
            headers = {'Content-Type': 'application/json'}

            if method in ['POST', 'PUT', 'PATCH']:
                response = requests.request(
                    method=method,
                    url=url,
                    json=test_case.invalid_data,
                    headers=headers,
                    timeout=10
                )
            else:  # GET, DELETE, etc.
                response = requests.request(
                    method=method,
                    url=url,
                    params=test_case.invalid_data,
                    headers=headers,
                    timeout=10
                )

            # Calculate duration
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Parse response
            try:
                response_body = response.json()
            except ValueError:
                response_body = {"raw": response.text}

            # Extract error message
            error_message = ""
            if isinstance(response_body, dict):
                error_message = response_body.get('error') or \
                               response_body.get('message') or \
                               response_body.get('msg') or \
                               str(response_body)

            # Determine if error is helpful
            is_helpful = self._is_error_message_helpful(error_message, response.status_code)

            # Generate documentation
            documentation = self._document_error_response(
                test_case.endpoint,
                response.status_code,
                error_message,
                response_body
            )

            # Check if test passed
            success = (
                400 <= response.status_code < 600 and  # Error status code
                len(error_message) > 0 and  # Has error message
                is_helpful  # Message is helpful
            )

            return ErrorTestResult(
                endpoint=test_case.endpoint,
                test_case=test_case,
                success=success,
                status_code=response.status_code,
                response_body=response_body,
                error_message=error_message,
                is_helpful=is_helpful,
                documentation=documentation,
                timestamp=datetime.now().isoformat(),
                duration_ms=duration_ms
            )

        except requests.exceptions.Timeout:
            return ErrorTestResult(
                endpoint=test_case.endpoint,
                test_case=test_case,
                success=False,
                status_code=0,
                response_body={"error": "Request timeout"},
                error_message="Request timeout - endpoint did not respond",
                is_helpful=False,
                documentation="Endpoint timeout - no error response received",
                timestamp=datetime.now().isoformat(),
                duration_ms=0
            )

        except requests.exceptions.ConnectionError:
            return ErrorTestResult(
                endpoint=test_case.endpoint,
                test_case=test_case,
                success=False,
                status_code=0,
                response_body={"error": "Connection failed"},
                error_message="Connection refused - endpoint not accessible",
                is_helpful=False,
                documentation="Connection error - endpoint may not be running",
                timestamp=datetime.now().isoformat(),
                duration_ms=0
            )

        except Exception as e:
            return ErrorTestResult(
                endpoint=test_case.endpoint,
                test_case=test_case,
                success=False,
                status_code=0,
                response_body={"error": str(e)},
                error_message=f"Test execution error: {str(e)}",
                is_helpful=False,
                documentation=f"Test error: {str(e)}",
                timestamp=datetime.now().isoformat(),
                duration_ms=0
            )

    def _is_error_message_helpful(
        self,
        error_message: str,
        status_code: int
    ) -> bool:
        """
        Determine if error message is helpful

        A helpful error message:
        - Explains what went wrong
        - Provides actionable guidance
        - Is not generic

        Args:
            error_message: Error message from response
            status_code: HTTP status code

        Returns:
            True if message is helpful
        """
        if not error_message or len(error_message) < 10:
            return False

        # Generic unhelpful messages
        unhelpful_patterns = [
            'error',
            'failed',
            'invalid',
            'bad request',
            'not found',
            'unauthorized',
            'forbidden'
        ]

        message_lower = error_message.lower()

        # Check if message is too generic
        if message_lower.strip() in unhelpful_patterns:
            return False

        # Check if message provides context
        has_context = (
            'field' in message_lower or
            'required' in message_lower or
            'missing' in message_lower or
            'format' in message_lower or
            'expected' in message_lower or
            'must' in message_lower or
            'cannot' in message_lower or
            ('invalid' in message_lower and len(message_lower) > 20)
        )

        return has_context

    def _document_error_response(
        self,
        endpoint: APIEndpoint,
        status_code: int,
        error_message: str,
        response_body: Dict[str, Any]
    ) -> str:
        """
        Generate documentation for error response

        Args:
            endpoint: API endpoint
            status_code: HTTP status code
            error_message: Error message
            response_body: Full response body

        Returns:
            Formatted documentation string
        """
        doc_lines = [
            f"Endpoint: {endpoint.method.value} {endpoint.path}",
            f"Status Code: {status_code}",
            f"Error Message: {error_message}",
            f"Response Body: {json.dumps(response_body, indent=2)}",
        ]

        # Add status code explanation
        status_explanations = {
            400: "Bad Request - Invalid input data",
            401: "Unauthorized - Authentication required",
            403: "Forbidden - Insufficient permissions",
            404: "Not Found - Resource does not exist",
            405: "Method Not Allowed - HTTP method not supported",
            409: "Conflict - Resource conflicts with existing data",
            422: "Unprocessable Entity - Semantic errors",
            429: "Too Many Requests - Rate limit exceeded",
            500: "Internal Server Error - Server error",
            502: "Bad Gateway - Upstream server error",
            503: "Service Unavailable - Server temporarily unavailable",
        }

        if status_code in status_explanations:
            doc_lines.append(f"Explanation: {status_explanations[status_code]}")

        return "\n".join(doc_lines)

    def test_all_error_handling(
        self,
        endpoints: List[APIEndpoint],
        base_url: str
    ) -> List[ErrorTestResult]:
        """
        Test error handling for all endpoints

        Args:
            endpoints: List of discovered endpoints
            base_url: Base URL for the API

        Returns:
            List of error test results
        """
        # Generate test cases
        test_cases = self.generate_error_test_cases(endpoints, base_url)

        # Execute all tests
        results = []
        for test_case in test_cases:
            result = self.test_error_handling(test_case, base_url)
            results.append(result)

            self.logger.info(
                f"Tested {test_case.endpoint.method.value} {test_case.endpoint.path}: "
                f"{'PASS' if result.success else 'FAIL'} "
                f"(status={result.status_code})"
            )

        return results

    def get_error_test_summary(
        self,
        results: List[ErrorTestResult]
    ) -> Dict[str, Any]:
        """
        Generate summary of error test results

        Args:
            results: List of error test results

        Returns:
            Summary statistics
        """
        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed

        # Status code distribution
        status_codes = {}
        for result in results:
            status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1

        # Helpful error messages
        helpful_count = sum(1 for r in results if r.is_helpful)

        return {
            'total_tests': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
            'status_codes': status_codes,
            'helpful_errors': helpful_count,
            'helpful_error_rate': (helpful_count / total * 100) if total > 0 else 0,
            'avg_duration_ms': sum(r.duration_ms for r in results) / total if total > 0 else 0,
        }

    # ========================================================================
    # Feature #127: HTTP Method Testing & Coverage
    # ========================================================================

    def get_methods_tested(self) -> Dict[str, int]:
        """
        Get count of tested endpoints by HTTP method

        Returns:
            Dictionary with method names as keys and test counts as values
        """
        if not hasattr(self, 'test_results'):
            self.test_results = []

        methods_tested = {
            'GET': 0,
            'POST': 0,
            'PUT': 0,
            'DELETE': 0,
            'PATCH': 0,
            'HEAD': 0,
            'OPTIONS': 0
        }

        for result in self.test_results:
            # APITestResult has endpoint, which has method
            method = result.endpoint.method.value
            methods_tested[method] += 1

        return methods_tested

    def run_api_tests(
        self,
        endpoints: Optional[List[APIEndpoint]] = None,
        auth_token: Optional[str] = None
    ) -> List[APITestResult]:
        """
        Run API tests for specified endpoints

        Args:
            endpoints: List of endpoints to test (defaults to discovered endpoints)
            auth_token: Optional auth token for requests

        Returns:
            List of APITestResult

        Step 2 of feature #127 acceptance criteria
        """
        # Discover endpoints if not provided
        if endpoints is None:
            discovery_result = self.discover_endpoints()
            endpoints = discovery_result.endpoints

        if not endpoints:
            self.logger.warning("No endpoints to test")
            return []

        self.logger.info(f"Running API tests for {len(endpoints)} endpoints...")

        # Initialize test results if needed
        if not hasattr(self, 'test_results'):
            self.test_results = []

        results = []
        for endpoint in endpoints:
            try:
                # Use existing test_endpoint method
                test_result = self.test_endpoint(
                    route=endpoint.path,
                    method=endpoint.method.value,
                    auth_token=auth_token
                )

                # Track the result
                self.test_results.append(test_result)
                results.append(test_result)

                self.logger.debug(
                    f"Test completed: {endpoint.method.value} {endpoint.path} - "
                    f"{'PASS' if test_result.success else 'FAIL'}"
                )

            except Exception as e:
                self.logger.error(f"Test failed for {endpoint.method.value} {endpoint.path}: {e}")
                # Create failure result
                failure_result = APITestResult(
                    method=endpoint.method,
                    route=endpoint.path,
                    success=False,
                    status_code=0,
                    duration_ms=0,
                    error=str(e)
                )
                self.test_results.append(failure_result)
                results.append(failure_result)

        self.logger.info(f"Completed {len(results)} API tests")
        return results

    def verify_method_tested(self, method: HTTPMethod) -> bool:
        """
        Verify that at least one endpoint with the given method has been tested

        Args:
            method: HTTP method to check

        Returns:
            True if at least one endpoint with this method has been tested

        Steps 3-6 of feature #127 acceptance criteria
        """
        methods_tested = self.get_methods_tested()
        count = methods_tested.get(method.value, 0)
        is_tested = count > 0

        self.logger.info(
            f"Method {method.value}: {count} endpoints tested - "
            f"{'✓ TESTED' if is_tested else '✗ NOT TESTED'}"
        )

        return is_tested

    def verify_all_methods_tested(self) -> Dict[str, bool]:
        """
        Verify that all HTTP methods (GET, POST, PUT, DELETE, PATCH) have been tested

        Returns:
            Dictionary with method names as keys and tested status as values

        Comprehensive check for steps 3-6 of feature #127
        """
        required_methods = [
            HTTPMethod.GET,
            HTTPMethod.POST,
            HTTPMethod.PUT,
            HTTPMethod.DELETE,
            HTTPMethod.PATCH
        ]

        results = {}
        for method in required_methods:
            results[method.value] = self.verify_method_tested(method)

        return results

    def generate_method_coverage_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive API method coverage report

        Returns:
            Coverage report with statistics by HTTP method
        """
        methods_tested = self.get_methods_tested()

        # Discover endpoints to get total counts
        discovery_result = self.discover_endpoints()
        endpoints = discovery_result.endpoints

        # Count endpoints by method
        method_totals = {
            'GET': 0,
            'POST': 0,
            'PUT': 0,
            'DELETE': 0,
            'PATCH': 0,
            'HEAD': 0,
            'OPTIONS': 0
        }

        for endpoint in endpoints:
            method_totals[endpoint.method.value] += 1

        # Calculate coverage percentages
        coverage = {}
        for method in method_totals:
            total = method_totals[method]
            tested = methods_tested.get(method, 0)
            coverage[method] = {
                'total': total,
                'tested': tested,
                'not_tested': total - tested,
                'coverage_percentage': (tested / total * 100) if total > 0 else 0
            }

        # Overall statistics
        total_endpoints = sum(method_totals.values())
        total_tested = sum(methods_tested.values())

        return {
            'summary': {
                'total_endpoints': total_endpoints,
                'tested_endpoints': total_tested,
                'coverage_percentage': (total_tested / total_endpoints * 100) if total_endpoints > 0 else 0
            },
            'by_method': coverage,
            'methods_tested': methods_tested,
            'method_totals': method_totals
        }
