"""
Unit tests for assistant database auto-creation (Feature #156)

Tests that assistant.db and its tables are automatically created when
accessing a project for the first time via the API.

This test verifies the get_engine() function's auto-creation behavior,
ensuring that:
1. The database file is created on first access
2. All required tables are created (conversations, conversation_messages)
3. The database is usable immediately after creation
4. Parent directories are created if they don't exist
"""

import pytest
from pathlib import Path
from sqlalchemy import inspect
from datetime import datetime, timezone

# Import the database module we're testing
from server.services.assistant_database import (
    get_engine,
    get_session,
    get_db_path,
    create_conversation,
    get_conversations,
    Base,
    Conversation,
    ConversationMessage,
)


class TestDatabaseAutoCreation:
    """Tests for automatic database creation on first access."""

    def test_database_file_created_on_first_access(self, tmp_path):
        """
        Feature #156 Step 4: Verify assistant.db file is created.

        Given:
            - A temporary project directory (empty, no database)
            - First access to get_engine()

        When:
            - get_engine() is called on fresh project directory

        Then:
            - assistant.db file is created
            - File exists at correct path
            - File is a valid SQLite database
        """
        # Create temporary project directory
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        # Verify database does NOT exist before
        db_path = get_db_path(project_dir)
        assert not db_path.exists(), "Database should not exist before get_engine() call"

        # Call get_engine() - this should auto-create the database
        engine = get_engine(project_dir)

        # Verify database file exists after
        assert db_path.exists(), "Database file should be created after get_engine() call"
        assert db_path.is_file(), "Database path should be a file, not a directory"
        assert db_path.name == "assistant.db", "Database file should be named assistant.db"

    def test_tables_created_on_first_access(self, tmp_path):
        """
        Feature #156 Step 5: Verify tables exist: conversations, conversation_messages.

        Given:
            - A fresh database (just created)

        When:
            - get_engine() is called

        Then:
            - conversations table exists
            - conversation_messages table exists
            - Both tables have correct schema
        """
        # Create temporary project directory
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        # Get engine (creates database and tables)
        engine = get_engine(project_dir)

        # Use SQLAlchemy inspector to check tables
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # Verify required tables exist
        assert "conversations" in table_names, "conversations table must exist"
        assert "conversation_messages" in table_names, "conversation_messages table must exist"

    def test_conversations_table_schema(self, tmp_path):
        """
        Verify conversations table has correct schema.

        Columns expected:
            - id (Integer, primary key)
            - project_name (String(100), nullable=False)
            - title (String(200), nullable=True)
            - created_at (DateTime)
            - updated_at (DateTime)
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        engine = get_engine(project_dir)
        inspector = inspect(engine)

        # Get columns for conversations table
        columns = {c["name"]: c for c in inspector.get_columns("conversations")}

        # Verify all required columns exist
        assert "id" in columns, "id column must exist"
        assert columns["id"]["primary_key"] == True, "id must be primary key"
        assert columns["id"]["type"].python_type == int, "id must be Integer type"

        assert "project_name" in columns, "project_name column must exist"
        assert columns["project_name"]["nullable"] == False, "project_name must be NOT NULL"

        assert "title" in columns, "title column must exist"
        assert columns["title"]["nullable"] == True, "title can be NULL (optional)"

        assert "created_at" in columns, "created_at column must exist"
        assert columns["created_at"]["type"].python_type == datetime, "created_at must be DateTime"

        assert "updated_at" in columns, "updated_at column must exist"
        assert columns["updated_at"]["type"].python_type == datetime, "updated_at must be DateTime"

    def test_conversation_messages_table_schema(self, tmp_path):
        """
        Verify conversation_messages table has correct schema.

        Columns expected:
            - id (Integer, primary key)
            - conversation_id (Integer, foreign key to conversations.id)
            - role (String(20), nullable=False)
            - content (Text, nullable=False)
            - timestamp (DateTime)
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        engine = get_engine(project_dir)
        inspector = inspect(engine)

        # Get columns for conversation_messages table
        columns = {c["name"]: c for c in inspector.get_columns("conversation_messages")}

        # Verify all required columns exist
        assert "id" in columns, "id column must exist"
        assert columns["id"]["primary_key"] == True, "id must be primary key"

        assert "conversation_id" in columns, "conversation_id column must exist"
        assert columns["conversation_id"]["nullable"] == False, "conversation_id must be NOT NULL"

        assert "role" in columns, "role column must exist"
        assert columns["role"]["nullable"] == False, "role must be NOT NULL"

        assert "content" in columns, "content column must exist"
        assert columns["content"]["nullable"] == False, "content must be NOT NULL"

        assert "timestamp" in columns, "timestamp column must exist"
        assert columns["timestamp"]["type"].python_type == datetime, "timestamp must be DateTime"

    def test_foreign_key_constraint(self, tmp_path):
        """
        Verify foreign key constraint exists on conversation_messages.conversation_id.

        This ensures referential integrity: messages cannot exist without
        a parent conversation.
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        engine = get_engine(project_dir)
        inspector = inspect(engine)

        # Get foreign key constraints
        foreign_keys = inspector.get_foreign_keys("conversation_messages")

        # Verify there is a foreign key on conversation_id
        assert len(foreign_keys) > 0, "conversation_messages should have foreign key constraints"

        # Find the conversation_id foreign key
        conversation_id_fk = None
        for fk in foreign_keys:
            if "conversation_id" in fk["constrained_columns"]:
                conversation_id_fk = fk
                break

        assert conversation_id_fk is not None, "conversation_id should have a foreign key constraint"
        assert conversation_id_fk["referred_table"] == "conversations", \
            "conversation_id should reference conversations table"
        assert "id" in conversation_id_fk["referred_columns"], \
            "conversation_id should reference conversations.id"

    def test_create_conversation_in_new_database(self, tmp_path):
        """
        Feature #156 Step 6: Test creating conversation in new database works.

        Given:
            - A fresh auto-created database
            - Empty tables

        When:
            - create_conversation() is called

        Then:
            - Conversation is created successfully
            - Conversation can be retrieved
            - All fields are populated correctly
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        # This triggers auto-creation
        project_name = "test_project"
        title = "Test Conversation"

        # Create a conversation
        conversation = create_conversation(project_dir, project_name, title)

        # Verify conversation was created
        assert conversation is not None, "Conversation should be created"
        assert conversation.id is not None, "Conversation should have an ID"
        assert conversation.project_name == project_name, "Project name should match"
        assert conversation.title == title, "Title should match"
        assert conversation.created_at is not None, "created_at should be set"
        assert conversation.updated_at is not None, "updated_at should be set"

        # Verify we can retrieve it
        conversations = get_conversations(project_dir, project_name)
        assert len(conversations) == 1, "Should have 1 conversation"
        assert conversations[0]["id"] == conversation.id, "Retrieved conversation ID should match"
        assert conversations[0]["title"] == title, "Retrieved title should match"
        assert conversations[0]["message_count"] == 0, "New conversation should have 0 messages"

    def test_parent_directory_creation(self, tmp_path):
        """
        Feature #149: Verify parent directories are created if they don't exist.

        Given:
            - A project directory path that doesn't exist yet

        When:
            - get_engine() is called

        Then:
            - Parent directories are created automatically
            - Database file is created successfully
            - No FileNotFoundError is raised
        """
        # Create a nested path that doesn't exist
        project_dir = tmp_path / "level1" / "level2" / "level3" / "my_project"

        # Verify parent directory does NOT exist before
        assert not project_dir.exists(), "Parent directory should not exist"

        # This should create parent directories automatically
        engine = get_engine(project_dir)

        # Verify parent directory was created
        assert project_dir.exists(), "Parent directory should be created"
        assert project_dir.is_dir(), "Project path should be a directory"

        # Verify database was created
        db_path = get_db_path(project_dir)
        assert db_path.exists(), "Database should be created in new directory"

    def test_engine_caching(self, tmp_path):
        """
        Verify engine is cached to avoid creating multiple engines for same project.

        Given:
            - Same project directory

        When:
            - get_engine() is called multiple times

        Then:
            - Same engine instance is returned
            - Database file is only created once
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        # Call get_engine() twice
        engine1 = get_engine(project_dir)
        engine2 = get_engine(project_dir)

        # Verify same instance is returned (cached)
        assert engine1 is engine2, "Same engine instance should be returned from cache"

    def test_session_creation(self, tmp_path):
        """
        Verify get_session() works with auto-created database.

        Given:
            - Fresh project directory

        When:
            - get_session() is called (which calls get_engine internally)

        Then:
            - Session is created successfully
            - Session can be used for database operations
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        # Get session
        session = get_session(project_dir)

        # Verify session is valid
        assert session is not None, "Session should be created"

        # Try to use it for a simple query
        conversations = session.query(Conversation).all()
        assert conversations == [], "New database should have no conversations"

        # Clean up
        session.close()

    def test_database_reuse_after_creation(self, tmp_path):
        """
        Verify database can be reused after initial creation.

        Given:
            - A database that was already created

        When:
            - get_engine() is called again

        Then:
            - Existing database is reused
            - No tables are recreated
            - Data is preserved
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create database and add data
        create_conversation(project_dir, "test_project", "First Conversation")

        # Call get_engine() again (should reuse existing database)
        engine = get_engine(project_dir)

        # Verify data is preserved
        conversations = get_conversations(project_dir, "test_project")
        assert len(conversations) == 1, "Existing conversation should be preserved"
        assert conversations[0]["title"] == "First Conversation", "Data should be unchanged"

    def test_cross_project_isolation(self, tmp_path):
        """
        Verify different projects have separate databases.

        Given:
            - Two different project directories

        When:
            - Databases are created for both projects

        Then:
            - Each has its own assistant.db file
            - Data is isolated between projects
        """
        # Create two separate projects
        project1_dir = tmp_path / "project1"
        project2_dir = tmp_path / "project2"

        project1_dir.mkdir(parents=True, exist_ok=True)
        project2_dir.mkdir(parents=True, exist_ok=True)

        # Create conversations in each project
        conv1 = create_conversation(project1_dir, "project1", "Project 1 Conversation")
        conv2 = create_conversation(project2_dir, "project2", "Project 2 Conversation")

        # Verify databases are separate
        db1_path = get_db_path(project1_dir)
        db2_path = get_db_path(project2_dir)

        assert db1_path.exists(), "Project 1 database should exist"
        assert db2_path.exists(), "Project 2 database should exist"
        assert db1_path != db2_path, "Each project should have its own database file"

        # Verify data isolation
        convs1 = get_conversations(project1_dir, "project1")
        convs2 = get_conversations(project2_dir, "project2")

        assert len(convs1) == 1, "Project 1 should have 1 conversation"
        assert len(convs2) == 1, "Project 2 should have 1 conversation"
        assert convs1[0]["id"] != convs2[0]["id"], "Conversation IDs should be different"

        # Verify project2's conversation is not in project1
        assert convs1[0]["title"] == "Project 1 Conversation"
        assert convs2[0]["title"] == "Project 2 Conversation"


class TestDatabaseIndexing:
    """Tests for database indexing and performance."""

    def test_indexes_are_created(self, tmp_path):
        """
        Verify important indexes are created for performance.

        Expected indexes:
            - conversations.id (primary key, auto-indexed)
            - conversations.project_name (for query performance)
            - conversation_messages.id (primary key, auto-indexed)
            - conversation_messages.conversation_id (for foreign key lookups)
        """
        project_dir = tmp_path / "test_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        engine = get_engine(project_dir)
        inspector = inspect(engine)

        # Check indexes on conversations table
        conversations_indexes = inspector.get_indexes("conversations")
        index_names = [idx["name"] for idx in conversations_indexes]

        # Verify project_name is indexed (for fast queries by project)
        project_name_indexed = any(
            "project_name" in str(idx.get("column_names", []))
            for idx in conversations_indexes
        )
        assert project_name_indexed, "project_name should be indexed for query performance"

        # Check indexes on conversation_messages table
        messages_indexes = inspector.get_indexes("conversation_messages")

        # Verify conversation_id is indexed (for foreign key lookups)
        conversation_id_indexed = any(
            "conversation_id" in str(idx.get("column_names", []))
            for idx in messages_indexes
        )
        assert conversation_id_indexed, "conversation_id should be indexed for JOIN performance"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
