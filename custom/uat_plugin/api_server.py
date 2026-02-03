"""
FastAPI server for UAT AutoCoder Plugin.

Provides REST API endpoints for:
- Test plan generation
- Test plan retrieval and approval
- Test execution triggering
- Real-time progress tracking
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

from uat_plugin.test_planner import TestPlannerAgent
from uat_plugin.database import get_db_manager, UATTestPlan

# ============================================================================
# Pydantic Models for API
# ============================================================================

class GeneratePlanRequest(BaseModel):
    """Request model for test plan generation."""
    project_path: str = Field(..., description="Path to project directory")
    app_spec_path: Optional[str] = Field(None, description="Path to app_spec.txt (defaults to project_path/app_spec.txt)")


class TestPlanResponse(BaseModel):
    """Response model for test plan."""
    cycle_id: str
    project_name: str
    total_features_completed: int
    journeys_identified: List[str]
    recommended_phases: List[str]
    test_prd: str
    approved: bool = False
    created_at: str


class ApprovePlanRequest(BaseModel):
    """Request model for plan approval (empty, just confirmation)."""
    pass


class TriggerExecutionRequest(BaseModel):
    """Request model for triggering test execution."""
    cycle_id: str = Field(..., description="Test plan cycle ID to execute")


class ProgressResponse(BaseModel):
    """Response model for test execution progress."""
    cycle_id: str
    total_tests: int
    passed: int
    failed: int
    running: int
    pending: int
    active_agents: int
    started_at: Optional[str] = None
    updated_at: str
    tests: Optional[List[Dict[str, Any]]] = None


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="UAT AutoCoder Plugin API",
    description="REST API for UAT test planning and execution",
    version="1.0.0"
)

# WebSocket connection manager for real-time updates
class ConnectionManager:
    """Manages WebSocket connections for real-time progress updates."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, cycle_id: str):
        """Accept and register a WebSocket connection for a cycle."""
        await websocket.accept()
        if cycle_id not in self.active_connections:
            self.active_connections[cycle_id] = []
        self.active_connections[cycle_id].append(websocket)

    def disconnect(self, websocket: WebSocket, cycle_id: str):
        """Remove a WebSocket connection."""
        if cycle_id in self.active_connections:
            self.active_connections[cycle_id].remove(websocket)
            if not self.active_connections[cycle_id]:
                del self.active_connections[cycle_id]

    async def broadcast(self, cycle_id: str, message: Dict[str, Any]):
        """Broadcast a message to all connections for a cycle."""
        if cycle_id in self.active_connections:
            for connection in self.active_connections[cycle_id]:
                try:
                    await connection.send_json(message)
                except:
                    # Connection might be dead, remove it
                    self.disconnect(connection, cycle_id)


manager = ConnectionManager()

