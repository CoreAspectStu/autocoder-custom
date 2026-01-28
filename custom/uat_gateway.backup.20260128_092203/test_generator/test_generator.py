"""
Test Generator - Generate automated tests from Journey definitions

This module loads Journey objects from the JourneyExtractor and generates
automated test code for various testing frameworks.
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import os
import hashlib
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from journey_extractor.journey_extractor import (
    Journey,
    JourneyStep,
    JourneyType,
    Scenario,
    ScenarioType
)
from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import TestGenerationError, handle_errors
from test_generator import api_test_generator


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class TestConfig:
    """Configuration for test generation"""
    output_format: str = "playwright"  # playwright, cypress, selenium
    output_directory: str = "output/tests"
    base_url: str = "http://localhost:3000"
    test_timeout_ms: int = 30000
    format_with_prettier: bool = True  # Format generated code with Prettier


@dataclass
class GeneratedTest:
    """Represents a generated test file"""
    test_name: str
    test_code: str
    test_type: str  # happy_path or error_path
    framework: str
    output_path: str


# ============================================================================
# Test Generator
# ============================================================================

class TestGenerator:
    """
    Generates automated tests from Journey definitions

    Responsibilities:
    - Load Journey objects from JourneyExtractor
    - Parse journey scenarios
    - Generate test code for target framework
    - Output test files to specified directory
    """

    def __init__(self, config: Optional[TestConfig] = None):
        self.logger = get_logger("test_generator")
        self.config = config or TestConfig()
        self._loaded_journeys: List[Journey] = []
        self._test_data_counter = 0

    @handle_errors(component="test_generator", reraise=True)
    def load_journeys(self, journeys: List[Journey]) -> None:
        """
        Load journey definitions into the test generator

        Args:
            journeys: List of Journey objects from JourneyExtractor

        Raises:
            TestGenerationError: If journeys cannot be loaded
        """
        if not journeys:
            raise TestGenerationError(
                "No journeys provided to load",
                component="test_generator",
                context={"journeys_count": len(journeys)}
            )

        self._loaded_journeys = journeys
        self.logger.info(f"Loaded {len(journeys)} journeys for test generation")

        # Log journey details
        for journey in journeys:
            self.logger.debug(
                f"  - {journey.name} ({journey.journey_type.value}): "
                f"{len(journey.scenarios)} scenarios, "
                f"{len(journey.steps)} steps"
            )

    @handle_errors(component="test_generator", reraise=True)
    def get_journey(self, journey_id: str) -> Optional[Journey]:
        """
        Get a specific journey by ID

        Args:
            journey_id: The journey identifier

        Returns:
            Journey object if found, None otherwise
        """
        for journey in self._loaded_journeys:
            if journey.journey_id == journey_id:
                return journey
        return None

    @handle_errors(component="test_generator", reraise=True)
    def get_all_journeys(self) -> List[Journey]:
        """
        Get all loaded journeys

        Returns:
            List of all Journey objects
        """
        return self._loaded_journeys

    @handle_errors(component="test_generator", reraise=True)
    def get_journey_count(self) -> int:
        """
        Get the count of loaded journeys

        Returns:
            Number of loaded journeys
        """
        return len(self._loaded_journeys)

    @handle_errors(component="test_generator", reraise=True)
    def get_scenarios(self, journey_id: str) -> List[Scenario]:
        """
        Get all scenarios for a specific journey

        Args:
            journey_id: The journey identifier

        Returns:
            List of Scenario objects

        Raises:
            TestGenerationError: If journey not found
        """
        journey = self.get_journey(journey_id)
        if not journey:
            raise TestGenerationError(
                f"Journey not found: {journey_id}",
                component="test_generator",
                context={"journey_id": journey_id}
            )
        return journey.scenarios

    @handle_errors(component="test_generator", reraise=True)
    def get_happy_path_scenarios(self) -> List[Scenario]:
        """
        Get all happy path scenarios across all journeys

        Returns:
            List of happy path Scenario objects
        """
        happy_paths = []
        for journey in self._loaded_journeys:
            for scenario in journey.scenarios:
                if scenario.scenario_type == ScenarioType.HAPPY_PATH:
                    happy_paths.append(scenario)
        return happy_paths

    @handle_errors(component="test_generator", reraise=True)
    def get_error_scenarios(self) -> List[Scenario]:
        """
        Get all error path scenarios across all journeys

        Returns:
            List of error path Scenario objects
        """
        error_paths = []
        for journey in self._loaded_journeys:
            for scenario in journey.scenarios:
                if scenario.scenario_type == ScenarioType.ERROR_PATH:
                    error_paths.append(scenario)
        return error_paths

    @handle_errors(component="test_generator", reraise=True)
    def get_journey_data(self, journey_id: str) -> Dict[str, Any]:
        """
        Get journey data as a dictionary for inspection

        Args:
            journey_id: The journey identifier

        Returns:
            Dictionary with journey data

        Raises:
            TestGenerationError: If journey not found
        """
        journey = self.get_journey(journey_id)
        if not journey:
            raise TestGenerationError(
                f"Journey not found: {journey_id}",
                component="test_generator",
                context={"journey_id": journey_id}
            )

        return {
            "journey_id": journey.journey_id,
            "journey_type": journey.journey_type.value,
            "name": journey.name,
            "description": journey.description,
            "priority": journey.priority,
            "step_count": len(journey.steps),
            "scenario_count": len(journey.scenarios),
            "related_stories": journey.related_stories,
            "scenarios": [
                {
                    "scenario_id": s.scenario_id,
                    "scenario_type": s.scenario_type.value,
                    "name": s.name,
                    "description": s.description,
                    "step_count": len(s.steps),
                    "error_type": s.error_type
                }
                for s in journey.scenarios
            ]
        }

    @handle_errors(component="test_generator", reraise=True)
    def verify_journey_accessible(self, journey_id: str) -> bool:
        """
        Verify that a journey and its data are accessible

        Args:
            journey_id: The journey identifier

        Returns:
            True if journey is accessible and has valid data
        """
        try:
            journey = self.get_journey(journey_id)
            if not journey:
                self.logger.error(f"Journey not found: {journey_id}")
                return False

            # Verify journey has required fields
            if not journey.name or not journey.description:
                self.logger.error(f"Journey missing name or description: {journey_id}")
                return False

            # Verify journey has scenarios
            if not journey.scenarios:
                self.logger.error(f"Journey has no scenarios: {journey_id}")
                return False

            # Verify scenarios have steps
            for scenario in journey.scenarios:
                if not scenario.steps:
                    self.logger.error(f"Scenario has no steps: {scenario.scenario_id}")
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Error verifying journey {journey_id}: {str(e)}")
            return False

    @handle_errors(component="test_generator", reraise=True)
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about loaded journeys

        Returns:
            Dictionary with test generation statistics
        """
        total_journeys = len(self._loaded_journeys)
        total_scenarios = sum(len(j.scenarios) for j in self._loaded_journeys)
        total_steps = sum(
            len(s.steps)
            for j in self._loaded_journeys
            for s in j.scenarios
        )

        happy_path_count = len(self.get_happy_path_scenarios())
        error_path_count = len(self.get_error_scenarios())

        # Count by journey type
        journey_types = {}
        for journey in self._loaded_journeys:
            jtype = journey.journey_type.value
            journey_types[jtype] = journey_types.get(jtype, 0) + 1

        return {
            "total_journeys": total_journeys,
            "total_scenarios": total_scenarios,
            "total_steps": total_steps,
            "happy_path_count": happy_path_count,
            "error_path_count": error_path_count,
            "journey_types": journey_types
        }

    @handle_errors(component="test_generator", reraise=True)
    def generate_tests(self, journey_id: Optional[str] = None) -> List[GeneratedTest]:
        """
        Generate test files for loaded journeys

        Args:
            journey_id: Optional specific journey ID. If None, generates tests for all journeys.

        Returns:
            List of GeneratedTest objects

        Raises:
            TestGenerationError: If test generation fails
        """
        if not self._loaded_journeys:
            raise TestGenerationError(
                "No journeys loaded. Call load_journeys() first.",
                component="test_generator",
                context={"journeys_count": 0}
            )

        generated_tests = []

        # Determine which journeys to generate tests for
        journeys_to_process = []
        if journey_id:
            journey = self.get_journey(journey_id)
            if not journey:
                raise TestGenerationError(
                    f"Journey not found: {journey_id}",
                    component="test_generator",
                    context={"journey_id": journey_id}
                )
            journeys_to_process = [journey]
        else:
            journeys_to_process = self._loaded_journeys

        # Generate test for each journey
        for journey in journeys_to_process:
            # Check if journey has scenarios
            if not journey.scenarios:
                self.logger.warning(
                    f"Journey '{journey.name}' (ID: {journey.journey_id}) has no scenarios. "
                    f"Skipping test generation for this journey."
                )
                continue

            for scenario in journey.scenarios:
                generated_test = self._generate_scenario_test(journey, scenario)
                generated_tests.append(generated_test)

        self.logger.info(f"Generated {len(generated_tests)} test files")
        return generated_tests

    @handle_errors(component="test_generator", reraise=True)
    def write_tests(self, journey_id: Optional[str] = None) -> List[str]:
        """
        Write generated test files to disk

        Args:
            journey_id: Optional specific journey ID. If None, writes tests for all journeys.

        Returns:
            List of file paths that were written

        Raises:
            TestGenerationError: If writing fails
        """
        # Generate tests (in memory)
        generated_tests = self.generate_tests(journey_id)

        if not generated_tests:
            self.logger.warning("No tests to write")
            return []

        written_paths = []

        # Write each generated test to disk
        for generated_test in generated_tests:
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(generated_test.output_path), exist_ok=True)

                # Write test file
                with open(generated_test.output_path, 'w', encoding='utf-8') as f:
                    f.write(generated_test.test_code)

                written_paths.append(generated_test.output_path)
                self.logger.debug(f"Wrote test file: {generated_test.output_path}")

            except Exception as e:
                self.logger.error(f"Failed to write test file {generated_test.output_path}: {str(e)}")
                raise TestGenerationError(
                    f"Failed to write test file: {generated_test.output_path}",
                    component="test_generator",
                    context={"error": str(e), "output_path": generated_test.output_path}
                )

        self.logger.info(f"Wrote {len(written_paths)} test files to disk")
        return written_paths

    @handle_errors(component="test_generator", reraise=True)
    def commit_tests(
        self,
        journey_id: str,
        message_suffix: Optional[str] = None
    ) -> str:
        """
        Write and commit generated test files to git

        This method:
        1. Writes test files for the specified journey
        2. Stages files in git
        3. Creates a commit with a descriptive message including the journey name

        Args:
            journey_id: The journey identifier whose tests should be committed
            message_suffix: Optional suffix to add to commit message

        Returns:
            The commit message that was created

        Raises:
            TestGenerationError: If journey not found or git operations fail
        """
        import subprocess

        # Get the journey
        journey = self.get_journey(journey_id)
        if not journey:
            raise TestGenerationError(
                f"Journey not found: {journey_id}",
                component="test_generator",
                context={"journey_id": journey_id}
            )

        # Write tests for this journey
        written_paths = self.write_tests(journey_id)

        if not written_paths:
            raise TestGenerationError(
                f"No test files were generated for journey: {journey_id}",
                component="test_generator",
                context={"journey_id": journey_id}
            )

        # Stage files in git
        try:
            self.logger.info(f"Staging {len(written_paths)} files in git")

            for file_path in written_paths:
                result = subprocess.run(
                    ['git', 'add', file_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    raise TestGenerationError(
                        f"Failed to stage file in git: {file_path}",
                        component="test_generator",
                        context={"error": result.stderr, "file_path": file_path}
                    )

                self.logger.debug(f"Staged: {file_path}")

        except subprocess.TimeoutExpired:
            raise TestGenerationError(
                "Git add timed out",
                component="test_generator"
            )
        except FileNotFoundError:
            raise TestGenerationError(
                "Git not found. Please ensure git is installed and accessible.",
                component="test_generator"
            )
        except Exception as e:
            raise TestGenerationError(
                f"Failed to stage files in git: {str(e)}",
                component="test_generator",
                context={"error": str(e)}
            )

        # Create commit message with journey name
        base_message = f"Add tests for journey: {journey.name}"

        if message_suffix:
            commit_message = f"{base_message} - {message_suffix}"
        else:
            commit_message = base_message

        # Add file list to commit message body
        file_list = "\n".join([f"  - {os.path.relpath(p)}" for p in written_paths])
        commit_message = f"{commit_message}\n\nGenerated files:\n{file_list}"

        # Create commit
        try:
            self.logger.info("Creating git commit")

            result = subprocess.run(
                ['git', 'commit', '-m', commit_message],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                # Check if nothing to commit
                if "nothing to commit" in result.stdout.lower():
                    raise TestGenerationError(
                        "No changes to commit (files may already be committed)",
                        component="test_generator",
                        context={"journey_id": journey_id}
                    )

                raise TestGenerationError(
                    f"Failed to create git commit: {result.stderr}",
                    component="test_generator",
                    context={"error": result.stderr}
                )

            # Get commit hash for verification
            hash_result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=10
            )

            commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else "unknown"

            self.logger.info(f"Created git commit {commit_hash} for {len(written_paths)} test files")

            return commit_message

        except subprocess.TimeoutExpired:
            raise TestGenerationError(
                "Git commit timed out",
                component="test_generator"
            )
        except Exception as e:
            raise TestGenerationError(
                f"Failed to create git commit: {str(e)}",
                component="test_generator",
                context={"error": str(e)}
            )

    @handle_errors(component="test_generator", reraise=True)
    def generate_page_objects(self, journey_id: Optional[str] = None, output_path: Optional[str] = None) -> str:
        """
        Generate Page Object Model classes for journeys

        Page Object Model (POM) encapsulates:
        - Page selectors (CSS locators)
        - Interaction methods
        - Page navigation methods
        - Methods return Page objects for chaining

        Args:
            journey_id: Optional specific journey ID. If None, generates for all journeys.
            output_path: Optional custom output path. Defaults to output_directory/page-objects.ts

        Returns:
            Path to generated page objects file

        Raises:
            TestGenerationError: If page object generation fails
        """
        if not self._loaded_journeys:
            raise TestGenerationError(
                "No journeys loaded. Call load_journeys() first.",
                component="test_generator",
                context={"journeys_count": 0}
            )

        if output_path is None:
            output_path = os.path.join(self.config.output_directory, "page-objects.ts")

        # Determine which journeys to generate page objects for
        journeys_to_process = []
        if journey_id:
            journey = self.get_journey(journey_id)
            if not journey:
                raise TestGenerationError(
                    f"Journey not found: {journey_id}",
                    component="test_generator",
                    context={"journey_id": journey_id}
                )
            journeys_to_process = [journey]
        else:
            journeys_to_process = self._loaded_journeys

        # Extract all unique pages from journeys
        pages = self._extract_pages_from_journeys(journeys_to_process)

        # Generate page objects code
        page_objects_code = self._generate_page_objects_code(pages)

        # Format with Prettier if enabled
        page_objects_code = self._format_code_with_prettier(page_objects_code, output_path)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write page objects file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(page_objects_code)

        self.logger.info(f"Generated page objects file: {output_path} ({len(pages)} pages)")
        return output_path

    def _extract_pages_from_journeys(self, journeys: List[Journey]) -> Dict[str, List[JourneyStep]]:
        """
        Extract unique pages from journey steps

        Args:
            journeys: List of Journey objects

        Returns:
            Dictionary mapping page names to their steps
        """
        pages = {}

        for journey in journeys:
            for scenario in journey.scenarios:
                current_page = None  # Track the current page

                for step in scenario.steps:
                    # Check if this step navigates to a new page
                    page_name = self._extract_page_name_from_step(step)

                    if page_name:
                        # This is a navigation step - update current page
                        current_page = page_name

                    # If we have a current page, add this step to it
                    if current_page:
                        if current_page not in pages:
                            pages[current_page] = []
                        pages[current_page].append(step)

        return pages

    def _extract_page_name_from_step(self, step: JourneyStep) -> Optional[str]:
        """
        Extract page name from a journey step

        Args:
            step: JourneyStep object

        Returns:
            Page name or None
        """
        # Extract page from URL patterns
        if step.action_type.lower() == "navigate" and step.target:
            # Extract page name from URL path
            # e.g., "/login" -> "LoginPage", "/dashboard" -> "DashboardPage"
            if step.target.startswith("/"):
                path = step.target.rstrip("/").lstrip("/")
                if path:
                    # Convert path to PascalCase
                    parts = path.split("/")
                    page_name = "".join(p.capitalize() for p in parts)
                    return f"{page_name}Page"

        # Extract page from target selectors
        if step.target:
            # Look for data-testid or data-page attributes
            if "data-page=" in step.target:
                import re
                match = re.search(r'data-page="([^"]+)"', step.target)
                if match:
                    page = match.group(1)
                    return f"{page.capitalize()}Page"

            # Infer page from common patterns
            for pattern in ["login", "dashboard", "settings", "profile", "home", "admin"]:
                if pattern in step.target.lower():
                    return f"{pattern.capitalize()}Page"

        return None

    def _generate_page_objects_code(self, pages: Dict[str, List[JourneyStep]]) -> str:
        """
        Generate TypeScript Page Object Model code

        Args:
            pages: Dictionary mapping page names to their steps

        Returns:
            Complete page-objects.ts file content
        """
        # Generate base page class
        base_class = self._generate_base_page_class()

        # Generate page classes
        page_classes = []
        for page_name, steps in sorted(pages.items()):
            page_class = self._generate_page_class(page_name, steps)
            page_classes.append(page_class)

        # Combine all parts
        code = f"""import {{ Page }} from '@playwright/test';

/**
 * Page Object Model for UAT Gateway
 *
 * This file contains Page Object classes that encapsulate:
 * - Page selectors (CSS locators, data-testid attributes)
 * - Interaction methods (click, fill, select, etc.)
 * - Page navigation methods
 * - Methods return Page objects for fluent chaining
 */

// ============================================================================
// Base Page Class
// ============================================================================

{base_class}

// ============================================================================
// Page Object Classes
// ============================================================================

{chr(10).join(page_classes)}
"""
        return code

    def _generate_base_page_class(self) -> str:
        """
        Generate base page class with common functionality

        Returns:
            BasePage class code
        """
        return """/**
 * Base Page class with common functionality
 * All page objects should extend this class
 */
export class BasePage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  /**
   * Navigate to a URL
   */
  async navigate(url: string): Promise<this> {
    await this.page.goto(url);
    return this;
  }

  /**
   * Wait for page to be loaded
   */
  async waitForLoadState(): Promise<this> {
    await this.page.waitForLoadState('networkidle');
    return this;
  }

  /**
   * Wait for element to be visible
   */
  async waitForVisible(selector: string): Promise<this> {
    await this.page.waitForSelector(selector, { state: 'visible' });
    return this;
  }

  /**
   * Check if element is visible
   */
  async isVisible(selector: string): Promise<boolean> {
    return await this.page.locator(selector).isVisible();
  }

  /**
   * Get page title
   */
  async getTitle(): Promise<string> {
    return await this.page.title();
  }

  /**
   * Get current URL
   */
  async getUrl(): Promise<string> {
    return this.page.url();
  }

  /**
   * Reload the page
   */
  async reload(): Promise<this> {
    await this.page.reload();
    return this;
  }

  /**
   * Go back in browser history
   */
  async goBack(): Promise<this> {
    await this.page.goBack();
    return this;
  }

  /**
   * Go forward in browser history
   */
  async goForward(): Promise<this> {
    await this.page.goForward();
    return this;
  }
}
"""

    def _generate_page_class(self, page_name: str, steps: List[JourneyStep]) -> str:
        """
        Generate a single page object class

        Args:
            page_name: Name of the page class
            steps: List of steps that interact with this page

        Returns:
            Page class code
        """
        # Extract selectors from steps
        selectors = self._extract_selectors_from_steps(steps)

        # Generate selector fields
        selector_fields = []
        for selector_name, selector_value in sorted(selectors.items()):
            comment = self._generate_selector_comment(selector_value)
            selector_fields.append(f"  /** {comment} */")
            selector_fields.append(f"  readonly {selector_name} = '{selector_value}';")

        # Generate interaction methods
        methods = []
        for step in steps:
            method = self._generate_interaction_method(step)
            if method:
                methods.append(method)

        # Combine into class
        if selector_fields:
            selectors_section = "\n".join(selector_fields)
        else:
            selectors_section = "  // No selectors defined"

        if methods:
            methods_section = "\n".join(methods)
        else:
            methods_section = "  // No interaction methods"

        return f"""/**
 * {page_name} Object
 *
 * Encapsulates interactions with the {page_name.replace('Page', '')} page
 */
export class {page_name} extends BasePage {{
  readonly url = '';

{selectors_section}

{methods_section}
}}
"""

    def _extract_selectors_from_steps(self, steps: List[JourneyStep]) -> Dict[str, str]:
        """
        Extract unique selectors from steps

        Args:
            steps: List of JourneyStep objects

        Returns:
            Dictionary mapping selector names to selector values
        """
        selectors = {}

        for step in steps:
            if step.target:
                # Generate a selector name from the target
                selector_name = self._generate_selector_name(step.target)

                # Clean up the selector value
                selector_value = step.target.strip()

                # Only add if not duplicate
                if selector_name not in selectors:
                    selectors[selector_name] = selector_value

        return selectors

    def _generate_selector_name(self, target: str) -> str:
        """
        Generate a camelCase selector name from target

        Args:
            target: CSS selector or locator

        Returns:
            Selector name in camelCase (valid TypeScript identifier)
        """
        # Remove special characters and convert to camelCase
        import re

        # Extract meaningful part from selector
        # Handle both single and double quotes
        if "data-testid=" in target:
            match = re.search(r'data-testid=[\'"]([^\'"]+)[\'"]', target)
            if match:
                test_id = match.group(1)
                # Convert to camelCase
                parts = test_id.split("-")
                return parts[0] + "".join(p.capitalize() for p in parts[1:])

        if "data-page=" in target:
            match = re.search(r'data-page=[\'"]([^\'"]+)[\'"]', target)
            if match:
                page = match.group(1)
                return f"{page}Selector"

        # For ID selectors
        if target.startswith("#"):
            name = target[1:].replace("-", "_").replace("_", " ")
            return self._to_camel_case(name)

        # For class selectors
        if target.startswith("."):
            name = target[1:].replace("-", "_").replace("_", " ")
            return f"{self._to_camel_case(name)}Selector"

        # For attribute selectors (handle both quote types)
        if "[" in target:
            match = re.search(r'\[([a-z-]+)=[\'"]([^\'"]+)[\'"]\]', target)
            if match:
                attr = match.group(1)
                value = match.group(2)
                return f"{attr}_{self._to_camel_case(value)}"

        # For URL patterns (starting with /)
        if target.startswith("/"):
            # Extract path name
            path = target.rstrip("/").lstrip("/")
            if path:
                # Convert to camelCase with "url" prefix
                parts = path.split("/")
                name = "".join(p.capitalize() for p in parts)
                return f"url{name}"
            return "urlSelector"

        # Default: use target as-is, sanitized
        # Remove all special characters that aren't valid in TypeScript identifiers
        name = target.replace("[", "").replace("]", "").replace('"', "").replace("'", "").replace("=", "_")
        name = name.replace("/", "_").replace(":", "_").replace(".", "_")
        name = name.replace("-", " ").replace("_", " ")

        # Convert to camelCase
        camel = self._to_camel_case(name)

        # Ensure we always return a valid identifier
        if not camel or not camel[0].isalpha():
            return "selector"

        return camel

    def _to_camel_case(self, text: str) -> str:
        """
        Convert text to camelCase

        Args:
            text: Input text

        Returns:
            camelCase string
        """
        # Remove special characters
        text = text.replace("-", " ").replace("_", " ").replace(".", " ")

        # Split into words
        words = text.split()

        if not words:
            return "selector"

        # First word lowercase, rest capitalized
        first = words[0].lower()
        rest = "".join(w.capitalize() for w in words[1:])

        return first + rest

    def _generate_selector_comment(self, selector: str) -> str:
        """
        Generate a helpful comment for a selector

        Args:
            selector: CSS selector

        Returns:
            Comment string
        """
        import re

        if selector.startswith("#"):
            return f"Element with ID: {selector}"
        elif selector.startswith("."):
            return f"Element with class: {selector}"
        elif "data-testid=" in selector:
            # Handle both single and double quotes
            match = re.search(r'data-testid=[\'"]([^\'"]+)[\'"]', selector)
            if match:
                test_id = match.group(1)
                return f"Element with test ID: {test_id}"
            return f"Element with test ID: {selector}"
        elif "data-page=" in selector:
            return f"Page indicator: {selector}"
        elif selector.startswith("/"):
            return f"URL path: {selector}"
        else:
            return f"Selector: {selector}"

    def _generate_interaction_method(self, step: JourneyStep) -> Optional[str]:
        """
        Generate an interaction method for a step

        Args:
            step: JourneyStep object

        Returns:
            Method code or None
        """
        if not step.target:
            return None

        action_type = step.action_type.lower()
        method_name = self._generate_method_name(action_type, step.target, step.description)

        if action_type == "click":
            return f"""
  /**
   * Click on {step.description or step.target}
   */
  async {method_name}(): Promise<this> {{
    await this.page.click('{step.target}');
    return this;
  }}"""

        elif action_type in ["type", "fill"]:
            return f"""
  /**
   * Fill in {step.description or step.target}
   */
  async {method_name}(value: string): Promise<this> {{
    await this.page.fill('{step.target}', value);
    return this;
  }}"""

        elif action_type == "select":
            return f"""
  /**
   * Select option from {step.description or step.target}
   */
  async {method_name}(value: string): Promise<this> {{
    await this.page.selectOption('{step.target}', value);
    return this;
  }}"""

        elif action_type in ["check", "assert", "expect"]:
            return f"""
  /**
   * Verify {step.description or step.target} is visible
   */
  async {method_name}(): Promise<this> {{
    await this.page.waitForSelector('{step.target}', {{ state: 'visible' }});
    return this;
  }}"""

        elif action_type == "wait":
            return f"""
  /**
   * Wait for {step.description or 'condition'}
   */
  async {method_name}(): Promise<this> {{
    await this.page.waitForLoadState('networkidle');
    return this;
  }}"""

        elif action_type == "navigate":
            url = step.target or "/"
            return f"""
  /**
   * Navigate to {step.description or url}
   */
  async {method_name}(): Promise<this> {{
    await this.page.goto('{url}');
    return this;
  }}"""

        return None

    def _generate_method_name(self, action_type: str, target: str, description: Optional[str]) -> str:
        """
        Generate a method name from action and target

        Args:
            action_type: Type of action (click, fill, etc.)
            target: Target selector
            description: Optional description

        Returns:
            Method name in camelCase
        """
        import re

        # Use description if available
        if description:
            # Extract action from description
            words = description.lower().split()

            # Skip common words at start
            skip_words = ["the", "a", "an", "on", "in", "at", "to", "for", "with", "verify", "check"]
            while words and words[0] in skip_words:
                words.pop(0)

            # Also skip action words to avoid duplicates like "navigateNavigate"
            action_skip_words = ["navigate", "click", "fill", "type", "select", "wait", "verify", "check"]
            while words and words[0] in action_skip_words:
                words.pop(0)

            if words:
                # Build method name
                action = action_type
                if action_type == "click":
                    action = "click"
                elif action_type in ["type", "fill"]:
                    action = "fill"
                elif action_type == "select":
                    action = "select"
                elif action_type in ["check", "assert", "expect"]:
                    action = "verify"
                elif action_type == "wait":
                    action = "waitFor"
                elif action_type == "navigate":
                    action = "goto"

                # Combine action with target
                target_part = "".join(w.capitalize() for w in words)
                return f"{action}{target_part}"

        # Fallback: generate from target
        selector_name = self._generate_selector_name(target)

        if action_type == "click":
            return f"click{selector_name.capitalize()}"
        elif action_type in ["type", "fill"]:
            return f"fill{selector_name.capitalize()}"
        elif action_type == "select":
            return f"select{selector_name.capitalize()}"
        elif action_type in ["check", "assert", "expect"]:
            return f"verify{selector_name.capitalize()}"
        elif action_type == "wait":
            return f"waitFor{selector_name.capitalize()}"
        elif action_type == "navigate":
            return f"goto{selector_name.capitalize()}"
        else:
            return f"{action_type}{selector_name.capitalize()}"

    @handle_errors(component="test_generator", reraise=True)
    def generate_fixtures(self, output_path: Optional[str] = None) -> str:
        """
        Generate reusable test fixtures file

        Fixtures provide common setup/teardown for tests:
        - Browser configuration
        - Authenticated state
        - Page context setup
        - Test data helpers

        Args:
            output_path: Optional custom output path. Defaults to output_directory/fixtures.ts

        Returns:
            Path to generated fixtures file

        Raises:
            TestGenerationError: If fixture generation fails
        """
        if output_path is None:
            output_path = os.path.join(self.config.output_directory, "fixtures.ts")

        # Generate fixtures code
        fixtures_code = self._generate_fixtures_code()

        # Format with Prettier if enabled
        fixtures_code = self._format_code_with_prettier(fixtures_code, output_path)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write fixtures file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(fixtures_code)

        self.logger.info(f"Generated fixtures file: {output_path}")
        return output_path

    def _generate_fixtures_code(self) -> str:
        """
        Generate TypeScript fixtures code

        Returns:
            Complete fixtures.ts file content
        """
        return """import { test as base } from '@playwright/test';

/**
 * Test Fixtures for UAT Gateway
 *
 * Provides reusable setup/teardown for common test scenarios
 */

// ============================================================================
// Authenticated State Fixture
// ============================================================================

export const test = base.extend<{
  authenticatedPage: typeof base.prototype['page'];
  testUser: {
    email: string;
    password: string;
    name: string;
  };
}>({
  // Setup: Create authenticated page
  authenticatedPage: async ({ page }, use) => {
    // Setup: Navigate to login page
    await page.goto('/login');

    // Setup: Fill in credentials
    await page.fill('#email', 'test@example.com');
    await page.fill('#password', 'TestPassword123!');

    // Setup: Submit login form
    await page.click('button[type="submit"]');

    // Setup: Wait for navigation to complete
    await page.waitForURL('**/dashboard');

    // Setup: Verify authentication was successful
    await page.waitForSelector('.user-menu', { state: 'visible' });

    // Use authenticated page in test
    await use(page);

    // Teardown: Logout after test
    await page.click('.user-menu');
    await page.click('button:has-text("Logout")');
    await page.waitForURL('**/login');
  },

  // Setup: Provide test user data
  testUser: async ({}, use) => {
    const user = {
      email: 'test@example.com',
      password: 'TestPassword123!',
      name: 'Test User'
    };
    await use(user);
  }
});

// ============================================================================
// Browser Context Fixture
// ============================================================================

export const testWithViewport = base.extend<{
  page: typeof base.prototype['page'];
}>({
  // Setup: Configure viewport
  page: async ({ page }, use) => {
    // Set common viewport size
    await page.setViewportSize({ width: 1280, height: 720 });

    // Use page in test
    await use(page);
  }
});

// ============================================================================
// Test Data Helpers Fixture
// ============================================================================

export const testWithData = base.extend<{
  testData: {
    generateEmail: () => string;
    generatePassword: () => string;
    generateUsername: () => string;
  };
}>({
  // Setup: Provide test data generators
  testData: async ({}, use) => {
    const data = {
      generateEmail: () => `test_${Date.now()}@example.com`,
      generatePassword: () => `Test${Date.now()}!`,
      generateUsername: () => `user_${Date.now()}`
    };
    await use(data);
  }
});

// ============================================================================
// Page Setup Fixture
// ============================================================================

export const testWithPageSetup = base.extend<{
  setupPage: typeof base.prototype['page'];
}>({
  // Setup: Configure page with common settings
  setupPage: async ({ page }, use) => {
    // Setup: Configure timeout
    page.setDefaultTimeout(30000);

    // Setup: Configure navigation timeout
    page.setDefaultNavigationTimeout(30000);

    // Use page in test
    await use(page);

    // Teardown: Clear all cookies and storage
    await page.context().clearCookies();
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  }
});

// ============================================================================
// API Response Mocking Fixture
// ============================================================================

export const testWithMocks = base.extend<{
  mockApiResponse: (endpoint: string, response: any) => Promise<void>;
}>({
  // Setup: Provide API mocking helper
  mockApiResponse: async ({ page }, use) => {
    const mock = async (endpoint: string, response: any) => {
      await page.route(endpoint, (route) => {
        route.fulfill({
          status: 200,
          body: JSON.stringify(response),
          headers: {
            'Content-Type': 'application/json'
          }
        });
      });
    };
    await use(mock);
  }
});

// ============================================================================
// Re-exports
// ============================================================================

export const expect = test.expect;
"""

    @handle_errors(component="test_generator", reraise=True)
    def _generate_scenario_test(self, journey: Journey, scenario: Scenario) -> GeneratedTest:
        """
        Generate a test file for a specific scenario

        Args:
            journey: The Journey object
            scenario: The Scenario object

        Returns:
            GeneratedTest object
        """
        # Generate test file name
        test_name = self._sanitize_filename(f"{journey.name}_{scenario.name}")
        output_path = os.path.join(
            self.config.output_directory,
            f"{test_name}.spec.ts"
        )

        # Generate TypeScript test code
        test_code = self._generate_typescript_test(journey, scenario)

        # Format with Prettier if enabled
        test_code = self._format_code_with_prettier(test_code, output_path)

        generated_test = GeneratedTest(
            test_name=test_name,
            test_code=test_code,
            test_type=scenario.scenario_type.value,
            framework=self.config.output_format,
            output_path=output_path
        )

        self.logger.debug(f"Generated test: {output_path}")
        return generated_test

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string for use as a filename

        Args:
            name: The string to sanitize

        Returns:
            Sanitized filename-safe string
        """
        # Replace spaces and special characters with underscores
        sanitized = name.lower().replace(" ", "_").replace("-", "_")
        # Remove any non-alphanumeric characters except underscores
        sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")
        # Remove consecutive underscores
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        return sanitized

    def _generate_hook_code(self, steps: List[JourneyStep]) -> str:
        """
        Generate code for beforeAll or afterAll hooks

        Args:
            steps: List of JourneyStep objects for setup/cleanup

        Returns:
            Hook code as string
        """
        hook_lines = []
        for step in steps:
            step_code = self._generate_step_code(step)
            if step_code:
                # Step code may contain newlines (comment + action), indent each line
                for code_line in step_code.split('\n'):
                    hook_lines.append(f"    {code_line}")
        return "\n".join(hook_lines)

    def _generate_typescript_test(self, journey: Journey, scenario: Scenario) -> str:
        """
        Generate TypeScript test code using Playwright

        Args:
            journey: The Journey object
            scenario: The Scenario object

        Returns:
            TypeScript test code as string
        """
        # Generate imports
        imports = self._generate_imports()

        # Generate test description
        test_description = f"{scenario.name}: {scenario.description}"

        # Generate test body from steps
        test_body = self._generate_test_body(journey, scenario)

        # Generate beforeAll hook if setup_steps exist
        beforeall_hook = ""
        if hasattr(scenario, 'setup_steps') and scenario.setup_steps:
            setup_code = self._generate_hook_code(scenario.setup_steps)
            beforeall_hook = f"""
  test.beforeAll(async ({{ page }}) => {{
{setup_code}
  }});
"""

        # Generate afterAll hook if cleanup_steps exist
        afterall_hook = ""
        if hasattr(scenario, 'cleanup_steps') and scenario.cleanup_steps:
            cleanup_code = self._generate_hook_code(scenario.cleanup_steps)
            afterall_hook = f"""
  test.afterAll(async ({{ page }}) => {{
{cleanup_code}
  }});
"""

        # Combine into complete test file
        test_code = f"""{imports}
import {{ test, expect }} from '@playwright/test';

// Test generated from journey: {journey.name}
// Journey ID: {journey.journey_id}
// Scenario: {scenario.name}
// Scenario ID: {scenario.scenario_id}
// Type: {scenario.scenario_type.value}
{"" if scenario.scenario_type == ScenarioType.HAPPY_PATH else f"// Error Type: {scenario.error_type}"}

test.describe('{journey.name}', () => {{
{beforeall_hook}  test('{test_description}', async ({{ page }}) => {{
{test_body}
  }});
{afterall_hook}}});
"""
        return test_code

    def _format_code_with_prettier(self, code: str, file_path: str) -> str:
        """
        Format generated code using Prettier

        Args:
            code: The code to format
            file_path: The file path (used to determine parser)

        Returns:
            Formatted code, or original code if formatting fails
        """
        if not self.config.format_with_prettier:
            self.logger.debug("Prettier formatting disabled, skipping")
            return code

        try:
            import subprocess
            import tempfile

            # Determine parser from file extension
            parser_map = {
                '.ts': 'typescript',
                '.tsx': 'typescript',
                '.js': 'babel',
                '.jsx': 'babel',
                '.json': 'json',
            }
            ext = os.path.splitext(file_path)[1]
            parser = parser_map.get(ext, 'typescript')

            # Create temporary file for Prettier to read
            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as tmp:
                tmp.write(code)
                tmp_path = tmp.name

            try:
                # Run Prettier via npx
                result = subprocess.run(
                    ['npx', 'prettier', '--parser', parser, tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0:
                    formatted_code = result.stdout
                    self.logger.debug(f"Code formatted with Prettier (parser: {parser})")
                    return formatted_code
                else:
                    self.logger.warning(f"Prettier formatting failed: {result.stderr}")
                    return code

            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        except FileNotFoundError:
            self.logger.warning("Prettier not found (npx not available), skipping formatting")
            return code
        except subprocess.TimeoutExpired:
            self.logger.warning("Prettier formatting timed out, using original code")
            return code
        except Exception as e:
            self.logger.warning(f"Prettier formatting error: {str(e)}, using original code")
            return code

    def _generate_imports(self) -> str:
        """
        Generate import statements for the test file

        Returns:
            Import statements as string
        """
        return """import { test } from '@playwright/test';"""

    def _generate_test_body(self, journey: Journey, scenario: Scenario) -> str:
        """
        Generate test body code from scenario steps

        Args:
            journey: The Journey object
            scenario: The Scenario object

        Returns:
            Test body code as string
        """
        lines = []

        for step in scenario.steps:
            step_code = self._generate_step_code(step)
            if step_code:
                # Step code may contain newlines (comment + action), indent each line
                for code_line in step_code.split('\n'):
                    lines.append(f"    {code_line}")

        return "\n".join(lines)


    def _generate_unique_test_data(self, step: JourneyStep, selector: Optional[str] = None) -> str:
        """
        Generate unique test data value for a step

        This ensures:
        1. Data is unique (includes timestamp and counter)
        2. Data is deterministic (same journey generates same values)
        3. Data is identifiable (has TEST_ prefix)
        4. Data prevents collisions (includes selector-based hash)

        Args:
            step: The JourneyStep object
            selector: Optional selector to make data more specific

        Returns:
            Unique test data string (e.g., "TEST_user_1737883200_abc123")
        """
        # Increment counter for uniqueness
        self._test_data_counter += 1

        # Generate deterministic timestamp based on journey_id and counter
        # Using current timestamp but making it deterministic via hash
        journey_seed = step.step_id if step.step_id else "unknown"
        base_timestamp = int(datetime.now().timestamp())

        # Create a deterministic hash from journey_seed + counter
        hash_input = f"{journey_seed}_{self._test_data_counter}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:6]

        # Extract field name from selector for better readability
        field_name = self._extract_field_name(selector)

        # Format: TEST_field_timestamp_hash
        # Example: TEST_email_1737883200_abc123
        if field_name:
            return f"TEST_{field_name}_{base_timestamp}_{hash_value}"
        else:
            return f"TEST_{base_timestamp}_{hash_value}"

    def _extract_field_name(self, selector: Optional[str]) -> str:
        """
        Extract a readable field name from a CSS selector

        Examples:
            #username -> "username"
            #email -> "email"
            [name='password'] -> "password"
            [data-testid='title-input'] -> "title"

        Args:
            selector: CSS selector string

        Returns:
            Extracted field name or empty string
        """
        if not selector:
            return ""

        import re

        # Try ID selector (#username)
        id_match = re.search(r'#([\w-]+)', selector)
        if id_match:
            field = id_match.group(1)
            # Remove common suffixes
            for suffix in ['-input', '-field', '-box']:
                if field.endswith(suffix):
                    field = field[:-len(suffix)]
            return field

        # Try name attribute ([name='password'])
        name_match = re.search(r"name=['\"]([^'\"]+)['\"]", selector)
        if name_match:
            return name_match.group(1)

        # Try data-testid ([data-testid='title-input'])
        testid_match = re.search(r"data-testid=['\"]([^'\"]+)['\"]", selector)
        if testid_match:
            field = testid_match.group(1)
            # Remove common suffixes
            for suffix in ['-input', '-field', '-box']:
                if field.endswith(suffix):
                    field = field[:-len(suffix)]
            return field

        # Try class selector (.email-input)
        class_match = re.search(r'\.([\w-]+)', selector)
        if class_match:
            field = class_match.group(1)
            # Remove common suffixes and prefixes
            for suffix in ['-input', '-field', '-box']:
                if field.endswith(suffix):
                    field = field[:-len(suffix)]
            for prefix in ['input-', 'field-']:
                if field.startswith(prefix):
                    field = field[len(prefix):]
            return field

        return ""

    def _generate_step_comment(self, step: JourneyStep) -> str:
        """
        Generate a descriptive comment for a step

        Args:
            step: The JourneyStep object

        Returns:
            Comment string (e.g., "// Navigate to login page")
        """
        # If step has a description, use it
        if step.description:
            # Capitalize first letter
            desc = step.description.strip()
            if desc:
                return f"// {desc[0].upper() + desc[1:] if len(desc) > 1 else desc.upper()}"

        # Fallback: Generate comment based on action type
        action_type = step.action_type.lower()
        fallback_comments = {
            "navigate": "Navigate to page",
            "click": "Click element",
            "type": "Type text",
            "fill": "Fill input field",
            "wait": "Wait for condition",
            "assert": "Verify assertion",
            "expect": "Verify expectation",
            "check": "Check element visibility",
        }

        comment = fallback_comments.get(action_type, f"Perform {action_type}")
        return f"// {comment}"

    def _generate_step_code(self, step: JourneyStep) -> Optional[str]:
        """
        Generate TypeScript code for a single step with descriptive comment

        Args:
            step: The JourneyStep object

        Returns:
            TypeScript code line with comment or None
        """
        action_type = step.action_type.lower()

        # Generate comment for this step
        comment = self._generate_step_comment(step)

        if action_type == "navigate":
            if step.target:
                return f"{comment}\nawait page.goto('{step.target}');"
            return f"{comment}\nawait page.goto('{self.config.base_url}');"

        elif action_type == "click":
            if step.target:
                return f"{comment}\nawait page.click('{step.target}');"
            return f"{comment}\n// TODO: Add click target"

        elif action_type == "type" or action_type == "fill":
            if step.target:
                # Generate unique test data to avoid collisions
                # If description has explicit value, use it; otherwise generate unique data
                if step.description and "=" in step.description:
                    # Extract explicit value from description
                    explicit_value = step.description.split("=")[1].strip().strip("'\"")
                    # Use explicit value but wrap in quotes if not already
                    if explicit_value.startswith("'") or explicit_value.startswith('"'):
                        value = explicit_value
                    else:
                        value = f"'{explicit_value}'"
                else:
                    # Generate unique test data with TEST_ prefix, timestamp, and hash
                    unique_data = self._generate_unique_test_data(step, step.target)
                    value = f"'{unique_data}'"
                return f"{comment}\nawait page.fill('{step.target}', {value});"
            return f"{comment}\n// TODO: Add fill target and value"

        elif action_type == "wait":
            if step.target and step.target.isdigit():
                return f"{comment}\nawait page.waitForTimeout({step.target});"
            return f"{comment}\nawait page.waitForLoadState('networkidle');"

        elif action_type == "assert" or action_type == "expect":
            # Check if this is an API assertion
            if step.expected_result and step.expected_result.startswith(("status_code=", "response_body.", "response_contains_")):
                return api_test_generator.generate_api_assertion_code(step, comment)
            elif step.target:
                return f"{comment}\nawait expect(page.locator('{step.target}')).toBeVisible();"
            return f"{comment}\n// TODO: Add assertion target"

        elif action_type == "check":
            if step.target:
                return f"{comment}\nawait expect(page.locator('{step.target}')).toBeVisible();"
            return f"{comment}\n// TODO: Add check target"

        elif action_type == "upload":
            # Generate file upload code using Playwright's setInputFiles()
            if step.target:
                # Use test fixtures path for file upload
                # This assumes test files are stored in a fixtures directory
                test_file_path = "./fixtures/test-file.txt"
                return f"await page.waitForSelector('{step.target}', {{ state: 'visible' }});\nawait page.setInputFiles('{step.target}', '{test_file_path}');"
            return "// TODO: Add upload target"

        elif action_type == "api_call":
            # Generate API test code using Playwright's APIRequestContext
            return api_test_generator.generate_api_call_code(step, "// Make API request", self.config.base_url)

        else:
            # Unknown action type - add as comment
            return f"// TODO: Implement {step.action_type} - {step.description}"

    def __str__(self) -> str:
        stats = self.get_statistics()
        return (
            f"TestGenerator("
            f"{stats['total_journeys']} journeys, "
            f"{stats['total_scenarios']} scenarios, "
            f"{stats['total_steps']} steps)"
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def create_test_generator(
    journeys: List[Journey],
    config: Optional[TestConfig] = None
) -> TestGenerator:
    """
    Create a TestGenerator and load journeys

    Args:
        journeys: List of Journey objects from JourneyExtractor
        config: Optional test generation configuration

    Returns:
        Configured TestGenerator with loaded journeys
    """
    generator = TestGenerator(config)
    generator.load_journeys(journeys)
    return generator


# Export main classes and functions
__all__ = [
    "TestGenerator",
    "TestConfig",
    "GeneratedTest",
    "create_test_generator",
]
