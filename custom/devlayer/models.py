"""
DevLayer data models for quality gate workflow.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal, Dict, Any
from enum import Enum


class Severity(str, Enum):
    """Bug severity levels"""
    CRITICAL = "Critical"  # 🔴
    HIGH = "High"          # 🟡
    MEDIUM = "Medium"      # 🟢
    LOW = "Low"            # ⚪


class Category(str, Enum):
    """Bug categories"""
    UI = "UI"
    LOGIC = "Logic"
    API = "API"
    PERFORMANCE = "Performance"
    ACCESSIBILITY = "A11Y"


class DevLayerStatus(str, Enum):
    """DevLayer card statuses"""
    TRIAGE = "triage"
    APPROVED_FOR_DEV = "approved_for_dev"
    ASSIGNED = "assigned"
    MONITORING = "monitoring"


class LinkType(str, Enum):
    """Card link types"""
    UAT_TO_DEVLAYER = "uat_to_devlayer"
    DEVLAYER_TO_DEV = "devlayer_to_dev"
    UAT_TO_DEV = "uat_to_dev"


class PipelineEventType(str, Enum):
    """Pipeline event types"""
    UAT_FAILURE = "uat_failure"
    DEVLAYER_APPROVAL = "devlayer_approval"
    DEV_COMPLETE = "dev_complete"
    UAT_RETEST = "uat_retest"


class PipelineStage(str, Enum):
    """Pipeline stages"""
    UAT = "uat"
    DEVLAYER = "devlayer"
    DEV = "dev"


class PipelineResult(str, Enum):
    """Pipeline event results"""
    PASS = "pass"
    FAIL = "fail"
    ARCHIVE = "archive"
    RETURN = "return"


@dataclass
class TestEvidence:
    """Test evidence from UAT failure"""
    scenario_id: str
    error_message: str
    steps_to_reproduce: list[str]
    screenshot_path: Optional[str] = None
    log_path: Optional[str] = None
    trace_path: Optional[str] = None
    journey_id: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DevLayerCard:
    """DevLayer card model"""
    id: Optional[str] = None
    uat_card_id: Optional[str] = None
    dev_card_id: Optional[str] = None
    severity: Optional[Severity] = None
    category: Optional[Category] = None
    triage_notes: Optional[str] = None
    triaged_by: Optional[str] = None
    triaged_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    status: DevLayerStatus = DevLayerStatus.TRIAGE
    title: str = ""
    description: str = ""
    evidence: Optional[TestEvidence] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def get_severity_emoji(self) -> str:
        """Get emoji for severity level"""
        emojis = {
            Severity.CRITICAL: "🔴",
            Severity.HIGH: "🟡",
            Severity.MEDIUM: "🟢",
            Severity.LOW: "⚪",
        }
        return emojis.get(self.severity, "⚪")

    def get_card_type_emoji(self) -> str:
        """Get emoji for card type (bug vs issue)"""
        return "🐛" if self.evidence else "📋"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "uat_card_id": self.uat_card_id,
            "dev_card_id": self.dev_card_id,
            "severity": self.severity.value if self.severity else None,
            "category": self.category.value if self.category else None,
            "triage_notes": self.triage_notes,
            "triaged_by": self.triaged_by,
            "triaged_at": self.triaged_at.isoformat() if self.triaged_at else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "evidence": {
                "scenario_id": self.evidence.scenario_id,
                "error_message": self.evidence.error_message,
                "steps_to_reproduce": self.evidence.steps_to_reproduce,
            } if self.evidence else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "emoji": f"{self.get_severity_emoji()} {self.get_card_type_emoji()}",
        }


@dataclass
class CardLink:
    """Bidirectional card link"""
    id: Optional[str] = None
    from_card_id: str = ""
    to_card_id: str = ""
    from_board: str = ""  # uat, devlayer, dev
    to_board: str = ""
    link_type: LinkType = LinkType.UAT_TO_DEVLAYER
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "from_card_id": self.from_card_id,
            "to_card_id": self.to_card_id,
            "from_board": self.from_board,
            "to_board": self.to_board,
            "link_type": self.link_type.value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class PipelineEvent:
    """Pipeline event for tracking card movement"""
    id: Optional[str] = None
    event_type: PipelineEventType = PipelineEventType.UAT_FAILURE
    card_id: str = ""
    from_stage: Optional[PipelineStage] = None
    to_stage: Optional[PipelineStage] = None
    result: Optional[PipelineResult] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "card_id": self.card_id,
            "from_stage": self.from_stage.value if self.from_stage else None,
            "to_stage": self.to_stage.value if self.to_stage else None,
            "result": self.result.value if self.result else None,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class QualityMetrics:
    """Quality pipeline metrics"""
    uat_pass_rate: float = 0.0
    uat_total_tests: int = 0
    uat_failed_tests: int = 0
    devlayer_triage_count: int = 0
    devlayer_approved_count: int = 0
    dev_active_cards: int = 0
    dev_completed_cards: int = 0
    pipeline_velocity_hours: Dict[str, float] = field(default_factory=dict)
    cards_in_pipeline: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "uat_pass_rate": round(self.uat_pass_rate * 100, 2),
            "uat_total_tests": self.uat_total_tests,
            "uat_failed_tests": self.uat_failed_tests,
            "devlayer_triage_count": self.devlayer_triage_count,
            "devlayer_approved_count": self.devlayer_approved_count,
            "dev_active_cards": self.dev_active_cards,
            "dev_completed_cards": self.dev_completed_cards,
            "pipeline_velocity_hours": self.pipeline_velocity_hours,
            "cards_in_pipeline": self.cards_in_pipeline,
        }
