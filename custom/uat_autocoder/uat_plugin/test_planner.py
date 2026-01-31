"""
Test Planner Agent - Analyzes PRD and completed features to generate test plans.

This agent is responsible for:
1. Reading and parsing app_spec.txt (project PRD)
2. Querying features.db for completed (passing) features
3. Identifying user journeys from the PRD
4. Mapping completed features to journeys
5. Determining logical test phases (Smoke, Functional, Journey, Regression)
6. Generating test scenarios per journey
7. Defining test dependencies
8. Creating test PRD document in Markdown format
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
import uuid


def parse_app_spec(app_spec_path: str) -> Dict[str, Any]:
    """
    Parse app_spec.txt to extract project requirements and user journeys.

    Args:
        app_spec_path: Path to app_spec.txt file

    Returns:
        Dictionary containing parsed PRD information
    """
    if not os.path.exists(app_spec_path):
        raise FileNotFoundError(f"app_spec.txt not found at {app_spec_path}")

    with open(app_spec_path, 'r') as f:
        content = f.read()

    # Parse key information
    prd_info = {
        'project_name': _extract_xml_tag(content, 'project_name'),
        'overview': _extract_xml_tag(content, 'overview'),
        'technology_stack': _extract_section(content, 'technology_stack'),
        'feature_count': _extract_xml_tag(content, 'feature_count'),
        'database_schema': _extract_section(content, 'database_schema'),
        'ui_integration': _extract_section(content, 'ui_integration'),
        'success_criteria': _extract_list(content, 'success_criteria'),
    }

    return prd_info


def _extract_xml_tag(content: str, tag_name: str) -> str:
    """Extract content from XML-like tag."""
    pattern = rf'<{tag_name}>(.*?)</{tag_name}>'
    match = re.search(pattern, content, re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_section(content: str, section_name: str) -> Dict[str, Any]:
    """Extract a section from app_spec.txt."""
    pattern = rf'<{section_name}>(.*?)</{section_name}>'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return {}

    section_content = match.group(1)

    # Try to parse as structured data
    result = {}
    subpatterns = [
        (r'<(\w+)>(.*?)</\1>', lambda m: (m.group(1), m.group(2).strip())),
        (r'<(\w+)>(.*?)</\1>', lambda m: (m.group(1), [s.strip() for s in m.group(2).split('\n') if s.strip()])),
    ]

    # Extract key-value pairs from nested tags
    for tag_pattern, processor in subpatterns:
        for match in re.finditer(tag_pattern, section_content, re.DOTALL):
            key, value = processor(match)
            if key and value:
                result[key] = value

    return result


def _extract_list(content: str, section_name: str) -> List[str]:
    """Extract a list of items from a section."""
    pattern = rf'<{section_name}>(.*?)</{section_name}>'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return []

    items = []
    item_match = re.search(r'<criterion>(.*?)</criterion>', match.group(1), re.DOTALL)
    while item_match:
        items.append(item_match.group(1).strip())
        # Find next criterion
        remaining = match.group(1)[item_match.end():]
        item_match = re.search(r'<criterion>(.*?)</criterion>', remaining, re.DOTALL)

    return items


def identify_user_journeys(prd_info: Dict[str, Any], completed_features: List[Dict[str, Any]]) -> List[str]:
    """
    Identify user journeys from PRD and completed features.

    Args:
        prd_info: Parsed PRD information
        completed_features: List of completed features from features.db

    Returns:
        List of unique user journey names
    """
    journeys = set()

    # Extract journeys from PRD
    overview = prd_info.get('overview', '').lower()
    if 'authentication' in overview or 'login' in overview:
        journeys.add('authentication')
    if 'payment' in overview or 'checkout' in overview:
        journeys.add('payment')
    if 'admin' in overview or 'management' in overview:
        journeys.add('admin')
    if 'onboarding' in overview or 'registration' in overview:
        journeys.add('onboarding')
    if 'dashboard' in overview:
        journeys.add('dashboard')
    if 'api' in overview:
        journeys.add('api')

    # Extract journeys from feature categories
    for feature in completed_features:
        category = feature.get('category', '').lower()
        journeys.add(category)

        # Also check description for journey hints
        description = feature.get('description', '').lower()
        if 'authentication' in description or 'login' in description:
            journeys.add('authentication')
        if 'payment' in description or 'checkout' in description:
            journeys.add('payment')
        if 'admin' in description:
            journeys.add('admin')

    return sorted(list(journeys))


def identify_untested_journeys(
    prd_info: Dict[str, Any],
    completed_features: List[Dict[str, Any]],
    previous_uat_cycles: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Identify user journeys that haven't been tested yet.

    Cross-references journeys from PRD/features with previous UAT cycles
    to determine which journeys still need testing.

    Args:
        prd_info: Parsed PRD information
        completed_features: List of completed features from features.db
        previous_uat_cycles: List of UAT tests from previous cycles (with journey field)

    Returns:
        Dictionary with:
            - all_journeys: List of all journeys identified from spec/features
            - tested_journeys: List of journeys that have previous tests
            - untested_journeys: List of journeys that need testing
            - journey_coverage: Dict mapping journey to test count
    """
    # Step 1: Identify all potential journeys
    all_journeys = set(identify_user_journeys(prd_info, completed_features))

    # Step 2: Extract tested journeys from previous UAT cycles
    tested_journeys = set()
    journey_coverage = {}

    for cycle in previous_uat_cycles:
        journey = cycle.get('journey')
        if journey:
            tested_journeys.add(journey)
            journey_coverage[journey] = journey_coverage.get(journey, 0) + 1

    # Step 3: Determine untested journeys
    untested_journeys = all_journeys - tested_journeys

    # Initialize journey coverage for untested journeys
    for journey in untested_journeys:
        journey_coverage[journey] = 0

    return {
        'all_journeys': sorted(list(all_journeys)),
        'tested_journeys': sorted(list(tested_journeys)),
        'untested_journeys': sorted(list(untested_journeys)),
        'journey_coverage': journey_coverage,
        'total_journeys': len(all_journeys),
        'tested_count': len(tested_journeys),
        'untested_count': len(untested_journeys)
    }


