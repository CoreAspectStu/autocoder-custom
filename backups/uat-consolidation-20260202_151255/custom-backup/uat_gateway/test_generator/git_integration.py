"""
Git Integration for Test Generator

This module provides git commit functionality for generated test files.
"""

import os
import subprocess
from typing import List, Optional
from pathlib import Path
import sys

# Add src directory to path for imports

from test_generator.test_generator import TestGenerator
from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestGenerationError, handle_errors


class GitIntegration:
    """
    Handles git operations for generated test files

    This class extends TestGenerator with git commit capabilities:
    - Writing test files to disk
    - Staging files in git
    - Creating commits with descriptive messages
    """

    def __init__(self, test_generator: TestGenerator):
        """
        Initialize git integration with a test generator instance

        Args:
            test_generator: The TestGenerator instance to use
        """
        self.generator = test_generator
        self.logger = get_logger("git_integration")

    @handle_errors(component="git_integration", reraise=True)
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
        # Generate test objects
        generated_tests = self.generator.generate_tests(journey_id)

        # Ensure output directory exists
        os.makedirs(self.generator.config.output_directory, exist_ok=True)

        written_paths = []

        # Write each test file
        for generated_test in generated_tests:
            try:
                # Format code with Prettier if enabled
                test_code = self.generator._format_code_with_prettier(
                    generated_test.test_code,
                    generated_test.output_path
                )

                # Write test file
                with open(generated_test.output_path, 'w', encoding='utf-8') as f:
                    f.write(test_code)

                written_paths.append(generated_test.output_path)
                self.logger.debug(f"Wrote test file: {generated_test.output_path}")

            except Exception as e:
                self.logger.error(f"Failed to write test file {generated_test.output_path}: {str(e)}")
                raise TestGenerationError(
                    f"Failed to write test file: {generated_test.output_path}",
                    component="git_integration",
                    context={"error": str(e), "output_path": generated_test.output_path}
                )

        self.logger.info(f"Wrote {len(written_paths)} test files to disk")
        return written_paths

    @handle_errors(component="git_integration", reraise=True)
    def commit_tests(
        self,
        journey_id: Optional[str] = None,
        message_suffix: Optional[str] = None
    ) -> str:
        """
        Write and commit generated test files to git

        This method:
        1. Generates test files for the specified journey (or all journeys)
        2. Writes test files to disk
        3. Stages files in git
        4. Creates a commit with a descriptive message

        Args:
            journey_id: Optional specific journey ID. If None, commits tests for all journeys.
            message_suffix: Optional suffix to add to commit message

        Returns:
            The commit message that was created

        Raises:
            TestGenerationError: If git operations fail
        """
        # Determine which journeys to process
        journeys_to_process = []
        if journey_id:
            journey = self.generator.get_journey(journey_id)
            if not journey:
                raise TestGenerationError(
                    f"Journey not found: {journey_id}",
                    component="git_integration",
                    context={"journey_id": journey_id}
                )
            journeys_to_process = [journey]
        else:
            journeys_to_process = self.generator._loaded_journeys

        if not journeys_to_process:
            raise TestGenerationError(
                "No journeys to commit",
                component="git_integration",
                context={"journey_id": journey_id}
            )

        # Collect all generated files
        all_generated_paths = []
        for journey in journeys_to_process:
            # Write tests for this journey
            written_paths = self.write_tests(journey.journey_id)
            all_generated_paths.extend(written_paths)

        if not all_generated_paths:
            self.logger.warning("No test files were generated, skipping git commit")
            return ""

        # Stage files in git
        try:
            self.logger.info(f"Staging {len(all_generated_paths)} files in git")

            # Add all generated files to git
            for file_path in all_generated_paths:
                result = subprocess.run(
                    ['git', 'add', '-f', file_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    raise TestGenerationError(
                        f"Failed to stage file in git: {file_path}",
                        component="git_integration",
                        context={"error": result.stderr, "file_path": file_path}
                    )

                self.logger.debug(f"Staged: {file_path}")

        except subprocess.TimeoutExpired:
            raise TestGenerationError(
                "Git add timed out",
                component="git_integration"
            )
        except FileNotFoundError:
            raise TestGenerationError(
                "Git not found. Please ensure git is installed and accessible.",
                component="git_integration"
            )
        except Exception as e:
            raise TestGenerationError(
                f"Failed to stage files in git: {str(e)}",
                component="git_integration",
                context={"error": str(e)}
            )

        # Create commit message
        journey_names = ", ".join([j.name for j in journeys_to_process])
        base_message = f"Generate tests for journey: {journey_names}"

        if message_suffix:
            commit_message = f"{base_message}\n\n{message_suffix}"
        else:
            commit_message = base_message

        # Add file list to commit message body
        file_list = "\n".join([f"  - {os.path.relpath(p)}" for p in all_generated_paths])
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
                    self.logger.warning("No changes to commit")
                    return commit_message

                raise TestGenerationError(
                    f"Failed to create git commit: {result.stderr}",
                    component="git_integration",
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

            self.logger.info(f"Created git commit {commit_hash} for {len(all_generated_paths)} test files")

            return commit_message

        except subprocess.TimeoutExpired:
            raise TestGenerationError(
                "Git commit timed out",
                component="git_integration"
            )
        except Exception as e:
            raise TestGenerationError(
                f"Failed to create git commit: {str(e)}",
                component="git_integration",
                context={"error": str(e)}
            )


# Monkey-patch TestGenerator to add git methods
def _add_git_methods_to_generator():
    """Add git commit methods to TestGenerator class"""
    def write_tests(self, journey_id: Optional[str] = None) -> List[str]:
        """Write generated test files to disk"""
        git_integration = GitIntegration(self)
        return git_integration.write_tests(journey_id)

    def commit_tests(self, journey_id: Optional[str] = None, message_suffix: Optional[str] = None) -> str:
        """Write and commit generated test files to git"""
        git_integration = GitIntegration(self)
        return git_integration.commit_tests(journey_id, message_suffix)

    # Add methods to TestGenerator
    TestGenerator.write_tests = write_tests
    TestGenerator.commit_tests = commit_tests


# Auto-patch on import
_add_git_methods_to_generator()
