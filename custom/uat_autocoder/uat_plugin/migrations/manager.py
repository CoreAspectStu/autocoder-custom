"""
Migration Manager for UAT AutoCoder Plugin

Provides a simple interface for running database migrations (upgrade/downgrade).
Wraps Alembic functionality in an easy-to-use API.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from alembic.config import Config
    from alembic import command
    from alembic.script import ScriptDirectory
    ALEMBIC_AVAILABLE = True
except ImportError:
    ALEMBIC_AVAILABLE = False
    print("Warning: Alembic not installed. Install with: uv pip install alembic")


class MigrationManager:
    """
    Manages database migrations for the UAT AutoCoder Plugin.

    Provides methods to upgrade, downgrade, and check migration status.
    """

    def __init__(self, migrations_dir: Optional[str] = None):
        """
        Initialize migration manager.

        Args:
            migrations_dir: Path to migrations directory (default: custom/uat_plugin/migrations)
        """
        if not ALEMBIC_AVAILABLE:
            raise RuntimeError("Alembic is not installed. Run: uv pip install alembic")

        # Get migrations directory
        if migrations_dir is None:
            current_dir = Path(__file__).parent
            self.migrations_dir = str(current_dir)
        else:
            self.migrations_dir = migrations_dir

        # Alembic config
        self.config = Config()
        self.config.set_main_option('script_location', self.migrations_dir)

        # Set database URL
        uat_db_path = os.path.expanduser('~/.autocoder/uat_tests.db')
        database_url = f'sqlite:///{uat_db_path}'
        self.config.set_main_option('sqlalchemy.url', database_url)

    def get_current_revision(self) -> Optional[str]:
        """
        Get the current database revision.

        Returns:
            Current revision ID or None if database is not initialized
        """
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        # Import database to get engine
        from database import get_db_manager

        db = get_db_manager()
        if not db._uat_engine:
            return None

        with db._uat_engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision()

    def get_latest_revision(self) -> Optional[str]:
        """
        Get the latest available migration revision.

        Returns:
            Latest revision ID or None if no migrations available
        """
        script = ScriptDirectory.from_config(self.config)
        return script.get_current_head()

    def get_migration_history(self) -> List[dict]:
        """
        Get list of all available migrations.

        Returns:
            List of migration dictionaries with revision, down_revision, and doc
        """
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(self.config)
        migrations = []

        for revision in script.walk_revisions():
            migrations.append({
                'revision': revision.revision,
                'down_revision': revision.down_revision,
                'doc': revision.doc,
                'branch_labels': revision.branch_labels
            })

        return list(reversed(migrations))

    def upgrade(self, revision: str = 'head') -> str:
        """
        Upgrade database to a specific revision.

        Args:
            revision: Target revision (default: 'head' for latest)

        Returns:
            Message describing what was done
        """
        command.upgrade(self.config, revision)
        current = self.get_current_revision()
        return f"Upgraded to revision: {current}"

    def downgrade(self, revision: str = '-1') -> str:
        """
        Downgrade database to a specific revision.

        Args:
            revision: Target revision (default: '-1' for one step back)

        Returns:
            Message describing what was done
        """
        command.downgrade(self.config, revision)
        current = self.get_current_revision()
        return f"Downgraded to revision: {current}"

    def stamp(self, revision: str) -> str:
        """
        Stamp database with a specific revision without running migrations.

        Useful for setting an existing database to a specific revision.

        Args:
            revision: Target revision to stamp

        Returns:
            Message describing what was done
        """
        command.stamp(self.config, revision)
        return f"Stamped database with revision: {revision}"

    def create_migration(
        self,
        message: str,
        autogenerate: bool = True
    ) -> str:
        """
        Create a new migration file.

        Args:
            message: Migration message/description
            autogenerate: Whether to autogenerate from model changes

        Returns:
            Path to created migration file
        """
        # Create versions directory if it doesn't exist
        versions_dir = os.path.join(self.migrations_dir, 'versions')
        os.makedirs(versions_dir, exist_ok=True)

        revision = command.revision(
            self.config,
            message=message,
            autogenerate=autogenerate
        )

        if revision:
            return f"Created migration: {revision.revision}"
        else:
            return "No migration created (no changes detected)"

    def check_status(self) -> dict:
        """
        Check migration status.

        Returns:
            Dictionary with current_revision, latest_revision, and status
        """
        current = self.get_current_revision()
        latest = self.get_latest_revision()

        if current is None:
            status = "not initialized"
        elif current == latest:
            status = "up to date"
        else:
            status = "needs upgrade"

        return {
            'current_revision': current,
            'latest_revision': latest,
            'status': status
        }


# Convenience functions

def get_migration_manager() -> MigrationManager:
    """
    Get the migration manager instance.

    Returns:
        MigrationManager instance
    """
    return MigrationManager()


def upgrade_database(revision: str = 'head') -> str:
    """
    Upgrade database to latest or specific revision.

    Args:
        revision: Target revision (default: 'head')

    Returns:
        Status message
    """
    mgr = get_migration_manager()
    return mgr.upgrade(revision)


def downgrade_database(revision: str = '-1') -> str:
    """
    Downgrade database by one step or to specific revision.

    Args:
        revision: Target revision (default: '-1')

    Returns:
        Status message
    """
    mgr = get_migration_manager()
    return mgr.downgrade(revision)


def check_migration_status() -> dict:
    """
    Check migration status.

    Returns:
        Dictionary with status information
    """
    mgr = get_migration_manager()
    return mgr.check_status()


if __name__ == '__main__':
    """
    CLI for running migrations manually.

    Usage:
        python manager.py status      # Check status
        python manager.py upgrade     # Upgrade to latest
        python manager.py downgrade   # Downgrade one step
        python manager.py history     # Show migration history
    """
    import argparse

    parser = argparse.ArgumentParser(description='UAT AutoCoder Database Migration Manager')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Status command
    subparsers.add_parser('status', help='Check migration status')

    # Upgrade command
    upgrade_parser = subparsers.add_parser('upgrade', help='Upgrade database')
    upgrade_parser.add_argument('--revision', default='head', help='Target revision (default: head)')

    # Downgrade command
    downgrade_parser = subparsers.add_parser('downgrade', help='Downgrade database')
    downgrade_parser.add_argument('--revision', default='-1', help='Target revision (default: -1)')

    # History command
    subparsers.add_parser('history', help='Show migration history')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create new migration')
    create_parser.add_argument('message', help='Migration message')
    create_parser.add_argument('--no-autogenerate', action='store_true', help='Disable autogenerate')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    mgr = get_migration_manager()

    if args.command == 'status':
        status = mgr.check_status()
        print(f"Current Revision: {status['current_revision']}")
        print(f"Latest Revision: {status['latest_revision']}")
        print(f"Status: {status['status']}")

    elif args.command == 'upgrade':
        result = mgr.upgrade(args.revision)
        print(result)

    elif args.command == 'downgrade':
        result = mgr.downgrade(args.revision)
        print(result)

    elif args.command == 'history':
        migrations = mgr.get_migration_history()
        print("Migration History:")
        for migration in migrations:
            print(f"  {migration['revision']}: {migration['doc']}")
            if migration['down_revision']:
                print(f"    ↓ from {migration['down_revision']}")

    elif args.command == 'create':
        result = mgr.create_migration(args.message, autogenerate=not args.no_autogenerate)
        print(result)
