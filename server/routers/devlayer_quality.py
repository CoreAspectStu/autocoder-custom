"""
DevLayer Quality Gate Router

Provides the quality gate workflow between UAT Gateway, DevLayer, and Dev boards.
Implements the complete workflow: UAT Test Failure → DevLayer Triage → Dev Fix → UAT Retest → Archive
"""

import logging
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

# Import from custom DevLayer module
try:
    from custom.devlayer.models import (
        DevLayerCard, CardLink, PipelineEvent, QualityMetrics,
        TestEvidence, Severity, Category, DevLayerStatus, LinkType
    )
    from custom.devlayer.manager import DevLayerManager, DevLayerConfig
    from custom.devlayer.database import DevLayerDatabase
    DEVLAYER_AVAILABLE = True
except ImportError:
    DEVLAYER_AVAILABLE = False
    logging.warning("DevLayer module not available. Quality gate features disabled.")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quality", tags=["quality-gate"])

# Database path - use home directory for persistence
DB_PATH = os.path.expanduser("~/.autocoder/quality_gate.db")

# Configuration
config = DevLayerConfig(
    db_path=DB_PATH,
    uat_gateway_url="http://localhost:8889",
    dev_board_url="http://localhost:4000",
    enable_slack=bool(os.environ.get('SLACK_WEBHOOK_URL')),
    enable_n8n=bool(os.environ.get('DEVLAYER_WEBHOOK_URL')),
    n8n_webhook_url=os.environ.get('DEVLAYER_WEBHOOK_URL', ''),
    slack_webhook_url=os.environ.get('SLACK_WEBHOOK_URL', ''),
)

# Global manager instance
_manager: Optional[DevLayerManager] = None


def get_manager() -> Optional[DevLayerManager]:
    """Get or create the DevLayer manager instance."""
    global _manager
    if not DEVLAYER_AVAILABLE:
        return None
    if _manager is None:
        _manager = DevLayerManager(config, "default")
    return _manager


# ============================================================================
# Request/Response Models
# ============================================================================

class TestEvidenceModel(BaseModel):
    """Test evidence from UAT failure."""
    scenario_id: str
    error_message: str
    steps_to_reproduce: List[str]
    screenshot_path: Optional[str] = None
    log_path: Optional[str] = None
    trace_path: Optional[str] = None
    journey_id: Optional[str] = None
    additional_data: Dict[str, Any] = {}


class CreateBugCardRequest(BaseModel):
    """Request to create a bug card from UAT failure."""
    evidence: TestEvidenceModel
    title: Optional[str] = None
    uat_card_id: Optional[str] = None


class TriageCardRequest(BaseModel):
    """Request to triage a bug card."""
    severity: Severity
    category: Category
    triage_notes: str
    triaged_by: str


class ApproveForDevRequest(BaseModel):
    """Request to approve a bug for Dev work."""
    approved_by: str
    assignee: Optional[str] = None


class RetestResultRequest(BaseModel):
    """UAT retest result."""
    passed: bool
    scenarios_tested: List[str]
    test_results: List[Dict[str, Any]] = []
    new_failures: List[Dict[str, Any]] = []


# ============================================================================
# Quality Gate API Routes
# ============================================================================

@router.get("/health")
async def health_check():
    """Check if quality gate system is available."""
    return {
        "available": DEVLAYER_AVAILABLE,
        "database": DB_PATH if DEVLAYER_AVAILABLE else None,
    }