def determine_test_phases(completed_features: List[Dict[str, Any]]) -> List[str]:
    """
    Determine logical test phases based on completed features.

    Args:
        completed_features: List of completed features

    Returns:
        List of test phases to run
    """
    phases = []

    feature_count = len(completed_features)

    # Always start with smoke tests
    phases.append('smoke')

    # Add functional tests if we have features to test
    if feature_count > 10:
        phases.append('functional')

    # Add regression tests for mature projects
    if feature_count > 30:
        phases.append('regression')

    # Add UAT phase for user-facing testing
    phases.append('uat')

    return phases


def generate_test_scenarios(
    prd_info: Dict[str, Any],
    completed_features: List[Dict[str, Any]],
    journeys: List[str],
    phases: List[str]
) -> List[Dict[str, Any]]:
    """
    Generate test scenarios for each journey and phase.

    Args:
        prd_info: Parsed PRD information
        completed_features: List of completed features
        journeys: User journey names
        phases: Test phases

    Returns:
        List of test scenario dictionaries
    """
    scenarios = []
    priority = 1

    for phase in phases:
        for journey in journeys:
            # Generate scenarios based on journey and phase
            if phase == 'smoke':
                # Smoke tests: Basic functionality checks
                scenarios.extend(_generate_smoke_tests(journey, completed_features, priority))
                priority += len(scenarios)
            elif phase == 'functional':
                # Functional tests: Detailed feature testing
                scenarios.extend(_generate_functional_tests(journey, completed_features, priority))
                priority += len(_generate_functional_tests(journey, completed_features, 0))
            elif phase == 'regression':
                # Regression tests: Cross-feature workflows
                scenarios.extend(_generate_regression_tests(journey, completed_features, priority))
                priority += len(_generate_regression_tests(journey, completed_features, 0))
            elif phase == 'uat':
                # UAT tests: User-facing scenarios
                scenarios.extend(_generate_uat_tests(journey, completed_features, priority))
                priority += len(_generate_uat_tests(journey, completed_features, 0))

    return scenarios


def _generate_smoke_tests(journey: str, features: List[Dict[str, Any]], start_priority: int) -> List[Dict[str, Any]]:
    """Generate smoke test scenarios for a journey."""
    scenarios = []

    # Basic smoke test for each journey
    scenario = {
        'phase': 'smoke',
        'journey': journey,
        'scenario': f'Smoke test: {journey} basic functionality',
        'description': f'Verify basic {journey} functionality is working',
        'test_type': 'e2e',
        'steps': [
            f'Navigate to {journey} page/section',
            'Verify page loads without errors',
            'Verify key UI elements are present',
            'Verify no console errors',
            'Take screenshot for visual verification'
        ],
        'expected_result': f'{journey.capitalize()} loads successfully with no errors',
        'priority': start_priority
    }
    scenarios.append(scenario)

    return scenarios


def _generate_functional_tests(journey: str, features: List[Dict[str, Any]], start_priority: int) -> List[Dict[str, Any]]:
    """Generate functional test scenarios for a journey."""
    scenarios = []

    # Group features by journey
    journey_features = [f for f in features if journey.lower() in f.get('category', '').lower()]

    for idx, feature in enumerate(journey_features[:5]):  # Limit to 5 per journey to avoid overwhelming tests
        scenario = {
            'phase': 'functional',
            'journey': journey,
            'scenario': f'Functional test: {feature["name"]}',
            'description': feature.get('description', ''),
            'test_type': 'e2e',
            'steps': feature.get('steps', []),
            'expected_result': f'Feature "{feature["name"]}" works as specified',
            'priority': start_priority + idx
        }
        scenarios.append(scenario)

    return scenarios


def _generate_regression_tests(journey: str, features: List[Dict[str, Any]], start_priority: int) -> List[Dict[str, Any]]:
    """Generate regression test scenarios for a journey."""
    scenarios = []

    # Cross-feature workflow test
    scenario = {
        'phase': 'regression',
        'journey': journey,
        'scenario': f'Regression test: {journey} workflow integrity',
        'description': f'Verify {journey} workflow with multiple related features',
        'test_type': 'e2e',
        'steps': [
            f'Complete {journey} end-to-end workflow',
            'Verify all related features work together',
            'Check for broken dependencies',
            'Verify data persistence across workflow',
            'Check for UI inconsistencies'
        ],
        'expected_result': f'{journey.capitalize()} workflow completes successfully with no regressions',
        'priority': start_priority
    }
    scenarios.append(scenario)

    return scenarios


