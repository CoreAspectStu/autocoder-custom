"""
Kanban Integrator - Create and manage Kanban cards for testing

This module integrates with Kanban systems (Trello, GitHub Projects, etc.)
to create cards for journeys, scenarios, and bugs.
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import KanbanIntegrationError, handle_errors
from custom.uat_gateway.kanban_integrator.rate_limiter import (
    RateLimiter,
    RateLimitError,
    get_rate_limiter,
    retry_on_rate_limit
)


# ============================================================================
# Data Models
# ============================================================================

class CardStatus(Enum):
    """Status of a Kanban card"""
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


@dataclass
class JourneyCard:
    """Kanban card representing a user journey"""
    card_id: str  # Unique identifier (e.g., "JOURNEY-20250126-001")
    journey_id: str  # ID from JourneyExtractor
    journey_name: str  # Human-readable name
    description: str  # Journey description
    emoji: str  # Journey emoji (🆔)
    status: CardStatus = CardStatus.BACKLOG
    scenario_count: int = 0  # Number of scenarios in this journey
    labels: List[str] = field(default_factory=list)  # Labels for categorization
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Feature #87: Links to feature cards
    linked_feature_ids: List[str] = field(default_factory=list)  # Feature cards this tests
    # Feature #94: Time estimate based on test execution duration
    estimated_work_minutes: int = 0  # Estimated work time in minutes (0 = not estimated)
    # Feature #151: Quick action buttons for UAT cards
    quick_actions: List[Dict[str, str]] = field(default_factory=list)  # Available actions: rerun, view_results, download_report

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "card_id": self.card_id,
            "journey_id": self.journey_id,
            "journey_name": self.journey_name,
            "description": self.description,
            "emoji": self.emoji,
            "status": self.status.value,
            "scenario_count": self.scenario_count,
            "labels": self.labels,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "linked_feature_ids": self.linked_feature_ids,
            "estimated_work_minutes": self.estimated_work_minutes,  # Feature #94
            "quick_actions": self.quick_actions  # Feature #151
        }

    def __str__(self) -> str:
        feature_suffix = f" → Features: {len(self.linked_feature_ids)}" if self.linked_feature_ids else ""
        return f"{self.emoji} {self.journey_name} ({self.card_id}){feature_suffix}"


@dataclass
class BugKanbanCard:
    """Kanban card representing a bug from test failure (Feature #88)"""
    card_id: str  # Unique identifier (e.g., "BUG-KANBAN-20250126-001")
    title: str  # Card title (derived from test name)
    test_name: str  # Test that found this bug (links to test)
    failure_type: str  # e.g., 'selector_not_found', 'timeout', 'assertion_failed', 'network_error'
    severity: str  # 'critical', 'high', 'medium', 'low'
    priority: int  # 1-10, 1 is highest priority
    error_message: Optional[str] = None  # Error message from test failure
    suggestion: Optional[str] = None  # Suggested fix
    assignee: Optional[str] = None  # Assigned developer/team
    labels: List[str] = field(default_factory=list)  # Labels for categorization
    status: CardStatus = CardStatus.TODO  # Bug cards start in TODO
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "card_id": self.card_id,
            "title": self.title,
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "severity": self.severity,
            "priority": self.priority,
            "error_message": self.error_message,
            "suggestion": self.suggestion,
            "assignee": self.assignee,
            "labels": self.labels,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    def __str__(self) -> str:
        return f"🐛 {self.title} ({self.card_id})"


@dataclass
class ScenarioCard:
    """Kanban card representing a test scenario"""
    card_id: str  # Unique identifier (e.g., "SCENARIO-20250126-001")
    scenario_id: str  # ID from JourneyExtractor
    scenario_name: str  # Human-readable name
    description: str  # Scenario description
    emoji: str  # Test emoji (🧪)
    status: CardStatus = CardStatus.BACKLOG
    journey_id: str = ""  # Parent journey ID for linking
    journey_name: str = ""  # Parent journey name for context
    scenario_type: str = ""  # happy_path or error_path
    step_count: int = 0  # Number of steps in this scenario
    labels: List[str] = field(default_factory=list)  # Labels for categorization
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Feature #87: Links to feature cards
    linked_feature_ids: List[str] = field(default_factory=list)  # Feature cards this tests
    # Feature #94: Time estimate based on test execution duration
    estimated_work_minutes: int = 0  # Estimated work time in minutes (0 = not estimated)
    # Feature #151: Quick action buttons for UAT cards
    quick_actions: List[Dict[str, str]] = field(default_factory=list)  # Available actions: rerun, view_results, download_report

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "card_id": self.card_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "description": self.description,
            "emoji": self.emoji,
            "status": self.status.value,
            "journey_id": self.journey_id,
            "journey_name": self.journey_name,
            "scenario_type": self.scenario_type,
            "step_count": self.step_count,
            "labels": self.labels,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "linked_feature_ids": self.linked_feature_ids,
            "estimated_work_minutes": self.estimated_work_minutes,  # Feature #94
            "quick_actions": self.quick_actions  # Feature #151
        }

    def __str__(self) -> str:
        feature_suffix = f" → Features: {len(self.linked_feature_ids)}" if self.linked_feature_ids else ""
        return f"{self.emoji} {self.scenario_name} ({self.card_id}){feature_suffix}"


# ============================================================================
# Main Integrator Class
# ============================================================================

