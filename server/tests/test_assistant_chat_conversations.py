"""
Unit tests for assistant chat conversations API (Feature #150)

Tests that GET /api/assistant/conversations/{project_name} returns
an empty array [] when no conversations exist, not a 404 error.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Import the router
from server.routers.assistant_chat import router, validate_project_name


@pytest.fixture
def app():
    """Create a test app with the assistant chat router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestListProjectConversations:
    """Tests for GET /api/assistant/conversations/{project_name}"""

    def test_returns_empty_array_when_no_conversations(self, client):
        """
        Feature #150: Verify endpoint returns [] when no conversations exist.

        Given:
            - A valid project name
            - Project directory exists
            - No conversations in database

        When:
            - GET /api/assistant/conversations/{project_name} is called

        Then:
            - Status code is 200 (not 404)
            - Response body is an empty array []
            - Frontend can distinguish "no conversations" from "project not found"
        """
        project_name = "test_project"

        # Mock the project path to exist
        with patch('server.routers.assistant_chat._get_project_path') as mock_get_path:
            mock_project_dir = Mock()
            mock_project_dir.exists.return_value = True
            mock_get_path.return_value = mock_project_dir

            # Mock get_conversations to return empty list
            with patch('server.routers.assistant_chat.get_conversations') as mock_get_convos:
                mock_get_convos.return_value = []

                # Make the request
                response = client.get(f"/api/assistant/conversations/{project_name}")

                # Verify status code is 200 (not 404)
                assert response.status_code == 200

                # Verify response is empty array
                assert response.json() == []

                # Verify get_conversations was called
                mock_get_convos.assert_called_once_with(mock_project_dir, project_name)

    def test_returns_404_when_project_not_found(self, client):
        """
        Verify endpoint returns 404 when project doesn't exist.

        This test ensures we distinguish between:
        - Project not found (404)
        - No conversations (200 with [])
        """
        project_name = "nonexistent_project"

        # Mock the project path to not exist
        with patch('server.routers.assistant_chat._get_project_path') as mock_get_path:
            mock_get_path.return_value = None

            # Make the request
            response = client.get(f"/api/assistant/conversations/{project_name}")

                # Verify status code is 404
            assert response.status_code == 404
            assert "Project not found" in response.json()["detail"]

    def test_returns_400_when_invalid_project_name(self, client):
        """Verify endpoint returns 400 for invalid project names."""
        invalid_project_name = "../../etc/passwd"  # Path traversal attempt

        # Make the request (no mocking needed, validation happens first)
        response = client.get(f"/api/assistant/conversations/{invalid_project_name}")

        # Verify status code is 400
        assert response.status_code == 400
        assert "Invalid project name" in response.json()["detail"]

    def test_returns_conversations_when_exist(self, client):
        """Verify endpoint returns conversations when they exist."""
        project_name = "test_project"

        # Mock the project path to exist
        with patch('server.routers.assistant_chat._get_project_path') as mock_get_path:
            mock_project_dir = Mock()
            mock_project_dir.exists.return_value = True
            mock_get_path.return_value = mock_project_dir

            # Mock get_conversations to return data
            with patch('server.routers.assistant_chat.get_conversations') as mock_get_convos:
                mock_get_convos.return_value = [
                    {
                        "id": 1,
                        "project_name": "test_project",
                        "title": "Test Conversation",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                        "message_count": 5
                    }
                ]

                # Make the request
                response = client.get(f"/api/assistant/conversations/{project_name}")

                # Verify status code is 200
                assert response.status_code == 200

                # Verify response contains conversation
                data = response.json()
                assert len(data) == 1
                assert data[0]["id"] == 1
                assert data[0]["title"] == "Test Conversation"
                assert data[0]["message_count"] == 5


class TestValidateProjectName:
    """Tests for validate_project_name function"""

    def test_accepts_valid_names(self):
        """Verify valid project names are accepted."""
        assert validate_project_name("test_project") == True
        assert validate_project_name("MyProject123") == True
        assert validate_project_name("my-project") == True
        assert validate_project_name("my_project") == True

    def test_rejects_invalid_names(self):
        """Verify invalid project names are rejected."""
        assert validate_project_name("") == False
        assert validate_project_name("../../etc/passwd") == False
        assert validate_project_name("project with spaces") == False
        assert validate_project_name("project/with/slashes") == False
        assert validate_project_name("a" * 51) == False  # Too long


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
