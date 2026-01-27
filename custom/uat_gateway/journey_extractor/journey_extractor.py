"""
Journey Extractor - Parse AutoCoder specs and identify user workflows

This module reads and parses spec.yaml files to extract journey definitions
that will be used for automated testing.
"""

import yaml
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import JourneyExtractionError, handle_errors


# ============================================================================
# Data Models
# ============================================================================

class JourneyType(Enum):
    """Types of user journeys that can be detected"""
    AUTHENTICATION = "authentication"
    PAYMENT = "payment"
    ONBOARDING = "onboarding"
    ADMIN = "admin"
    CRUD = "crud"
    SEARCH = "search"
    FILTER = "filter"
    EXPORT = "export"
    UNKNOWN = "unknown"


@dataclass
class JourneyStep:
    """Represents a single step in a user journey"""
    step_id: str
    description: str
    action_type: str  # navigate, click, type, wait, assert, etc.
    target: Optional[str] = None  # selector or endpoint
    expected_result: Optional[str] = None

    def __str__(self) -> str:
        if self.target:
            return f"{self.action_type}: {self.description} ({self.target})"
        return f"{self.action_type}: {self.description}"


class ScenarioType(Enum):
    """Types of test scenarios"""
    HAPPY_PATH = "happy_path"  # Everything works correctly
    ERROR_PATH = "error_path"  # Error conditions and validation


@dataclass
class Scenario:
    """Represents a test scenario (happy path or error path)"""
    scenario_id: str
    scenario_type: ScenarioType
    name: str
    description: str
    steps: List[JourneyStep] = field(default_factory=list)
    error_type: Optional[str] = None  # For error paths: validation, auth, network, etc.
    acceptance_criteria: List[str] = field(default_factory=list)  # Acceptance criteria from stories
    data_variations: List[Dict[str, Any]] = field(default_factory=list)  # Data-driven test variations
    setup_steps: List[JourneyStep] = field(default_factory=list)  # Setup steps for beforeAll hook
    cleanup_steps: List[JourneyStep] = field(default_factory=list)  # Cleanup steps for afterAll hook
    dependencies: List[str] = field(default_factory=list)  # List of scenario_ids this scenario depends on

    def add_step(self, step: JourneyStep) -> None:
        """Add a step to this scenario"""
        self.steps.append(step)

    def add_data_variation(self, variation: Dict[str, Any]) -> None:
        """Add a data variation for data-driven testing"""
        self.data_variations.append(variation)

    def add_dependency(self, dependency_scenario_id: str) -> None:
        """Add a dependency on another scenario"""
        if dependency_scenario_id not in self.dependencies:
            self.dependencies.append(dependency_scenario_id)

    def has_data_variations(self) -> bool:
        """Check if this scenario has data variations"""
        return len(self.data_variations) > 0

    def has_dependencies(self) -> bool:
        """Check if this scenario has dependencies"""
        return len(self.dependencies) > 0

    def __str__(self) -> str:
        error_suffix = f" [{self.error_type}]" if self.error_type else ""
        data_suffix = f" [{len(self.data_variations)} variations]" if self.data_variations else ""
        dep_suffix = f" [{len(self.dependencies)} deps]" if self.dependencies else ""
        return f"Scenario({self.scenario_type.value}{error_suffix}{data_suffix}{dep_suffix}: {self.name} - {len(self.steps)} steps)"


@dataclass
class Journey:
    """Represents a detected user journey"""
    journey_id: str
    journey_type: JourneyType
    name: str
    description: str
    steps: List[JourneyStep] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)
    priority: int = 5  # 1-10, 1 is highest
    related_stories: List[str] = field(default_factory=list)

    def add_step(self, step: JourneyStep) -> None:
        """Add a step to this journey"""
        self.steps.append(step)

    def add_scenario(self, scenario: Scenario) -> None:
        """Add a scenario to this journey"""
        self.scenarios.append(scenario)

    def get_happy_path_scenario(self) -> Optional['Scenario']:
        """Get the happy path scenario for this journey"""
        for scenario in self.scenarios:
            if scenario.scenario_type == ScenarioType.HAPPY_PATH:
                return scenario
        return None

    def get_error_scenarios(self) -> List['Scenario']:
        """Get all error path scenarios for this journey"""
        return [s for s in self.scenarios if s.scenario_type == ScenarioType.ERROR_PATH]

    def __str__(self) -> str:
        error_count = len(self.get_error_scenarios())
        return f"Journey({self.journey_type.value}: {self.name} - {len(self.steps)} steps, {len(self.scenarios)} scenarios [{error_count} error paths])"


@dataclass
class Story:
    """Represents a user story within a phase"""
    story_id: str
    description: str
    acceptance_criteria: List[str]
    success_metric: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)  # List of story_ids this depends on

    @classmethod
    def from_dict(cls, story_id: str, data: Dict[str, Any]) -> 'Story':
        """Create Story from dictionary"""
        return cls(
            story_id=story_id,
            description=data.get('description', ''),
            acceptance_criteria=data.get('acceptance_criteria', []),
            success_metric=data.get('success_metric'),
            depends_on=data.get('depends_on', [])
        )


@dataclass
class Feature:
    """Represents an individual feature extracted from acceptance criteria"""
    feature_id: str
    story_id: str
    description: str
    dependencies: List[str] = field(default_factory=list)  # List of feature_ids this depends on

    def add_dependency(self, dependency_feature_id: str) -> None:
        """Add a dependency on another feature"""
        if dependency_feature_id not in self.dependencies:
            self.dependencies.append(dependency_feature_id)

    def __str__(self) -> str:
        dep_str = f" [{len(self.dependencies)} deps]" if self.dependencies else ""
        return f"Feature({self.feature_id}: {self.description}{dep_str})"

    def __hash__(self) -> int:
        return hash(self.feature_id)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Feature):
            return False
        return self.feature_id == other.feature_id


@dataclass
class Phase:
    """Represents a development phase with multiple stories"""
    phase_id: str
    stories: Dict[str, Story] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, phase_id: str, data: Dict[str, Any]) -> 'Phase':
        """Create Phase from dictionary

        Args:
            phase_id: Phase identifier
            data: Phase data containing 'stories' key

        Note:
            stories can be either a list or dict format
        """
        stories = {}
        stories_data = data.get('stories', [])

        # Handle both list and dict formats for stories
        if isinstance(stories_data, list):
            # List format: each item is a dict with one key (story_id)
            for story_item in stories_data:
                if isinstance(story_item, dict):
                    for story_key, story_data in story_item.items():
                        stories[story_key] = Story.from_dict(story_key, story_data)
        elif isinstance(stories_data, dict):
            # Dict format: direct key-value pairs
            for story_key, story_data in stories_data.items():
                stories[story_key] = Story.from_dict(story_key, story_data)

        return cls(
            phase_id=phase_id,
            stories=stories
        )


