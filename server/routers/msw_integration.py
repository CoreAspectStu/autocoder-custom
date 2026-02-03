"""
MSW (Mock Service Worker) Integration Router

Provides API endpoints for generating and managing MSW mock handlers.

Endpoints:
- POST /api/msw/generate - Generate MSW handlers for API endpoints
- POST /api/msw/scenarios - Create mock scenarios (error, delay, etc.)
- GET /api/msw/handlers - List all generated MSW handlers
- GET /api/msw/handlers/{id} - Get details of a specific handler
- DELETE /api/msw/handlers/{id} - Delete a mock handler
- GET /api/msw/health - Health check endpoint
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
import sys
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import MSW adapter from UAT Gateway
try:
    from custom.uat_gateway.adapters.msw.msw_adapter import (
        MSWAdapter,
        MSWHandler,
        MSWGenerationResult
    )
    from custom.uat_gateway.adapters.api.api_adapter import (
        APIAdapter,
        APIEndpoint,
        HTTPMethod
    )
    MSW_ADAPTER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  MSW Adapter not available: {e}")
    MSW_ADAPTER_AVAILABLE = False

router = APIRouter(
    prefix="/api/msw",
    tags=["msw-integration"]
)

# ============================================================================
# Request/Response Models
# ============================================================================

class GenerateHandlersRequest(BaseModel):
    """Request to generate MSW handlers"""
    project_path: str
    backend_path: Optional[str] = None
    scenarios: List[str] = ["default", "error"]
    default_delay_ms: int = 200
    auto_start_worker: bool = True


class HandlerInfo(BaseModel):
    """Information about a generated handler"""
    endpoint_path: str
    method: str
    scenario: str
    delay_ms: int
    response_status: int
    description: str


class GenerateResponse(BaseModel):
    """Response for handler generation"""
    handlers_generated: int
    endpoints_processed: int
    output_files: List[str]
    errors: List[str]


class ScenarioRequest(BaseModel):
    """Request to create a mock scenario"""
    project_path: str
    endpoint_path: str
    method: str
    scenario_type: str  # 'error', 'delay', 'success', 'empty'
    delay_ms: int = 0
    error_status: int = 500
    error_message: str = "Internal Server Error"


class ScenarioResponse(BaseModel):
    """Response for scenario creation"""
    scenario_id: str
    endpoint_path: str
    method: str
    scenario_type: str
    handler_code: str


# ============================================================================
# Global MSW Adapter Instance (per project)
# ============================================================================

_adapters: Dict[str, MSWAdapter] = {}


def get_adapter(project_path: str) -> MSWAdapter:
    """Get or create an MSW adapter for the project"""
    if project_path not in _adapters:
        if not MSW_ADAPTER_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="MSW Adapter not available. Install required dependencies."
            )

        _adapters[project_path] = MSWAdapter(
            base_url="http://localhost:4001",
            default_delay_ms=200
        )
    return _adapters[project_path]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/generate")
async def generate_handlers(request: GenerateHandlersRequest) -> GenerateResponse:
    """
    Generate MSW handlers for API endpoints.

    This endpoint discovers API endpoints from the backend code
    and generates MSW mock handlers for them.

    Args:
        request: GenerateHandlersRequest with generation details

    Returns:
        Summary of generated handlers
    """
    if not MSW_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="MSW Adapter not available. Install required dependencies."
        )

    try:
        # First discover API endpoints
        backend_path = request.backend_path or str(Path(request.project_path) / "src")
        api_adapter = APIAdapter()
        discovery = api_adapter.discover_endpoints(backend_path)

        if not discovery.endpoints:
            return GenerateResponse(
                handlers_generated=0,
                endpoints_processed=0,
                output_files=[],
                errors=["No API endpoints found in backend code"]
            )

        # Generate MSW handlers
        msw_adapter = get_adapter(request.project_path)
        msw_adapter.default_delay_ms = request.default_delay_ms

        output_dir = Path(request.project_path) / "msw"
        result = msw_adapter.generate_handlers(
            endpoints=discovery.endpoints,
            output_dir=output_dir,
            scenarios=request.scenarios,
            auto_start_worker=request.auto_start_worker
        )

        return GenerateResponse(
            handlers_generated=result.handlers_generated,
            endpoints_processed=result.endpoints_processed,
            output_files=result.output_files,
            errors=result.errors
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate handlers: {str(e)}"
        )


@router.post("/scenarios")
async def create_scenario(request: ScenarioRequest) -> ScenarioResponse:
    """
    Create a custom mock scenario.

    This endpoint creates a specific scenario (error, delay, etc.)
    for an API endpoint.

    Args:
        request: ScenarioRequest with scenario details

    Returns:
        Generated scenario handler code
    """
    if not MSW_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="MSW Adapter not available. Install required dependencies."
        )

    try:
        msw_adapter = get_adapter(request.project_path)

        # Create endpoint object
        endpoint = APIEndpoint(
            path=request.endpoint_path,
            method=HTTPMethod[request.method.upper()],
            route=request.endpoint_path
        )

        # Generate handler for the scenario
        handler = msw_adapter._generate_handler_for_endpoint(
            endpoint=endpoint,
            scenario=request.scenario_type,
            delay_ms=request.delay_ms
        )

        if not handler:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to generate handler for {request.method} {request.endpoint_path}"
            )

        scenario_id = f"{request.method}_{request.endpoint_path}_{request.scenario_type}".replace("/", "_")

        return ScenarioResponse(
            scenario_id=scenario_id,
            endpoint_path=request.endpoint_path,
            method=request.method,
            scenario_type=request.scenario_type,
            handler_code=handler.handler_code
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create scenario: {str(e)}"
        )


@router.get("/handlers")
async def list_handlers(project_path: str) -> Dict[str, Any]:
    """
    List all generated MSW handlers for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        List of all MSW handlers with metadata
    """
    if not MSW_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="MSW Adapter not available. Install required dependencies."
        )

    try:
        msw_dir = Path(project_path) / "msw"
        handlers_file = msw_dir / "msw-handlers.ts"

        if not handlers_file.exists():
            return {
                "handlers": [],
                "total_count": 0,
                "handlers_file": str(handlers_file)
            }

        # Parse the handlers file to extract handler information
        handlers = []
        content = handlers_file.read_text()

        # Simple regex-based extraction of handler definitions
        # This is a placeholder - in production, you'd use proper TypeScript parsing
        import re

        # Find http.XXX patterns
        patterns = re.findall(r'http\.(get|post|put|delete|patch)\([\'"]([^\'"]+)[\'"]', content)

        for method, path in set(patterns):
            handlers.append({
                "method": method.upper(),
                "path": path,
                "scenarios": ["default", "error"],  # Placeholder
                "delay_ms": 200
            })

        return {
            "handlers": handlers,
            "total_count": len(handlers),
            "handlers_file": str(handlers_file)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list handlers: {str(e)}"
        )


@router.delete("/handlers/{handler_id}")
async def delete_handler(project_path: str, handler_id: str) -> Dict[str, Any]:
    """
    Delete a specific MSW handler.

    Args:
        project_path: Path to the project directory
        handler_id: ID of the handler to delete

    Returns:
        Success status
    """
    if not MSW_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="MSW Adapter not available. Install required dependencies."
        )

    try:
        # This is a placeholder - in production, you'd:
        # 1. Parse the handlers file
        # 2. Remove the specific handler
        # 3. Rewrite the file

        return {
            "message": f"Handler '{handler_id}' deleted (placeholder - not implemented)",
            "handler_id": handler_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete handler: {str(e)}"
        )


@router.get("/scenarios")
async def list_scenarios() -> Dict[str, Any]:
    """
    List available scenario types.

    Returns:
        List of available scenario types with descriptions
    """
    scenarios = {
        "default": {
            "description": "Default successful response",
            "response_status": 200,
            "delay_ms": 200
        },
        "success": {
            "description": "Successful response with custom data",
            "response_status": 200,
            "delay_ms": 200
        },
        "error": {
            "description": "Error response with error message",
            "response_status": 500,
            "delay_ms": 200
        },
        "delay": {
            "description": "Response with simulated network delay",
            "response_status": 200,
            "delay_ms": 5000
        },
        "empty": {
            "description": "Empty response (204 No Content)",
            "response_status": 204,
            "delay_ms": 200
        },
        "timeout": {
            "description": "Simulated timeout (no response)",
            "response_status": None,
            "delay_ms": 30000
        },
        "unauthorized": {
            "description": "Unauthorized access (401)",
            "response_status": 401,
            "delay_ms": 200
        },
        "forbidden": {
            "description": "Forbidden access (403)",
            "response_status": 403,
            "delay_ms": 200
        },
        "not_found": {
            "description": "Resource not found (404)",
            "response_status": 404,
            "delay_ms": 200
        }
    }

    return {
        "scenarios": scenarios,
        "total_count": len(scenarios)
    }


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for MSW integration service.

    Returns:
        Status of the MSW integration service
    """
    return {
        "service": "msw-integration",
        "available": MSW_ADAPTER_AVAILABLE,
        "version": "1.0.0",
        "supported_frameworks": ["playwright", "msw"],
        "endpoints": [
            "POST /api/msw/generate",
            "POST /api/msw/scenarios",
            "GET /api/msw/handlers",
            "DELETE /api/msw/handlers/{id}",
            "GET /api/msw/scenarios",
            "GET /api/msw/health"
        ]
    }
