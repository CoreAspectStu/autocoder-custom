"""
API Testing Router

Provides API endpoints for API testing using the UAT Gateway API adapter.

Endpoints:
- POST /api/api-testing/discover - Discover API endpoints from backend code
- POST /api/api-testing/test - Test a single API endpoint
- POST /api/api-testing/test-all - Test all discovered endpoints
- POST /api/api-testing/error-tests - Test error handling for endpoints
- GET /api/api-testing/performance - Get performance statistics
- GET /api/api-testing/slow-requests - Get list of slow API requests
- GET /api/api-testing/health - Health check endpoint
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
import sys
from datetime import datetime
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import API adapter from UAT Gateway
try:
    from custom.uat_gateway.adapters.api.api_adapter import (
        APIAdapter,
        APIEndpoint,
        HTTPMethod,
        DiscoveryResult,
        APITestResult,
        ErrorTestResult,
        PerformanceStats
    )
    API_ADAPTER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  API Adapter not available: {e}")
    API_ADAPTER_AVAILABLE = False

router = APIRouter(
    prefix="/api/api-testing",
    tags=["api-testing"]
)

# ============================================================================
# Request/Response Models
# ============================================================================

class DiscoverEndpointsRequest(BaseModel):
    """Request to discover API endpoints"""
    project_path: str
    backend_path: Optional[str] = None  # Path to backend source code
    framework: Optional[str] = None  # 'fastapi', 'express', etc.


class TestEndpointRequest(BaseModel):
    """Request to test a single API endpoint"""
    project_path: str
    base_url: str  # e.g., 'http://localhost:3000'
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str  # e.g., '/api/users'
    headers: Optional[Dict[str, str]] = None
    query_params: Optional[Dict[str, Any]] = None
    body: Optional[Dict[str, Any]] = None
    timeout: int = 5000


class TestAllEndpointsRequest(BaseModel):
    """Request to test all discovered endpoints"""
    project_path: str
    base_url: str
    headers: Optional[Dict[str, str]] = None
    timeout: int = 5000


class ErrorTestRequest(BaseModel):
    """Request to test error handling"""
    project_path: str
    base_url: str
    endpoints: List[Dict[str, Any]]  # List of endpoints to test


class PerformanceRequest(BaseModel):
    """Request for performance statistics"""
    project_path: str
    threshold_ms: float = 1000  # Slow request threshold


class EndpointSummary(BaseModel):
    """Summary of a discovered endpoint"""
    path: str
    method: str
    parameters: List[str]
    query_params: List[str]
    body_params: List[str]
    middleware: List[str]


class DiscoveryResponse(BaseModel):
    """Response for endpoint discovery"""
    endpoints: List[Dict[str, Any]]
    files_scanned: int
    endpoints_found: int
    frameworks_detected: List[str]


class TestResponse(BaseModel):
    """Response for endpoint testing"""
    endpoint: Dict[str, Any]
    success: bool
    status_code: Optional[int]
    response_time_ms: Optional[float]
    error: Optional[str]


# ============================================================================
# Global API Adapter Instance (per project)
# ============================================================================

_adapters: Dict[str, APIAdapter] = {}


def get_adapter(project_path: str) -> APIAdapter:
    """Get or create an API adapter for the project"""
    if project_path not in _adapters:
        if not API_ADAPTER_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="API Adapter not available. Install required dependencies."
            )

        _adapters[project_path] = APIAdapter(
            output_dir=str(Path(project_path) / "api" / "reports")
        )
    return _adapters[project_path]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/discover")
async def discover_endpoints(request: DiscoverEndpointsRequest) -> DiscoveryResponse:
    """
    Discover API endpoints from backend source code.

    This endpoint scans the backend code to find API endpoints,
    extracting HTTP methods, routes, and parameters.

    Args:
        request: DiscoverEndpointsRequest with discovery details

    Returns:
        List of discovered endpoints with metadata
    """
    if not API_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="API Adapter not available. Install required dependencies."
        )

    try:
        backend_path = request.backend_path or str(Path(request.project_path) / "src")
        adapter = get_adapter(request.project_path)

        result = adapter.discover_endpoints(backend_path)

        return DiscoveryResponse(
            endpoints=[
                {
                    "path": ep.path,
                    "method": ep.method.value,
                    "route": ep.route,
                    "parameters": ep.parameters,
                    "query_params": ep.query_params,
                    "body_params": ep.body_params,
                    "middleware": ep.middleware,
                    "file": ep.file,
                    "line": ep.line
                }
                for ep in result.endpoints
            ],
            files_scanned=result.files_scanned,
            endpoints_found=result.endpoints_found,
            frameworks_detected=result.frameworks_detected
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to discover endpoints: {str(e)}"
        )


@router.post("/test")
async def test_endpoint(request: TestEndpointRequest) -> TestResponse:
    """
    Test a single API endpoint.

    This endpoint sends an HTTP request to the specified API endpoint
    and returns the response details.

    Args:
        request: TestEndpointRequest with test details

    Returns:
        Test result with status code, response time, and response body
    """
    if not API_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="API Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(request.project_path)

        # Create endpoint object
        endpoint = APIEndpoint(
            path=request.path,
            method=HTTPMethod[request.method.upper()],
            route=request.path
        )

        # Test the endpoint
        result = adapter.test_endpoint(
            endpoint=endpoint,
            base_url=request.base_url,
            headers=request.headers or {},
            query_params=request.query_params or {},
            body=request.body,
            timeout=request.timeout
        )

        return TestResponse(
            endpoint={
                "path": result.endpoint.path,
                "method": result.endpoint.method.value
            },
            success=result.success,
            status_code=result.status_code,
            response_time_ms=result.response_time_ms,
            error=result.error
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test endpoint: {str(e)}"
        )


@router.post("/test-all")
async def test_all_endpoints(request: TestAllEndpointsRequest) -> Dict[str, Any]:
    """
    Test all discovered API endpoints.

    This endpoint runs tests on all discovered API endpoints
    and returns a summary of results.

    Args:
        request: TestAllEndpointsRequest with test details

    Returns:
        Summary of all test results
    """
    if not API_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="API Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(request.project_path)

        # First discover endpoints
        backend_path = str(Path(request.project_path) / "src")
        discovery = adapter.discover_endpoints(backend_path)

        if not discovery.endpoints:
            return {
                "total_endpoints": 0,
                "tested": 0,
                "passed": 0,
                "failed": 0,
                "results": []
            }

        # Test all endpoints
        results = adapter.run_api_tests(
            endpoints=discovery.endpoints,
            base_url=request.base_url,
            headers=request.headers or {},
            timeout=request.timeout
        )

        return {
            "total_endpoints": len(discovery.endpoints),
            "tested": len(results),
            "passed": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "results": [
                {
                    "path": r.endpoint.path,
                    "method": r.endpoint.method.value,
                    "success": r.success,
                    "status_code": r.status_code,
                    "response_time_ms": r.response_time_ms,
                    "error": r.error
                }
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test endpoints: {str(e)}"
        )


@router.post("/error-tests")
async def test_error_handling(request: ErrorTestRequest) -> Dict[str, Any]:
    """
    Test error handling for API endpoints.

    This endpoint tests how API endpoints handle various error conditions
    such as invalid data, missing parameters, etc.

    Args:
        request: ErrorTestRequest with test details

    Returns:
        Summary of error handling test results
    """
    if not API_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="API Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(request.project_path)

        # Convert endpoint dictionaries to APIEndpoint objects
        endpoints = []
        for ep_data in request.endpoints:
            endpoints.append(APIEndpoint(
                path=ep_data.get("path", "/"),
                method=HTTPMethod[ep_data.get("method", "GET").upper()],
                route=ep_data.get("route", "")
            ))

        # Run error tests
        results = adapter.test_all_error_handling(
            endpoints=endpoints,
            base_url=request.base_url
        )

        return {
            "total_tests": len(results),
            "passed": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "helpful_errors": sum(1 for r in results if r.is_helpful),
            "results": [
                {
                    "path": r.endpoint.path,
                    "method": r.endpoint.method.value,
                    "test_description": r.test_case.description,
                    "success": r.success,
                    "status_code": r.status_code,
                    "is_helpful": r.is_helpful,
                    "error_message": r.error_message
                }
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test error handling: {str(e)}"
        )


@router.post("/performance")
async def get_performance_stats(request: PerformanceRequest) -> Dict[str, Any]:
    """
    Get performance statistics for API endpoints.

    This endpoint returns performance metrics including average response times,
    slow requests, and request counts.

    Args:
        request: PerformanceRequest with project details

    Returns:
        Performance statistics for all measured endpoints
    """
    if not API_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="API Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(request.project_path)

        # Get performance report
        report = adapter.generate_performance_report(
            slow_threshold_ms=request.threshold_ms
        )

        return report
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get performance stats: {str(e)}"
        )


@router.post("/slow-requests")
async def get_slow_requests(request: PerformanceRequest) -> Dict[str, Any]:
    """
    Get list of slow API requests.

    This endpoint returns all requests that exceeded the threshold
    response time.

    Args:
        request: PerformanceRequest with project details

    Returns:
        List of slow requests with details
    """
    if not API_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="API Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(request.project_path)

        slow_requests = adapter.get_slow_requests(
            threshold_ms=request.threshold_ms
        )

        return {
            "threshold_ms": request.threshold_ms,
            "count": len(slow_requests),
            "requests": [
                {
                    "endpoint_path": r.endpoint_path,
                    "method": r.method,
                    "response_time_ms": r.response_time_ms,
                    "status_code": r.status_code,
                    "timestamp": r.timestamp.isoformat()
                }
                for r in slow_requests
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get slow requests: {str(e)}"
        )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for API testing service.

    Returns:
        Status of the API testing service
    """
    return {
        "service": "api-testing",
        "available": API_ADAPTER_AVAILABLE,
        "version": "1.0.0",
        "supported_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        "endpoints": [
            "POST /api/api-testing/discover",
            "POST /api/api-testing/test",
            "POST /api/api-testing/test-all",
            "POST /api/api-testing/error-tests",
            "POST /api/api-testing/performance",
            "POST /api/api-testing/slow-requests",
            "GET /api/api-testing/health"
        ]
    }