@dataclass
class Spec:
    """Represents a loaded and parsed spec.yaml file"""
    project_name: str
    project_type: str
    tech_stack: List[str]
    description: str
    problem_statement: str
    solution: str
    phases: Dict[str, Phase] = field(default_factory=dict)
    dependencies: Dict[str, Any] = field(default_factory=dict)
    success_criteria: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Spec':
        """Create Spec from dictionary

        Note:
            phases can be either a list or dict format

        Raises:
            JourneyExtractionError: If required fields are missing or empty
        """
        # Validate required fields
        required_fields = {
            'project_name': 'Project name',
            'project_type': 'Project type',
            'problem_statement': 'Problem statement',
            'solution': 'Solution'
        }

        missing_fields = []
        empty_fields = []

        for field, display_name in required_fields.items():
            if field not in data:
                missing_fields.append(display_name)
            elif not data[field] or str(data[field]).strip() == '':
                empty_fields.append(display_name)

        # Raise error if fields are missing or empty
        if missing_fields or empty_fields:
            error_parts = []
            if missing_fields:
                error_parts.append(f"Missing required fields: {', '.join(missing_fields)}")
            if empty_fields:
                error_parts.append(f"Empty required fields: {', '.join(empty_fields)}")

            raise JourneyExtractionError(
                f"Spec validation failed: {'; '.join(error_parts)}",
                component="journey_extractor",
                context={
                    "missing_fields": missing_fields,
                    "empty_fields": empty_fields,
                    "spec_data": {k: v for k, v in data.items() if k in required_fields}
                }
            )

        phases = {}
        phases_data = data.get('phases', [])

        # Handle both list and dict formats for phases
        if isinstance(phases_data, list):
            # List format: each item is a dict with one key (phase_id)
            for phase_item in phases_data:
                if isinstance(phase_item, dict):
                    for phase_key, phase_data in phase_item.items():
                        phases[phase_key] = Phase.from_dict(phase_key, phase_data)
        elif isinstance(phases_data, dict):
            # Dict format: direct key-value pairs
            for phase_key, phase_data in phases_data.items():
                phases[phase_key] = Phase.from_dict(phase_key, phase_data)

        # Parse tech_stack as list if it's a string
        tech_stack = data.get('tech_stack', '')
        if isinstance(tech_stack, str):
            tech_stack = [s.strip() for s in tech_stack.split(',')]

        return cls(
            project_name=data.get('project_name', ''),
            project_type=data.get('project_type', ''),
            tech_stack=tech_stack,
            description=data.get('description', ''),
            problem_statement=data.get('problem_statement', ''),
            solution=data.get('solution', ''),
            phases=phases,
            dependencies=data.get('dependencies', {}),
            success_criteria=data.get('success_criteria', {})
        )


# ============================================================================
# Journey Extractor
# ============================================================================