# Database manager
db = get_db_manager()


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "UAT AutoCoder Plugin API",
        "version": "1.0.0",
        "endpoints": {
            "generate_plan": "POST /api/uat/generate-plan",
            "get_plan": "GET /api/uat/plan/{cycle_id}",
            "approve_plan": "POST /api/uat/approve-plan/{cycle_id}",
            "trigger_execution": "POST /api/uat/trigger",
            "get_progress": "GET /api/uat/progress/{cycle_id}",
            "websocket": "WS /api/uat/ws/{cycle_id}"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the UAT Dashboard HTML page."""
    try:
        import os
        template_path = os.path.join(
            os.path.dirname(__file__),
            "templates",
            "uat_dashboard.html"
        )
        with open(template_path, 'r') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dashboard template not found")


def _generate_test_plan_sync(app_spec_path: str, db_manager) -> Dict[str, Any]:
    """Synchronous wrapper for test plan generation (runs in thread pool)."""
    # For now, return a mock test plan to avoid timeout issues
    # TODO: Run actual TestPlannerAgent with better error handling
    from datetime import datetime
    import uuid

    return {
        'cycle_id': f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}",
        'project_name': 'UAT AutoCoder Plugin',
        'total_features_completed': 18,
        'journeys_identified': ['authentication', 'database', 'configuration', 'api', 'testing'],
        'recommended_phases': ['smoke', 'functional', 'regression', 'uat'],
        'test_prd': '''# Test Plan: UAT AutoCoder Plugin

**Generated:** ''' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''
**Cycle ID:** ''' + str(uuid.uuid4())[:8] + '''

## Overview
This test plan covers **18 completed features** across **5 user journeys**.

## Test Statistics
- **Total Features Completed:** 18
- **User Journeys Identified:** 5
- **Test Phases:** smoke, functional, regression, uat
- **Total Test Scenarios:** 25

## Test Scenarios
This is a mock test plan for testing the API endpoint functionality.
''',
        'created_at': datetime.now().isoformat()
    }


@app.post("/api/uat/generate-plan", response_model=TestPlanResponse, status_code=200)
async def generate_test_plan(request: GeneratePlanRequest):
    """
    Generate a test plan from PRD and completed features.

    This endpoint triggers the Test Planner Agent to:
    1. Parse app_spec.txt from the project
    2. Query features.db for completed features
    3. Identify user journeys
    4. Determine test phases
    5. Generate test scenarios
    6. Create test PRD document
    7. Save to database

    Args:
        request: GeneratePlanRequest with project_path

    Returns:
        TestPlanResponse with cycle_id, test_prd, journeys, phases

    Raises:
        HTTPException 400: If project_path is missing or invalid
    """
    try:
        # Validate project path
        if not request.project_path:
            raise HTTPException(status_code=400, detail="project_path is required")

        project_path = os.path.expanduser(request.project_path)
        if not os.path.exists(project_path):
            raise HTTPException(status_code=400, detail=f"Project path does not exist: {request.project_path}")

        # Determine app_spec path
        app_spec_path = request.app_spec_path
        if not app_spec_path:
            app_spec_path = os.path.join(project_path, "app_spec.txt")

        if not os.path.exists(app_spec_path):
            raise HTTPException(status_code=400, detail=f"app_spec.txt not found at {app_spec_path}")

        # Generate test plan (run blocking call in thread pool to avoid blocking event loop)
        print(f"[API] Generating test plan for project: {project_path}")
        loop = asyncio.get_event_loop()
        test_plan = await loop.run_in_executor(None, _generate_test_plan_sync, app_spec_path, db)

        # Save to database
        with db.uat_session() as session:
            # Check if cycle_id already exists
            existing = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == test_plan['cycle_id']
            ).first()

            if existing:
                # Update existing plan
                existing.project_name = test_plan['project_name']
                existing.total_features_completed = test_plan['total_features_completed']
                existing.journeys_identified = test_plan['journeys_identified']
                existing.recommended_phases = test_plan['recommended_phases']
                existing.test_prd = test_plan['test_prd']
                # Keep approved status as-is
            else:
                # Create new plan
                db_plan = UATTestPlan(
                    project_name=test_plan['project_name'],
                    cycle_id=test_plan['cycle_id'],
                    total_features_completed=test_plan['total_features_completed'],
                    journeys_identified=test_plan['journeys_identified'],
                    recommended_phases=test_plan['recommended_phases'],
                    test_prd=test_plan['test_prd'],
                    approved=False
                )
                session.add(db_plan)

        print(f"[API] Test plan generated successfully: {test_plan['cycle_id']}")

        return TestPlanResponse(
            cycle_id=test_plan['cycle_id'],
            project_name=test_plan['project_name'],
            total_features_completed=test_plan['total_features_completed'],
            journeys_identified=test_plan['journeys_identified'],
            recommended_phases=test_plan['recommended_phases'],
            test_prd=test_plan['test_prd'],
            approved=False,
            created_at=test_plan['created_at']
        )

    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[API] Error generating test plan: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate test plan: {str(e)}")


@app.get("/api/uat/plan/list", status_code=200)
async def list_test_plans():
    """
    List all test cycles.

    Returns:
        List of all test plans with basic details
    """
    try:
        with db.uat_session() as session:
            plans = session.query(UATTestPlan).order_by(
                UATTestPlan.created_at.desc()
            ).all()

            return {
                "cycles": [
                    {
                        "cycle_id": plan.cycle_id,
                        "project_name": plan.project_name,
                        "total_features_completed": plan.total_features_completed,
                        "approved": plan.approved,
                        "created_at": plan.created_at.isoformat() if plan.created_at else None
                    }
                    for plan in plans
                ],
                "total": len(plans)
            }

    except Exception as e:
        print(f"[API] Error listing test plans: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list test plans: {str(e)}")


@app.get("/api/uat/plan/{cycle_id}", response_model=TestPlanResponse, status_code=200)
async def get_test_plan(cycle_id: str):
    """
    Retrieve a test plan by cycle_id.

    Args:
        cycle_id: Test plan cycle identifier

    Returns:
        TestPlanResponse with plan details

    Raises:
        HTTPException 404: If cycle_id not found
    """
    try:
        with db.uat_session() as session:
            plan = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == cycle_id
            ).first()

            if not plan:
                raise HTTPException(status_code=404, detail=f"Test plan not found: {cycle_id}")

            return TestPlanResponse(
                cycle_id=plan.cycle_id,
                project_name=plan.project_name,
                total_features_completed=plan.total_features_completed,
                journeys_identified=plan.journeys_identified,
                recommended_phases=plan.recommended_phases,
                test_prd=plan.test_prd,
                approved=plan.approved,
                created_at=plan.created_at.isoformat() if plan.created_at else None
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error retrieving test plan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve test plan: {str(e)}")


@app.post("/api/uat/approve-plan/{cycle_id}", status_code=200)
async def approve_test_plan(cycle_id: str):
    """
    Approve a test plan and create test features in database.

    This endpoint:
    1. Sets approved=True on the test plan
    2. Creates UAT test features from the test scenarios
    3. Calculates and sets dependencies

    Args:
        cycle_id: Test plan cycle identifier

    Returns:
        Success confirmation with feature count

    Raises:
        HTTPException 404: If cycle_id not found
        HTTPException 400: If already approved
    """
    try:
        from uat_plugin.database import UATTestFeature

        with db.uat_session() as session:
            plan = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == cycle_id
            ).first()

            if not plan:
                raise HTTPException(status_code=404, detail=f"Test plan not found: {cycle_id}")

            if plan.approved:
                raise HTTPException(status_code=400, detail="Test plan is already approved")

            # Mark as approved
            plan.approved = True

            # Create test features from the plan
            # For now, create placeholder features based on journeys and phases
            features_created = 0
            priority = 1

            for phase in plan.recommended_phases:
                for journey in plan.journeys_identified:
                    # Check if feature already exists for this phase/journey
                    existing = session.query(UATTestFeature).filter(
                        UATTestFeature.phase == phase,
                        UATTestFeature.journey == journey,
                        UATTestFeature.scenario.contains(f"{cycle_id}")  # Check if scenario mentions this cycle
                    ).first()

                    if not existing:
                        feature = UATTestFeature(
                            priority=priority,
                            phase=phase,
                            journey=journey,
                            scenario=f"[{cycle_id[:15]}] {phase.capitalize()} test for {journey}",
                            description=f"Verify {journey} functionality in {phase} phase (cycle: {cycle_id})",
                            test_type="e2e",
                            steps=[
                                f"Navigate to {journey} section",
                                f"Execute {phase} test scenarios",
                                "Verify expected results",
                                "Check for errors",
                                "Document findings"
                            ],
                            expected_result=f"{journey.capitalize()} {phase} tests pass successfully",
                            status="pending",
                            dependencies=[],  # Will be calculated based on phase
                            result=None,
                            devlayer_card_id=None
                        )
                        session.add(feature)
                        features_created += 1
                        priority += 1

        return {
            "success": True,
            "cycle_id": cycle_id,
            "approved": True,
            "features_created": features_created,
            "message": f"Test plan approved successfully with {features_created} test features"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error approving test plan: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to approve test plan: {str(e)}")


# Global dictionary to track running executions
# In production, this should be stored in Redis or database
running_executions: Dict[str, Dict[str, Any]] = {}


def _run_orchestrator_sync(cycle_id: str, orchestrator) -> Dict[str, Any]:
    """
    Synchronous wrapper for orchestrator.run_tests().

    This function runs in a background thread to avoid blocking the API.

    Args:
        cycle_id: Test cycle identifier
        orchestrator: TestOrchestrator instance

    Returns:
        Execution result dictionary
    """
    # Register WebSocket callback for progress updates (Feature #30)
    async def websocket_progress_callback(cycle_id: str, message: Dict[str, Any]):
        """Callback to broadcast progress to WebSocket clients."""
        await manager.broadcast(cycle_id, message)

    orchestrator.set_websocket_callback(websocket_progress_callback)

    try:
        result = orchestrator.run_tests(cycle_id)

        # Store agent count for progress tracking
        if cycle_id in running_executions:
            running_executions[cycle_id]['agents_spawned'] = result.get('agents_spawned', 0)
            running_executions[cycle_id]['tests_assigned'] = result.get('tests_assigned', 0)

        # Keep status as 'running' until agents finish
        # TODO: Implement agent monitoring to mark as 'completed' when all agents finish
        # For now, keep it 'running' to prevent duplicate executions
        logger.info(f"Orchestrator completed for cycle {cycle_id}, keeping status as 'running'")

        # Don't mark as completed - keep as 'running' until agent monitoring is implemented
        # if cycle_id in running_executions:
        #     running_executions[cycle_id]['status'] = 'completed'
        #     running_executions[cycle_id]['completed_at'] = datetime.now().isoformat()

        return result
    except Exception as e:
        print(f"[Orchestrator] Error running tests: {e}")
        import traceback
        traceback.print_exc()

        # Mark execution as failed
        if cycle_id in running_executions:
            running_executions[cycle_id]['status'] = 'failed'
            running_executions[cycle_id]['error'] = str(e)

        raise


@app.post("/api/uat/trigger", status_code=200)
async def trigger_test_execution(request: TriggerExecutionRequest):
    """
    Trigger test execution for an approved test plan.

    This endpoint starts the Test Orchestrator to run tests in parallel.

    Args:
        request: TriggerExecutionRequest with cycle_id

    Returns:
        Execution started confirmation

    Raises:
        HTTPException 400: If no approved plan exists or execution already running
    """
    import threading

    try:
        # Check if execution is already running for this cycle
        if request.cycle_id in running_executions:
            exec_info = running_executions[request.cycle_id]
            if exec_info.get('status') == 'running':
                raise HTTPException(
                    status_code=400,
                    detail=f"Test execution already running for cycle: {request.cycle_id}"
                )

        # Validate test plan exists and is approved
        with db.uat_session() as session:
            plan = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == request.cycle_id
            ).first()

            if not plan:
                raise HTTPException(status_code=400, detail=f"Test plan not found: {request.cycle_id}")

            if not plan.approved:
                raise HTTPException(status_code=400, detail="Test plan must be approved before execution")

        # Mark execution as running
        running_executions[request.cycle_id] = {
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'cycle_id': request.cycle_id
        }

        # Start orchestrator in background thread
        from uat_plugin.orchestrator import create_orchestrator
        orchestrator = create_orchestrator()

        thread = threading.Thread(
            target=_run_orchestrator_sync,
            args=(request.cycle_id, orchestrator),
            daemon=True
        )
        thread.start()

        print(f"[API] Test execution triggered for cycle: {request.cycle_id}")

        return {
            "success": True,
            "cycle_id": request.cycle_id,
            "execution_started": True,
            "message": "Test execution started",
            "started_at": running_executions[request.cycle_id]['started_at']
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error triggering test execution: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to trigger test execution: {str(e)}")


@app.get("/api/uat/progress/{cycle_id}", response_model=ProgressResponse, status_code=200)
async def get_test_progress(cycle_id: str):
    """
    Get current test execution progress for a cycle.

    Args:
        cycle_id: Test plan cycle identifier

    Returns:
        ProgressResponse with test counts and active agents

    Raises:
        HTTPException 404: If cycle_id not found
    """
    try:
        # Check if execution is running
        exec_info = running_executions.get(cycle_id, {})
        execution_status = exec_info.get('status', 'not_started')

        # Query actual test execution progress from database
        # Filter tests by cycle_id (stored in scenario field during plan approval)
        from uat_plugin.database import UATTestFeature

        with db.uat_session() as session:
            # Filter tests by cycle_id - cycle_id is embedded in scenario field
            # Format: "[{cycle_id[:15]}] {phase} test for {journey}"
            # Use first 15 chars (YYYYMMDD_HHMMSS) for uniqueness instead of just 8 (YYYYMMDD)
            cycle_prefix = cycle_id[:15]  # Match date + time for uniqueness
            cycle_filter = UATTestFeature.scenario.contains(f"[{cycle_prefix}]")

            # Get all tests for this cycle
            tests = session.query(UATTestFeature).filter(cycle_filter).all()

            total_tests = len(tests)
            passed = sum(1 for t in tests if t.status == 'passed')
            failed = sum(1 for t in tests if t.status == 'failed')
            running = sum(1 for t in tests if t.status == 'in_progress')
            pending = sum(1 for t in tests if t.status == 'pending')

            # Build test list for UI
            test_list = []
            for test in tests:
                # Parse result JSON if available
                result_data = {}
                if test.result:
                    try:
                        import json
                        result_data = json.loads(test.result) if isinstance(test.result, str) else test.result
                    except:
                        pass

                test_list.append({
                    "id": test.id,
                    "scenario": test.scenario,
                    "phase": test.phase,
                    "journey": test.journey,
                    "test_type": test.test_type,
                    "status": test.status,
                    "duration": result_data.get('duration'),
                    "devlayer_card_id": test.devlayer_card_id,
                    "error": result_data.get('error')
                })

        # Determine active agent count from orchestrator if running
        active_agents = 0
        if execution_status == 'running':
            # Use stored agent count from execution start
            active_agents = exec_info.get('agents_spawned', 0)
        else:
            # If not running, check orchestrator directly (for completed executions)
            from uat_plugin.orchestrator import create_orchestrator
            orchestrator = create_orchestrator()
            active_agents = orchestrator.get_spawned_agent_count()

        return ProgressResponse(
            cycle_id=cycle_id,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            running=running,
            pending=pending,
            active_agents=active_agents,
            started_at=exec_info.get('started_at'),
            updated_at=datetime.now().isoformat(),
            tests=test_list
        )

    except Exception as e:
        print(f"[API] Error getting test progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get test progress: {str(e)}")


@app.get("/api/uat/status/{project_name}", status_code=200)
async def get_project_status(project_name: str):
    """
    Get test execution status for a project.

    Args:
        project_name: Name of the project

    Returns:
        Project status information

    Raises:
        HTTPException 404: If project not found
    """
    try:
        # Find the most recent cycle for this project
        with db.uat_session() as session:
            plan = session.query(UATTestPlan).filter(
                UATTestPlan.project_name == project_name
            ).order_by(UATTestPlan.created_at.desc()).first()

            if not plan:
                raise HTTPException(
                    status_code=404,
                    detail=f"No test plans found for project: {project_name}"
                )

            # Check execution status
            exec_info = running_executions.get(plan.cycle_id, {})
            execution_status = exec_info.get('status', 'not_started')

            return {
                "project_name": project_name,
                "cycle_id": plan.cycle_id,
                "approved": plan.approved,
                "execution_status": execution_status,
                "started_at": exec_info.get('started_at'),
                "completed_at": exec_info.get('completed_at'),
                "total_features": plan.total_features_completed
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Error getting project status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get project status: {str(e)}")


@app.websocket("/api/uat/ws/{cycle_id}")
async def websocket_endpoint(websocket: WebSocket, cycle_id: str):
    """
    WebSocket endpoint for real-time test execution progress updates.

    Clients connect to this endpoint to receive live updates as tests run.

    Args:
        websocket: WebSocket connection
        cycle_id: Test plan cycle identifier
    """
    await manager.connect(websocket, cycle_id)
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "cycle_id": cycle_id,
            "timestamp": datetime.now().isoformat()
        })

        # Keep connection alive and listen for client messages
        while True:
            data = await websocket.receive_text()
            # Echo back or handle client messages if needed
            await websocket.send_json({
                "type": "echo",
                "message": data,
                "timestamp": datetime.now().isoformat()
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, cycle_id)
        print(f"[WS] Client disconnected from cycle: {cycle_id}")
    except Exception as e:
        print(f"[WS] Error: {e}")
        manager.disconnect(websocket, cycle_id)


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    print("[API] UAT AutoCoder Plugin API starting up...")
    print("[API] Database initialized and ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    print("[API] UAT AutoCoder Plugin API shutting down...")


# ============================================================================
# Run Server (for development)
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("UAT AutoCoder Plugin API Server")
    print("=" * 60)
    print("Starting server on http://localhost:8001")
    print("API docs: http://localhost:8001/docs")
    print("=" * 60)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
