"""
API Test Generation Extension for TestGenerator

This module provides methods for generating API endpoint tests using Playwright's APIRequestContext.
"""

from typing import Optional
from journey_extractor.journey_extractor import JourneyStep


def generate_api_call_code(step: JourneyStep, comment: str, base_url: str) -> str:
    """
    Generate TypeScript code for API call using Playwright's APIRequestContext

    Args:
        step: The JourneyStep object with action_type='api_call'
        comment: The step comment to include
        base_url: The base URL for API requests

    Returns:
        TypeScript code for making API request

    Expected target format: "METHOD /endpoint"
    Examples:
        "GET /api/users"
        "POST /api/users"
        "PUT /api/users/123"
        "DELETE /api/users/123"
    """
    target = step.target or ""

    # Parse HTTP method and endpoint
    parts = target.strip().split(" ", 1)
    if len(parts) != 2:
        return f"{comment}\n// TODO: Invalid API call format. Expected: 'METHOD /endpoint', got: '{target}'"

    method = parts[0].upper()
    endpoint = parts[1]

    # Generate the API request code using Playwright's APIRequestContext
    return f"{comment}\nconst response = await page.request.{method.lower()}('{base_url}{endpoint}');"


def generate_api_assertion_code(step: JourneyStep, comment: str) -> str:
    """
    Generate TypeScript code for API response assertions

    Args:
        step: The JourneyStep object with action_type='assert'
        comment: The step comment to include

    Returns:
        TypeScript code for asserting on API response

    Expected expected_result format:
        "status_code=200"
        "response_body.field=value"
        "response_contains_users"
    """
    if not step.expected_result:
        return f"{comment}\n// TODO: Add assertion criterion"

    criterion = step.expected_result.strip()

    # Status code assertion
    if criterion.startswith("status_code="):
        status_code = criterion.split("=", 1)[1].strip()
        return f"{comment}\nawait expect(response).toBeOK();\nconst statusCode = response.status();\nawait expect(statusCode.toString()).toBe('{status_code}');"

    # Response body field assertion
    elif criterion.startswith("response_body."):
        field_path = criterion.split(".", 1)[1].strip()
        if "=" in field_path:
            field, expected_value = field_path.split("=", 1)
            field = field.strip()
            expected_value = expected_value.strip().strip("'\"")
            return f"{comment}\nconst responseBody = await response.json();\nawait expect(responseBody.{field}).toBe('{expected_value}');"
        else:
            # Just check field exists
            return f"{comment}\nconst responseBody = await response.json();\nawait expect(responseBody.{field_path}).toBeDefined();"

    # Response contains check
    elif criterion.startswith("response_contains_"):
        parts = criterion.split("_")
        if len(parts) >= 3:
            contains_what = "_".join(parts[2:]).strip()
        else:
            contains_what = ""
        return f"{comment}\nconst responseBody = await response.json();\nawait expect(JSON.stringify(responseBody)).toContain('{contains_what}');"

    else:
        # Generic assertion
        return f"{comment}\nawait expect(response).toBeOK();"