@router.get("/stats")
async def get_board_stats(manager: DevLayerManager = Depends(get_manager)) -> Dict[str, int]:
    """Get DevLayer board statistics by column."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")
    return manager.get_board_stats()


@router.get("/metrics")
async def get_quality_metrics(manager: DevLayerManager = Depends(get_manager)) -> Dict[str, Any]:
    """Get quality pipeline metrics."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    metrics = manager.get_quality_metrics()
    return {
        "metrics": metrics.to_dict(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/bug")
async def create_uat_bug_card(
    req: CreateBugCardRequest,
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """
    Create a DevLayer bug card from UAT test failure.

    This endpoint is called automatically when a UAT test fails.
    Creates the card in 'triage' status and triggers n8n workflow.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    try:
        evidence = TestEvidence(**req.evidence.model_dump())
        card = await manager.create_uat_bug_card(
            evidence=evidence,
            title=req.title,
            uat_card_id=req.uat_card_id,
        )

        return {
            "success": True,
            "card_id": card.id,
            "card": card.to_dict(),
        }
    except Exception as e:
        logger.error(f"Failed to create bug card: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/triage/{card_id}")
async def triage_bug(
    card_id: str,
    req: TriageCardRequest,
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """Triage a DevLayer bug card with severity and category."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    try:
        card = await manager.triage_card(
            card_id=card_id,
            severity=req.severity,
            category=req.category,
            triage_notes=req.triage_notes,
            triaged_by=req.triaged_by,
        )

        return {
            "success": True,
            "card_id": card.id,
            "card": card.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to triage bug: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve/{card_id}")
async def approve_bug_for_dev(
    card_id: str,
    req: ApproveForDevRequest,
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """
    Approve a DevLayer bug card for Dev work.

    Creates a Dev card and links all three cards together.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    try:
        card = await manager.approve_for_dev(
            card_id=card_id,
            approved_by=req.approved_by,
            assignee=req.assignee,
        )

        return {
            "success": True,
            "card_id": card.id,
            "dev_card_id": card.dev_card_id,
            "card": card.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to approve bug: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cards/{card_id}")
async def get_card(
    card_id: str,
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """Get a DevLayer card by ID."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    card = manager.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found")

    return card.to_dict()


@router.get("/cards")
async def get_cards_by_status(
    status: DevLayerStatus,
    manager: DevLayerManager = Depends(get_manager),
) -> List[Dict[str, Any]]:
    """Get all cards with a specific status."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    cards = manager.get_cards_by_status(status)
    return [card.to_dict() for card in cards]


@router.get("/cards/{card_id}/linked")
async def get_linked_cards(
    card_id: str,
    manager: DevLayerManager = Depends(get_manager),
) -> List[Dict[str, Any]]:
    """Get all cards linked to a specific card."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    links = manager.get_linked_cards(card_id)
    return [link.to_dict() for link in links]


@router.post("/dev/complete/{dev_card_id}")
async def on_dev_complete(
    dev_card_id: str,
    completed_by: str,
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """
    Handle Dev card completion - triggers UAT retest.

    This endpoint is called when a Dev card is marked complete.
    Calculates affected scenarios and triggers UAT retest.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    try:
        result = await manager.on_dev_complete(dev_card_id, completed_by)
        return {
            "success": True,
            **result,
        }
    except Exception as e:
        logger.error(f"Failed to process Dev completion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/uat/retest/{devlayer_card_id}")
async def on_uat_retest_complete(
    devlayer_card_id: str,
    req: RetestResultRequest,
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """
    Handle UAT retest completion.

    Archives cards if passed, returns to Dev if failed.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    try:
        result = await manager.on_uat_retest_complete(
            devlayer_card_id,
            req.model_dump(),
        )

        return {
            "success": True,
            "result": result,
        }
    except Exception as e:
        logger.error(f"Failed to process retest result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/events")
async def get_pipeline_events(
    card_id: Optional[str] = None,
    limit: int = 100,
    manager: DevLayerManager = Depends(get_manager),
) -> List[Dict[str, Any]]:
    """Get pipeline events, optionally filtered by card ID."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    events = manager.get_pipeline_events(card_id, limit)
    return [event.to_dict() for event in events]


@router.get("/pipeline/dashboard")
async def get_pipeline_dashboard(
    project_id: Optional[str] = None,
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """
    Get quality pipeline dashboard.

    Returns real-time metrics on cards in each pipeline stage,
    pass rates, velocity, and flow data.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    metrics = manager.get_quality_metrics()
    board_stats = manager.get_board_stats()
    events = manager.get_pipeline_events(limit=50)

    return {
        "project_id": project_id or "default",
        "metrics": metrics.to_dict(),
        "board_stats": board_stats,
        "recent_events": [e.to_dict() for e in events],
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/pipeline/flow")
async def get_pipeline_flow(
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """
    Get pipeline flow data for visualization.

    Returns card movement data for the flow diagram.
    """
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    events = manager.get_pipeline_events(limit=200)

    # Group events by stage transition
    flow_data: Dict[str, int] = {}
    for event in events:
        if event.from_stage and event.to_stage:
            key = f"{event.from_stage.value}_to_{event.to_stage.value}"
            flow_data[key] = flow_data.get(key, 0) + 1

    return {
        "flow_data": flow_data,
        "total_transitions": len(events),
    }


@router.get("/pipeline/export")
async def export_pipeline_data(
    format: str = "json",
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """Export pipeline data as JSON or CSV."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    metrics = manager.get_quality_metrics()
    events = manager.get_pipeline_events(limit=1000)
    board_stats = manager.get_board_stats()

    data = {
        "metrics": metrics.to_dict(),
        "board_stats": board_stats,
        "events": [e.to_dict() for e in events],
        "exported_at": datetime.utcnow().isoformat(),
    }

    if format.lower() == "csv":
        # Convert to CSV format (simplified)
        return {
            "format": "csv",
            "data": data,  # In production, convert to actual CSV
        }

    return data


@router.post("/archive")
async def archive_cards(
    card_ids: List[str],
    manager: DevLayerManager = Depends(get_manager),
) -> Dict[str, Any]:
    """Archive completed cards."""
    if not manager:
        raise HTTPException(status_code=503, detail="Quality gate not available")

    try:
        archived_count = manager.db.archive_cards(card_ids)
        return {
            "success": True,
            "archived_count": archived_count,
            "card_ids": card_ids,
        }
    except Exception as e:
        logger.error(f"Failed to archive cards: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Export router for inclusion in main app
quality_gate_router = router
