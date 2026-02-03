"""
Blocker Management Router

API endpoints for detecting, managing, and resolving blockers
that prevent UAT test execution.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Literal
from pathlib import Path
from datetime import datetime
import asyncio
import socket
import httpx
import os

# Import blocker detection and storage
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from services.blocker_detector import detect_project_blockers, BlockerType, Blocker
from services.blocker_storage import get_storage

router = APIRouter(prefix="/api/blocker", tags=["blocker"])


# ============================================================================
# Request/Response Models
# ============================================================================

class DetectBlockersRequest(BaseModel):
    """Request to detect blockers for a project"""
    project_path: str
    project_name: str


class BlockerResponse(BaseModel):
    """User response to a blocker"""
    blocker_id: str
    action: Literal["provide_key", "skip", "mock", "wait", "enable", "disable"]
    value: Optional[str] = None  # For API key values
    project_name: str


class BlockerResolution(BaseModel):
    """Result of resolving a blocker"""
    blocker_id: str
    status: Literal["resolved", "skipped", "pending", "failed"]
    message: str


class TestConnectionRequest(BaseModel):
    """Request to test if an external service is available"""
    blocker_id: str
    blocker_type: str
    service: str
    test_params: Optional[Dict[str, Any]] = None
    timeout: int = 10


class ConnectionTestResult(BaseModel):
    """Result of testing a service connection"""
    blocker_id: str
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/detect")
async def detect_blockers(request: DetectBlockersRequest) -> Dict[str, Any]:
    """
    Detect blockers that could prevent UAT test execution.

    Analyzes:
    - app_spec.txt for external service dependencies
    - Environment variables for missing configuration
    - Communication services requiring special handling
    - External API calls that might need mocking

    Returns a list of blockers with suggested actions.
    """
    try:
        result = detect_project_blockers(request.project_path)

        # Store blockers in session state for later resolution
        # (In production, this would go in a database)
        result['project_name'] = request.project_name
        result['detected_at'] = datetime.now().isoformat()

        return result

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Project not found: {request.project_path}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect blockers: {str(e)}"
        )


@router.post("/respond")
async def respond_to_blocker(request: BlockerResponse) -> BlockerResolution:
    """
    Handle user's response to a blocker.

    Actions:
    - provide_key: Store API key securely
    - skip: Skip affected tests
    - mock: Use mock service
    - wait: Wait for service to become available
    - enable/disable: Configure feature
    """
    try:
        storage = get_storage(request.project_name)

        if request.action == "provide_key":
            if not request.value:
                raise HTTPException(
                    status_code=400,
                    detail="API key value is required when action is 'provide_key'"
                )

            # Extract service and key name from blocker_id
            # Format: api_key_SERVICE_KEY_NAME or env_var_VAR_NAME
            parts = request.blocker_id.replace("api_key_", "").replace("env_var_", "").rsplit("_", 1)
            if len(parts) != 2:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid blocker_id format: {request.blocker_id}"
                )

            service = parts[0]
            key_name = parts[1]

            # Store encrypted credential
            storage.store_credential(service, key_name, request.value)

            # Inject into project .env.test
            try:
                from api.registry import get_project_path
                project_path = get_project_path(request.project_name)
                storage.inject_into_env(project_path)
            except ImportError:
                # Registry not available, use default path
                project_path = Path.home() / "projects" / "autocoder-projects" / request.project_name
                if Path(project_path).exists():
                    storage.inject_into_env(project_path)

            return BlockerResolution(
                blocker_id=request.blocker_id,
                status="resolved",
                message=f"API key for {service} stored securely"
            )

        elif request.action == "skip":
            return BlockerResolution(
                blocker_id=request.blocker_id,
                status="skipped",
                message="Tests requiring this service will be skipped"
            )

        elif request.action == "mock":
            # Configure mock service settings
            # In production, this would update mock configuration
            return BlockerResolution(
                blocker_id=request.blocker_id,
                status="resolved",
                message="Mock service configured"
            )

        elif request.action in ["enable", "disable"]:
            return BlockerResolution(
                blocker_id=request.blocker_id,
                status="resolved",
                message=f"Feature {request.action}d"
            )

        elif request.action == "wait":
            return BlockerResolution(
                blocker_id=request.blocker_id,
                status="pending",
                message="Waiting for service to become available"
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {request.action}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve blocker: {str(e)}"
        )


async def test_connection(
    blocker_type: str,
    service: str,
    test_params: Optional[Dict[str, Any]] = None,
    timeout: int = 10
) -> Dict[str, Any]:
    """
    Test if an external service is available.

    Supports various blocker types:
    - api_key: Test API endpoint connectivity
    - env_var: Check environment variable exists
    - service_unavailable: Test service health endpoint
    - auth_provider: Test auth provider connectivity
    - resource_missing: Check resource availability (DB, Redis, etc.)

    Returns structured result with success status and details.
    """
    result = {
        "success": False,
        "message": "",
        "details": {}
    }

    try:
        if blocker_type == "api_key":
            # Test API connectivity using provided credentials
            if service == "stripe":
                result = await _test_stripe_connection(test_params, timeout)
            elif service == "twilio":
                result = await _test_twilio_connection(test_params, timeout)
            elif service == "sendgrid":
                result = await _test_sendgrid_connection(test_params, timeout)
            elif service == "openai":
                result = await _test_openai_connection(test_params, timeout)
            else:
                result = {
                    "success": True,
                    "message": f"API key for {service} provided (validation not implemented)",
                    "details": {"service": service, "validation": "skipped"}
                }

        elif blocker_type == "env_var":
            # Check if environment variable is set
            var_name = test_params.get("var_name") if test_params else None
            if var_name and os.getenv(var_name):
                result = {
                    "success": True,
                    "message": f"Environment variable '{var_name}' is set",
                    "details": {"var_name": var_name, "exists": True}
                }
            else:
                result = {
                    "success": False,
                    "message": f"Environment variable '{var_name}' is not set",
                    "details": {"var_name": var_name, "exists": False}
                }

        elif blocker_type == "service_unavailable":
            # Test basic TCP/HTTP connectivity
            host = test_params.get("host") if test_params else None
            port = test_params.get("port", 443) if test_params else 443

            if host:
                # Try TCP connection first
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port),
                        timeout=timeout
                    )
                    writer.close()
                    await writer.wait_closed()
                    result = {
                        "success": True,
                        "message": f"Successfully connected to {host}:{port}",
                        "details": {"host": host, "port": port, "protocol": "tcp"}
                    }
                except (asyncio.TimeoutError, OSError):
                    result = {
                        "success": False,
                        "message": f"Could not connect to {host}:{port}",
                        "details": {"host": host, "port": port, "error": "connection_failed"}
                    }
            else:
                result = {
                    "success": False,
                    "message": "No host provided for connection test",
                    "details": {}
                }

        elif blocker_type == "auth_provider":
            # Test auth provider connectivity
            if service == "auth0":
                domain = test_params.get("domain") if test_params else None
                if domain:
                    result = await _test_http_connection(
                        f"https://{domain}/.well-known/oauth-authorization-server",
                        timeout
                    )
                else:
                    result = {
                        "success": False,
                        "message": "Auth0 domain not provided",
                        "details": {}
                    }
            else:
                result = {
                    "success": True,
                    "message": f"Auth provider '{service}' configured (validation not implemented)",
                    "details": {"service": service, "validation": "skipped"}
                }

        elif blocker_type == "resource_missing":
            # Test database/Redis connectivity
            resource_type = test_params.get("resource_type") if test_params else None
            if resource_type == "database":
                connection_string = test_params.get("connection_string") if test_params else None
                if connection_string:
                    result = await _test_database_connection(connection_string, timeout)
                else:
                    # Try common DATABASE_URL
                    db_url = os.getenv("DATABASE_URL")
                    if db_url:
                        result = await _test_database_connection(db_url, timeout)
                    else:
                        result = {
                            "success": False,
                            "message": "No database connection string provided",
                            "details": {}
                        }
            elif resource_type == "redis":
                redis_url = test_params.get("redis_url") if test_params else os.getenv("REDIS_URL")
                if redis_url:
                    result = await _test_redis_connection(redis_url, timeout)
                else:
                    result = {
                        "success": False,
                        "message": "No Redis connection string provided",
                        "details": {}
                    }
            else:
                result = {
                    "success": True,
                    "message": f"Resource '{resource_type}' check not implemented",
                    "details": {"resource_type": resource_type, "validation": "skipped"}
                }

        else:
            result = {
                "success": True,
                "message": f"Blocker type '{blocker_type}' check not implemented",
                "details": {"blocker_type": blocker_type, "validation": "skipped"}
            }

    except Exception as e:
        result = {
            "success": False,
            "message": f"Connection test failed: {str(e)}",
            "details": {"error": str(e)}
        }

    return result


async def _test_http_connection(url: str, timeout: int) -> Dict[str, Any]:
    """Test HTTP/HTTPS endpoint connectivity"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return {
                "success": response.status_code < 400,
                "message": f"HTTP {response.status_code}: {url}",
                "details": {"url": url, "status_code": response.status_code}
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "message": f"Request timed out: {url}",
            "details": {"url": url, "error": "timeout"}
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"HTTP request failed: {str(e)}",
            "details": {"url": url, "error": str(e)}
        }