def _generate_uat_tests(journey: str, features: List[Dict[str, Any]], start_priority: int) -> List[Dict[str, Any]]:
    """Generate UAT test scenarios for a journey."""
    scenarios = []

    # User-facing scenario test
    scenario = {
        'phase': 'uat',
        'journey': journey,
        'scenario': f'UAT test: User can complete {journey} task',
        'description': f'From user perspective, verify {journey} task can be completed successfully',
        'test_type': 'e2e',
        'steps': [
            f'As a user, navigate to {journey}',
            f'Complete typical {journey} user workflow',
            'Verify feedback and notifications',
            'Verify result meets user expectations',
            'Verify no blocking issues'
        ],
        'expected_result': f'User can successfully complete {journey} task',
        'priority': start_priority
    }
    scenarios.append(scenario)

    return scenarios


def calculate_test_dependencies(scenarios: List[Dict[str, Any]]) -> Dict[int, List[int]]:
    """
    Calculate dependencies between test scenarios.

    Rules:
    - Smoke tests have no dependencies (run first)
    - Functional tests depend on smoke tests for same journey
    - Regression tests depend on functional tests
    - UAT tests depend on regression tests

    Args:
        scenarios: List of test scenarios

    Returns:
        Dictionary mapping scenario index to list of dependent scenario indices
    """
    dependencies = {}

    # Group scenarios by phase and journey
    phase_order = {'smoke': 0, 'functional': 1, 'regression': 2, 'uat': 3}

    for i, scenario in enumerate(scenarios):
        phase = scenario['phase']
        journey = scenario['journey']

        deps = []

        # Find scenarios this one depends on
        if phase == 'functional':
            # Depends on smoke test for same journey
            smoke_tests = [j for j, s in enumerate(scenarios)
                          if s['phase'] == 'smoke' and s['journey'] == journey]
            deps.extend(smoke_tests)
        elif phase == 'regression':
            # Depends on functional tests for same journey
            functional_tests = [j for j, s in enumerate(scenarios)
                              if s['phase'] == 'functional' and s['journey'] == journey]
            deps.extend(functional_tests)
        elif phase == 'uat':
            # Depends on regression tests for same journey
            regression_tests = [j for j, s in enumerate(scenarios)
                              if s['phase'] == 'regression' and s['journey'] == journey]
            deps.extend(regression_tests)

        dependencies[i] = deps

    return dependencies


