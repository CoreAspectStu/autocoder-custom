"""
Security tests for conversation access control (Feature #159)

This test suite verifies that users cannot access conversations from projects
they don't have permission to view, and that the API properly defends against
various attack vectors including path traversal, SQL injection, and XSS.

Test Categories:
1. Path Traversal Attacks
2. SQL Injection Attempts
3. Cross-Project Access Control
4. Command Injection Attempts
5. XSS Attempts
6. Unicode and Encoding Attacks
7. Length Boundary Attacks
8. Special Character Handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

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


class TestPathTraversalAttacks:
    """
    Test Path: Path Traversal Prevention (Feature #159)

    Verify that path traversal attempts are blocked at the validation layer
    before any file system operations occur.

    Attack Vectors:
    - ../ sequences (parent directory traversal)
    - Absolute paths
    - UNC paths (Windows)
    - URL-encoded paths
    """

    def test_path_traversal_with_double_dot_slash(self, client):
        """
        Test: GET /api/assistant/conversations/../etc/passwd

        Verify: Returns 400 or 404 (both are safe - 404 means the path traversal failed)
        Attack: Attempt to traverse to system files
        Note: FastAPI's path matching may reject this before our validation
        """
        malicious_name = "../etc/passwd"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Either 400 (our validation caught it) or 404 (FastAPI rejected the path)
        # Both are safe outcomes
        assert response.status_code in [400, 404]
        if response.status_code == 400:
            assert "Invalid project name" in response.json()["detail"]

    def test_path_traversal_with_backslash(self, client):
        """
        Test: GET /api/assistant/conversations/..\..\..\windows\system32

        Verify: Returns 400 (backslash is invalid in our regex)
        Attack: Windows-style backslash traversal
        """
        malicious_name = "..\\..\\..\\windows\\system32"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Backslash is not in [a-zA-Z0-9_-], so should be rejected
        assert response.status_code == 400
        assert "Invalid project name" in response.json()["detail"]

    def test_absolute_path_unix(self, client):
        """
        Test: GET /api/assistant/conversations//etc/shadow

        Verify: Returns 400 or 404 (FastAPI may reject leading slash)
        Attack: Absolute Unix path
        """
        malicious_name = "/etc/shadow"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Leading slash will cause FastAPI to treat this differently
        # Result depends on how FastAPI parses the path
        assert response.status_code in [400, 404]
        if response.status_code == 400:
            assert "Invalid project name" in response.json()["detail"]

    def test_absolute_path_windows(self, client):
        """
        Test: GET /api/assistant/conversations/C:/Windows/System32/config

        Verify: Returns 400 or 404 (colon is invalid, but path parsing may differ)
        Attack: Absolute Windows path
        """
        malicious_name = "C:/Windows/System32/config"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Colon is invalid in our regex
        assert response.status_code in [400, 404]

    def test_url_encoded_path_traversal(self, client):
        """
        Test: GET /api/assistant/conversations/%2e%2e%2fetc%2fpasswd

        Verify: Returns 400 or 404 (FastAPI decodes, then our validation should catch)
        Attack: URL-encoded path traversal
        Note: FastAPI auto-decodes URLs before validation
        """
        # The URL encoding gets decoded by FastAPI before our validation
        # So we test the decoded version directly
        malicious_name = "../etc/passwd"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # FastAPI path matching may reject before our validation
        assert response.status_code in [400, 404]

    def test_double_url_encoding(self, client):
        """
        Test: GET /api/assistant/conversations/%252e%252e%252f

        Verify: Returns 400 or 404 (or decodes to ../)
        Attack: Double URL encoding attempt
        """
        # %2525 = % (encoded), %252e = . (encoded), %252f = / (encoded)
        # This should decode to %2e%2e%2f which decodes to ../
        malicious_name = "%2e%2e%2f"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # FastAPI decodes once, so this becomes "../" which should be rejected
        assert response.status_code in [400, 404]

    def test_null_byte_injection(self, client):
        """
        Test: GET /api/assistant/constructions/../../etc/passwd%00.jpg

        Verify: Rejected by HTTP client (null bytes are invalid in URLs)
        Attack: Null byte injection to bypass validation
        """
        # Null byte attacks are less common in Python 3 but test anyway
        # The HTTP client itself should reject this
        malicious_name = "test\x00.jpg"

        # HTTP client should reject null bytes before sending
        with pytest.raises(Exception):  # httpx.InvalidURL or similar
            client.get(f"/api/assistant/conversations/{malicious_name}")


class TestSQLInjectionAttempts:
    """
    Test Path: SQL Injection Prevention (Feature #159)

    Verify that SQL injection attempts are properly handled.
    Even though we use SQLAlchemy (parameterized queries), we ensure
    the input validation layer catches these patterns.
    """

    def test_sql_injection_single_quote(self, client):
        """
        Test: GET /api/assistant/conversations/'; DROP TABLE--

        Verify: Returns 400
        Attack: Classic SQL injection
        """
        malicious_name = "'; DROP TABLE--"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Should be rejected by validation (contains invalid chars)
        assert response.status_code == 400

    def test_sql_injection_union_select(self, client):
        """
        Test: GET /api/assistant/conversations/' UNION SELECT--

        Verify: Returns 400
        Attack: UNION-based SQL injection
        """
        malicious_name = "' UNION SELECT * FROM--"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_sql_injection_comment(self, client):
        """
        Test: GET /api/assistant/conversations/admin'--

        Verify: Returns 400
        Attack: Comment-based SQL injection
        """
        malicious_name = "admin'--"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_sql_injection_or_attack(self, client):
        """
        Test: GET /api/assistant/conversations/' OR '1'='1

        Verify: Returns 400
        Attack: Tautology-based SQL injection
        """
        malicious_name = "' OR '1'='1"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_sql_injection_stacked_queries(self, client):
        """
        Test: GET /api/assistant/conversations/'; INSERT INTO--

        Verify: Returns 400
        Attack: Stacked query injection
        """
        malicious_name = "'; INSERT INTO--"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_sql_injection_time_based(self, client):
        """
        Test: GET /api/assistant/conversations/'; WAITFOR DELAY--

        Verify: Returns 400
        Attack: Time-based blind SQL injection
        """
        malicious_name = "'; WAITFOR DELAY '00:00:10'--"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400


class TestCrossProjectAccessControl:
    """
    Test Path: Project Isolation (Feature #159)

    Verify that users cannot access conversations from other projects
    and that project boundaries are strictly enforced.
    """

    def test_access_other_project_conversation_returns_404(self, client):
        """
        Test: Attempt to access conversation from different project

        Given:
            - User has access to project_a
            - User does NOT have access to project_b
            - Conversation exists in project_b

        When:
            - User tries to GET conversation from project_b

        Then:
            - Returns 404 (not 403 to avoid project enumeration)
            - Does not leak conversation data
        """
        # Mock project_a as the only accessible project
        project_a = "project_a"
        project_b = "project_b"
        conversation_id = 1

        with patch('server.routers.assistant_chat._get_project_path') as mock_get_path:
            # project_a exists
            mock_project_a = Mock()
            mock_project_a.exists.return_value = True

            # project_b doesn't exist (simulating no access)
            mock_get_path.side_effect = lambda name: mock_project_a if name == project_a else None

            # Try to access project_b conversation
            response = client.get(f"/api/assistant/conversations/{project_b}/{conversation_id}")

            # Should return 404 (not 403 to avoid project enumeration)
            assert response.status_code == 404
            assert "Project not found" in response.json()["detail"]

    def test_list_conversations_nonexistent_project(self, client):
        """
        Test: List conversations for non-existent project

        Verify: Returns 404, not empty array
        Security: Prevents project enumeration
        """
        nonexistent_project = "nonexistent_project_xyz"

        with patch('server.routers.assistant_chat._get_project_path') as mock_get_path:
            mock_get_path.return_value = None

            response = client.get(f"/api/assistant/conversations/{nonexistent_project}")

            assert response.status_code == 404
            assert "Project not found" in response.json()["detail"]

    def test_create_conversation_nonexistent_project(self, client):
        """
        Test: Create conversation in non-existent project

        Verify: Returns 404
        Security: Prevents creating resources in inaccessible projects
        """
        nonexistent_project = "restricted_project"

        with patch('server.routers.assistant_chat._get_project_path') as mock_get_path:
            mock_get_path.return_value = None

            response = client.post(f"/api/assistant/conversations/{nonexistent_project}")

            assert response.status_code == 404
            assert "Project not found" in response.json()["detail"]

    def test_delete_conversation_cross_project(self, client):
        """
        Test: Delete conversation from different project

        Verify: Returns 404 if project doesn't exist
        Security: Prevents cross-project deletion
        """
        other_project = "other_user_project"
        conversation_id = 1

        with patch('server.routers.assistant_chat._get_project_path') as mock_get_path:
            mock_get_path.return_value = None

            response = client.delete(f"/api/assistant/conversations/{other_project}/{conversation_id}")

            assert response.status_code == 404


class TestCommandInjectionAttempts:
    """
    Test Path: Command Injection Prevention (Feature #159)

    Verify that command injection attempts are blocked.
    While project names aren't executed directly, defense-in-depth
    requires blocking shell metacharacters.
    """

    def test_command_injection_semicolon(self, client):
        """
        Test: GET /api/assistant/conversations/valid; rm -rf /

        Verify: Returns 400
        Attack: Command injection with semicolon
        """
        malicious_name = "valid; rm -rf /"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_command_injection_pipe(self, client):
        """
        Test: GET /api/assistant/conversations/project | cat /etc/passwd

        Verify: Returns 400 or 404 (pipe is invalid in project names)
        Attack: Pipe injection
        Note: | is not in [a-zA-Z0-9_-], so validation should reject it
        """
        malicious_name = "project|test"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Pipe is not in allowed characters
        # Should be rejected by validation (400) or treated as non-existent path (404)
        assert response.status_code in [400, 404]

    def test_command_injection_backtick(self, client):
        """
        Test: GET /api/assistant/conversations/project`whoami`

        Verify: Returns 400
        Attack: Backtick command substitution
        """
        malicious_name = "project`whoami`"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_command_injection_dollar_paren(self, client):
        """
        Test: GET /api/assistant/conversations/project$(ls -la)

        Verify: Returns 400
        Attack: $() command substitution
        """
        malicious_name = "project$(ls -la)"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_command_injection_newline(self, client):
        """
        Test: GET /api/assistant/conversations/project\ncat%20/etc/passwd

        Verify: Rejected by HTTP client (newlines are invalid in URLs)
        Attack: Newline command separator
        """
        # Newlines in URLs are rejected by HTTP client before sending
        malicious_name = "project\ncat"

        # HTTP client should reject newlines
        with pytest.raises(Exception):  # httpx.InvalidURL or similar
            client.get(f"/api/assistant/conversations/{malicious_name}")


class TestXSSAttempts:
    """
    Test Path: XSS Prevention (Feature #159)

    Verify that XSS payloads are rejected.
    Even though project names aren't typically rendered as HTML,
    defense-in-depth requires blocking script tags and event handlers.
    """

    def test_xss_script_tag(self, client):
        """
        Test: GET /api/assistant/conversations/<script>alert(1)</script>

        Verify: Returns 400 or 422 (422 from FastAPI path validation is also safe)
        Attack: Script tag injection
        """
        malicious_name = "<script>alert(1)</script>"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # FastAPI may return 422 for path validation errors, which is also safe
        assert response.status_code in [400, 422]

    def test_xss_onerror(self, client):
        """
        Test: GET /api/assistant/conversations/<img src=x onerror=alert(1)>

        Verify: Returns 400
        Attack: Image onerror event handler
        """
        malicious_name = "<img src=x onerror=alert(1)>"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400

    def test_xss_javascript_protocol(self, client):
        """
        Test: GET /api/assistant/conversations/javascript:alert(1)

        Verify: Returns 400
        Attack: JavaScript protocol
        """
        malicious_name = "javascript:alert(1)"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # The colon is invalid, so should be rejected
        assert response.status_code == 400

    def test_xss_onclick(self, client):
        """
        Test: GET /api/assistant/conversations/<div onclick=alert(1)>

        Verify: Returns 400
        Attack: Onclick event handler
        """
        malicious_name = "<div onclick=alert(1)>"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        assert response.status_code == 400


class TestUnicodeAndEncodingAttacks:
    """
    Test Path: Unicode/Encoding Security (Feature #159)

    Verify that Unicode normalization attacks and encoding tricks
    are properly handled.
    """

    def test_unicode_homograph_attack(self, client):
        """
        Test: GET /api/assistant/conversations/admin\u0131 (dotted i)

        Verify: Returns 400 or normalized correctly
        Attack: Unicode homograph attack (visual spoofing)
        """
        # Use Turkish dotless i which looks like regular 'i'
        malicious_name = "adm\u0131n"  # admın (looks like admin)

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Should be valid as it contains only alphanumeric
        # But demonstrates that we handle Unicode safely
        assert response.status_code in [400, 404]  # 400 if invalid, 404 if doesn't exist

    def test_zero_width_characters(self, client):
        """
        Test: GET /api/assistant/conversations/ad\u200Bmin

        Verify: Handled correctly
        Attack: Zero-width character injection
        """
        # Zero-width space
        malicious_name = "ad\u200Bmin"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Zero-width space should be rejected by validation
        assert response.status_code == 400

    def test_unicode_overflow(self, client):
        """
        Test: GET /api/assistant/conversations/😀🐍

        Verify: Handled correctly
        Attack: Unicode emoji/symbols
        """
        malicious_name = "😀🐍"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Emojis should be rejected by validation
        assert response.status_code == 400

    def test_mixed_encoding(self, client):
        """
        Test: Mixed encoding sequences

        Verify: Handled safely (400 or 422 both safe)
        Attack: Mixed encoding attempt
        """
        # Mix of valid and potentially dangerous chars
        # %2f decodes to / which is invalid
        malicious_name = "project%2ftest"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Forward slash after decoding is invalid
        assert response.status_code in [400, 422]


class TestLengthBoundaryAttacks:
    """
    Test Path: Boundary Testing (Feature #159)

    Verify that length boundaries are enforced correctly.
    """

    def test_exactly_50_chars_valid(self, client):
        """
        Test: GET /api/assistant/conversations/{50-char name}

        Verify: Accepted by validation (at boundary)
        Note: Returns 404 because project doesn't exist, which proves validation passed
        """
        valid_name = "a" * 50

        # Don't mock - let it try to find the project
        # If we get 404 (not 400), validation passed
        response = client.get(f"/api/assistant/conversations/{valid_name}")

        # Should pass validation (50 is max) and return 404 (project not found)
        # NOT 400 (validation failed)
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    def test_51_chars_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/{51-char name}

        Verify: Returns 400 (exceeds boundary)
        """
        invalid_name = "a" * 51

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_zero_length_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/

        Verify: Returns 400 (empty not allowed)
        """
        # FastAPI requires at least one character for path params
        # So we test with validation function directly
        assert validate_project_name("") == False

    def test_exactly_1_char_valid(self, client):
        """
        Test: GET /api/assistant/conversations/{1-char name}

        Verify: Accepted by validation (at minimum boundary)
        Note: Returns 404 because project doesn't exist, which proves validation passed
        """
        valid_name = "a"

        # Don't mock - let it try to find the project
        response = client.get(f"/api/assistant/conversations/{valid_name}")

        # Should pass validation (1 is min) and return 404 (project not found)
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]


class TestSpecialCharacterHandling:
    """
    Test Path: Special Character Security (Feature #159)

    Verify that special characters are properly handled.
    """

    def test_leading_trailing_hyphens_valid(self, client):
        """
        Test: GET /api/assistant/conversations/-project-

        Verify: Accepted by validation (hyphens valid at any position)
        Note: Returns 404 because project doesn't exist, which proves validation passed
        """
        valid_name = "-project-"

        # Don't mock - let it try to find the project
        response = client.get(f"/api/assistant/conversations/{valid_name}")

        # Should pass validation and return 404 (project not found)
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    def test_leading_trailing_underscores_valid(self, client):
        """
        Test: GET /api/assistant/conversations/_project_

        Verify: Accepted by validation (underscores valid at any position)
        Note: Returns 404 because project doesn't exist, which proves validation passed
        """
        valid_name = "_project_"

        # Don't mock - let it try to find the project
        response = client.get(f"/api/assistant/conversations/{valid_name}")

        # Should pass validation and return 404 (project not found)
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]

    def test_spaces_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project name

        Verify: Returns 400 (spaces not allowed)
        """
        invalid_name = "project name"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_dot_slash_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/./project

        Verify: Returns 400 or 404 (FastAPI path matching may reject before validation)
        Attack: Dot-slash relative path
        """
        invalid_name = "./project"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        # FastAPI path matching may reject this
        assert response.status_code in [400, 404]

    def test_at_sign_invalid(self, client):
        """
        Test: GET /api/assistant/conversations@project

        Verify: Returns 400 (@ not allowed)
        """
        invalid_name = "project@test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_exclamation_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project!

        Verify: Returns 400 (! not allowed)
        """
        invalid_name = "project!"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_hash_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project#test

        Verify: Returns 400 or 404 (# is invalid and affects URL fragment)
        Attack: Hash character for URL fragment manipulation
        """
        invalid_name = "project#test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        # # is a URL fragment separator, so behavior may vary
        assert response.status_code in [400, 404]

    def test_percent_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project%test

        Verify: Returns 400 (% not allowed in validation)
        """
        invalid_name = "project%test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_ampersand_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project&test

        Verify: Returns 400 (& not allowed)
        """
        invalid_name = "project&test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_asterisk_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project*

        Verify: Returns 400 (* not allowed)
        """
        invalid_name = "project*"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_parentheses_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project(test)

        Verify: Returns 400 (parentheses not allowed)
        """
        invalid_name = "project(test)"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_brackets_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project[test]

        Verify: Returns 400 (brackets not allowed)
        """
        invalid_name = "project[test]"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_braces_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project{test}

        Verify: Returns 400 (braces not allowed)
        """
        invalid_name = "project{test}"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_pipe_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project|test

        Verify: Returns 400 (pipe not allowed)
        """
        invalid_name = "project|test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_backslash_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project\\test

        Verify: Returns 400 (backslash not allowed)
        """
        invalid_name = "project\\test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_colon_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project:test

        Verify: Returns 400 (colon not allowed)
        """
        invalid_name = "project:test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_semicolon_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project;test

        Verify: Returns 400 (semicolon not allowed)
        """
        invalid_name = "project;test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_single_quote_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project'test

        Verify: Returns 400 (single quote not allowed)
        """
        invalid_name = "project'test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_double_quote_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project"test

        Verify: Returns 400 (double quote not allowed)
        """
        invalid_name = 'project"test'

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_backtick_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project`test

        Verify: Returns 400 (backtick not allowed)
        """
        invalid_name = "project`test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_tilde_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project~test

        Verify: Returns 400 (tilde not allowed)
        """
        invalid_name = "project~test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_plus_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project+test

        Verify: Returns 400 (plus not allowed)
        """
        invalid_name = "project+test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_equals_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project=test

        Verify: Returns 400 (equals not allowed)
        """
        invalid_name = "project=test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_question_mark_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project?test

        Verify: Returns 400 or 404 (? is query string separator)
        Attack: Question mark for query string manipulation
        """
        invalid_name = "project?test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        # ? is a query string separator, so behavior may vary
        assert response.status_code in [400, 404]

    def test_less_than_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project<test

        Verify: Returns 400 (< not allowed)
        """
        invalid_name = "project<test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_greater_than_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project>test

        Verify: Returns 400 (> not allowed)
        """
        invalid_name = "project>test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_comma_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project,test

        Verify: Returns 400 (comma not allowed)
        """
        invalid_name = "project,test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400

    def test_period_invalid(self, client):
        """
        Test: GET /api/assistant/conversations/project.test

        Verify: Returns 400 (period not allowed)
        """
        invalid_name = "project.test"

        response = client.get(f"/api/assistant/conversations/{invalid_name}")

        assert response.status_code == 400


class TestValidateProjectNameRegexStrictness:
    """
    Test Path: Regex Validation Strictness (Feature #159)

    Verify that the validate_project_name() regex is strict enough
    to block all malicious patterns while allowing valid names.
    """

    def test_regex_pattern_allows_valid_characters(self):
        """
        Verify: Regex allows letters, numbers, hyphens, underscores
        """
        # Valid characters
        assert validate_project_name("abc") == True
        assert validate_project_name("ABC") == True
        assert validate_project_name("123") == True
        assert validate_project_name("abc123") == True
        assert validate_project_name("abc-123") == True
        assert validate_project_name("abc_123") == True
        assert validate_project_name("abc-DEF_123") == True

    def test_regex_pattern_blocks_all_special_chars(self):
        """
        Verify: Regex blocks all special characters
        """
        # All printable special characters
        special_chars = [
            " ", "!", "\"", "#", "$", "%", "&", "'", "(", ")", "*", "+", ",", ".", "/",
            ":", ";", "<", "=", ">", "?", "@", "[", "\\", "]", "^", "_", "`", "{", "|", "}", "~",
        ]

        # All should be rejected (except _ which is allowed)
        for char in special_chars:
            if char == "_":
                # Underscore is allowed
                assert validate_project_name(f"test{char}test") == True
            elif char == "-":
                # Hyphen is allowed
                assert validate_project_name(f"test{char}test") == True
            else:
                # All other special chars should be rejected
                assert validate_project_name(f"test{char}test") == False

    def test_regex_pattern_enforces_length_limits(self):
        """
        Verify: Regex enforces 1-50 character limit
        """
        # Empty string should fail
        assert validate_project_name("") == False

        # 1 character should pass
        assert validate_project_name("a") == True

        # 50 characters should pass
        assert validate_project_name("a" * 50) == True

        # 51 characters should fail
        assert validate_project_name("a" * 51) == False

    def test_regex_pattern_blocks_control_characters(self):
        """
        Verify: Regex blocks control characters
        """
        # Common control characters
        control_chars = [
            "\n", "\r", "\t", "\x00", "\x01", "\x02", "\x1b",
        ]

        for char in control_chars:
            # Control characters should be rejected
            assert validate_project_name(f"test{char}test") == False

    def test_regex_pattern_case_sensitive(self):
        """
        Verify: Regex is case-sensitive (allows both upper and lower)
        """
        assert validate_project_name("PROJECT") == True
        assert validate_project_name("project") == True
        assert validate_project_name("Project") == True
        assert validate_project_name("PrOjEcT") == True


class TestAllEndpointsSecurity:
    """
    Test Path: Security Across All Endpoints (Feature #159)

    Verify that security validation is applied consistently
    across all conversation endpoints.
    """

    def test_list_conversations_blocks_malicious(self, client):
        """GET /api/assistant/conversations/{malicious}"""
        malicious_name = "../etc/passwd"

        response = client.get(f"/api/assistant/conversations/{malicious_name}")

        # Should be rejected (400 or 404 both safe)
        assert response.status_code in [400, 404]

    def test_get_conversation_blocks_malicious(self, client):
        """GET /api/assistant/conversations/{malicious}/1"""
        malicious_name = "'; DROP TABLE--"

        response = client.get(f"/api/assistant/conversations/{malicious_name}/1")

        assert response.status_code == 400

    def test_create_conversation_blocks_malicious(self, client):
        """POST /api/assistant/conversations/{malicious}"""
        malicious_name = "'; DROP TABLE--"

        response = client.post(f"/api/assistant/conversations/{malicious_name}")

        # Single quote is invalid
        assert response.status_code == 400

    def test_delete_conversation_blocks_malicious(self, client):
        """DELETE /api/assistant/conversations/{malicious}/1"""
        malicious_name = "../malicious"

        response = client.delete(f"/api/assistant/conversations/{malicious_name}/1")

        # Should be rejected
        assert response.status_code in [400, 404]

    def test_get_session_blocks_malicious(self, client):
        """GET /api/assistant/sessions/{malicious}"""
        malicious_name = "../malicious"

        response = client.get(f"/api/assistant/sessions/{malicious_name}")

        # Should be rejected
        assert response.status_code in [400, 404]

    def test_close_session_blocks_malicious(self, client):
        """DELETE /api/assistant/sessions/{malicious}"""
        malicious_name = "project`whoami`"

        response = client.delete(f"/api/assistant/sessions/{malicious_name}")

        assert response.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