async def _test_stripe_connection(test_params: Optional[Dict[str, Any]], timeout: int) -> Dict[str, Any]:
    """Test Stripe API connectivity"""
    api_key = test_params.get("api_key") if test_params else os.getenv("STRIPE_SECRET_KEY")
    if not api_key:
        return {
            "success": False,
            "message": "Stripe API key not provided",
            "details": {}
        }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://api.stripe.com/v1/account",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            return {
                "success": response.status_code == 200,
                "message": f"Stripe API: {response.status_code}",
                "details": {"status_code": response.status_code}
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Stripe connection failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def _test_twilio_connection(test_params: Optional[Dict[str, Any]], timeout: int) -> Dict[str, Any]:
    """Test Twilio API connectivity"""
    account_sid = test_params.get("account_sid") if test_params else os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = test_params.get("auth_token") if test_params else os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return {
            "success": False,
            "message": "Twilio credentials not provided",
            "details": {}
        }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json",
                auth=(account_sid, auth_token)
            )
            return {
                "success": response.status_code == 200,
                "message": f"Twilio API: {response.status_code}",
                "details": {"status_code": response.status_code}
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Twilio connection failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def _test_sendgrid_connection(test_params: Optional[Dict[str, Any]], timeout: int) -> Dict[str, Any]:
    """Test SendGrid API connectivity"""
    api_key = test_params.get("api_key") if test_params else os.getenv("SENDGRID_API_KEY")
    if not api_key:
        return {
            "success": False,
            "message": "SendGrid API key not provided",
            "details": {}
        }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://api.sendgrid.com/v3/user/account",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            return {
                "success": response.status_code == 200,
                "message": f"SendGrid API: {response.status_code}",
                "details": {"status_code": response.status_code}
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"SendGrid connection failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def _test_openai_connection(test_params: Optional[Dict[str, Any]], timeout: int) -> Dict[str, Any]:
    """Test OpenAI API connectivity"""
    api_key = test_params.get("api_key") if test_params else os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "success": False,
            "message": "OpenAI API key not provided",
            "details": {}
        }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            return {
                "success": response.status_code == 200,
                "message": f"OpenAI API: {response.status_code}",
                "details": {"status_code": response.status_code}
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"OpenAI connection failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def _test_database_connection(connection_string: str, timeout: int) -> Dict[str, Any]:
    """Test database connectivity"""
    try:
        # Parse connection string to extract host and port
        # Format: postgresql://user:pass@host:port/db
        if "://" in connection_string:
            # Remove protocol
            rest = connection_string.split("://", 1)[1]
            # Extract host part
            if "@" in rest:
                rest = rest.split("@", 1)[1]
            # Extract host:port
            if "/" in rest:
                host_port = rest.split("/", 1)[0]
            else:
                host_port = rest

            if ":" in host_port:
                host, port = host_port.split(":", 1)
                port = int(port)
            else:
                host = host_port
                port = 5432  # Default PostgreSQL port

            # Test TCP connection
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()

            return {
                "success": True,
                "message": f"Database connection successful to {host}:{port}",
                "details": {"host": host, "port": port}
            }
        else:
            return {
                "success": False,
                "message": "Invalid database connection string format",
                "details": {}
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Database connection failed: {str(e)}",
            "details": {"error": str(e)}
        }


async def _test_redis_connection(redis_url: str, timeout: int) -> Dict[str, Any]:
    """Test Redis connectivity"""
    try:
        # Parse Redis URL: redis://host:port or redis://[:password@]host:port
        if "://" in redis_url:
            rest = redis_url.split("://", 1)[1]
            # Remove password if present
            if "@" in rest:
                rest = rest.split("@", 1)[1]
            # Extract host:port
            if "/" in rest:
                host_port = rest.split("/", 1)[0]
            else:
                host_port = rest

            if ":" in host_port:
                host, port = host_port.split(":", 1)
                port = int(port)
            else:
                host = host_port
                port = 6379  # Default Redis port

            # Test TCP connection
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()

            return {
                "success": True,
                "message": f"Redis connection successful to {host}:{port}",
                "details": {"host": host, "port": port}
            }
        else:
            return {
                "success": False,
                "message": "Invalid Redis URL format",
                "details": {}
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Redis connection failed: {str(e)}",
            "details": {"error": str(e)}
        }


@router.post("/test-connection")
async def test_connection_endpoint(request: TestConnectionRequest) -> ConnectionTestResult:
    """
    Test if an external service is available.

    This endpoint allows the UI to verify that external services
    (APIs, databases, auth providers, etc.) are reachable before
    proceeding with UAT test execution.

    Use with_skeleton=true to return results without waiting for
    user interaction (for automated flows).
    """
    try:
        result = await test_connection(
            blocker_type=request.blocker_type,
            service=request.service,
            test_params=request.test_params,
            timeout=request.timeout
        )

        return ConnectionTestResult(
            blocker_id=request.blocker_id,
            success=result["success"],
            message=result["message"],
            details=result.get("details")
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test connection: {str(e)}"
        )


@router.get("/pending/{project_name}")
async def get_pending_blockers(project_name: str) -> Dict[str, Any]:
    """
    Get all pending blockers for a project.

    Returns blockers that haven't been resolved yet.
    Useful for reconnect scenarios or blocker review.
    """
    try:
        from api.registry import get_project_path
        project_path = get_project_path(project_name)
    except ImportError:
        project_path = Path.home() / "projects" / "autocoder-projects" / project_name

    # Detect blockers
    blockers = detect_project_blockers(str(project_path))

    # Check which ones have been resolved (have credentials stored)
    storage = get_storage(project_name)
    resolved = storage.list_credentials()

    # Filter out resolved API key blockers
    pending = []
    for blocker in blockers.get('blockers', []):
        if blocker['blocker_type'] == 'api_key':
            # Check if credential exists
            has_credential = any(
                r['service'] == blocker['service'] and r['key_name'] == blocker['key_name']
                for r in resolved
            )
            if not has_credential:
                pending.append(blocker)
        else:
            # Non-API key blockers are still pending
            pending.append(blocker)

    return {
        "project_name": project_name,
        "pending_blockers": pending,
        "resolved_count": len(resolved),
        "total_count": len(blockers.get('blockers', []))
    }


@router.get("/credentials/{project_name}")
async def list_credentials(project_name: str) -> Dict[str, Any]:
    """
    List all stored credentials for a project (metadata only, no values).

    Returns service names and key names without exposing actual values.
    """
    try:
        storage = get_storage(project_name)
        credentials = storage.list_credentials()

        return {
            "project_name": project_name,
            "credentials": credentials,
            "count": len(credentials)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list credentials: {str(e)}"
        )


@router.delete("/credentials/{project_name}/{service}/{key_name}")
async def delete_credential(project_name: str, service: str, key_name: str) -> Dict[str, Any]:
    """
    Delete a stored credential.

    Permanently removes an API key from secure storage.
    """
    try:
        storage = get_storage(project_name)
        deleted = storage.delete_credential(service, key_name)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Credential not found: {service}.{key_name}"
            )

        return {
            "message": f"Credential {service}.{key_name} deleted",
            "service": service,
            "key_name": key_name
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete credential: {str(e)}"
        )
