"""
DevLayer - Quality Gate Board for AutoCoder
============================================

DevLayer provides a triage board between UAT Gateway and Dev boards.
When UAT tests fail, bugs flow to DevLayer for prioritization, then to
Dev for fixes, then back to UAT for retesting.

Features:
- Triage board with severity levels and categories
- Bidirectional card linking between UAT, DevLayer, and Dev
- Automated triggers for card movement
- Smart retesting of affected scenarios only
- Quality pipeline dashboard
- n8n workflow integrations

Usage:
    from custom.devlayer import DevLayerManager

    manager = DevLayerManager(project_id="my-project")
    await manager.create_uat_bug_card(test_failure)
    await manager.approve_for_dev(card_id, severity="High")
"""

__version__ = "1.0.0"

from .manager import DevLayerManager, DevLayerConfig
from .models import (
    DevLayerCard,
    CardLink,
    PipelineEvent,
    QualityMetrics,
    TestEvidence,
    Severity,
    Category,
    DevLayerStatus,
    LinkType,
    PipelineEventType,
    PipelineStage,
    PipelineResult,
)

__all__ = [
    "DevLayerManager",
    "DevLayerConfig",
    "DevLayerCard",
    "CardLink",
    "PipelineEvent",
    "QualityMetrics",
    "TestEvidence",
    "Severity",
    "Category",
    "DevLayerStatus",
    "LinkType",
    "PipelineEventType",
    "PipelineStage",
    "PipelineResult",
    "__version__",
]