class KanbanIntegrator:
    """
    Integrates with Kanban systems to create and manage cards

    This class handles:
    - Creating journey cards with journey emoji (🆔) - Feature #83
    - Creating scenario cards with test emoji (🧪) - Feature #84
    - Updating card status based on test results (pending Feature #85)
    - Adding test results as comments (pending Feature #86)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Kanban integrator

        Args:
            config: Configuration dictionary with API keys, board IDs, etc.
                   Example: {
                       "provider": "trello" | "github" | "linear",
                       "api_key": "...",
                       "board_id": "...",
                       ...
                   }
        """
        self.logger = get_logger(__name__)
        self.config = config or {}
        self._card_counter = 0  # Track number of cards created

        # Kanban provider (trello, github, linear, etc.)
        self.provider = self.config.get("provider", "mock")

        # Rate limiter for API calls (Feature #90)
        rate_limit_config = self.config.get("rate_limit", {})
        if rate_limit_config:
            requests_per_minute = rate_limit_config.get("requests_per_minute", 100)
            self._rate_limiter = RateLimiter(requests_per_minute=requests_per_minute)
            self.logger.info(f"Rate limiter enabled: {requests_per_minute} requests per minute")
        else:
            # Use default rate limiter
            self._rate_limiter = get_rate_limiter()
            self.logger.info("Using default rate limiter (100 requests per minute)")

        # In-memory card storage for mock provider (Feature #85)
        # Stores cards by card_id for status tracking
        self._cards: Dict[str, Any] = {}  # card_id -> JourneyCard/ScenarioCard/BugKanbanCard

        # Reverse mapping for feature-to-test-card links (Feature #87)
        self._feature_to_test_cards: Dict[str, List[str]] = {}  # feature_id -> list of test card IDs

        # Persistent storage for file provider (Feature #263)
        if self.provider == "file":
            self.storage_dir = Path(self.config.get("storage_dir", "state/kanban_cards"))
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            # Load existing cards from storage
            self._load_cards_from_disk()
            self.logger.info(f"File-based storage enabled: {self.storage_dir}")
        else:
            self.storage_dir = None

        self.logger.info(f"KanbanIntegrator initialized with provider: {self.provider}")

    def get_rate_limiter_stats(self) -> Dict[str, Any]:
        """
        Get rate limiter statistics (Feature #90)

        Returns:
            Dictionary with rate limiter statistics including:
            - requests_per_minute_limit: Configured limit
            - requests_in_last_minute: Current request count
            - remaining_capacity: Available request capacity
            - total_requests: Total requests made
            - rate_limit_hits: Number of times rate limit was hit
            - total_wait_time_seconds: Total time spent waiting
            - average_wait_time_seconds: Average wait per request
        """
        return self._rate_limiter.get_stats()

    def _load_cards_from_disk(self) -> None:
        """
        Load all cards from disk storage (Feature #263)

        This method loads all persisted cards from the storage directory
        into memory. Called during initialization for file provider.
        """
        if not self.storage_dir or not self.storage_dir.exists():
            return

        loaded_count = 0
        for card_file in self.storage_dir.glob("*.json"):
            try:
                with open(card_file, 'r') as f:
                    card_data = json.load(f)

                # Reconstruct card object based on type
                card_id = card_data.get("card_id")
                if not card_id:
                    continue

                # Determine card type from ID prefix
                if card_id.startswith("JOURNEY-"):
                    card = JourneyCard(**card_data)
                elif card_id.startswith("SCENARIO-"):
                    from custom.uat_gateway.kanban_integrator.kanban_integrator import ScenarioCard
                    card = ScenarioCard(**card_data)
                elif card_id.startswith("BUG-"):
                    card = BugKanbanCard(**card_data)
                else:
                    self.logger.warning(f"Unknown card type for {card_id}, skipping")
                    continue

                # Convert ISO strings back to datetime objects
                if "created_at" in card_data and isinstance(card_data["created_at"], str):
                    card.created_at = datetime.fromisoformat(card_data["created_at"])
                if "updated_at" in card_data and isinstance(card_data["updated_at"], str):
                    card.updated_at = datetime.fromisoformat(card_data["updated_at"])

                # Convert status string back to enum
                if "status" in card_data and isinstance(card_data["status"], str):
                    card.status = CardStatus(card_data["status"])

                self._cards[card_id] = card
                loaded_count += 1

            except Exception as e:
                self.logger.error(f"Failed to load card from {card_file}: {e}")

        if loaded_count > 0:
            self.logger.info(f"Loaded {loaded_count} cards from disk storage")

    def _save_card_to_disk(self, card: Any) -> None:
        """
        Save a card to disk storage (Feature #263)

        Args:
            card: JourneyCard, ScenarioCard, or BugKanbanCard to save
        """
        if not self.storage_dir:
            return

        try:
            card_file = self.storage_dir / f"{card.card_id}.json"

            # Convert card to dictionary
            card_data = card.to_dict() if hasattr(card, 'to_dict') else {
                "card_id": card.card_id,
                "journey_id": card.journey_id,
                "journey_name": card.journey_name,
                "description": card.description,
                "emoji": card.emoji,
                "status": card.status.value if hasattr(card.status, 'value') else card.status,
                "scenario_count": card.scenario_count,
                "labels": card.labels,
                "created_at": card.created_at.isoformat(),
                "updated_at": card.updated_at.isoformat(),
                "linked_feature_ids": getattr(card, 'linked_feature_ids', []),
                "estimated_work_minutes": getattr(card, 'estimated_work_minutes', 0),
                "quick_actions": getattr(card, 'quick_actions', [])
            }

            # Write to disk
            with open(card_file, 'w') as f:
                json.dump(card_data, f, indent=2)

            self.logger.debug(f"Saved card to disk: {card_file}")

        except Exception as e:
            self.logger.error(f"Failed to save card {card.card_id} to disk: {e}")

    def _delete_card_from_disk(self, card_id: str) -> bool:
        """
        Delete a card from disk storage (Feature #263)

        Args:
            card_id: ID of card to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if not self.storage_dir:
            return False

        try:
            card_file = self.storage_dir / f"{card_id}.json"

            if card_file.exists():
                card_file.unlink()
                self.logger.debug(f"Deleted card from disk: {card_file}")
                return True
            else:
                self.logger.warning(f"Card file not found for deletion: {card_file}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to delete card {card_id} from disk: {e}")
            return False

    def _generate_quick_actions(self, card_type: str, card_id: str) -> List[Dict[str, str]]:
        """
        Generate quick action buttons for UAT cards (Feature #151)

        Args:
            card_type: Type of card ('journey' or 'scenario')
            card_id: Unique card identifier

        Returns:
            List of action dictionaries with 'id', 'label', 'icon', and 'action' keys
        """
        # Common quick actions for UAT cards
        actions = [
            {
                "id": f"{card_id}_rerun",
                "label": "Rerun Tests",
                "icon": "🔄",
                "action": "rerun",
                "description": "Rerun all tests for this journey/scenario"
            },
            {
                "id": f"{card_id}_view_results",
                "label": "View Results",
                "icon": "📊",
                "action": "view_results",
                "description": "View detailed test results and execution history"
            },
            {
                "id": f"{card_id}_download_report",
                "label": "Download Report",
                "icon": "📥",
                "action": "download_report",
                "description": "Download test execution report as PDF/JSON"
            }
        ]

        return actions

    def _find_existing_journey_card(self, journey_id: str) -> Optional[JourneyCard]:
        """
        Find an existing journey card by journey_id (Feature #268)

        Args:
            journey_id: Journey ID to search for

        Returns:
            JourneyCard if found, None otherwise
        """
        # For mock provider, search in-memory storage
        if self.provider == "mock":
            for card_id, card in self._cards.items():
                if isinstance(card, JourneyCard) and card.journey_id == journey_id:
                    self.logger.debug(f"Found existing card for journey {journey_id}: {card_id}")
                    return card
            return None
        else:
            # For real providers, this would query the Kanban API
            self.logger.warning(f"_find_existing_journey_card not implemented for provider {self.provider}")
            return None

    @handle_errors(component="kanban_integrator", reraise=True)
    def create_journey_cards(self, journeys: List[Any]) -> List[JourneyCard]:
        """
        Create Kanban cards for each journey (Feature #83)

        Prevents duplicate cards for the same journey (Feature #268).

        Args:
            journeys: List of Journey objects from JourneyExtractor

        Returns:
            List of JourneyCard objects

        Raises:
            KanbanIntegrationError: If card creation fails
        """
        self.logger.info(f"Creating journey cards for {len(journeys)} journeys")

        cards = []

        for journey in journeys:
            try:
                # Extract journey information
                journey_id = getattr(journey, 'journey_id', 'unknown')
                journey_name = getattr(journey, 'name', 'Unnamed Journey')
                description = getattr(journey, 'description', '')
                scenarios = getattr(journey, 'scenarios', [])

                # Feature #268: Check for existing card to prevent duplicates
                existing_card = self._find_existing_journey_card(journey_id)
                if existing_card:
                    self.logger.info(
                        f"Journey card already exists for {journey_id}, "
                        f"returning existing card {existing_card.card_id}"
                    )
                    cards.append(existing_card)
                    continue

                # Generate unique card ID
                self._card_counter += 1
                date_str = datetime.now().strftime("%Y%m%d")
                card_id = f"JOURNEY-{date_str}-{self._card_counter:03d}"

                # Generate quick actions for this card (Feature #151)
                quick_actions = self._generate_quick_actions("journey", card_id)

                # Create journey card with journey emoji
                card = JourneyCard(
                    card_id=card_id,
                    journey_id=journey_id,
                    journey_name=journey_name,
                    description=description,
                    emoji="🆔",  # Journey emoji (Feature #83 requirement)
                    scenario_count=len(scenarios),
                    labels=self._generate_journey_labels(journey),
                    quick_actions=quick_actions  # Feature #151
                )

                cards.append(card)

                # Store card in memory for mock provider (Feature #85)
                self._cards[card_id] = card

                # Save to disk for file provider (Feature #263)
                if self.provider == "file":
                    self._save_card_to_disk(card)

                self.logger.debug(f"Created journey card: {card}")

            except Exception as e:
                self.logger.error(f"Failed to create card for journey: {e}")
                raise KanbanIntegrationError(f"Failed to create journey card: {e}")

        self.logger.info(f"Created {len(cards)} journey cards")
        return cards

    @handle_errors(component="kanban_integrator", reraise=True)
    def create_scenario_cards(self, journeys: List[Any]) -> List[ScenarioCard]:
        """
        Create Kanban cards for each scenario (Feature #84)

        Args:
            journeys: List of Journey objects from JourneyExtractor

        Returns:
            List of ScenarioCard objects

        Raises:
            KanbanIntegrationError: If card creation fails
        """
        self.logger.info(f"Creating scenario cards for {len(journeys)} journeys")

        cards = []

        for journey in journeys:
            try:
                # Extract journey information
                journey_id = getattr(journey, 'journey_id', 'unknown')
                journey_name = getattr(journey, 'name', 'Unnamed Journey')
                scenarios = getattr(journey, 'scenarios', [])

                # Create a scenario card for each scenario
                for scenario in scenarios:
                    # Extract scenario information
                    scenario_id = getattr(scenario, 'scenario_id', 'unknown')
                    scenario_name = getattr(scenario, 'name', 'Unnamed Scenario')
                    description = getattr(scenario, 'description', '')
                    scenario_type = getattr(scenario, 'scenario_type', None)
                    steps = getattr(scenario, 'steps', [])

                    # Generate unique card ID
                    self._card_counter += 1
                    date_str = datetime.now().strftime("%Y%m%d")
                    card_id = f"SCENARIO-{date_str}-{self._card_counter:03d}"

                    # Generate quick actions for this card (Feature #151)
                    quick_actions = self._generate_quick_actions("scenario", card_id)

                    # Create scenario card with test emoji
                    card = ScenarioCard(
                        card_id=card_id,
                        scenario_id=scenario_id,
                        scenario_name=scenario_name,
                        description=description,
                        emoji="🧪",  # Test emoji (Feature #84 requirement)
                        journey_id=journey_id,
                        journey_name=journey_name,
                        scenario_type=scenario_type.value if scenario_type else "unknown",
                        step_count=len(steps),
                        labels=self._generate_scenario_labels(scenario, journey),
                        quick_actions=quick_actions  # Feature #151
                    )

                    cards.append(card)

                    # Store card in memory for mock provider (Feature #85)
                    self._cards[card_id] = card

                    # Save to disk for file provider (Feature #263)
                    if self.provider == "file":
                        self._save_card_to_disk(card)

                    self.logger.debug(f"Created scenario card: {card}")

            except Exception as e:
                self.logger.error(f"Failed to create card for scenario: {e}")
                raise KanbanIntegrationError(f"Failed to create scenario card: {e}")

        self.logger.info(f"Created {len(cards)} scenario cards")
        return cards

    def _generate_scenario_labels(self, scenario: Any, journey: Any) -> List[str]:
        """
        Generate labels for a scenario card

        Args:
            scenario: Scenario object
            journey: Parent Journey object

        Returns:
            List of label strings
        """
        labels = ["scenario", "automated-test"]

        # Add scenario type label
        scenario_type = getattr(scenario, 'scenario_type', None)
        if scenario_type:
            labels.append(scenario_type.value)

        # Add journey type label for context
        journey_type = getattr(journey, 'journey_type', None)
        if journey_type:
            labels.append(journey_type.value)

        # Add priority label from parent journey
        priority = getattr(journey, 'priority', 5)
        if priority <= 3:
            labels.append("high-priority")
        elif priority >= 8:
            labels.append("low-priority")

        return labels

    def _generate_journey_labels(self, journey: Any) -> List[str]:
        """
        Generate labels for a journey card

        Args:
            journey: Journey object

        Returns:
            List of label strings
        """
        labels = ["journey", "automated-test"]

        # Add journey type label
        journey_type = getattr(journey, 'journey_type', None)
        if journey_type:
            labels.append(journey_type.value)

        # Add priority label
        priority = getattr(journey, 'priority', 5)
        if priority <= 3:
            labels.append("high-priority")
        elif priority >= 8:
            labels.append("low-priority")

        return labels

    @handle_errors(component="kanban_integrator", reraise=False, default_return=0)
    def calculate_time_estimate(self, test_results: List[Any]) -> int:
        """
        Calculate time estimate based on test execution duration (Feature #94)

        Estimates work time required based on:
        - Total test execution time
        - Buffer for debugging, investigation, and fixes
        - Failure rate (more failures = more time needed)

        Args:
            test_results: List of TestResult objects with duration_ms field

        Returns:
            Estimated work time in minutes (rounded to nearest integer)

        Example:
            >>> results = [MockTestResult("test", duration_ms=5000)]
            >>> estimate = integrator.calculate_time_estimate(results)
            >>> print(f"Estimated {estimate} minutes")
        """
        if not test_results:
            self.logger.warning("No test results provided for time estimate")
            return 0

        # Calculate total test duration
        total_duration_ms = sum(
            getattr(t, 'duration_ms', 0) for t in test_results
        )

        # Convert to minutes
        base_minutes = total_duration_ms / 1000 / 60

        # Calculate failure rate
        failed_tests = sum(1 for t in test_results if not getattr(t, 'passed', True))
        failure_rate = failed_tests / len(test_results) if test_results else 0

        # Base buffer multiplier (accounts for overhead)
        # - 1.5x for debugging time
        # - 1.2x for fix time
        # - 1.1x for retest time
        # - 1.3x for investigation time
        # Combined: 1.5 * 1.2 * 1.1 * 1.3 = 2.57x
        base_buffer_multiplier = 2.57

        # Increase buffer based on failure rate
        # More failures = more debugging/fixing needed
        failure_buffer_multiplier = 1.0 + (failure_rate * 2.0)  # Up to 3x for 100% failures

        # Combined buffer
        combined_buffer = base_buffer_multiplier * failure_buffer_multiplier

        # Clamp buffer to reasonable range (1.5x - 5.0x)
        combined_buffer = max(1.5, min(combined_buffer, 5.0))

        # Calculate estimate with buffer
        estimated_minutes = base_minutes * combined_buffer

        # Round to nearest integer (minimum 1 minute)
        estimated_minutes = max(1, int(round(estimated_minutes)))

        self.logger.debug(
            f"Time estimate calculation: "
            f"base_time={base_minutes:.2f}min, "
            f"buffer={combined_buffer:.2f}x, "
            f"estimate={estimated_minutes}min"
        )

        return estimated_minutes

    @handle_errors(component="kanban_integrator", reraise=False)
    def get_card_by_id(self, card_id: str) -> Optional[Any]:
        """
        Retrieve a card by its ID (Feature #85 - now functional for mock provider)

        Args:
            card_id: Card ID to search for

        Returns:
            JourneyCard, ScenarioCard, or BugKanbanCard if found, None otherwise
        """
        # For mock provider, check in-memory storage
        if self.provider == "mock":
            card = self._cards.get(card_id)
            if card:
                self.logger.debug(f"Found card {card_id} in mock storage")
                return card
            else:
                self.logger.warning(f"Card {card_id} not found in mock storage")
                return None
        else:
            # For real providers, this would query the Kanban API
            self.logger.warning(f"get_card_by_id not implemented for provider {self.provider}")
            return None

    @handle_errors(component="kanban_integrator", reraise=False, default_return=False)
    def update_card_status(self, card_id: str, status: CardStatus) -> bool:
        """
        Update the status of a card (Feature #85 - fully implemented for mock provider)

        Args:
            card_id: Card ID to update
            status: New status

        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Updating card {card_id} to status {status.value}")

        # For mock or file provider, update storage
        if self.provider in ("mock", "file"):
            card = self._cards.get(card_id)
            if not card:
                self.logger.error(f"Card {card_id} not found for status update")
                return False

            # Update card status
            old_status = card.status
            card.status = status
            card.updated_at = datetime.now()

            # Save to disk for file provider (Feature #263)
            if self.provider == "file":
                self._save_card_to_disk(card)

            self.logger.info(f"Updated card {card_id} from {old_status.value} to {status.value}")
            return True
        else:
            # For real providers, this would call the Kanban API
            self.logger.warning(f"update_card_status not implemented for provider {self.provider}")
            return False


    @handle_errors(component="kanban_integrator", reraise=False, default_return=False)
    def link_to_feature(self, card_id: str, feature_id: str) -> bool:
        """
        Link a test card to a feature card (Feature #87)

        Creates a bidirectional link between a test card (journey or scenario)
        and the feature card it tests.

        Args:
            card_id: The test card ID (journey or scenario card)
            feature_id: The feature card ID to link to

        Returns:
            True if link was created successfully, False otherwise
        """
        self.logger.info(f"Linking test card {card_id} to feature {feature_id}")

        # For mock provider, update in-memory storage
        if self.provider == "mock":
            card = self._cards.get(card_id)
            if not card:
                self.logger.error(f"Card {card_id} not found for linking")
                return False

            # Check if card supports feature links (JourneyCard or ScenarioCard)
            if not hasattr(card, 'linked_feature_ids'):
                self.logger.warning(f"Card {card_id} does not support feature links")
                return False

            # Add feature_id to card if not already linked
            if feature_id not in card.linked_feature_ids:
                card.linked_feature_ids.append(feature_id)
                card.updated_at = datetime.now()

                # Track reverse mapping for get_linked_test_cards()
                if feature_id not in self._feature_to_test_cards:
                    self._feature_to_test_cards[feature_id] = []

                if card_id not in self._feature_to_test_cards[feature_id]:
                    self._feature_to_test_cards[feature_id].append(card_id)

                self.logger.info(f"Created bidirectional link: {card_id} ↔ {feature_id}")
            else:
                self.logger.debug(f"Link already exists: {card_id} → {feature_id}")

            return True
        else:
            # For real providers, this would call the Kanban API
            self.logger.warning(f"link_to_feature not implemented for provider {self.provider}")
            return False

    @handle_errors(component="kanban_integrator", reraise=False, default_return=[])
    def get_linked_features(self, card_id: str) -> List[str]:
        """
        Get all feature IDs linked to a test card (Feature #87)

        Args:
            card_id: The test card ID

        Returns:
            List of feature card IDs linked to this test card
        """
        self.logger.debug(f"Getting linked features for card {card_id}")

        # For mock provider, check in-memory storage
        if self.provider == "mock":
            card = self._cards.get(card_id)
            if card and hasattr(card, 'linked_feature_ids'):
                return card.linked_feature_ids.copy()
            else:
                self.logger.warning(f"Card {card_id} not found or has no feature links")
                return []
        else:
            # For real providers, this would query the Kanban API
            self.logger.warning(f"get_linked_features not implemented for provider {self.provider}")
            return []

    @handle_errors(component="kanban_integrator", reraise=False, default_return=[])
    def get_linked_test_cards(self, feature_id: str) -> List[str]:
        """
        Get all test card IDs linked to a feature card (Feature #87)

        This provides the reverse lookup - finding all tests that verify
        a particular feature.

        Args:
            feature_id: The feature card ID

        Returns:
            List of test card IDs (journey/scenario cards) linked to this feature
        """
        self.logger.debug(f"Getting linked test cards for feature {feature_id}")

        # For mock provider, check reverse mapping
        if self.provider == "mock":
            if not hasattr(self, '_feature_to_test_cards'):
                return []

            return self._feature_to_test_cards.get(feature_id, []).copy()
        else:
            # For real providers, this would query the Kanban API
            self.logger.warning(f"get_linked_test_cards not implemented for provider {self.provider}")
            return []

    @handle_errors(component="kanban_integrator", reraise=False, default_return=False)
    def add_comment(self, card_id: str, comment: str) -> bool:
        """
        Add a comment to a card (Feature #86)

        Args:
            card_id: Card ID to comment on
            comment: Comment text

        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Adding comment to card {card_id}")

        # In production, this would call the Kanban API (Trello, GitHub, etc.)
        # For now, we log the comment and simulate success
        self.logger.debug(f"Comment content:\n{comment}")

        # Store comment in memory for testing (in production, this goes to the API)
        if not hasattr(self, '_comments'):
            self._comments = {}

        if card_id not in self._comments:
            self._comments[card_id] = []

        self._comments[card_id].append({
            'comment': comment,
            'timestamp': datetime.now().isoformat()
        })

        return True

    @handle_errors(component="kanban_integrator", reraise=False, default_return=False)
    def add_test_results_comment(self, card_id: str, test_results: List[Any]) -> bool:
        """
        Add test results as a formatted comment to a card (Feature #86)

        Args:
            card_id: Card ID to comment on
            test_results: List of TestResult objects

        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Adding test results comment to card {card_id}")

        if not test_results:
            self.logger.warning("No test results to add as comment")
            return False

        # Calculate summary statistics
        total_tests = len(test_results)
        passed_tests = sum(1 for t in test_results if getattr(t, 'passed', False))
        failed_tests = total_tests - passed_tests
        pass_percentage = (passed_tests * 100 // total_tests) if total_tests > 0 else 0
        total_duration_ms = sum(getattr(t, 'duration_ms', 0) for t in test_results)

        # Build comment with test results
        comment = f"""## Test Results - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

**Summary:** {passed_tests}/{total_tests} tests passed ({pass_percentage}%)

**Duration:** {total_duration_ms / 1000:.2f}s ({total_duration_ms}ms)

**Tests:**
"""

        # Add each test result
        for result in test_results:
            test_name = getattr(result, 'test_name', 'unknown')
            passed = getattr(result, 'passed', False)
            duration_ms = getattr(result, 'duration_ms', 0)
            error_message = getattr(result, 'error_message', None)

            # Status indicator
            status = "✅ PASS" if passed else "❌ FAIL"
            comment += f"- {status}: {test_name} ({duration_ms}ms)\n"

            # Add error details for failed tests
            if not passed and error_message:
                comment += f"  💥 Error: {error_message}\n"

        # Add the comment using the base add_comment method
        return self.add_comment(card_id, comment)

    def get_comments(self, card_id: str) -> List[Dict[str, Any]]:
        """
        Get all comments for a card (for testing)

        Args:
            card_id: Card ID to get comments for

        Returns:
            List of comment dictionaries
        """
        if not hasattr(self, '_comments'):
            return []

        return self._comments.get(card_id, [])

    def _find_existing_bug_card(self, test_name: str, failure_type: str) -> Optional[BugKanbanCard]:
        """
        Find an existing bug card by test_name and failure_type (Feature #270)

        A bug is uniquely identified by the combination of:
        - test_name: Which test failed
        - failure_type: How it failed (assertion_failed, timeout, etc.)

        This prevents creating duplicate bug cards for the same test failure.

        Args:
            test_name: Test name to search for
            failure_type: Failure type to search for

        Returns:
            BugKanbanCard if found, None otherwise
        """
        # For mock provider, search in-memory storage
        if self.provider == "mock":
            for card_id, card in self._cards.items():
                if isinstance(card, BugKanbanCard):
                    if card.test_name == test_name and card.failure_type == failure_type:
                        self.logger.debug(
                            f"Found existing bug card for {test_name} "
                            f"({failure_type}): {card_id}"
                        )
                        return card
            return None
        else:
            # For real providers, this would query the Kanban API
            self.logger.warning(
                f"_find_existing_bug_card not implemented for provider {self.provider}"
            )
            return None

    @handle_errors(component="kanban_integrator", reraise=True)
    def create_bug_cards(self, bug_cards: List[Any]) -> List[BugKanbanCard]:
        """
        Create Kanban bug cards from test failures (Feature #88)

        Creates bug cards in the Kanban system for each test failure.
        Bug cards include:
        - Link to the failed test
        - Error details (message, type, suggestion)
        - Assignment to developer/team
        - Severity and priority
        - Artifacts (screenshots, videos, traces)

        Prevents duplicate bug cards for the same test failure (Feature #270).

        Args:
            bug_cards: List of BugCard objects from ResultProcessor

        Returns:
            List of BugKanbanCard objects created in Kanban system

        Raises:
            KanbanIntegrationError: If bug card creation fails
        """
        self.logger.info(f"Creating bug cards for {len(bug_cards)} test failures")

        kanban_cards = []

        for bug_card in bug_cards:
            try:
                # Extract bug card information
                card_id = getattr(bug_card, 'card_id', 'unknown')
                test_name = getattr(bug_card, 'test_name', 'Unknown Test')
                failure_type = getattr(bug_card, 'failure_type', 'unknown')
                severity = getattr(bug_card, 'severity', 'medium')
                priority = getattr(bug_card, 'priority', 5)
                error_message = getattr(bug_card, 'error_message', None)
                suggestion = getattr(bug_card, 'suggestion', None)
                assignee = getattr(bug_card, 'assignee', None)
                labels = getattr(bug_card, 'labels', [])

                # Feature #270: Check for existing bug card to prevent duplicates
                existing_card = self._find_existing_bug_card(test_name, failure_type)
                if existing_card:
                    self.logger.info(
                        f"Bug card already exists for {test_name} "
                        f"({failure_type}), returning existing card {existing_card.card_id}"
                    )
                    kanban_cards.append(existing_card)
                    continue

                # Generate unique Kanban card ID
                self._card_counter += 1
                date_str = datetime.now().strftime("%Y%m%d")
                kanban_card_id = f"BUG-KANBAN-{date_str}-{self._card_counter:03d}"

                # Generate title from test name
                # Extract just the test description (after the colon)
                if ':' in test_name:
                    title = test_name.split(':', 1)[1].strip()
                else:
                    title = test_name

                # Add emoji prefix
                title = f"🐛 {title}"

                # Create Kanban bug card
                kanban_card = BugKanbanCard(
                    card_id=kanban_card_id,
                    title=title,
                    test_name=test_name,
                    failure_type=failure_type,
                    severity=severity,
                    priority=priority,
                    error_message=error_message,
                    suggestion=suggestion,
                    assignee=assignee,
                    labels=labels,
                    status=CardStatus.TODO  # Bug cards start in TODO
                )

                kanban_cards.append(kanban_card)

                # Store card in memory for mock provider
                self._cards[kanban_card_id] = kanban_card

                # Save to disk for file provider (Feature #263)
                if self.provider == "file":
                    self._save_card_to_disk(kanban_card)

                self.logger.debug(f"Created bug card: {kanban_card}")

            except Exception as e:
                self.logger.error(f"Failed to create bug card: {e}")
                raise KanbanIntegrationError(f"Failed to create bug card: {e}")

        self.logger.info(f"Created {len(kanban_cards)} bug cards")
        return kanban_cards

    @handle_errors(component="kanban_integrator", reraise=False, default_return=False)
    def update_bug_card_status(self, kanban_card_id: str, test_result: Any) -> bool:
        """
        Update bug card status when test is fixed (Feature #89)

        When a test that previously failed now passes, this method:
        1. Updates the bug card status from TODO to DONE
        2. Adds a comment documenting the fix
        3. Records the fix timestamp

        Args:
            kanban_card_id: The bug card ID to update (e.g., "BUG-KANBAN-20250126-001")
            test_result: TestResult object showing the test now passes

        Returns:
            True if status was updated successfully, False otherwise

        Example:
            >>> integrator = KanbanIntegrator()
            >>> bug_card = create_bug_card(...)
            >>> test_result = TestResult(test_name="...", passed=True)
            >>> success = integrator.update_bug_card_status(
            ...     kanban_card_id="BUG-KANBAN-20250126-001",
            ...     test_result=test_result
            ... )
        """
        self.logger.info(f"Updating bug card {kanban_card_id} status based on test result")

        # Validate test_result
        if not hasattr(test_result, 'passed'):
            self.logger.error("test_result must have 'passed' attribute")
            return False

        # Only update status if test passed
        if not test_result.passed:
            self.logger.info(
                f"Test {getattr(test_result, 'test_name', 'unknown')} still failing, "
                f"not updating bug card status"
            )
            return False

        # For mock provider, update in-memory storage
        if self.provider == "mock":
            card = self._cards.get(kanban_card_id)
            if not card:
                self.logger.error(f"Bug card {kanban_card_id} not found")
                return False

            # Verify it's a bug card
            if not isinstance(card, BugKanbanCard):
                self.logger.error(
                    f"Card {kanban_card_id} is not a bug card "
                    f"(type: {type(card).__name__})"
                )
                return False

            # Update card status to DONE (Fixed)
            old_status = card.status
            card.status = CardStatus.DONE
            card.updated_at = datetime.now()

            self.logger.info(
                f"Updated bug card {kanban_card_id} "
                f"from {old_status.value} to {card.status.value} (Fixed)"
            )

            # Document the fix with a comment
            test_name = getattr(test_result, 'test_name', 'unknown')
            duration_ms = getattr(test_result, 'duration_ms', 0)

            fix_comment = f"""## Bug Fixed ✅

**Test:** {test_name}
**Status:** PASS
**Fixed At:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Duration:** {duration_ms}ms

The test that previously failed is now passing. This bug has been marked as fixed.
"""

            self.add_comment(kanban_card_id, fix_comment)

            return True
        else:
            # For real providers, this would call the Kanban API
            self.logger.warning(
                f"update_bug_card_status not implemented for provider {self.provider}"
            )
            return False

    # ========================================================================
    # API Error Handling with Retry (Feature #91)
    # ========================================================================

    def _retry_with_backoff(self,
                           func: Callable,
                           max_retries: int = 3,
                           base_delay: float = 1.0,
                           max_delay: float = 10.0) -> Any:
        """
        Execute a function with exponential backoff retry logic (Feature #91)

        This method implements retry logic for API calls that may fail due to:
        - Network errors
        - Rate limiting
        - Temporary server errors

        Args:
            func: Function to execute (should return result or raise exception)
            max_retries: Maximum number of retry attempts (default: 3)
            base_delay: Initial delay between retries in seconds (default: 1.0)
            max_delay: Maximum delay between retries in seconds (default: 10.0)

        Returns:
            Result from function execution

        Raises:
            KanbanIntegrationError: If all retries are exhausted
        """
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                # Attempt to execute the function
                result = func()

                if attempt > 0:
                    self.logger.info(
                        f"API call succeeded on attempt {attempt + 1}/{max_retries + 1}"
                    )

                return result

            except Exception as e:
                last_exception = e

                # Don't retry on certain errors (e.g., authentication)
                if self._is_non_retryable_error(e):
                    self.logger.error(f"Non-retryable error encountered: {e}")
                    raise KanbanIntegrationError(f"Non-retryable API error: {e}")

                if attempt < max_retries:
                    # Calculate exponential backoff delay
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    self.logger.warning(
                        f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )

                    # Log the error for tracking
                    self.logger.error(
                        f"API error on attempt {attempt + 1}: {type(e).__name__}: {e}",
                        extra={
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "attempt": attempt + 1,
                            "will_retry": True
                        }
                    )

                    time.sleep(delay)
                else:
                    # Final attempt failed
                    self.logger.error(
                        f"API call failed after {max_retries + 1} attempts: {e}"
                    )
                    raise KanbanIntegrationError(
                        f"API call failed after {max_retries + 1} attempts: {e}"
                    )

        # Should never reach here, but just in case
        raise KanbanIntegrationError(
            f"Retry logic exhausted: {last_exception}"
        )

    def _is_non_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error should not be retried

        Args:
            error: Exception to check

        Returns:
            True if error is non-retryable, False otherwise
        """
        error_message = str(error).lower()

        # Non-retryable errors
        non_retryable_patterns = [
            "authentication",
            "unauthorized",
            "forbidden",
            "invalid api key",
            "not found",
            "401",
            "403",
            "404"
        ]

        for pattern in non_retryable_patterns:
            if pattern in error_message:
                return True

        return False

    def _mock_api_call_with_error(self,
                                  card_data: Dict[str, Any],
                                  should_fail: bool = False,
                                  error_type: str = "network") -> Dict[str, Any]:
        """
        Mock API call that can simulate errors for testing (Feature #91)

        This method simulates API calls to Kanban providers (Trello, GitHub, etc.)
        and can inject errors for testing graceful error handling.

        Args:
            card_data: Card data to send to API
            should_fail: Whether to simulate an error (default: False)
            error_type: Type of error to simulate ("network", "rate_limit", "server", "auth")

        Returns:
            Mock API response with card_id and status

        Raises:
            KanbanIntegrationError: When simulating API errors
        """
        if should_fail:
            # Simulate different types of API errors
            if error_type == "network":
                error = KanbanIntegrationError(
                    "Network error: Connection refused"
                )
            elif error_type == "rate_limit":
                error = KanbanIntegrationError(
                    "Rate limit exceeded: Too many requests"
                )
            elif error_type == "server":
                error = KanbanIntegrationError(
                    "Server error: Internal server error (500)"
                )
            elif error_type == "auth":
                error = KanbanIntegrationError(
                    "Authentication error: Invalid API key (401)"
                )
            else:
                error = KanbanIntegrationError(
                    f"Unknown error: {error_type}"
                )

            self.logger.error(f"Mock API error: {error.message}")
            raise error

        # Simulate successful API call
        return {
            "success": True,
            "card_id": card_data.get("card_id", "unknown"),
            "status": "created",
            "url": f"https://kanban.example.com/card/{card_data.get('card_id', 'unknown')}"
        }

    @handle_errors(component="kanban_integrator", reraise=True)
    def create_card_with_retry(self,
                               card_data: Dict[str, Any],
                               max_retries: int = 3,
                               base_delay: float = 1.0,
                               max_delay: float = 10.0) -> Dict[str, Any]:
        """
        Create a Kanban card with automatic retry on API errors (Feature #91)

        This method demonstrates graceful error handling with retry logic:
        1. Attempts to create card via API
        2. Catches API errors (network, rate limit, server errors)
        3. Logs each error attempt
        4. Retries with exponential backoff
        5. Raises KanbanIntegrationError if all retries fail

        Args:
            card_data: Dictionary containing card information
                      Example: {
                          "card_id": "JOURNEY-20250126-001",
                          "title": "User Login Journey",
                          "description": "Journey description",
                          "labels": ["journey", "authentication"]
                      }
            max_retries: Maximum number of retry attempts (default: 3)
            base_delay: Initial delay between retries in seconds (default: 1.0)
            max_delay: Maximum delay between retries in seconds (default: 10.0)

        Returns:
            API response dictionary with card_id and status

        Raises:
            KanbanIntegrationError: If card creation fails after all retries

        Example:
            >>> integrator = KanbanIntegrator()
            >>> card_data = {
            ...     "card_id": "JOURNEY-20250126-001",
            ...     "title": "User Login Journey",
            ...     "description": "User logs in",
            ...     "labels": ["journey", "auth"]
            ... }
            >>> result = integrator.create_card_with_retry(card_data)
            >>> print(result['card_id'])
            'JOURNEY-20250126-001'
        """
        self.logger.info(
            f"Creating card {card_data.get('card_id', 'unknown')} "
            f"with retry logic (max {max_retries} retries)"
        )

        # Define the API call function with retry logic
        def api_call() -> Dict[str, Any]:
            # In production, this would make actual HTTP request to:
            # - Trello API: POST /1/cards
            # - GitHub API: POST /projects/columns/cards
            # - Linear API: POST /api/issues
            return self._mock_api_call_with_error(card_data)

        # Execute with retry logic
        try:
            result = self._retry_with_backoff(
                api_call,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay
            )

            self.logger.info(
                f"Card {card_data.get('card_id', 'unknown')} created successfully"
            )

            return result

        except KanbanIntegrationError as e:
            self.logger.error(
                f"Failed to create card {card_data.get('card_id', 'unknown')} "
                f"after {max_retries + 1} attempts: {e}"
            )
            raise

    @handle_errors(component="kanban_integrator", reraise=False, default_return=0)
    def archive_old_cards(self, older_than_hours: float = 1.0) -> int:
        """
        Archive old test cards from previous runs (Feature #92)

        When running test suites multiple times, old cards from previous runs
        should be archived to preserve history while keeping the board clean.
        New cards from the current run remain active.

        Args:
            older_than_hours: Archive cards older than this many hours (default: 1.0)

        Returns:
            Number of cards archived

        Raises:
            KanbanIntegrationError: If archival fails (only if reraise=True)

        Example:
            >>> kanban = KanbanIntegrator(config={"provider": "mock"})
            >>> # Archive cards older than 1 hour
            >>> count = kanban.archive_old_cards(older_than_hours=1.0)
            >>> print(f"Archived {count} old cards")
        """
        self.logger.info(f"Archiving cards older than {older_than_hours} hours")

        # Calculate cutoff time
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)

        archived_count = 0

        # For mock provider, archive from in-memory storage
        if self.provider == "mock":
            for card_id, card in list(self._cards.items()):
                # Check if card should be archived
                if card.status != CardStatus.ARCHIVED:  # Don't re-archive
                    if isinstance(card, (JourneyCard, ScenarioCard, BugKanbanCard)):
                        # Check if card is old enough
                        if card.created_at < cutoff_time:
                            # Archive the card
                            old_status = card.status
                            card.status = CardStatus.ARCHIVED
                            card.updated_at = datetime.now()

                            archived_count += 1

                            self.logger.info(
                                f"Archived card {card_id} "
                                f"(status: {old_status.value} -> ARCHIVED)"
                            )

                            self.logger.debug(
                                f"Card {card_id} created at {card.created_at.isoformat()}, "
                                f"older than cutoff {cutoff_time.isoformat()}"
                            )
        else:
            # For real providers, this would call the Kanban API
            self.logger.warning(
                f"archive_old_cards not implemented for provider {self.provider}"
            )
            self.logger.info(
                "For production, implement API calls to:"
                "  1. List all cards"
                "  2. Filter by creation date"
                "  3. Update status to ARCHIVED"
                "  - Trello API: PUT /cards/{id}"
                "  - GitHub API: PATCH /projects/columns/cards"
                "  - Linear API: PATCH /api/issues"
            )

        self.logger.info(f"Archived {archived_count} old cards")

        return archived_count

    @handle_errors(component="kanban_integrator", reraise=False, default_return=[])
    def get_archived_cards(self) -> List[Any]:
        """
        Get all archived cards (Feature #92 helper)

        Returns:
            List of archived cards (JourneyCard, ScenarioCard, or BugKanbanCard)

        Example:
            >>> kanban = KanbanIntegrator(config={"provider": "mock"})
            >>> archived = kanban.get_archived_cards()
            >>> print(f"Found {len(archived)} archived cards")
        """
        self.logger.debug("Getting archived cards")

        archived = []

        # For mock provider, check in-memory storage
        if self.provider == "mock":
            for card_id, card in self._cards.items():
                if card.status == CardStatus.ARCHIVED:
                    archived.append(card)

            self.logger.debug(f"Found {len(archived)} archived cards")
        else:
            # For real providers, query the API
            self.logger.warning(
                f"get_archived_cards not implemented for provider {self.provider}"
            )

        return archived

    @handle_errors(component="kanban_integrator", reraise=False, default_return=False)
    def delete_card(self, card_id: str) -> bool:
        """
        Delete a card from the Kanban board (Feature #246)

        Permanently removes a card from the Kanban system.
        This operation cannot be undone.

        Args:
            card_id: Card ID to delete

        Returns:
            True if deletion was successful, False otherwise

        Example:
            >>> integrator = KanbanIntegrator()
            >>> card = create_test_card()
            >>> success = integrator.delete_card(card.card_id)
            >>> print(f"Deleted: {success}")
        """
        self.logger.info(f"Deleting card {card_id}")

        # For mock or file provider, delete from storage
        if self.provider in ("mock", "file"):
            # Check if card exists
            if card_id not in self._cards:
                self.logger.warning(f"Card {card_id} not found for deletion")
                return False

            # Get card details before deletion for logging
            card = self._cards[card_id]
            self.logger.debug(
                f"Deleting card: {card_id} "
                f"(type: {type(card).__name__}, status: {card.status.value})"
            )

            # Remove from card storage
            del self._cards[card_id]

            # Clean up feature links if present
            if hasattr(card, 'linked_feature_ids'):
                for feature_id in card.linked_feature_ids:
                    if feature_id in self._feature_to_test_cards:
                        if card_id in self._feature_to_test_cards[feature_id]:
                            self._feature_to_test_cards[feature_id].remove(card_id)
                            self.logger.debug(f"Removed link: {card_id} → {feature_id}")

            # Clean up comments if present
            if hasattr(self, '_comments') and card_id in self._comments:
                del self._comments[card_id]
                self.logger.debug(f"Removed comments for card {card_id}")

            # Delete from disk for file provider (Feature #263)
            if self.provider == "file":
                self._delete_card_from_disk(card_id)

            self.logger.info(f"Card {card_id} deleted successfully")
            return True
        else:
            # For real providers, this would call the Kanban API
            # - Trello API: DELETE /1/cards/{id}
            # - GitHub API: DELETE /projects/columns/cards/{id}
            # - Linear API: DELETE /api/issues/{id}
            self.logger.warning(
                f"delete_card not implemented for provider {self.provider}"
            )
            self.logger.info(
                "For production, implement API calls to delete cards from:"
                "  - Trello API: DELETE /1/cards/{id}"
                "  - GitHub API: DELETE /projects/columns/cards/{id}"
                "  - Linear API: DELETE /api/issues/{id}"
            )
            return False

    # ========================================================================
    # Feature #274: Journey Deletion and Cleanup
    # ========================================================================

    @handle_errors(component="kanban_integrator", reraise=False, default_return=None)
    def get_journey_card(self, card_id: str) -> Optional[JourneyCard]:
        """
        Get a journey card by its ID (Feature #274)

        Args:
            card_id: Journey card ID

        Returns:
            JourneyCard if found, None otherwise
        """
        card = self.get_card_by_id(card_id)
        if card and isinstance(card, JourneyCard):
            return card
        return None

    @handle_errors(component="kanban_integrator", reraise=False, default_return=None)
    def get_scenario_card(self, card_id: str) -> Optional[ScenarioCard]:
        """
        Get a scenario card by its ID (Feature #274)

        Args:
            card_id: Scenario card ID

        Returns:
            ScenarioCard if found, None otherwise
        """
        card = self.get_card_by_id(card_id)
        if card and isinstance(card, ScenarioCard):
            return card
        return None

    @handle_errors(component="kanban_integrator", reraise=False, default_return=[])
    def get_all_journey_cards(self) -> List[JourneyCard]:
        """
        Get all journey cards (Feature #274)

        Returns:
            List of all JourneyCard objects
        """
        journey_cards = []
        for card in self._cards.values():
            if isinstance(card, JourneyCard):
                journey_cards.append(card)
        return journey_cards

    @handle_errors(component="kanban_integrator", reraise=False, default_return=[])
    def get_all_scenario_cards(self) -> List[ScenarioCard]:
        """
        Get all scenario cards (Feature #274)

        Returns:
            List of all ScenarioCard objects
        """
        scenario_cards = []
        for card in self._cards.values():
            if isinstance(card, ScenarioCard):
                scenario_cards.append(card)
        return scenario_cards

    @handle_errors(component="kanban_integrator", reraise=False, default_return=False)
    def delete_journey(self, journey_id: str) -> bool:
        """
        Delete a journey and archive all related cards (Feature #274)

        When a journey is deleted:
        1. Journey card is archived (not deleted)
        2. All scenario cards for this journey are archived
        3. Feature links are cleaned up
        4. Comments are preserved

        Args:
            journey_id: Journey ID to delete

        Returns:
            True if journey was found and archived, False otherwise

        Note:
            This uses archiving instead of permanent deletion to preserve history.
            Cards are marked as ARCHIVED but not removed from storage.
        """
        self.logger.info(f"Deleting journey {journey_id}")

        # For mock or file provider
        if self.provider in ("mock", "file"):
            # Find the journey card
            journey_card = None
            for card in self._cards.values():
                if isinstance(card, JourneyCard) and card.journey_id == journey_id:
                    journey_card = card
                    break

            if not journey_card:
                self.logger.warning(f"Journey {journey_id} not found for deletion")
                return False

            self.logger.info(f"Found journey card: {journey_card.card_id}")

            # Archive the journey card
            old_status = journey_card.status
            journey_card.status = CardStatus.ARCHIVED
            journey_card.updated_at = datetime.now()
            self.logger.info(
                f"Archived journey card {journey_card.card_id}: "
                f"{old_status.value} → {CardStatus.ARCHIVED.value}"
            )

            # Save to disk for file provider
            if self.provider == "file":
                self._save_card_to_disk(journey_card)

            # Find and archive all scenario cards for this journey
            archived_scenarios = 0
            for card in list(self._cards.values()):  # Use list() to avoid modification during iteration
                if isinstance(card, ScenarioCard) and card.journey_id == journey_id:
                    old_scenario_status = card.status
                    card.status = CardStatus.ARCHIVED
                    card.updated_at = datetime.now()
                    archived_scenarios += 1
                    self.logger.debug(
                        f"Archived scenario card {card.card_id}: "
                        f"{old_scenario_status.value} → {CardStatus.ARCHIVED.value}"
                    )

                    # Save to disk for file provider
                    if self.provider == "file":
                        self._save_card_to_disk(card)

            self.logger.info(
                f"Journey {journey_id} deletion complete: "
                f"1 journey card archived, {archived_scenarios} scenario cards archived"
            )

            return True
        else:
            # For real providers, this would call the Kanban API
            self.logger.warning(
                f"delete_journey not implemented for provider {self.provider}"
            )
            return False
