"""
DevLayer database schema and operations.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from .models import (
    DevLayerCard, CardLink, PipelineEvent, QualityMetrics,
    Severity, Category, DevLayerStatus, LinkType, PipelineEventType,
    PipelineStage, PipelineResult
)


class DevLayerDatabase:
    """Database operations for DevLayer quality gate system."""

    def __init__(self, db_path: str = "devlayer.db"):
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_database(self):
        """Initialize database tables."""
        with self.get_connection() as conn:
            conn.executescript("""
                -- DevLayer cards table
                CREATE TABLE IF NOT EXISTS devlayer_cards (
                    id TEXT PRIMARY KEY,
                    uat_card_id TEXT,
                    dev_card_id TEXT,
                    severity TEXT,
                    category TEXT,
                    triage_notes TEXT,
                    triaged_by TEXT,
                    triaged_at TIMESTAMP,
                    approved_by TEXT,
                    approved_at TIMESTAMP,
                    status TEXT DEFAULT 'triage',
                    title TEXT,
                    description TEXT,
                    evidence_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Card links table
                CREATE TABLE IF NOT EXISTS card_links (
                    id TEXT PRIMARY KEY,
                    from_card_id TEXT NOT NULL,
                    to_card_id TEXT NOT NULL,
                    from_board TEXT NOT NULL,
                    to_board TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Pipeline events table
                CREATE TABLE IF NOT EXISTS pipeline_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    card_id TEXT NOT NULL,
                    from_stage TEXT,
                    to_stage TEXT,
                    result TEXT,
                    evidence_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Archived cards table
                CREATE TABLE IF NOT EXISTS archived_cards (
                    id TEXT PRIMARY KEY,
                    devlayer_card_id TEXT,
                    uat_card_id TEXT,
                    dev_card_id TEXT,
                    card_data_json TEXT NOT NULL,
                    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_devlayer_cards_status ON devlayer_cards(status);
                CREATE INDEX IF NOT EXISTS idx_devlayer_cards_severity ON devlayer_cards(severity);
                CREATE INDEX IF NOT EXISTS idx_card_links_from ON card_links(from_card_id);
                CREATE INDEX IF NOT EXISTS idx_card_links_to ON card_links(to_card_id);
                CREATE INDEX IF NOT EXISTS idx_pipeline_events_card ON pipeline_events(card_id);
                CREATE INDEX IF NOT EXISTS idx_pipeline_events_type ON pipeline_events(event_type);
            """)

    def create_card(self, card: DevLayerCard) -> str:
        """Create a new DevLayer card."""
        import uuid
        card_id = str(uuid.uuid4())
        card.id = card_id
        card.created_at = datetime.utcnow()
        card.updated_at = datetime.utcnow()

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO devlayer_cards (
                    id, uat_card_id, dev_card_id, severity, category,
                    triage_notes, triaged_by, triaged_at, approved_by, approved_at,
                    status, title, description, evidence_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                card.id, card.uat_card_id, card.dev_card_id,
                card.severity.value if card.severity else None,
                card.category.value if card.category else None,
                card.triage_notes, card.triaged_by,
                card.triaged_at.isoformat() if card.triaged_at else None,
                card.approved_by,
                card.approved_at.isoformat() if card.approved_at else None,
                card.status.value, card.title, card.description,
                json.dumps({
                    "scenario_id": card.evidence.scenario_id,
                    "error_message": card.evidence.error_message,
                    "steps_to_reproduce": card.evidence.steps_to_reproduce,
                    "screenshot_path": card.evidence.screenshot_path,
                    "log_path": card.evidence.log_path,
                    "trace_path": card.evidence.trace_path,
                    "journey_id": card.evidence.journey_id,
                }) if card.evidence else None,
                card.created_at.isoformat(),
                card.updated_at.isoformat(),
            ))

        return card_id

    def get_card(self, card_id: str) -> Optional[DevLayerCard]:
        """Get a DevLayer card by ID."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM devlayer_cards WHERE id = ?",
                (card_id,)
            ).fetchone()

            if not row:
                return None

            evidence = None
            if row["evidence_json"]:
                evidence_data = json.loads(row["evidence_json"])
                from .models import TestEvidence
                evidence = TestEvidence(**evidence_data)

            return DevLayerCard(
                id=row["id"],
                uat_card_id=row["uat_card_id"],
                dev_card_id=row["dev_card_id"],
                severity=Severity(row["severity"]) if row["severity"] else None,
                category=Category(row["category"]) if row["category"] else None,
                triage_notes=row["triage_notes"],
                triaged_by=row["triaged_by"],
                triaged_at=datetime.fromisoformat(row["triaged_at"]) if row["triaged_at"] else None,
                approved_by=row["approved_by"],
                approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
                status=DevLayerStatus(row["status"]),
                title=row["title"],
                description=row["description"],
                evidence=evidence,
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def update_card(self, card: DevLayerCard) -> bool:
        """Update an existing DevLayer card."""
        card.updated_at = datetime.utcnow()

        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE devlayer_cards SET
                    uat_card_id = ?, dev_card_id = ?, severity = ?, category = ?,
                    triage_notes = ?, triaged_by = ?, triaged_at = ?,
                    approved_by = ?, approved_at = ?, status = ?,
                    title = ?, description = ?, evidence_json = ?, updated_at = ?
                WHERE id = ?
            """, (
                card.uat_card_id, card.dev_card_id,
                card.severity.value if card.severity else None,
                card.category.value if card.category else None,
                card.triage_notes, card.triaged_by,
                card.triaged_at.isoformat() if card.triaged_at else None,
                card.approved_by,
                card.approved_at.isoformat() if card.approved_at else None,
                card.status.value, card.title, card.description,
                json.dumps({
                    "scenario_id": card.evidence.scenario_id,
                    "error_message": card.evidence.error_message,
                    "steps_to_reproduce": card.evidence.steps_to_reproduce,
                    "screenshot_path": card.evidence.screenshot_path,
                    "log_path": card.evidence.log_path,
                    "trace_path": card.evidence.trace_path,
                    "journey_id": card.evidence.journey_id,
                }) if card.evidence else None,
                card.updated_at.isoformat(),
                card.id,
            ))

            return cursor.rowcount > 0

    def get_cards_by_status(self, status: DevLayerStatus) -> List[DevLayerCard]:
        """Get all cards with a specific status."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM devlayer_cards WHERE status = ? ORDER BY created_at DESC",
                (status.value,)
            ).fetchall()

            cards = []
            for row in rows:
                evidence = None
                if row["evidence_json"]:
                    evidence_data = json.loads(row["evidence_json"])
                    from .models import TestEvidence
                    evidence = TestEvidence(**evidence_data)

                cards.append(DevLayerCard(
                    id=row["id"],
                    uat_card_id=row["uat_card_id"],
                    dev_card_id=row["dev_card_id"],
                    severity=Severity(row["severity"]) if row["severity"] else None,
                    category=Category(row["category"]) if row["category"] else None,
                    triage_notes=row["triage_notes"],
                    triaged_by=row["triaged_by"],
                    triaged_at=datetime.fromisoformat(row["triaged_at"]) if row["triaged_at"] else None,
                    approved_by=row["approved_by"],
                    approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
                    status=DevLayerStatus(row["status"]),
                    title=row["title"],
                    description=row["description"],
                    evidence=evidence,
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                ))

            return cards

    def create_card_link(self, link: CardLink) -> str:
        """Create a bidirectional card link."""
        import uuid
        link_id = str(uuid.uuid4())
        link.id = link_id

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO card_links (id, from_card_id, to_card_id, from_board, to_board, link_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                link.id, link.from_card_id, link.to_card_id,
                link.from_board, link.to_board, link.link_type.value,
                link.created_at.isoformat(),
            ))

            # Create reverse link
            reverse_id = str(uuid.uuid4())
            reverse_type = self._get_reverse_link_type(link.link_type)
            conn.execute("""
                INSERT INTO card_links (id, from_card_id, to_card_id, from_board, to_board, link_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                reverse_id, link.to_card_id, link.from_card_id,
                link.to_board, link.from_board, reverse_type.value,
                link.created_at.isoformat(),
            ))

        return link_id

    def _get_reverse_link_type(self, link_type: LinkType) -> LinkType:
        """Get the reverse link type."""
        reverses = {
            LinkType.UAT_TO_DEVLAYER: LinkType.DEVLAYER_TO_DEV,
            LinkType.DEVLAYER_TO_DEV: LinkType.UAT_TO_DEVLAYER,
            LinkType.UAT_TO_DEV: LinkType.DEVLAYER_TO_DEV,  # Direct link
        }
        return reverses.get(link_type, link_type)

    def get_linked_cards(self, card_id: str) -> List[CardLink]:
        """Get all links for a card."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM card_links WHERE from_card_id = ? OR to_card_id = ?",
                (card_id, card_id)
            ).fetchall()

            return [
                CardLink(
                    id=row["id"],
                    from_card_id=row["from_card_id"],
                    to_card_id=row["to_card_id"],
                    from_board=row["from_board"],
                    to_board=row["to_board"],
                    link_type=LinkType(row["link_type"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    def create_pipeline_event(self, event: PipelineEvent) -> str:
        """Create a pipeline event."""
        import uuid
        event_id = str(uuid.uuid4())
        event.id = event_id

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO pipeline_events (
                    id, event_type, card_id, from_stage, to_stage, result, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.id, event.event_type.value, event.card_id,
                event.from_stage.value if event.from_stage else None,
                event.to_stage.value if event.to_stage else None,
                event.result.value if event.result else None,
                json.dumps(event.evidence),
                event.created_at.isoformat(),
            ))

        return event_id

    def get_pipeline_events(self, card_id: Optional[str] = None, limit: int = 100) -> List[PipelineEvent]:
        """Get pipeline events, optionally filtered by card ID."""
        with self.get_connection() as conn:
            if card_id:
                rows = conn.execute("""
                    SELECT * FROM pipeline_events
                    WHERE card_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (card_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM pipeline_events
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()

            return [
                PipelineEvent(
                    id=row["id"],
                    event_type=PipelineEventType(row["event_type"]),
                    card_id=row["card_id"],
                    from_stage=PipelineStage(row["from_stage"]) if row["from_stage"] else None,
                    to_stage=PipelineStage(row["to_stage"]) if row["to_stage"] else None,
                    result=PipelineResult(row["result"]) if row["result"] else None,
                    evidence=json.loads(row["evidence_json"]) if row["evidence_json"] else {},
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    def archive_cards(self, card_ids: List[str]) -> int:
        """Archive completed cards."""
        import uuid
        archived_count = 0

        with self.get_connection() as conn:
            for card_id in card_ids:
                card = self.get_card(card_id)
                if card:
                    archive_id = str(uuid.uuid4())
                    conn.execute("""
                        INSERT INTO archived_cards (id, devlayer_card_id, uat_card_id, dev_card_id, card_data_json, archived_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        archive_id, card.id, card.uat_card_id, card.dev_card_id,
                        json.dumps(card.to_dict()),
                        datetime.utcnow().isoformat(),
                    ))

                    # Delete from active cards
                    conn.execute("DELETE FROM devlayer_cards WHERE id = ?", (card_id,))
                    archived_count += 1

        return archived_count

    def get_quality_metrics(self) -> QualityMetrics:
        """Calculate quality pipeline metrics."""
        with self.get_connection() as conn:
            # Get card counts by status
            triage_count = conn.execute(
                "SELECT COUNT(*) FROM devlayer_cards WHERE status = 'triage'"
            ).fetchone()[0]

            approved_count = conn.execute(
                "SELECT COUNT(*) FROM devlayer_cards WHERE status = 'approved_for_dev'"
            ).fetchone()[0]

            # Get pipeline velocity (average time in each stage)
            velocity_data = conn.execute("""
                SELECT
                    from_stage,
                    AVG(julianday(created_at) - julianday(
                        (SELECT created_at FROM pipeline_events p2
                         WHERE p2.card_id = p1.card_id
                         AND p2.created_at < p1.created_at
                         ORDER BY p2.created_at DESC LIMIT 1)
                    )) * 24 as avg_hours
                FROM pipeline_events p1
                WHERE from_stage IS NOT NULL
                GROUP BY from_stage
            """).fetchall()

            velocity = {row["from_stage"]: row["avg_hours"] for row in velocity_data}

            # Get cards in pipeline
            cards_in_pipeline = conn.execute(
                "SELECT COUNT(*) FROM devlayer_cards"
            ).fetchone()[0]

            return QualityMetrics(
                devlayer_triage_count=triage_count,
                devlayer_approved_count=approved_count,
                pipeline_velocity_hours=velocity,
                cards_in_pipeline=cards_in_pipeline,
            )

    def get_board_stats(self) -> Dict[str, int]:
        """Get statistics for DevLayer board columns."""
        with self.get_connection() as conn:
            stats = {}

            for status in DevLayerStatus:
                count = conn.execute(
                    "SELECT COUNT(*) FROM devlayer_cards WHERE status = ?",
                    (status.value,)
                ).fetchone()[0]
                stats[status.value] = count

            return stats