class JourneyExtractor:
    """
    Extracts journey definitions from AutoCoder spec files

    Responsibilities:
    - Load and parse spec.yaml files
    - Validate spec structure
    - Extract project metadata
    - Parse phases and stories
    - Provide access to journey definitions
    """

    def __init__(self):
        self.logger = get_logger("journey_extractor")
        self._loaded_spec: Optional[Spec] = None
        self._spec_path: Optional[Path] = None

    @handle_errors(component="journey_extractor", reraise=True)
    def load_spec(self, spec_path: str) -> Spec:
        """
        Load and parse a spec.yaml file

        Args:
            spec_path: Path to the spec.yaml file

        Returns:
            Spec object with parsed data

        Raises:
            JourneyExtractionError: If file cannot be loaded or parsed
        """
        spec_path_obj = Path(spec_path)

        # Validate file exists
        if not spec_path_obj.exists():
            raise JourneyExtractionError(
                f"Spec file not found: {spec_path}",
                component="journey_extractor",
                context={"spec_path": spec_path}
            )

        # Load YAML file
        try:
            with open(spec_path_obj, 'r') as f:
                spec_data = yaml.safe_load(f)

            if not spec_data:
                raise JourneyExtractionError(
                    f"Spec file is empty: {spec_path}",
                    component="journey_extractor",
                    context={"spec_path": spec_path}
                )

            self.logger.info(f"Loaded spec file: {spec_path}")

            # Parse into Spec object
            spec = Spec.from_dict(spec_data)

            # Cache the loaded spec
            self._loaded_spec = spec
            self._spec_path = spec_path_obj

            self.logger.info(
                f"Parsed spec: {spec.project_name} "
                f"({len(spec.phases)} phases, "
                f"{sum(len(p.stories) for p in spec.phases.values())} stories)"
            )

            return spec

        except yaml.YAMLError as e:
            raise JourneyExtractionError(
                f"Failed to parse YAML: {str(e)}",
                component="journey_extractor",
                context={"spec_path": spec_path, "error": str(e)}
            )
        except Exception as e:
            raise JourneyExtractionError(
                f"Failed to load spec: {str(e)}",
                component="journey_extractor",
                context={"spec_path": spec_path, "error": str(e)}
            )

    def get_current_spec(self) -> Optional[Spec]:
        """Get the currently loaded spec"""
        return self._loaded_spec

    def get_current_spec_path(self) -> Optional[Path]:
        """Get the path of the currently loaded spec"""
        return self._spec_path

    def get_phases(self) -> Dict[str, Phase]:
        """Get all phases from the loaded spec"""
        if self._loaded_spec is None:
            return {}
        return self._loaded_spec.phases

    def get_stories(self, phase_id: str) -> Dict[str, Story]:
        """Get all stories from a specific phase"""
        phases = self.get_phases()
        if phase_id not in phases:
            return {}
        return phases[phase_id].stories

    # ========================================================================
    # Feature Extraction Methods
    # ========================================================================

    @handle_errors(component="journey_extractor", reraise=True)
    def extract_features(self, spec: Optional[Spec] = None) -> Dict[str, Feature]:
        """
        Extract individual features from story acceptance criteria

        Args:
            spec: Spec to extract features from (uses loaded spec if None)

        Returns:
            Dictionary mapping feature_id to Feature objects

        Raises:
            JourneyExtractionError: If extraction fails
        """
        if spec is None:
            spec = self._loaded_spec

        if spec is None:
            raise JourneyExtractionError(
                "No spec loaded - call load_spec() first",
                component="journey_extractor"
            )

        features = {}
        feature_counter = 0

        # Extract features from each story's acceptance criteria
        for phase_id, phase in spec.phases.items():
            for story_id, story in phase.stories.items():
                for i, criterion in enumerate(story.acceptance_criteria):
                    feature_counter += 1
                    feature_id = f"feature_{feature_counter:03d}"

                    feature = Feature(
                        feature_id=feature_id,
                        story_id=story_id,
                        description=criterion.strip()
                    )
                    features[feature_id] = feature

        self.logger.info(f"Extracted {len(features)} features from {feature_counter} acceptance criteria")

        return features

    @handle_errors(component="journey_extractor", reraise=True)
    def build_dependency_graph(
        self,
        features: Dict[str, Feature],
        spec: Optional[Spec] = None
    ) -> Dict[str, List[str]]:
        """
        Build dependency graph between features based on textual relationships

        Analyzes feature descriptions to identify dependencies:
        - Sequential ordering (story-level dependencies)
        - Keyword references ("after X", "requires X", "depends on X")
        - Story ordering (earlier stories may be prerequisites)

        Args:
            features: Dictionary of features to analyze
            spec: Spec object for story ordering context (uses loaded spec if None)

        Returns:
            Dictionary mapping feature_id to list of dependency feature_ids

        Raises:
            JourneyExtractionError: If graph building fails
        """
        if spec is None:
            spec = self._loaded_spec

        # Get story ordering to establish dependencies
        story_order = {}
        if spec:
            story_counter = 0
            for phase_id, phase in spec.phases.items():
                for story_id in phase.stories.keys():
                    story_order[story_id] = story_counter
                    story_counter += 1

        # Build dependency map
        dependency_graph: Dict[str, List[str]] = {fid: [] for fid in features.keys()}

        # Group features by story
        features_by_story: Dict[str, List[Feature]] = {}
        for feature in features.values():
            if feature.story_id not in features_by_story:
                features_by_story[feature.story_id] = []
            features_by_story[feature.story_id].append(feature)

        # Add dependencies based on story ordering
        for story_id, story_features in features_by_story.items():
            # Features in later stories depend on features in earlier stories
            for feature in story_features:
                current_story_order = story_order.get(feature.story_id, 0)

                # Find features from earlier stories that might be dependencies
                for other_story_id, other_story_order in story_order.items():
                    if other_story_order < current_story_order:
                        # Features from earlier stories could be dependencies
                        if other_story_id in features_by_story:
                            for dependency_feature in features_by_story[other_story_id]:
                                # Add dependency based on textual similarity
                                if self._is_related_feature(feature, dependency_feature):
                                    feature.add_dependency(dependency_feature.feature_id)
                                    dependency_graph[feature.feature_id].append(dependency_feature.feature_id)

        self.logger.info(f"Built dependency graph with {sum(len(deps) for deps in dependency_graph.values())} dependencies")

        return dependency_graph

    def _is_related_feature(self, feature: Feature, potential_dependency: Feature) -> bool:
        """
        Check if two features are related based on textual analysis

        Looks for:
        - Common keywords
        - Sequential references ("after", "then", "next")
        - Entity relationships (same subject/object)

        Args:
            feature: The feature to check
            potential_dependency: The potential dependency feature

        Returns:
            True if features appear to be related
        """
        feature_lower = feature.description.lower()
        dependency_lower = potential_dependency.description.lower()

        # Extract key nouns/verbs (simple heuristic)
        feature_words = set(re.findall(r'\b[a-z]{3,}\b', feature_lower))
        dependency_words = set(re.findall(r'\b[a-z]{3,}\b', dependency_lower))

        # Check for significant word overlap (at least 2 common words)
        common_words = feature_words & dependency_words
        if len(common_words) >= 2:
            return True

        # Check for sequential language
        sequential_patterns = [
            r'\b(then|next|after|subsequent|following)\b',
            r'\b(requires|depends on|needs|relies on)\b'
        ]

        for pattern in sequential_patterns:
            if re.search(pattern, feature_lower):
                # If feature has sequential language, check if it references dependency
                for word in dependency_words:
                    if word in feature_lower and len(word) > 4:
                        return True

        return False

    @handle_errors(component="journey_extractor", reraise=True)
    def detect_circular_dependencies(
        self,
        dependency_graph: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        Detect circular dependencies in the dependency graph

        Uses depth-first search to find cycles in the directed graph.

        Args:
            dependency_graph: Dictionary mapping feature_id to list of dependencies

        Returns:
            List of cycles (each cycle is a list of feature_ids)

        Raises:
            JourneyExtractionError: If cycle detection fails
        """
        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node: str) -> bool:
            """Depth-first search to detect cycles"""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in dependency_graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # Found a cycle - extract it from the path
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        # Run DFS on all nodes
        for node in dependency_graph.keys():
            if node not in visited:
                dfs(node)

        if cycles:
            self.logger.warning(f"Detected {len(cycles)} circular dependencies")
            for i, cycle in enumerate(cycles, 1):
                self.logger.warning(f"  Cycle {i}: {' -> '.join(cycle)}")
        else:
            self.logger.info("No circular dependencies detected")

        return cycles

    # ========================================================================
    # Pattern Detection Methods
    # ========================================================================

    @handle_errors(component="journey_extractor", reraise=True)
    def detect_patterns(self, spec: Optional[Spec] = None) -> List[Journey]:
        """
        Detect user journey patterns from loaded spec

        Args:
            spec: Spec to analyze (uses loaded spec if None)

        Returns:
            List of detected Journey objects with scenarios
        """
        if spec is None:
            spec = self._loaded_spec

        if spec is None:
            raise JourneyExtractionError(
                "No spec loaded - call load_spec() first",
                component="journey_extractor"
            )

        journeys = []

        # Detect different pattern types
        journeys.extend(self._detect_auth_patterns(spec))
        journeys.extend(self._detect_payment_patterns(spec))
        journeys.extend(self._detect_onboarding_patterns(spec))
        journeys.extend(self._detect_admin_patterns(spec))
        journeys.extend(self._detect_crud_patterns(spec))

        self.logger.info(f"Detected {len(journeys)} journeys from spec")

        # Generate scenarios for each journey
        self.generate_scenarios(journeys, spec)
        self.logger.info(f"Generated scenarios for {len(journeys)} journeys")

        return journeys

    def _detect_auth_patterns(self, spec: Spec) -> List[Journey]:
        """Detect authentication-related journeys"""
        journeys = []
        auth_keywords = {
            'login': ['login', 'signin', 'sign-in', 'log in', 'auth', 'authenticate'],
            'logout': ['logout', 'signout', 'sign-out', 'log out'],
            'register': ['register', 'signup', 'sign-up', 'sign up', 'create account'],
            'reset': ['reset password', 'forgot password', 'change password', 'recover']
        }

        login_flow = []
        logout_flow = []
        register_flow = []
        reset_flow = []

        # Scan all stories for auth-related content
        for phase_id, phase in spec.phases.items():
            for story_id, story in phase.stories.items():
                story_text = f"{story_id} {story.description} {' '.join(story.acceptance_criteria)}".lower()

                # Check for login patterns
                if any(kw in story_text for kw in auth_keywords['login']):
                    login_flow.append(story_id)

                # Check for logout patterns
                if any(kw in story_text for kw in auth_keywords['logout']):
                    logout_flow.append(story_id)

                # Check for register patterns
                if any(kw in story_text for kw in auth_keywords['register']):
                    register_flow.append(story_id)

                # Check for password reset patterns
                if any(kw in story_text for kw in auth_keywords['reset']):
                    reset_flow.append(story_id)

        # Create login journey
        if login_flow:
            journey = Journey(
                journey_id=f"journey_auth_login",
                journey_type=JourneyType.AUTHENTICATION,
                name="User Login Flow",
                description="User authenticates and gains access to the system",
                priority=2,  # High priority
                related_stories=login_flow
            )
            journey.add_step(JourneyStep(
                step_id="login_navigate",
                description="Navigate to login page",
                action_type="navigate",
                target="/login"
            ))
            journey.add_step(JourneyStep(
                step_id="login_enter_email",
                description="Enter email address",
                action_type="type",
                target="#email"
            ))
            journey.add_step(JourneyStep(
                step_id="login_enter_password",
                description="Enter password",
                action_type="type",
                target="#password"
            ))
            journey.add_step(JourneyStep(
                step_id="login_submit",
                description="Submit login form",
                action_type="click",
                target='button[type="submit"]'
            ))
            journey.add_step(JourneyStep(
                step_id="login_verify",
                description="Verify user is logged in",
                action_type="assert",
                target="/dashboard",
                expected_result="User is redirected to dashboard or home page"
            ))
            journeys.append(journey)

        # Create logout journey
        if logout_flow:
            journey = Journey(
                journey_id=f"journey_auth_logout",
                journey_type=JourneyType.AUTHENTICATION,
                name="User Logout Flow",
                description="User logs out and session is terminated",
                priority=3,
                related_stories=logout_flow
            )
            journey.add_step(JourneyStep(
                step_id="logout_click",
                description="Click logout button/link",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="logout_verify",
                description="Verify user is logged out",
                action_type="assert",
                expected_result="User is redirected to login page"
            ))
            journeys.append(journey)

        # Create registration journey
        if register_flow:
            journey = Journey(
                journey_id=f"journey_auth_register",
                journey_type=JourneyType.AUTHENTICATION,
                name="User Registration Flow",
                description="New user creates an account",
                priority=2,
                related_stories=register_flow
            )
            journey.add_step(JourneyStep(
                step_id="register_navigate",
                description="Navigate to registration page",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="register_fill_form",
                description="Fill registration form",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="register_submit",
                description="Submit registration",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="register_verify",
                description="Verify account created",
                action_type="assert",
                expected_result="Success message or redirect to dashboard"
            ))
            journeys.append(journey)

        # Create password reset journey
        if reset_flow:
            journey = Journey(
                journey_id=f"journey_auth_reset",
                journey_type=JourneyType.AUTHENTICATION,
                name="Password Reset Flow",
                description="User resets forgotten password",
                priority=4,
                related_stories=reset_flow
            )
            journey.add_step(JourneyStep(
                step_id="reset_navigate",
                description="Navigate to forgot password page",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="reset_enter_email",
                description="Enter email address",
                action_type="type"
            ))
            journey.add_step(JourneyStep(
                step_id="reset_submit",
                description="Submit reset request",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="reset_verify_email",
                description="Verify reset email sent",
                action_type="assert",
                expected_result="Confirmation message displayed"
            ))
            journeys.append(journey)

        return journeys

    def _detect_payment_patterns(self, spec: Spec) -> List[Journey]:
        """Detect payment-related journeys"""
        journeys = []
        payment_keywords = {
            'checkout': ['checkout', 'check out', 'complete purchase', 'place order'],
            'payment': ['payment', 'make payment', 'pay now', 'enter payment'],
            'confirmation': ['payment confirmation', 'order confirmation', 'receipt'],
            'billing': ['billing', 'invoice', 'subscription', 'plan']
        }

        checkout_flow = []
        payment_flow = []
        confirmation_flow = []

        # Scan all stories for payment-related content
        for phase_id, phase in spec.phases.items():
            for story_id, story in phase.stories.items():
                story_text = f"{story_id} {story.description} {' '.join(story.acceptance_criteria)}".lower()

                # Check for checkout patterns
                if any(kw in story_text for kw in payment_keywords['checkout']):
                    checkout_flow.append(story_id)

                # Check for payment patterns
                if any(kw in story_text for kw in payment_keywords['payment']):
                    payment_flow.append(story_id)

                # Check for confirmation patterns
                if any(kw in story_text for kw in payment_keywords['confirmation']):
                    confirmation_flow.append(story_id)

        # Create checkout journey
        if checkout_flow or payment_flow:
            related_stories = list(set(checkout_flow + payment_flow))
            journey = Journey(
                journey_id=f"journey_payment_checkout",
                journey_type=JourneyType.PAYMENT,
                name="Checkout Flow",
                description="User completes checkout process",
                priority=1,  # Critical priority
                related_stories=related_stories
            )
            journey.add_step(JourneyStep(
                step_id="checkout_navigate",
                description="Navigate to checkout page",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="checkout_review",
                description="Review order details",
                action_type="assert"
            ))
            journey.add_step(JourneyStep(
                step_id="checkout_enter_shipping",
                description="Enter shipping information",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="checkout_enter_payment",
                description="Enter payment information",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="checkout_submit",
                description="Submit order",
                action_type="click"
            ))
            journeys.append(journey)

        # Create payment confirmation journey
        if confirmation_flow or payment_flow:
            related_stories = list(set(confirmation_flow + payment_flow))
            journey = Journey(
                journey_id=f"journey_payment_confirmation",
                journey_type=JourneyType.PAYMENT,
                name="Payment Confirmation",
                description="User receives payment confirmation",
                priority=2,
                related_stories=related_stories
            )
            journey.add_step(JourneyStep(
                step_id="confirmation_wait",
                description="Wait for payment processing",
                action_type="wait"
            ))
            journey.add_step(JourneyStep(
                step_id="confirmation_verify",
                description="Verify payment confirmation message",
                action_type="assert",
                expected_result="Success message or order ID displayed"
            ))
            journey.add_step(JourneyStep(
                step_id="confirmation_check_receipt",
                description="Check for receipt or order summary",
                action_type="assert",
                expected_result="Order details and amount shown"
            ))
            journeys.append(journey)

        return journeys

    def _detect_onboarding_patterns(self, spec: Spec) -> List[Journey]:
        """Detect onboarding-related journeys"""
        journeys = []
        onboarding_keywords = {
            'signup': ['signup', 'sign-up', 'sign up', 'create account', 'register', 'get started'],
            'welcome': ['welcome', 'intro', 'introduction', 'tour', 'tutorial', 'walkthrough'],
            'setup': ['setup', 'configure', 'profile setup', 'preferences', 'settings'],
            'verification': ['verify', 'verify email', 'email verification', 'confirm email', 'phone verification']
        }

        signup_flow = []
        welcome_flow = []
        setup_flow = []

        # Scan all stories for onboarding-related content
        for phase_id, phase in spec.phases.items():
            for story_id, story in phase.stories.items():
                story_text = f"{story_id} {story.description} {' '.join(story.acceptance_criteria)}".lower()

                # Check for signup patterns
                if any(kw in story_text for kw in onboarding_keywords['signup']):
                    signup_flow.append(story_id)

                # Check for welcome patterns
                if any(kw in story_text for kw in onboarding_keywords['welcome']):
                    welcome_flow.append(story_id)

                # Check for setup patterns
                if any(kw in story_text for kw in onboarding_keywords['setup']):
                    setup_flow.append(story_id)

        # Create registration/signup journey
        if signup_flow:
            journey = Journey(
                journey_id=f"journey_onboarding_signup",
                journey_type=JourneyType.ONBOARDING,
                name="User Registration",
                description="New user creates an account and begins onboarding",
                priority=2,  # High priority
                related_stories=signup_flow
            )
            journey.add_step(JourneyStep(
                step_id="signup_navigate",
                description="Navigate to registration page",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="signup_fill_form",
                description="Fill registration form",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="signup_submit",
                description="Submit registration",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="signup_verify",
                description="Verify account created",
                action_type="assert",
                expected_result="Success message or redirect to welcome"
            ))
            journeys.append(journey)

        # Create welcome tour journey
        if welcome_flow:
            journey = Journey(
                journey_id=f"journey_onboarding_welcome",
                journey_type=JourneyType.ONBOARDING,
                name="Welcome Tour",
                description="User receives welcome introduction to the platform",
                priority=3,
                related_stories=welcome_flow
            )
            journey.add_step(JourneyStep(
                step_id="welcome_check_display",
                description="Check welcome modal/page is displayed",
                action_type="assert",
                expected_result="Welcome message shown"
            ))
            journey.add_step(JourneyStep(
                step_id="welcome_navigate_tour",
                description="Navigate through tour steps",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="welcome_complete_tour",
                description="Complete or skip tour",
                action_type="click"
            ))
            journeys.append(journey)

        # Create profile setup journey
        if setup_flow:
            journey = Journey(
                journey_id=f"journey_onboarding_setup",
                journey_type=JourneyType.ONBOARDING,
                name="Profile Setup",
                description="User configures their profile and preferences",
                priority=4,
                related_stories=setup_flow
            )
            journey.add_step(JourneyStep(
                step_id="setup_navigate",
                description="Navigate to profile setup",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="setup_enter_details",
                description="Enter profile information",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="setup_configure_preferences",
                description="Configure user preferences",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="setup_save",
                description="Save profile settings",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="setup_verify",
                description="Verify profile is updated",
                action_type="assert",
                expected_result="Profile information displayed correctly"
            ))
            journeys.append(journey)

        return journeys

    def _detect_admin_patterns(self, spec: Spec) -> List[Journey]:
        """Detect admin panel-related journeys"""
        journeys = []
        admin_keywords = {
            'user_management': ['user management', 'manage users', 'admin users', 'user list'],
            'content_management': ['content management', 'manage content', 'admin content', 'cms'],
            'settings': ['admin settings', 'system settings', 'configuration', 'admin panel'],
            'reports': ['admin reports', 'analytics', 'dashboard', 'admin dashboard']
        }

        user_mgmt_flow = []
        content_mgmt_flow = []
        settings_flow = []

        # Scan all stories for admin-related content
        for phase_id, phase in spec.phases.items():
            for story_id, story in phase.stories.items():
                story_text = f"{story_id} {story.description} {' '.join(story.acceptance_criteria)}".lower()

                # Check for user management patterns
                if any(kw in story_text for kw in admin_keywords['user_management']):
                    user_mgmt_flow.append(story_id)

                # Check for content management patterns
                if any(kw in story_text for kw in admin_keywords['content_management']):
                    content_mgmt_flow.append(story_id)

                # Check for settings patterns
                if any(kw in story_text for kw in admin_keywords['settings']):
                    settings_flow.append(story_id)

        # Create user management journey
        if user_mgmt_flow:
            journey = Journey(
                journey_id=f"journey_admin_user_management",
                journey_type=JourneyType.ADMIN,
                name="User Management",
                description="Admin manages user accounts and permissions",
                priority=2,  # High priority
                related_stories=user_mgmt_flow
            )
            journey.add_step(JourneyStep(
                step_id="user_mgmt_navigate",
                description="Navigate to user management panel",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="user_mgmt_view_list",
                description="View list of users",
                action_type="assert",
                expected_result="User list is displayed"
            ))
            journey.add_step(JourneyStep(
                step_id="user_mgmt_search",
                description="Search or filter users",
                action_type="type"
            ))
            journey.add_step(JourneyStep(
                step_id="user_mgmt_edit",
                description="Edit user details or permissions",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="user_mgmt_save",
                description="Save user changes",
                action_type="click"
            ))
            journeys.append(journey)

        # Create content management journey
        if content_mgmt_flow:
            journey = Journey(
                journey_id=f"journey_admin_content_management",
                journey_type=JourneyType.ADMIN,
                name="Content Management",
                description="Admin manages platform content",
                priority=3,
                related_stories=content_mgmt_flow
            )
            journey.add_step(JourneyStep(
                step_id="content_mgmt_navigate",
                description="Navigate to content management",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="content_mgmt_list",
                description="View content list",
                action_type="assert"
            ))
            journey.add_step(JourneyStep(
                step_id="content_mgmt_create",
                description="Create new content",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="content_mgmt_edit_form",
                description="Fill content form",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="content_mgmt_publish",
                description="Publish or save content",
                action_type="click"
            ))
            journeys.append(journey)

        # Create system settings journey
        if settings_flow:
            journey = Journey(
                journey_id=f"journey_admin_settings",
                journey_type=JourneyType.ADMIN,
                name="System Settings",
                description="Admin configures system settings",
                priority=3,
                related_stories=settings_flow
            )
            journey.add_step(JourneyStep(
                step_id="settings_navigate",
                description="Navigate to admin settings",
                action_type="navigate"
            ))
            journey.add_step(JourneyStep(
                step_id="settings_view",
                description="View current settings",
                action_type="assert"
            ))
            journey.add_step(JourneyStep(
                step_id="settings_modify",
                description="Modify system configuration",
                action_type="fill_form"
            ))
            journey.add_step(JourneyStep(
                step_id="settings_save",
                description="Save settings",
                action_type="click"
            ))
            journey.add_step(JourneyStep(
                step_id="settings_verify",
                description="Verify settings applied",
                action_type="assert",
                expected_result="Settings confirmation message"
            ))
            journeys.append(journey)

        return journeys

    def _detect_crud_patterns(self, spec: Spec) -> List[Journey]:
        """Detect CRUD operation journeys"""
        # TODO: Implement CRUD pattern detection
        return []

    # ========================================================================
    # Scenario Generation Methods
    # ========================================================================

    def _get_acceptance_criteria_for_journey(self, journey: Journey, spec: Spec) -> List[str]:
        """
        Extract acceptance criteria from stories related to a journey

        Args:
            journey: Journey to get acceptance criteria for
            spec: Spec object containing stories

        Returns:
            List of acceptance criteria from all related stories
        """
        acceptance_criteria = []

        for story_id in journey.related_stories:
            # Find the story in the spec
            for phase in spec.phases.values():
                if story_id in phase.stories:
                    story = phase.stories[story_id]
                    # Add all acceptance criteria from this story
                    acceptance_criteria.extend(story.acceptance_criteria)
                    break

        return acceptance_criteria

    def _get_dependencies_for_journey(self, journey: Journey, spec: Spec) -> List[str]:
        """
        Extract dependencies from stories related to a journey

        Feature #258: Gather all story dependencies and convert them to scenario IDs

        Args:
            journey: Journey to get dependencies for
            spec: Spec object containing stories

        Returns:
            List of scenario IDs that this journey's scenarios depend on
        """
        dependencies = []

        for story_id in journey.related_stories:
            # Find the story in the spec
            for phase in spec.phases.values():
                if story_id in phase.stories:
                    story = phase.stories[story_id]
                    # Add dependencies from this story
                    if story.depends_on:
                        # Convert story IDs to scenario IDs
                        for dep_story_id in story.depends_on:
                            # Create happy path scenario ID for the dependency
                            dep_scenario_id = f"{dep_story_id}_happy_path"
                            dependencies.append(dep_scenario_id)
                    break

        return dependencies

    def generate_scenarios(self, journeys: List[Journey], spec: Spec) -> None:
        """
        Generate test scenarios for all journeys

        Each journey gets:
        - 1 happy path scenario (success case)
        - N error path scenarios (failure cases)

        Args:
            journeys: List of journeys to generate scenarios for
            spec: Spec object containing acceptance criteria
        """
        for journey in journeys:
            self._generate_happy_path_scenario(journey, spec)
            self._generate_error_scenarios(journey, spec)

    def _generate_happy_path_scenario(self, journey: Journey, spec: Spec) -> None:
        """
        Generate happy path scenario from journey steps

        The happy path is the default success flow through the journey

        Args:
            journey: Journey to generate scenario for
            spec: Spec object containing acceptance criteria
        """
        # Extract acceptance criteria from related stories
        acceptance_criteria = self._get_acceptance_criteria_for_journey(journey, spec)

        # Extract dependencies from related stories (Feature #258)
        dependencies = self._get_dependencies_for_journey(journey, spec)

        # Create happy path scenario from journey steps
        scenario = Scenario(
            scenario_id=f"{journey.journey_id}_happy_path",
            scenario_type=ScenarioType.HAPPY_PATH,
            name=f"Happy Path: {journey.name}",
            description=f"Successful completion of {journey.name}",
            steps=list(journey.steps),  # Copy all journey steps
            acceptance_criteria=acceptance_criteria,
            dependencies=dependencies  # Feature #258: Add dependencies
        )
        journey.add_scenario(scenario)

    def _generate_error_scenarios(self, journey: Journey, spec: Spec) -> None:
        """
        Generate error path scenarios for a journey

        Error scenarios test failure conditions and error handling

        Args:
            journey: Journey to generate scenarios for
            spec: Spec object containing acceptance criteria
        """
        journey_type = journey.journey_type

        # Generate error scenarios based on journey type
        if journey_type == JourneyType.AUTHENTICATION:
            self._generate_auth_error_scenarios(journey, spec)
        elif journey_type == JourneyType.PAYMENT:
            self._generate_payment_error_scenarios(journey, spec)
        elif journey_type == JourneyType.ONBOARDING:
            self._generate_onboarding_error_scenarios(journey, spec)
        elif journey_type == JourneyType.ADMIN:
            self._generate_admin_error_scenarios(journey, spec)
        else:
            # Generic error scenarios for other journey types
            self._generate_generic_error_scenarios(journey, spec)

    def _generate_auth_error_scenarios(self, journey: Journey, spec: Spec) -> None:
        """Generate error scenarios for authentication journeys

        Args:
            journey: Journey to generate scenarios for
            spec: Spec object containing acceptance criteria
        """
        journey_name_lower = journey.name.lower()
        acceptance_criteria = self._get_acceptance_criteria_for_journey(journey, spec)
        journey_name_lower = journey.name.lower()

        # Login error scenarios
        if 'login' in journey_name_lower:
            # Invalid credentials
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_invalid_credentials",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Login with Invalid Credentials",
                description="User attempts to login with incorrect email/password",
                acceptance_criteria=acceptance_criteria,
                error_type="invalid_credentials"
            )
            scenario.add_step(JourneyStep(
                step_id="login_invalid_navigate",
                description="Navigate to login page",
                action_type="navigate",
                target="/login"
            ))
            scenario.add_step(JourneyStep(
                step_id="login_invalid_enter_email",
                description="Enter invalid email address",
                action_type="type",
                target="#email"
            ))
            scenario.add_step(JourneyStep(
                step_id="login_invalid_enter_password",
                description="Enter invalid password",
                action_type="type",
                target="#password"
            ))
            scenario.add_step(JourneyStep(
                step_id="login_invalid_submit",
                description="Submit login form",
                action_type="click",
                target='button[type="submit"]'
            ))
            scenario.add_step(JourneyStep(
                step_id="login_invalid_verify_error",
                description="Verify error message is displayed",
                action_type="assert",
                target=".error, .error-message, .alert",
                expected_result="Error message: Invalid credentials"
            ))
            journey.add_scenario(scenario)

            # Missing fields
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_missing_fields",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Login with Missing Fields",
                description="User attempts to login without entering required fields",
                acceptance_criteria=acceptance_criteria,
                error_type="validation_error"
            )
            scenario.add_step(JourneyStep(
                step_id="login_empty_navigate",
                description="Navigate to login page",
                action_type="navigate",
                target="/login"
            ))
            scenario.add_step(JourneyStep(
                step_id="login_empty_submit",
                description="Submit form without entering credentials",
                action_type="click",
                target='button[type="submit"]'
            ))
            scenario.add_step(JourneyStep(
                step_id="login_empty_verify_error",
                description="Verify validation error is displayed",
                action_type="assert",
                target=".error, .error-message, .validation-error",
                expected_result="Error message: Required fields missing"
            ))
            journey.add_scenario(scenario)

        # Registration error scenarios
        elif 'register' in journey_name_lower or 'registration' in journey_name_lower or 'sign up' in journey_name_lower:
            # Email already exists
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_email_exists",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Register with Existing Email",
                description="User attempts to register with an email that's already in use",
                acceptance_criteria=acceptance_criteria,
                error_type="duplicate_email"
            )
            scenario.add_step(JourneyStep(
                step_id="register_exists_navigate",
                description="Navigate to registration page",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_enter_email",
                description="Enter email that already exists",
                action_type="type"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_fill_form",
                description="Fill rest of registration form",
                action_type="fill_form"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_submit",
                description="Submit registration",
                action_type="click"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_verify_error",
                description="Verify error message about existing email",
                action_type="assert",
                expected_result="Error message: Email already registered"
            ))
            journey.add_scenario(scenario)

            # Password mismatch
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_password_mismatch",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Register with Password Mismatch",
                description="User enters different passwords in password and confirm fields",
                acceptance_criteria=acceptance_criteria,
                error_type="validation_error"
            )
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_navigate",
                description="Navigate to registration page",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_fill_form",
                description="Fill form with mismatched passwords",
                action_type="fill_form"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_submit",
                description="Submit registration",
                action_type="click"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_verify_error",
                description="Verify password mismatch error",
                action_type="assert",
                expected_result="Error message: Passwords do not match"
            ))
            journey.add_scenario(scenario)

        # Password reset error scenarios
        elif 'reset' in journey_name_lower or 'forgot' in journey_name_lower:
            # Email not found
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_email_not_found",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Reset Password for Non-Existent Email",
                description="User attempts to reset password for email not in system",
                acceptance_criteria=acceptance_criteria,
                error_type="email_not_found"
            )
            scenario.add_step(JourneyStep(
                step_id="reset_not_found_navigate",
                description="Navigate to forgot password page",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="reset_not_found_enter_email",
                description="Enter email that doesn't exist",
                action_type="type"
            ))
            scenario.add_step(JourneyStep(
                step_id="reset_not_found_submit",
                description="Submit reset request",
                action_type="click"
            ))
            scenario.add_step(JourneyStep(
                step_id="reset_not_found_verify_error",
                description="Verify email not found error",
                action_type="assert",
                expected_result="Error message: Email address not found"
            ))
            journey.add_scenario(scenario)

    def _generate_payment_error_scenarios(self, journey: Journey, spec: Spec) -> None:
        """Generate error scenarios for payment journeys

        Args:
            journey: Journey to generate scenarios for
            spec: Spec object containing acceptance criteria
        """
        journey_name_lower = journey.name.lower()
        acceptance_criteria = self._get_acceptance_criteria_for_journey(journey, spec)
        # Payment declined
        scenario = Scenario(
            scenario_id=f"{journey.journey_id}_error_payment_declined",
            scenario_type=ScenarioType.ERROR_PATH,
            name="Payment Declined",
            description="Payment is declined by payment processor",
            acceptance_criteria=acceptance_criteria,
            error_type="payment_declined"
        )
        scenario.add_step(JourneyStep(
            step_id="payment_declined_navigate",
            description="Navigate to checkout",
            action_type="navigate"
        ))
        scenario.add_step(JourneyStep(
            step_id="payment_declined_enter_details",
            description="Enter invalid payment details",
            action_type="fill_form"
        ))
        scenario.add_step(JourneyStep(
            step_id="payment_declined_submit",
            description="Submit payment",
            action_type="click"
        ))
        scenario.add_step(JourneyStep(
            step_id="payment_declined_verify_error",
            description="Verify payment declined error",
            action_type="assert",
            expected_result="Error message: Payment declined"
        ))
        journey.add_scenario(scenario)

        # Missing required fields
        scenario = Scenario(
            scenario_id=f"{journey.journey_id}_error_missing_payment_details",
            scenario_type=ScenarioType.ERROR_PATH,
            name="Missing Payment Details",
            description="User submits payment without completing required fields",
            acceptance_criteria=acceptance_criteria,
            error_type="validation_error"
        )
        scenario.add_step(JourneyStep(
            step_id="payment_missing_navigate",
            description="Navigate to checkout",
            action_type="navigate"
        ))
        scenario.add_step(JourneyStep(
            step_id="payment_missing_partial_fill",
            description="Partially fill payment form",
            action_type="fill_form"
        ))
        scenario.add_step(JourneyStep(
            step_id="payment_missing_submit",
            description="Submit incomplete form",
            action_type="click"
        ))
        scenario.add_step(JourneyStep(
            step_id="payment_missing_verify_error",
            description="Verify missing fields error",
            action_type="assert",
            expected_result="Error message: Required payment fields missing"
        ))
        journey.add_scenario(scenario)

    def _generate_onboarding_error_scenarios(self, journey: Journey, spec: Spec) -> None:
        """Generate error scenarios for onboarding journeys

        Args:
            journey: Journey to generate scenarios for
            spec: Spec object containing acceptance criteria
        """
        journey_name_lower = journey.name.lower()
        acceptance_criteria = self._get_acceptance_criteria_for_journey(journey, spec)
        journey_name_lower = journey.name.lower()

        # Registration/signup errors
        if 'signup' in journey_name_lower or 'sign up' in journey_name_lower or 'registration' in journey_name_lower:
            # Email already exists
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_email_exists",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Register with Existing Email",
                description="User attempts to register with an email that's already in use",
                acceptance_criteria=acceptance_criteria,
                error_type="duplicate_email"
            )
            scenario.add_step(JourneyStep(
                step_id="register_exists_navigate",
                description="Navigate to registration page",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_enter_email",
                description="Enter email that already exists",
                action_type="type"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_fill_form",
                description="Fill rest of registration form",
                action_type="fill_form"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_submit",
                description="Submit registration",
                action_type="click"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_exists_verify_error",
                description="Verify error message about existing email",
                action_type="assert",
                expected_result="Error message: Email already registered"
            ))
            journey.add_scenario(scenario)

            # Password mismatch
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_password_mismatch",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Register with Password Mismatch",
                description="User enters different passwords in password and confirm fields",
                acceptance_criteria=acceptance_criteria,
                error_type="validation_error"
            )
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_navigate",
                description="Navigate to registration page",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_fill_form",
                description="Fill form with mismatched passwords",
                action_type="fill_form"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_submit",
                description="Submit registration",
                action_type="click"
            ))
            scenario.add_step(JourneyStep(
                step_id="register_mismatch_verify_error",
                description="Verify password mismatch error",
                action_type="assert",
                expected_result="Error message: Passwords do not match"
            ))
            journey.add_scenario(scenario)

        # Profile setup errors
        if 'setup' in journey_name_lower or 'profile' in journey_name_lower:
            # Invalid data format
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_invalid_data",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Invalid Profile Data",
                description="User enters invalid data in profile fields",
                acceptance_criteria=acceptance_criteria,
                error_type="validation_error"
            )
            scenario.add_step(JourneyStep(
                step_id="setup_invalid_navigate",
                description="Navigate to profile setup",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="setup_invalid_enter_data",
                description="Enter invalid data (e.g., invalid email format)",
                action_type="fill_form"
            ))
            scenario.add_step(JourneyStep(
                step_id="setup_invalid_submit",
                description="Submit profile",
                action_type="click"
            ))
            scenario.add_step(JourneyStep(
                step_id="setup_invalid_verify_error",
                description="Verify validation error",
                action_type="assert",
                expected_result="Error message: Invalid data format"
            ))
            journey.add_scenario(scenario)

    def _generate_admin_error_scenarios(self, journey: Journey, spec: Spec) -> None:
        """Generate error scenarios for admin journeys

        Args:
            journey: Journey to generate scenarios for
            spec: Spec object containing acceptance criteria
        """
        journey_name_lower = journey.name.lower()
        acceptance_criteria = self._get_acceptance_criteria_for_journey(journey, spec)
        journey_name_lower = journey.name.lower()

        # User management errors
        if 'user' in journey_name_lower:
            # User not found
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_user_not_found",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Edit Non-Existent User",
                description="Admin attempts to edit user that doesn't exist",
                acceptance_criteria=acceptance_criteria,
                error_type="not_found"
            )
            scenario.add_step(JourneyStep(
                step_id="user_not_found_navigate",
                description="Navigate to user management",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="user_not_found_search",
                description="Search for non-existent user",
                action_type="type"
            ))
            scenario.add_step(JourneyStep(
                step_id="user_not_found_verify_empty",
                description="Verify no results found",
                action_type="assert",
                expected_result="Empty search results or not found message"
            ))
            journey.add_scenario(scenario)

        # Settings errors
        if 'settings' in journey_name_lower:
            # Invalid configuration
            scenario = Scenario(
                scenario_id=f"{journey.journey_id}_error_invalid_config",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Invalid System Configuration",
                description="Admin attempts to save invalid configuration",
                acceptance_criteria=acceptance_criteria,
                error_type="validation_error"
            )
            scenario.add_step(JourneyStep(
                step_id="config_invalid_navigate",
                description="Navigate to system settings",
                action_type="navigate"
            ))
            scenario.add_step(JourneyStep(
                step_id="config_invalid_enter_values",
                description="Enter invalid configuration values",
                action_type="fill_form"
            ))
            scenario.add_step(JourneyStep(
                step_id="config_invalid_submit",
                description="Save settings",
                action_type="click"
            ))
            scenario.add_step(JourneyStep(
                step_id="config_invalid_verify_error",
                description="Verify validation error",
                action_type="assert",
                expected_result="Error message: Invalid configuration values"
            ))
            journey.add_scenario(scenario)

    def _generate_generic_error_scenarios(self, journey: Journey, spec: Spec) -> None:
        """Generate generic error scenarios for any journey type

        Args:
            journey: Journey to generate scenarios for
            spec: Spec object containing acceptance criteria
        """
        acceptance_criteria = self._get_acceptance_criteria_for_journey(journey, spec)
        # Network error
        scenario = Scenario(
            scenario_id=f"{journey.journey_id}_error_network",
            scenario_type=ScenarioType.ERROR_PATH,
            name="Network Error",
            description="Network error occurs during journey",
            acceptance_criteria=acceptance_criteria,
            error_type="network_error"
        )
        scenario.add_step(JourneyStep(
            step_id="network_error_start",
            description="Start journey (network unavailable)",
            action_type="navigate"
        ))
        scenario.add_step(JourneyStep(
            step_id="network_error_verify",
            description="Verify network error message",
            action_type="assert",
            expected_result="Error message: Network connection failed"
        ))
        journey.add_scenario(scenario)


# ============================================================================
# Convenience Functions
# ============================================================================

def load_spec(spec_path: str) -> Spec:
    """
    Convenience function to load a spec file

    Args:
        spec_path: Path to the spec.yaml file

    Returns:
        Parsed Spec object
    """
    extractor = JourneyExtractor()
    return extractor.load_spec(spec_path)


# Export main classes and functions
__all__ = [
    "JourneyExtractor",
    "Spec",
    "Phase",
    "Story",
    "Journey",
    "JourneyStep",
    "JourneyType",
    "Scenario",
    "ScenarioType",
    "load_spec",
]
