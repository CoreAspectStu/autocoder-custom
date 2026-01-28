"""
DevLayer manager for quality gate workflow orchestration.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

from .models import (
    DevLayerCard, CardLink, PipelineEvent, QualityMetrics,
    TestEvidence, Severity, Category, DevLayerStatus, LinkType,
    PipelineEventType, PipelineStage, PipelineResult
)
from .database import DevLayerDatabase


logger = logging.getLogger(__name__)


class DevLayerConfig:
    """Configuration for DevLayer manager."""

    def __init__(
        self,
        db_path: str = "devlayer.db",
        uat_gateway_url: str = "http://localhost:8889",
        dev_board_url: str = "http://localhost:4000",
        enable_slack: bool = True,
        enable_n8n: bool = True,
        n8n_webhook_url: Optional[str] = None,
        slack_webhook_url: Optional[str] = None,
    ):
        self.db_path = db_path
        self.uat_gateway_url = uat_gateway_url
        self.dev_board_url = dev_board_url
        self.enable_slack = enable_slack
        self.enable_n8n = enable_n8n
        self.n8n_webhook_url = n8n_webhook_url
        self.slack_webhook_url = slack_webhook_url


class DevLayerManager:
    """
    Main manager for DevLayer quality gate workflow.

    Orchestrates the flow: UAT Test Failure → DevLayer Triage → Dev Fix → UAT Retest
    """

    def __init__(self, config: DevLayerConfig, project_id: str):
        self.config = config
        self.project_id = project_id
        self.db = DevLayerDatabase(config.db_path)

    async def create_uat_bug_card(
        self,
        evidence: TestEvidence,
        title: Optional[str] = None,
        uat_card_id: Optional[str] = None,
    ) -> DevLayerCard:
        """
        Create a DevLayer card from UAT test failure.

        This is triggered automatically when a UAT test fails.
        """
        if not title:
            title = f"UAT Bug: {evidence.error_message[:50]}..."

        card = DevLayerCard(
            title=title,
            description=f"Test failure in scenario {evidence.scenario_id}",
            evidence=evidence,
            uat_card_id=uat_card_id,
            status=DevLayerStatus.TRIAGE,
        )

        card_id = self.db.create_card(card)
        card.id = card_id

        # Create pipeline event
        event = PipelineEvent(
            event_type=PipelineEventType.UAT_FAILURE,
            card_id=card_id,
            from_stage=PipelineStage.UAT,
            to_stage=PipelineStage.DEVLAYER,
            evidence={
                "scenario_id": evidence.scenario_id,
                "error_message": evidence.error_message,
                "steps": evidence.steps_to_reproduce,
            },
        )
        self.db.create_pipeline_event(event)

        # Create link to UAT card
        if uat_card_id:
            link = CardLink(
                from_card_id=uat_card_id,
                to_card_id=card_id,
                from_board="uat",
                to_board="devlayer",
                link_type=LinkType.UAT_TO_DEVLAYER,
            )
            self.db.create_card_link(link)

        # Trigger n8n workflow for UAT failure
        if self.config.enable_n8n and self.config.n8n_webhook_url:
            await self._trigger_n8n_workflow("uat_failure", card.to_dict())

        # Send Slack notification
        if self.config.enable_slack and self.config.slack_webhook_url:
            await self._send_slack_notification("uat_failure", card.to_dict())

        logger.info(f"Created DevLayer card {card_id} from UAT failure in scenario {evidence.scenario_id}")
        return card

    async def triage_card(
        self,
        card_id: str,
        severity: Severity,
        category: Category,
        triage_notes: str,
        triaged_by: str,
    ) -> DevLayerCard:
        """
        Triage a DevLayer card with severity and category.
        """
        card = self.db.get_card(card_id)
        if not card:
            raise ValueError(f"Card {card_id} not found")

        card.severity = severity
        card.category = category
        card.triage_notes = triage_notes
        card.triaged_by = triaged_by
        card.triaged_at = datetime.utcnow()

        self.db.update_card(card)
        logger.info(f"Triage complete for card {card_id}: {severity.value} - {category.value}")

        return card

    async def approve_for_dev(
        self,
        card_id: str,
        approved_by: str,
        assignee: Optional[str] = None,
    ) -> DevLayerCard:
        """
        Approve a DevLayer card for Dev work.

        This triggers automatic creation of a Dev card.
        """
        card = self.db.get_card(card_id)
        if not card:
            raise ValueError(f"Card {card_id} not found")

        card.status = DevLayerStatus.APPROVED_FOR_DEV
        card.approved_by = approved_by
        card.approved_at = datetime.utcnow()

        self.db.update_card(card)

        # Create pipeline event
        event = PipelineEvent(
            event_type=PipelineEventType.DEVLAYER_APPROVAL,
            card_id=card_id,
            from_stage=PipelineStage.DEVLAYER,
            to_stage=PipelineStage.DEV,
            evidence={
                "severity": card.severity.value if card.severity else None,
                "category": card.category.value if card.category else None,
                "approved_by": approved_by,
            },
        )
        self.db.create_pipeline_event(event)

        # Create Dev card (this would call Dev board API)
        dev_card_id = await self._create_dev_card(card, assignee)

        # Update card with Dev reference
        card.dev_card_id = dev_card_id
        card.status = DevLayerStatus.ASSIGNED
        self.db.update_card(card)

        # Create bidirectional link
        link = CardLink(
            from_card_id=card_id,
            to_card_id=dev_card_id,
            from_board="devlayer",
            to_board="dev",
            link_type=LinkType.DEVLAYER_TO_DEV,
        )
        self.db.create_card_link(link)

        # Trigger n8n workflow
        if self.config.enable_n8n and self.config.n8n_webhook_url:
            await self._trigger_n8n_workflow("devlayer_approval", card.to_dict())

        # Send Slack notification
        if self.config.enable_slack and self.config.slack_webhook_url:
            await self._send_slack_notification("devlayer_approval", card.to_dict())

        logger.info(f"Card {card_id} approved for Dev, created Dev card {dev_card_id}")
        return card

    async def on_dev_complete(self, dev_card_id: str, completed_by: str) -> Dict[str, Any]:
        """
        Handle Dev card completion - trigger UAT retest.

        This is called when a Dev card is marked complete.
        """
        # Find linked DevLayer and UAT cards
        links = self.db.get_linked_cards(dev_card_id)
        devlayer_card_id = None
        uat_card_id = None

        for link in links:
            if link.from_board == "devlayer":
                devlayer_card_id = link.from_card_id
            elif link.from_board == "uat":
                uat_card_id = link.from_card_id

        if not devlayer_card_id:
            logger.warning(f"No DevLayer card found for Dev card {dev_card_id}")
            return {"status": "no_linked_card"}

        # Create pipeline event
        event = PipelineEvent(
            event_type=PipelineEventType.DEV_COMPLETE,
            card_id=devlayer_card_id,
            from_stage=PipelineStage.DEV,
            to_stage=PipelineStage.UAT,
            evidence={
                "dev_card_id": dev_card_id,
                "completed_by": completed_by,
            },
        )
        self.db.create_pipeline_event(event)

        # Calculate affected scenarios
        affected_scenarios = await self._calculate_affected_scenarios(dev_card_id)

        # Trigger UAT retest
        retest_result = await self._trigger_uat_retest(
            devlayer_card_id,
            affected_scenarios,
        )

        # Send Slack notification
        if self.config.enable_slack and self.config.slack_webhook_url:
            await self._send_slack_notification("dev_complete", {
                "devlayer_card_id": devlayer_card_id,
                "dev_card_id": dev_card_id,
                "retest_result": retest_result,
            })

        return {
            "status": "retest_triggered",
            "devlayer_card_id": devlayer_card_id,
            "affected_scenarios": affected_scenarios,
            "retest_result": retest_result,
        }

    async def on_uat_retest_complete(
        self,
        devlayer_card_id: str,
        retest_result: Dict[str, Any],
    ) -> str:
        """
        Handle UAT retest completion.

        If passed: Archive all linked cards.
        If failed: Update cards and return to Dev.
        """
        passed = retest_result.get("passed", False)
        result = PipelineResult.PASS if passed else PipelineResult.RETURN

        # Create pipeline event
        event = PipelineEvent(
            event_type=PipelineEventType.UAT_RETEST,
            card_id=devlayer_card_id,
            from_stage=PipelineStage.UAT,
            to_stage=PipelineStage.DEV if not passed else None,
            result=result,
            evidence=retest_result,
        )
        self.db.create_pipeline_event(event)

        if passed:
            # Archive all linked cards
            card = self.db.get_card(devlayer_card_id)
            if card:
                card_ids_to_archive = [devlayer_card_id]
                if card.uat_card_id:
                    card_ids_to_archive.append(card.uat_card_id)
                if card.dev_card_id:
                    card_ids_to_archive.append(card.dev_card_id)

                archived_count = self.db.archive_cards(card_ids_to_archive)

                # Send success notification
                if self.config.enable_slack and self.config.slack_webhook_url:
                    await self._send_slack_notification("uat_retest_passed", {
                        "archived_count": archived_count,
                        "card_ids": card_ids_to_archive,
                    })

                logger.info(f"Archived {archived_count} cards after successful UAT retest")
                return "archived"
        else:
            # Return to Dev
            card = self.db.get_card(devlayer_card_id)
            if card:
                card.status = DevLayerStatus.TRIAGE  # Back to triage
                if card.evidence:
                    # Update with new evidence
                    card.evidence.steps_to_reproduce.extend(
                        retest_result.get("new_failures", [])
                    )
                self.db.update_card(card)

                # Send failure notification
                if self.config.enable_slack and self.config.slack_webhook_url:
                    await self._send_slack_notification("uat_retest_failed", {
                        "devlayer_card_id": devlayer_card_id,
                        "new_failures": retest_result.get("new_failures", []),
                    })

                logger.info(f"Card {devlayer_card_id} returned to Dev after failed retest")
                return "returned_to_dev"

        return "unknown"

    async def _create_dev_card(self, devlayer_card: DevLayerCard, assignee: Optional[str]) -> str:
        """Create a Dev card from DevLayer approval."""
        # This would call the Dev board API
        # For now, return a mock ID
        import uuid
        dev_card_id = f"dev-{uuid.uuid4().hex[:8]}"

        logger.info(f"Created Dev card {dev_card_id} from DevLayer card {devlayer_card.id}")
        return dev_card_id

    async def _calculate_affected_scenarios(self, dev_card_id: str) -> List[str]:
        """
        Calculate which UAT scenarios are affected by a Dev change.

        Uses code coverage data to determine impact.
        """
        # This would integrate with code coverage tools
        # For now, return all scenarios
        return ["all"]

    async def _trigger_uat_retest(
        self,
        devlayer_card_id: str,
        affected_scenarios: List[str],
    ) -> Dict[str, Any]:
        """
        Trigger UAT retest for affected scenarios.

        Calls UAT Gateway orchestrator to run targeted tests.
        """
        try:
            # Import UAT Gateway orchestrator
            import sys
            import os
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))

            from custom.uat_gateway.orchestrator.orchestrator import (
                Orchestrator,
                OrchestratorConfig,
            )

            # Path to project
            project_path = Path.home() / "projects" / "autocoder-projects" / self.project_id

            # Change to project directory for orchestrator
            original_cwd = os.getcwd()
            os.chdir(project_path)

            # Configure orchestrator for retest
            config = OrchestratorConfig(
                spec_path="spec.yaml",
                state_directory=str(Path.home() / ".autocoder" / "uat_gateway" / self.project_id),
                base_url="http://localhost:3000",
            )

            # Run UAT cycle for retest
            orchestrator = Orchestrator(config)
            result = orchestrator.run_cycle()

            # Restore original directory
            os.chdir(original_cwd)

            # Extract test results
            test_results = []
            if hasattr(result, 'test_results') and result.test_results:
                for tr in result.test_results:
                    test_results.append({
                        "scenario": tr.scenario_id,
                        "status": tr.status,
                        "error": tr.error_message,
                    })

            return {
                "passed": result.success,
                "scenarios_tested": affected_scenarios,
                "test_results": test_results,
            }

        except Exception as e:
            logger.error(f"Failed to trigger UAT retest: {e}")
            # Return failure result so workflow can continue
            return {
                "passed": False,
                "scenarios_tested": affected_scenarios,
                "test_results": [],
                "error": str(e),
            }

    async def _trigger_n8n_workflow(self, workflow_type: str, data: Dict[str, Any]) -> bool:
        """Trigger an n8n workflow."""
        if not self.config.n8n_webhook_url:
            return False

        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "workflow_type": workflow_type,
                    "project_id": self.project_id,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                }

                async with session.post(
                    self.config.n8n_webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        logger.info(f"n8n workflow '{workflow_type}' triggered successfully")
                        return True
                    else:
                        logger.warning(f"n8n workflow '{workflow_type}' returned status {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to trigger n8n workflow '{workflow_type}': {e}")
            return False

    async def _send_slack_notification(self, notification_type: str, data: Dict[str, Any]) -> bool:
        """Send a Slack notification."""
        if not self.config.slack_webhook_url:
            return False

        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                # Format message based on type
                message = self._format_slack_message(notification_type, data)

                async with session.post(
                    self.config.slack_webhook_url,
                    json={"text": message},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        logger.info(f"Slack notification '{notification_type}' sent successfully")
                        return True
                    else:
                        logger.warning(f"Slack notification '{notification_type}' returned status {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Slack notification '{notification_type}': {e}")
            return False

    def _format_slack_message(self, notification_type: str, data: Dict[str, Any]) -> str:
        """Format a Slack notification message."""
        emoji_map = {
            "uat_failure": "🐞",
            "devlayer_approval": "✅",
            "dev_complete": "🔧",
            "uat_retest_passed": "✨",
            "uat_retest_failed": "❌",
        }

        emoji = emoji_map.get(notification_type, "ℹ️")

        if notification_type == "uat_failure":
            return (
                f"{emoji} *UAT Test Failed*\n"
                f"Scenario: {data.get('evidence', {}).get('scenario_id', 'Unknown')}\n"
                f"Error: {data.get('evidence', {}).get('error_message', 'Unknown')}\n"
                f"Card ID: {data.get('id', 'Unknown')}"
            )

        elif notification_type == "devlayer_approval":
            return (
                f"{emoji} *Bug Approved for Dev*\n"
                f"Severity: {data.get('severity', 'Unknown')}\n"
                f"Category: {data.get('category', 'Unknown')}\n"
                f"Card ID: {data.get('id', 'Unknown')}"
            )

        elif notification_type == "dev_complete":
            return (
                f"{emoji} *Dev Card Complete - Retesting*\n"
                f"DevLayer Card: {data.get('devlayer_card_id', 'Unknown')}\n"
                f"Dev Card: {data.get('dev_card_id', 'Unknown')}"
            )

        elif notification_type == "uat_retest_passed":
            return (
                f"{emoji} *UAT Retest Passed - Archiving Cards*\n"
                f"Archived: {data.get('archived_count', 0)} cards"
            )

        elif notification_type == "uat_retest_failed":
            return (
                f"{emoji} *UAT Retest Failed - Returning to Dev*\n"
                f"Card: {data.get('devlayer_card_id', 'Unknown')}\n"
                f"New Failures: {len(data.get('new_failures', []))}"
            )

        return f"{emoji} {notification_type}: {data}"

    def get_card(self, card_id: str) -> Optional[DevLayerCard]:
        """Get a DevLayer card by ID."""
        return self.db.get_card(card_id)

    def get_cards_by_status(self, status: DevLayerStatus) -> List[DevLayerCard]:
        """Get all cards with a specific status."""
        return self.db.get_cards_by_status(status)

    def get_board_stats(self) -> Dict[str, int]:
        """Get board statistics."""
        return self.db.get_board_stats()

    def get_quality_metrics(self) -> QualityMetrics:
        """Get quality pipeline metrics."""
        return self.db.get_quality_metrics()

    def get_pipeline_events(self, card_id: Optional[str] = None, limit: int = 100) -> List[PipelineEvent]:
        """Get pipeline events."""
        return self.db.get_pipeline_events(card_id, limit)

    def get_linked_cards(self, card_id: str) -> List[CardLink]:
        """Get linked cards for a card."""
        return self.db.get_linked_cards(card_id)
