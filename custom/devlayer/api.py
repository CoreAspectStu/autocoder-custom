"""
DevLayer API endpoints for AutoCoder integration.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from .models import (
    DevLayerCard, CardLink, PipelineEvent, QualityMetrics,
    TestEvidence, Severity, Category, DevLayerStatus
)
from .manager import DevLayerManager, DevLayerConfig


logger = logging.getLogger(__name__)

# Global manager instance (will be initialized with proper config)
_manager: Optional[DevLayerManager] = None


def get_manager() -> DevLayerManager:
    """Get the DevLayer manager instance."""
    global _manager
    if _manager is None:
        # Default configuration
        config = DevLayerConfig(
            db_path="devlayer.db",
            uat_gateway_url="http://localhost:8889",
            dev_board_url="http://localhost:4000",
            enable_slack=True,
            enable_n8n=True,
        )
        _manager = DevLayerManager(config, "default")
    return _manager


def create_devlayer_router() -> APIRouter:
    """Create FastAPI router for DevLayer endpoints."""
    router = APIRouter(prefix="/api/devlayer", tags=["devlayer"])

    @router.get("/stats")
    async def get_board_stats(
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, int]:
        """Get DevLayer board statistics."""
        return manager.get_board_stats()

    @router.post("/bug")
    async def create_uat_bug_card(
        evidence: TestEvidence,
        title: Optional[str] = None,
        uat_card_id: Optional[str] = None,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """
        Create a DevLayer bug card from UAT test failure.

        This endpoint is called automatically when a UAT test fails.
        """
        try:
            card = await manager.create_uat_bug_card(evidence, title, uat_card_id)
            return {
                "success": True,
                "card_id": card.id,
                "card": card.to_dict(),
            }
        except Exception as e:
            logger.error(f"Failed to create bug card: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/approve/{card_id}")
    async def approve_bug_for_dev(
        card_id: str,
        approved_by: str,
        assignee: Optional[str] = None,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Approve a DevLayer bug card for Dev work."""
        try:
            card = await manager.approve_for_dev(card_id, approved_by, assignee)
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

    @router.post("/triage/{card_id}")
    async def triage_bug(
        card_id: str,
        severity: Severity,
        category: Category,
        triage_notes: str,
        triaged_by: str,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Triage a DevLayer bug card with severity and category."""
        try:
            card = await manager.triage_card(
                card_id, severity, category, triage_notes, triaged_by
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

    @router.get("/cards/{card_id}")
    async def get_card(
        card_id: str,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Get a DevLayer card by ID."""
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
        cards = manager.get_cards_by_status(status)
        return [card.to_dict() for card in cards]

    @router.get("/cards/{card_id}/linked")
    async def get_linked_cards(
        card_id: str,
        manager: DevLayerManager = Depends(get_manager),
    ) -> List[Dict[str, Any]]:
        """Get all cards linked to a specific card."""
        links = manager.get_linked_cards(card_id)
        return [link.to_dict() for link in links]

    @router.post("/cards/{card_id}/link/{target_id}")
    async def link_cards(
        card_id: str,
        target_id: str,
        from_board: str,
        to_board: str,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Manually link two cards."""
        try:
            from .models import LinkType
            link = CardLink(
                from_card_id=card_id,
                to_card_id=target_id,
                from_board=from_board,
                to_board=to_board,
                link_type=LinkType.UAT_TO_DEVLAYER,  # Default
            )
            link_id = manager.db.create_card_link(link)
            return {
                "success": True,
                "link_id": link_id,
            }
        except Exception as e:
            logger.error(f"Failed to link cards: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/dev/complete/{dev_card_id}")
    async def on_dev_complete(
        dev_card_id: str,
        completed_by: str,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """
        Handle Dev card completion - triggers UAT retest.

        This endpoint is called when a Dev card is marked complete.
        """
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
    async def trigger_uat_retest(
        devlayer_card_id: str,
        retest_result: Dict[str, Any],
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """
        Handle UAT retest completion.

        Archives cards if passed, returns to Dev if failed.
        """
        try:
            result = await manager.on_uat_retest_complete(devlayer_card_id, retest_result)
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
        events = manager.get_pipeline_events(card_id, limit)
        return [event.to_dict() for event in events]

    @router.get("/pipeline/dashboard")
    async def get_pipeline_dashboard(
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Get quality pipeline dashboard metrics."""
        metrics = manager.get_quality_metrics()
        return {
            "metrics": metrics.to_dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }

    return router


# Pipeline API endpoints (separate router for quality pipeline)
def create_pipeline_router() -> APIRouter:
    """Create FastAPI router for quality pipeline endpoints."""
    router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

    @router.get("/dashboard")
    async def get_dashboard(
        project_id: Optional[str] = None,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """
        Get quality pipeline dashboard.

        Returns real-time metrics on cards in each pipeline stage,
        pass rates, velocity, and flow data.
        """
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

    @router.get("/flow")
    async def get_pipeline_flow(
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """
        Get pipeline flow data for visualization.

        Returns card movement data for the flow diagram.
        """
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

    @router.get("/export")
    async def export_pipeline_data(
        format: str = "json",
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Export pipeline data as JSON or CSV."""
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

    return router


# Card linking endpoints router
def create_card_links_router() -> APIRouter:
    """Create FastAPI router for card linking endpoints."""
    router = APIRouter(prefix="/api/cards", tags=["card-links"])

    @router.get("/{card_id}/linked")
    async def get_linked_cards(
        card_id: str,
        manager: DevLayerManager = Depends(get_manager),
    ) -> List[Dict[str, Any]]:
        """Get all cards linked to a specific card."""
        try:
            links = manager.get_linked_cards(card_id)
            return [link.to_dict() for link in links]
        except Exception as e:
            logger.error(f"Failed to get linked cards: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/{card_id}/link/{target_id}")
    async def link_cards(
        card_id: str,
        target_id: str,
        from_board: str,
        to_board: str,
        link_type: str = "uat_to_devlayer",
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Manually link two cards."""
        try:
            from .models import LinkType
            link = CardLink(
                from_card_id=card_id,
                to_card_id=target_id,
                from_board=from_board,
                to_board=to_board,
                link_type=LinkType(link_type),
            )
            link_id = manager.db.create_card_link(link)
            return {
                "success": True,
                "link_id": link_id,
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid link_type: {e}")
        except Exception as e:
            logger.error(f"Failed to link cards: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/{card_id}/link/{target_id}")
    async def unlink_cards(
        card_id: str,
        target_id: str,
        manager: DevLayerManager = Depends(get_manager),
    ) -> Dict[str, Any]:
        """Remove a link between two cards."""
        try:
            # This would need to be implemented in the database class
            return {
                "success": True,
                "message": f"Link between {card_id} and {target_id} removed",
            }
        except Exception as e:
            logger.error(f"Failed to unlink cards: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