def generate_test_prd(
    prd_info: Dict[str, Any],
    completed_features: List[Dict[str, Any]],
    journeys: List[str],
    phases: List[str],
    scenarios: List[Dict[str, Any]]
) -> str:
    """
    Generate test PRD document in Markdown format.

    Args:
        prd_info: Parsed PRD information
        completed_features: List of completed features
        journeys: User journey names
        phases: Test phases
        scenarios: Test scenarios

    Returns:
        Markdown formatted test PRD
    """
    lines = []

    # Header
    lines.append(f"# Test Plan: {prd_info.get('project_name', 'UAT AutoCoder Plugin')}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Cycle ID:** {str(uuid.uuid4())[:8]}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append(f"This test plan covers **{len(completed_features)} completed features** across **{len(journeys)} user journeys**.")
    lines.append("")
    lines.append(prd_info.get('overview', ''))
    lines.append("")

    # Test Statistics
    lines.append("## Test Statistics")
    lines.append("")
    lines.append(f"- **Total Features Completed:** {len(completed_features)}")
    lines.append(f"- **User Journeys Identified:** {len(journeys)}")
    lines.append(f"- **Test Phases:** {', '.join(phases)}")
    lines.append(f"- **Total Test Scenarios:** {len(scenarios)}")
    lines.append("")

    # User Journeys
    lines.append("## User Journeys")
    lines.append("")
    for journey in journeys:
        journey_count = len([s for s in scenarios if s['journey'] == journey])
        lines.append(f"### {journey.capitalize()}")
        lines.append(f"- {journey_count} test scenarios")
        lines.append("")

    # Test Phases
    lines.append("## Test Phases")
    lines.append("")
    for phase in phases:
        phase_count = len([s for s in scenarios if s['phase'] == phase])
        lines.append(f"### {phase.capitalize()}")
        phase_desc = {
            'smoke': 'Basic functionality checks to ensure critical paths work',
            'functional': 'Detailed testing of individual features',
            'regression': 'Cross-feature workflow testing',
            'uat': 'User-facing scenario validation'
        }
        lines.append(phase_desc.get(phase, ''))
        lines.append(f"- {phase_count} scenarios")
        lines.append("")

    # Test Scenarios
    lines.append("## Test Scenarios")
    lines.append("")

    # Group by phase and journey
    for phase in phases:
        lines.append(f"### {phase.capitalize()} Tests")
        lines.append("")

        for journey in journeys:
            journey_scenarios = [s for s in scenarios if s['phase'] == phase and s['journey'] == journey]
            if not journey_scenarios:
                continue

            lines.append(f"#### {journey.capitalize()}")
            lines.append("")

            for scenario in journey_scenarios:
                lines.append(f"**{scenario['scenario']}** (Priority: {scenario['priority']})")
                lines.append("")
                lines.append(f"- **Description:** {scenario['description']}")
                lines.append(f"- **Test Type:** {scenario['test_type']}")
                lines.append(f"- **Expected Result:** {scenario['expected_result']}")
                lines.append("")

    # Execution Notes
    lines.append("## Execution Notes")
    lines.append("")
    lines.append("- Tests will be executed in parallel by 3-5 concurrent agents")
    lines.append("- Each test will capture screenshots, videos, and console logs on failure")
    lines.append("- Failed tests will automatically create DevLayer bug cards")
    lines.append("- Progress will be reported in real-time via WebSocket")
    lines.append("")

    return "\n".join(lines)


class TestPlannerAgent:
    """
    Main Test Planner Agent class.

    Coordinates the entire test planning process:
    1. Parse PRD
    2. Query completed features
    3. Identify journeys
    4. Determine phases
    5. Generate scenarios
    6. Calculate dependencies
    7. Generate test PRD
    """

    def __init__(self, app_spec_path: Optional[str] = None, db_manager=None):
        """
        Initialize Test Planner Agent.

        Args:
            app_spec_path: Path to app_spec.txt (defaults to ./app_spec.txt)
            db_manager: DatabaseManager instance (creates new if None)
        """
        self.app_spec_path = app_spec_path or os.path.join(os.getcwd(), 'app_spec.txt')

        from custom.uat_plugin.database import get_db_manager
        self.db = db_manager or get_db_manager()

    def generate_test_plan(self) -> Dict[str, Any]:
        """
        Generate complete test plan from PRD and completed features.

        Returns:
            Dictionary containing test plan details
        """
        # Step 1: Parse PRD
        print("Step 1: Parsing app_spec.txt...")
        prd_info = parse_app_spec(self.app_spec_path)

        # Step 2: Query completed features
        print("Step 2: Querying features.db for completed features...")
        stats = self.db.get_feature_stats()
        completed_features = self.db.query_passing_features()
        print(f"  Database Statistics:")
        print(f"    - Total features: {stats['total']}")
        print(f"    - Passing (completed): {stats['passing']}")
        print(f"    - In Progress: {stats['in_progress']}")
        print(f"    - Pending (not started): {stats['pending']}")
        print(f"  Using {len(completed_features)} passing features for test planning")

        # Step 3: Identify user journeys
        print("Step 3: Identifying user journeys...")
        journeys = identify_user_journeys(prd_info, completed_features)
        print(f"  Identified {len(journeys)} journeys: {', '.join(journeys)}")

        # Step 4: Determine test phases
        print("Step 4: Determining test phases...")
        phases = determine_test_phases(completed_features)
        print(f"  Phases: {', '.join(phases)}")

        # Step 5: Generate test scenarios
        print("Step 5: Generating test scenarios...")
        scenarios = generate_test_scenarios(prd_info, completed_features, journeys, phases)
        print(f"  Generated {len(scenarios)} scenarios")

        # Step 6: Calculate dependencies
        print("Step 6: Calculating test dependencies...")
        dependencies = calculate_test_dependencies(scenarios)

        # Step 7: Generate test PRD
        print("Step 7: Generating test PRD document...")
        test_prd = generate_test_prd(prd_info, completed_features, journeys, phases, scenarios)

        # Create cycle ID
        cycle_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

        return {
            'cycle_id': cycle_id,
            'project_name': prd_info.get('project_name', 'Unknown'),
            'total_features_completed': len(completed_features),
            'journeys_identified': journeys,
            'recommended_phases': phases,
            'test_scenarios': scenarios,
            'test_dependencies': dependencies,
            'test_prd': test_prd,
            'created_at': datetime.now().isoformat()
        }


if __name__ == '__main__':
    # Test the Test Planner Agent
    print("=" * 60)
    print("Test Planner Agent - Standalone Test")
    print("=" * 60)
    print()

    try:
        agent = TestPlannerAgent()
        test_plan = agent.generate_test_plan()

        print("\n" + "=" * 60)
        print("TEST PLAN GENERATED SUCCESSFULLY")
        print("=" * 60)
        print(f"\nCycle ID: {test_plan['cycle_id']}")
        print(f"Project: {test_plan['project_name']}")
        print(f"Completed Features: {test_plan['total_features_completed']}")
        print(f"Journeys: {', '.join(test_plan['journeys_identified'])}")
        print(f"Phases: {', '.join(test_plan['recommended_phases'])}")
        print(f"Test Scenarios: {len(test_plan['test_scenarios'])}")
        print()

        # Show current database state
        stats = agent.db.get_feature_stats()
        print("Current Database State:")
        print(f"  - Total features: {stats['total']}")
        print(f"  - Passing: {stats['passing']}")
        print(f"  - In Progress: {stats['in_progress']}")
        print(f"  - Pending: {stats['pending']}")
        print()

        print("Test PRD Preview (first 500 chars):")
        print("-" * 60)
        print(test_plan['test_prd'][:500] + "...")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

# ==============================================================================
# FEATURE #12: Conversational Test Framework Modification
# ==============================================================================

def modify_test_plan(
    original_plan: Dict[str, Any],
    modification_type: str,
    modification_params: Dict[str, Any] = None,
    user_message: str = None
) -> Dict[str, Any]:
    """
    Modify a test plan based on user conversational input (FR11)

    This function applies modifications to a previously generated test plan:
    - add_tests: Add specific tests to the plan
    - remove_tests: Remove tests from the plan
    - change_phases: Adjust phase allocation
    - adjust_journeys: Add/remove journeys
    - custom: Natural language modifications

    Args:
        original_plan: Original test plan from generate_test_plan()
        modification_type: Type of modification to apply
        modification_params: Structured parameters for the modification
        user_message: Natural language description from user

    Returns:
        Modified test plan with same structure as generate_test_plan()
    """
    if modification_params is None:
        modification_params = {}

    # Create a copy to avoid modifying the original
    modified_plan = original_plan.copy()
    modified_plan['test_scenarios'] = original_plan['test_scenarios'].copy()
    modified_plan['test_dependencies'] = original_plan['test_dependencies'].copy()

    print(f"🔧 Applying modification: {modification_type}")

    if modification_type == "add_tests":
        # Add new tests based on params
        tests_to_add = modification_params.get('tests', [])
        new_priority = max(s['priority'] for s in modified_plan['test_scenarios']) + 1

        for test_spec in tests_to_add:
            new_scenario = {
                'phase': test_spec.get('phase', 'functional'),
                'journey': test_spec.get('journey', 'general'),
                'scenario': test_spec.get('scenario', 'Custom test'),
                'description': test_spec.get('description', 'User-requested test'),
                'test_type': test_spec.get('test_type', 'e2e'),
                'steps': test_spec.get('steps', ['Execute custom test']),
                'expected_result': test_spec.get('expected_result', 'Test passes'),
                'priority': new_priority
            }
            modified_plan['test_scenarios'].append(new_scenario)
            new_priority += 1

        print(f"  ✓ Added {len(tests_to_add)} test(s)")

    elif modification_type == "remove_tests":
        # Remove tests based on criteria
        remove_criteria = modification_params.get('criteria', {})

        # Filter scenarios based on criteria
        original_count = len(modified_plan['test_scenarios'])

        if 'phase' in remove_criteria:
            phase_to_remove = remove_criteria['phase']
            modified_plan['test_scenarios'] = [
                s for s in modified_plan['test_scenarios']
                if s['phase'] != phase_to_remove
            ]
            print(f"  ✓ Removed all {phase_to_remove} tests")

        if 'journey' in remove_criteria:
            journey_to_remove = remove_criteria['journey']
            modified_plan['test_scenarios'] = [
                s for s in modified_plan['test_scenarios']
                if s['journey'] != journey_to_remove
            ]
            print(f"  ✓ Removed all {journey_to_remove} journey tests")

        removed_count = original_count - len(modified_plan['test_scenarios'])
        print(f"  ✓ Total removed: {removed_count} test(s)")

    elif modification_type == "change_phases":
        # Adjust phase allocation
        new_phases = modification_params.get('phases', [])
        phase_adjustments = modification_params.get('adjustments', {})

        # Filter scenarios to only include specified phases
        if new_phases:
            modified_plan['test_scenarios'] = [
                s for s in modified_plan['test_scenarios']
                if s['phase'] in new_phases
            ]
            modified_plan['recommended_phases'] = new_phases
            print(f"  ✓ Updated phases to: {', '.join(new_phases)}")

        # Adjust test counts per phase
        if phase_adjustments:
            for phase, target_count in phase_adjustments.items():
                current_count = sum(1 for s in modified_plan['test_scenarios'] if s['phase'] == phase)
                if target_count < current_count:
                    # Reduce tests in this phase
                    phase_scenarios = [s for s in modified_plan['test_scenarios'] if s['phase'] == phase]
                    scenarios_to_remove = current_count - target_count
                    modified_plan['test_scenarios'] = [
                        s for s in modified_plan['test_scenarios']
                        if not (s['phase'] == phase and phase_scenarios.index(s) < scenarios_to_remove)
                    ]
                    print(f"  ✓ Reduced {phase} tests from {current_count} to {target_count}")
                elif target_count > current_count:
                    # Add more tests to this phase
                    tests_to_add = target_count - current_count
                    new_priority = max(s['priority'] for s in modified_plan['test_scenarios']) + 1
                    for i in range(tests_to_add):
                        modified_plan['test_scenarios'].append({
                            'phase': phase,
                            'journey': modification_params.get('default_journey', 'general'),
                            'scenario': f'Additional {phase} test #{i+1}',
                            'description': f'User-requested additional {phase} test',
                            'test_type': 'e2e',
                            'steps': [f'Execute {phase} test scenario #{i+1}'],
                            'expected_result': f'{phase.capitalize()} test passes',
                            'priority': new_priority
                        })
                        new_priority += 1
                    print(f"  ✓ Increased {phase} tests from {current_count} to {target_count}")

    elif modification_type == "adjust_journeys":
        # Add or remove journeys
        journeys_to_add = modification_params.get('add', [])
        journeys_to_remove = modification_params.get('remove', [])

        # Remove journeys
        for journey in journeys_to_remove:
            original_count = len(modified_plan['test_scenarios'])
            modified_plan['test_scenarios'] = [
                s for s in modified_plan['test_scenarios']
                if s['journey'] != journey
            ]
            removed_count = original_count - len(modified_plan['test_scenarios'])
            if journey in modified_plan.get('journeys_identified', []):
                modified_plan['journeys_identified'].remove(journey)
            print(f"  ✓ Removed journey: {journey} ({removed_count} tests)")

        # Add journeys
        for journey in journeys_to_add:
            if journey not in modified_plan.get('journeys_identified', []):
                modified_plan.setdefault('journeys_identified', []).append(journey)

                # Add basic smoke test for new journey
                new_priority = max(s['priority'] for s in modified_plan['test_scenarios']) + 1
                modified_plan['test_scenarios'].append({
                    'phase': 'smoke',
                    'journey': journey,
                    'scenario': f'Smoke test: {journey} basic functionality',
                    'description': f'Verify basic {journey} functionality is working',
                    'test_type': 'e2e',
                    'steps': [
                        f'Navigate to {journey} page/section',
                        'Verify page loads without errors',
                        'Verify key UI elements are present'
                    ],
                    'expected_result': f'{journey.capitalize()} loads successfully',
                    'priority': new_priority
                })
                print(f"  ✓ Added journey: {journey}")

    elif modification_type == "custom" and user_message:
        # Parse natural language modifications (simple keyword matching)
        message_lower = user_message.lower()

        # Parse "add X tests" patterns
        import re
        add_pattern = r'add (\d+) more? (\w+) tests?'
        add_match = re.search(add_pattern, message_lower)

        if add_match:
            count = int(add_match.group(1))
            phase = add_match.group(2).rstrip('s')  # Remove trailing 's'
            valid_phases = ['smoke', 'functional', 'regression', 'uat']

            if phase in valid_phases:
                new_priority = max(s['priority'] for s in modified_plan['test_scenarios']) + 1
                for i in range(count):
                    modified_plan['test_scenarios'].append({
                        'phase': phase,
                        'journey': 'general',
                        'scenario': f'Additional {phase} test #{i+1}',
                        'description': f'User-requested additional {phase} test',
                        'test_type': 'e2e',
                        'steps': [f'Execute {phase} test scenario #{i+1}'],
                        'expected_result': f'{phase.capitalize()} test passes',
                        'priority': new_priority
                    })
                    new_priority += 1
                print(f"  ✓ Added {count} {phase} test(s) based on: '{user_message}'")

        # Parse "remove X phase" patterns
        remove_pattern = r'remove all? (\w+) tests?'
        remove_match = re.search(remove_pattern, message_lower)

        if remove_match:
            phase = remove_match.group(1).rstrip('s')
            valid_phases = ['smoke', 'functional', 'regression', 'uat']

            if phase in valid_phases:
                original_count = len(modified_plan['test_scenarios'])
                modified_plan['test_scenarios'] = [
                    s for s in modified_plan['test_scenarios']
                    if s['phase'] != phase
                ]
                removed_count = original_count - len(modified_plan['test_scenarios'])
                print(f"  ✓ Removed {phase} tests ({removed_count} removed) based on: '{user_message}'")

        # Parse "add journey X" patterns
        journey_pattern = r'add journey (\w+)'
        journey_match = re.search(journey_pattern, message_lower)

        if journey_match:
            journey = journey_match.group(1)
            if journey not in modified_plan.get('journeys_identified', []):
                modified_plan.setdefault('journeys_identified', []).append(journey)
                new_priority = max(s['priority'] for s in modified_plan['test_scenarios']) + 1
                modified_plan['test_scenarios'].append({
                    'phase': 'smoke',
                    'journey': journey,
                    'scenario': f'Smoke test: {journey} basic functionality',
                    'description': f'Verify basic {journey} functionality',
                    'test_type': 'e2e',
                    'steps': [f'Navigate to {journey}', 'Verify it loads'],
                    'expected_result': f'{journey.capitalize()} works',
                    'priority': new_priority
                })
                print(f"  ✓ Added journey: {journey} based on: '{user_message}'")

    # Recalculate dependencies after modifications
    modified_plan['test_dependencies'] = calculate_dependencies(
        modified_plan['test_scenarios']
    )

    # Update recommended_phases based on remaining scenarios
    remaining_phases = sorted(list(set(s['phase'] for s in modified_plan['test_scenarios'])))
    if remaining_phases:
        modified_plan['recommended_phases'] = remaining_phases

    # Update journeys_identified based on remaining scenarios
    remaining_journeys = sorted(list(set(s['journey'] for s in modified_plan['test_scenarios'])))
    if remaining_journeys:
        modified_plan['journeys_identified'] = remaining_journeys

    print(f"✅ Modification complete: {len(modified_plan['test_scenarios'])} scenarios")

    return modified_plan


# ==============================================================================
# FEATURE #13: Test Framework Rejection with Clarifying Questions
# ==============================================================================

def analyze_rejection_reason(rejection_reason: str) -> Dict[str, Any]:
    """
    Analyze rejection reason to determine category and clarifying questions.

    Args:
        rejection_reason: User's explanation for rejecting the test framework

    Returns:
        Dictionary with:
        - category: 'too_many_tests', 'missing_coverage', 'wrong_phases', 'wrong_journeys', 'other'
        - clarifying_questions: List of specific questions to ask
        - suggested_improvements: List of potential improvements
    """
    reason_lower = rejection_reason.lower()

    # Category 1: Too many tests
    if any(word in reason_lower for word in ['too many', 'overwhelming', 'too much', 'excessive', 'reduce']):
        return {
            'category': 'too_many_tests',
            'clarifying_questions': [
                'Which phase has too many tests? (smoke, functional, regression, uat)',
                'What would be an ideal total number of tests?',
                'Are there specific journeys you care about most?',
                'Should I prioritize critical path tests over edge cases?'
            ],
            'suggested_improvements': [
                'Reduce test count to focus on critical paths',
                'Consolidate similar test scenarios',
                'Remove redundant test coverage'
            ]
        }

    # Category 2: Missing coverage
    elif any(word in reason_lower for word in ['missing', 'not enough', 'incomplete', 'lack', 'need more']):
        return {
            'category': 'missing_coverage',
            'clarifying_questions': [
                'Which user journey is missing coverage?',
                'Are there specific features or scenarios not covered?',
                'Should I add more edge case testing?',
                'What test types are missing? (e2e, visual, api, a11y)'
            ],
            'suggested_improvements': [
                'Add tests for missing user journeys',
                'Expand coverage for under-tested features',
                'Include additional test types (visual, a11y, api)'
            ]
        }

    # Category 3: Wrong phases
    elif any(word in reason_lower for word in ['phase', 'stages', 'smoke', 'functional', 'regression', 'uat']):
        return {
            'category': 'wrong_phases',
            'clarifying_questions': [
                'Which phases do you want to remove or add?',
                'Do you prefer a simpler phased approach?',
                'Should smoke tests be more comprehensive?',
                'Should regression phase be skipped for this cycle?'
            ],
            'suggested_improvements': [
                'Adjust phase allocation to match testing strategy',
                'Add or remove specific phases',
                'Rebalance test distribution across phases'
            ]
        }

    # Category 4: Wrong journeys
    elif any(word in reason_lower for word in ['journey', 'flow', 'scenario', 'user path']):
        return {
            'category': 'wrong_journeys',
            'clarifying_questions': [
                'Which user journeys are most important?',
                'Are there journeys listed that aren\'t relevant?',
                'Should I focus on happy path or error scenarios?',
                'What are the critical user workflows to test?'
            ],
            'suggested_improvements': [
                'Refine journey selection to match actual usage',
                'Remove irrelevant user journeys',
                'Add missing critical workflows'
            ]
        }

    # Category 5: Other / Generic
    else:
        return {
            'category': 'other',
            'clarifying_questions': [
                'What specific aspect of the test plan needs improvement?',
                'Are there particular test scenarios you want added or removed?',
                'Should the plan focus more on quality or speed of execution?',
                'Any specific testing concerns or constraints I should know about?'
            ],
            'suggested_improvements': [
                'General refinement based on user feedback',
                'Customize test plan to specific needs',
                'Balance comprehensiveness with practicality'
            ]
        }


def reject_test_plan(
    original_plan: Dict[str, Any],
    rejection_reason: str
) -> Dict[str, Any]:
    """
    Handle test plan rejection with clarifying questions (FR13)

    When a user rejects a proposed test framework, this function:
    1. Analyzes the rejection reason
    2. Generates clarifying questions
    3. Provides context for regeneration

    Args:
        original_plan: The test plan that was rejected
        rejection_reason: User's explanation for rejection

    Returns:
        Dictionary with:
        - analysis: Category of rejection
        - clarifying_questions: List of questions to ask user
        - suggested_improvements: Potential improvements
        - conversation_context: Context for next iteration
    """
    print(f"❌ Test plan rejected. Reason: {rejection_reason}")
    print("🔍 Analyzing rejection reason...")

    # Analyze the rejection
    analysis = analyze_rejection_reason(rejection_reason)

    print(f"  Category: {analysis['category']}")
    print(f"  Questions: {len(analysis['clarifying_questions'])}")

    return {
        'original_cycle_id': original_plan.get('cycle_id'),
        'rejection_reason': rejection_reason,
        'analysis': analysis,
        'conversation_context': {
            'iteration': 1,
            'original_plan_summary': {
                'test_count': len(original_plan.get('test_scenarios', [])),
                'phases': original_plan.get('recommended_phases', []),
                'journeys': original_plan.get('journeys_identified', [])
            }
        }
    }


def regenerate_test_plan(
    original_plan: Dict[str, Any],
    rejection_context: Dict[str, Any],
    user_answers: Dict[str, str]
) -> Dict[str, Any]:
    """
    Regenerate test plan based on user's answers to clarifying questions (FR13)

    Creates an improved test plan that addresses the user's concerns:

    Args:
        original_plan: The originally rejected test plan
        rejection_context: Context from reject_test_plan() call
        user_answers: User's responses to clarifying questions

    Returns:
        Improved test plan with same structure as generate_test_plan()
    """
    print("🔄 Regenerating test plan based on feedback...")

    category = rejection_context['analysis']['category']
    improved_plan = original_plan.copy()
    improved_plan['test_scenarios'] = original_plan['test_scenarios'].copy()

    # Apply improvements based on category
    if category == 'too_many_tests':
        # Reduce test count based on user preferences
        target_count = _extract_target_count(user_answers)
        priority_journeys = _extract_priority_journeys(user_answers)

        if target_count and target_count < len(improved_plan['test_scenarios']):
            # Keep highest priority tests
            improved_plan['test_scenarios'] = improved_plan['test_scenarios'][:target_count]
            print(f"  ✓ Reduced to {target_count} tests")

        if priority_journeys:
            # Filter to priority journeys
            improved_plan['test_scenarios'] = [
                s for s in improved_plan['test_scenarios']
                if s['journey'] in priority_journeys
            ]
            print(f"  ✓ Focused on journeys: {priority_journeys}")

    elif category == 'missing_coverage':
        # Add tests for missing coverage
        missing_journeys = _extract_missing_journeys(user_answers)
        missing_types = _extract_missing_test_types(user_answers)

        new_priority = max(s['priority'] for s in improved_plan['test_scenarios']) + 1

        for journey in missing_journeys:
            improved_plan['test_scenarios'].append({
                'phase': 'functional',
                'journey': journey,
                'scenario': f'{journey.capitalize()} - end-to-end flow',
                'description': f'Test complete {journey} workflow',
                'test_type': 'e2e',
                'steps': [f'Navigate to {journey}', f'Complete {journey} flow', 'Verify success'],
                'expected_result': f'{journey.capitalize()} completes successfully',
                'priority': new_priority
            })
            new_priority += 1
            print(f"  ✓ Added journey: {journey}")

    elif category == 'wrong_phases':
        # Adjust phase allocation
        phases_to_remove = _extract_phases_to_remove(user_answers)
        phases_to_add = _extract_phases_to_add(user_answers)

        if phases_to_remove:
            improved_plan['test_scenarios'] = [
                s for s in improved_plan['test_scenarios']
                if s['phase'] not in phases_to_remove
            ]
            print(f"  ✓ Removed phases: {phases_to_remove}")

        # Update recommended phases
        remaining_phases = list(set(s['phase'] for s in improved_plan['test_scenarios']))
        improved_plan['recommended_phases'] = sorted(remaining_phases)

    elif category == 'wrong_journeys':
        # Refine journey selection
        journeys_to_remove = _extract_journeys_to_remove(user_answers)
        journeys_to_keep = _extract_journeys_to_keep(user_answers)

        if journeys_to_remove:
            improved_plan['test_scenarios'] = [
                s for s in improved_plan['test_scenarios']
                if s['journey'] not in journeys_to_remove
            ]
            print(f"  ✓ Removed journeys: {journeys_to_remove}")

        if journeys_to_keep:
            improved_plan['test_scenarios'] = [
                s for s in improved_plan['test_scenarios']
                if s['journey'] in journeys_to_keep
            ]
            print(f"  ✓ Kept journeys: {journeys_to_keep}")

        # Update journeys list
        remaining_journeys = list(set(s['journey'] for s in improved_plan['test_scenarios']))
        improved_plan['journeys_identified'] = sorted(remaining_journeys)

    # Recalculate dependencies
    improved_plan['test_dependencies'] = calculate_dependencies(
        improved_plan['test_scenarios']
    )

    # Update metadata
    improved_plan['regenerated'] = True
    improved_plan['regeneration_iteration'] = rejection_context['conversation_context']['iteration']
    improved_plan['based_on_feedback'] = user_answers

    print(f"✅ Regeneration complete: {len(improved_plan['test_scenarios'])} scenarios")

    return improved_plan


# Helper functions for parsing user answers
def _extract_target_count(user_answers: Dict[str, str]) -> Optional[int]:
    """Extract target test count from user answers."""
    import re
    for key, value in user_answers.items():
        if 'ideal' in key.lower() or 'number' in key.lower() or 'count' in key.lower():
            match = re.search(r'\d+', value)
            if match:
                return int(match.group())
    return None


def _extract_priority_journeys(user_answers: Dict[str, str]) -> List[str]:
    """Extract priority journeys from user answers."""
    journeys = []
    for key, value in user_answers.items():
        if 'journey' in key.lower() or 'care about' in key.lower():
            # Extract journey names (simple comma split)
            parts = value.split(',')
            journeys.extend([p.strip().lower() for p in parts if p.strip()])
    return list(set(journeys))


def _extract_missing_journeys(user_answers: Dict[str, str]) -> List[str]:
    """Extract missing journeys from user answers."""
    journeys = []
    for key, value in user_answers.items():
        if 'missing' in key.lower() or 'not covered' in key.lower():
            parts = value.split(',')
            journeys.extend([p.strip().lower() for p in parts if p.strip()])
    return list(set(journeys))


def _extract_missing_test_types(user_answers: Dict[str, str]) -> List[str]:
    """Extract missing test types from user answers."""
    types = []
    for key, value in user_answers.items():
        if 'test type' in key.lower():
            mentioned = value.lower()
            if 'e2e' in mentioned:
                types.append('e2e')
            if 'visual' in mentioned:
                types.append('visual')
            if 'api' in mentioned:
                types.append('api')
            if 'a11y' in mentioned or 'accessibility' in mentioned:
                types.append('a11y')
    return list(set(types))


def _extract_phases_to_remove(user_answers: Dict[str, str]) -> List[str]:
    """Extract phases to remove from user answers."""
    phases = []
    valid_phases = ['smoke', 'functional', 'regression', 'uat']
    for key, value in user_answers.items():
        if 'remove' in key.lower():
            for phase in valid_phases:
                if phase in value.lower():
                    phases.append(phase)
    return list(set(phases))


def _extract_phases_to_add(user_answers: Dict[str, str]) -> List[str]:
    """Extract phases to add from user answers."""
    phases = []
    valid_phases = ['smoke', 'functional', 'regression', 'uat']
    for key, value in user_answers.items():
        if 'add' in key.lower():
            for phase in valid_phases:
                if phase in value.lower():
                    phases.append(phase)
    return list(set(phases))


def _extract_journeys_to_remove(user_answers: Dict[str, str]) -> List[str]:
    """Extract journeys to remove from user answers."""
    journeys = []
    for key, value in user_answers.items():
        if 'relevant' in key.lower() or 'remove' in key.lower():
            parts = value.split(',')
            journeys.extend([p.strip().lower() for p in parts if p.strip()])
    return list(set(journeys))


def _extract_journeys_to_keep(user_answers: Dict[str, str]) -> List[str]:
    """Extract journeys to keep from user answers."""
    journeys = []
    for key, value in user_answers.items():
        if 'important' in key.lower() or 'focus' in key.lower():
            parts = value.split(',')
            journeys.extend([p.strip().lower() for p in parts if p.strip()])
    return list(set(journeys))
