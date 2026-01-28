"""
Main entry point for UAT Gateway Orchestrator

This script runs the complete UAT testing cycle from spec to Kanban update.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import argparse
import json
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.orchestrator.orchestrator import Orchestrator, OrchestratorConfig, OrchestratorResult
from custom.uat_gateway.utils.logger import get_logger


def load_config_from_env() -> dict:
    """Load configuration from environment variables"""
    config = {
        "spec_path": os.getenv("UAT_SPEC_PATH", "spec.yaml"),
        "test_directory": os.getenv("UAT_TEST_DIR", "tests/e2e"),
        "output_directory": os.getenv("UAT_OUTPUT_DIR", "output"),
        "state_directory": os.getenv("UAT_STATE_DIR", "state"),
        "base_url": os.getenv("UAT_BASE_URL", "http://localhost:3000"),
        "kanban_api_url": os.getenv("KANBAN_API_URL"),
        "kanban_api_token": os.getenv("KANBAN_API_TOKEN"),
        "parallel_execution": os.getenv("UAT_PARALLEL", "true").lower() == "true",
        "max_parallel_tests": int(os.getenv("UAT_MAX_PARALLEL", "3")),
        "retry_flaky_tests": os.getenv("UAT_RETRY", "true").lower() == "true",
        "max_retries": int(os.getenv("UAT_MAX_RETRIES", "2")),
        "enable_checkpoints": os.getenv("UAT_CHECKPOINTS", "true").lower() == "true",
        "checkpoint_interval_seconds": int(os.getenv("UAT_CHECKPOINT_INTERVAL", "60")),
    }
    return config


def load_config_from_file(config_path: str) -> dict:
    """Load configuration from YAML file"""
    try:
        import yaml
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
            return config_data or {}
    except Exception as e:
        print(f"Warning: Failed to load config file {config_path}: {e}")
        return {}


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="UAT Gateway - Run complete UAT testing cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings
  python main.py

  # Run with custom spec file
  python main.py --spec my_spec.yaml

  # Run with custom base URL
  python main.py --base-url http://localhost:4000

  # Run with verbose logging
  python main.py --verbose

  # Run without Kanban integration
  python main.py --no-kanban

  # Dry run (don't execute tests)
  python main.py --dry-run
        """
    )

    parser.add_argument(
        "--spec", "-s",
        default="spec.yaml",
        help="Path to spec.yaml file (default: spec.yaml)"
    )

    parser.add_argument(
        "--test-dir", "-t",
        default="tests/e2e",
        help="Test output directory (default: tests/e2e)"
    )

    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        help="Output directory for test artifacts (default: output)"
    )

    parser.add_argument(
        "--state-dir",
        default="state",
        help="State directory (default: state)"
    )

    parser.add_argument(
        "--base-url", "-u",
        default="http://localhost:3000",
        help="Base URL for testing (default: http://localhost:3000)"
    )

    parser.add_argument(
        "--kanban-url",
        help="Kanban API URL (overrides KANBAN_API_URL env var)"
    )

    parser.add_argument(
        "--kanban-token",
        help="Kanban API token (overrides KANBAN_API_TOKEN env var)"
    )

    parser.add_argument(
        "--no-kanban",
        action="store_true",
        help="Disable Kanban integration"
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        default=True,
        help="Enable parallel test execution (default: enabled)"
    )

    parser.add_argument(
        "--no-parallel",
        action="store_false",
        dest="parallel",
        help="Disable parallel test execution"
    )

    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=3,
        help="Maximum parallel test workers (default: 3)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Enable quiet mode (errors only)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate spec and extract journeys without running tests"
    )

    parser.add_argument(
        "--config", "-c",
        default="config/uat_config.yaml",
        help="Path to configuration file (default: config/uat_config.yaml)"
    )

    parser.add_argument(
        "--save-result",
        action="store_true",
        help="Save result to JSON file"
    )

    parser.add_argument(
        "--result-file",
        default="output/orchestrator_result.json",
        help="Path to save result JSON (default: output/orchestrator_result.json)"
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    # Parse arguments
    args = parse_arguments()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = get_logger(__name__)

    logger.info("=" * 70)
    logger.info("UAT GATEWAY ORCHESTRATOR")
    logger.info("=" * 70)
    logger.info(f"Start time: {datetime.now().isoformat()}")

    # Load configuration (priority: CLI args > config file > env vars > defaults)
    env_config = load_config_from_env()
    file_config = load_config_from_file(args.config) if Path(args.config).exists() else {}

    # Merge configs (env vars -> file config -> CLI args)
    config = OrchestratorConfig(
        spec_path=args.spec,
        test_directory=args.test_dir,
        output_directory=args.output_dir,
        state_directory=args.state_dir,
        base_url=args.base_url,
        kanban_api_url=args.kanban_url if args.kanban_url else env_config.get("kanban_api_url"),
        kanban_api_token=args.kanban_token if args.kanban_token else env_config.get("kanban_api_token"),
        parallel_execution=args.parallel,
        max_parallel_tests=args.workers,
        enable_checkpoints=True,
        checkpoint_interval_seconds=60,
    )

    # Disable Kanban if requested or no credentials
    if args.no_kanban or not config.kanban_api_url or not config.kanban_api_token:
        config.kanban_api_url = None
        config.kanban_api_token = None
        logger.info("Kanban integration disabled")

    # Log configuration
    logger.info(f"Spec file: {config.spec_path}")
    logger.info(f"Test directory: {config.test_directory}")
    logger.info(f"Output directory: {config.output_directory}")
    logger.info(f"Base URL: {config.base_url}")
    logger.info(f"Parallel execution: {config.parallel_execution}")
    logger.info(f"Max workers: {config.max_parallel_tests}")
    logger.info(f"Kanban integration: {'Enabled' if config.kanban_api_url else 'Disabled'}")

    # Create orchestrator
    try:
        orchestrator = Orchestrator(config)
        orchestrator.initialize_components()

        # Run cycle (or dry run)
        if args.dry_run:
            logger.info("\nDRY RUN MODE - Validating spec and extracting journeys only...")
            # Just parse spec and extract journeys
            spec = orchestrator._parse_spec()
            if spec:
                logger.info("✓ Spec parsed successfully")
                journeys = orchestrator._extract_journeys(spec)
                if journeys:
                    logger.info(f"✓ Extracted {len(journeys)} journeys")
                    for journey in journeys:
                        logger.info(f"  - {journey.name}: {len(journey.scenarios)} scenarios")
                    result = OrchestratorResult(
                        success=True,
                        start_time=datetime.now(),
                        end_time=datetime.now(),
                        duration_seconds=0.0,
                        spec_parsed=True,
                        journeys_extracted=True,
                        total_journeys=len(journeys),
                        total_scenarios=sum(len(j.scenarios) for j in journeys)
                    )
                else:
                    logger.error("✗ No journeys extracted")
                    result = OrchestratorResult(
                        success=False,
                        start_time=datetime.now(),
                        end_time=datetime.now(),
                        duration_seconds=0.0,
                        errors=["No journeys extracted from spec"]
                    )
            else:
                logger.error("✗ Failed to parse spec")
                result = OrchestratorResult(
                    success=False,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    duration_seconds=0.0,
                    errors=["Failed to parse spec file"]
                )
        else:
            # Full cycle
            result = orchestrator.run_cycle()

        # Save result to JSON if requested
        if args.save_result:
            result_path = Path(args.result_file)
            result_path.parent.mkdir(parents=True, exist_ok=True)
            with open(result_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
            logger.info(f"\n✓ Result saved to: {result_path}")

        # Exit with appropriate code
        if result.success:
            logger.info("\n✓ UAT cycle completed successfully")
            sys.exit(0)
        else:
            logger.error("\n✗ UAT cycle failed")
            if result.errors:
                logger.error("Errors:")
                for error in result.errors:
                    logger.error(f"  - {error}")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("\n\nUAT cycle interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n✗ UAT cycle failed with exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
