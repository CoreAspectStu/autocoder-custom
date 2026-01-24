"""
DevLayer Client - Python API for agent-to-human communication

Usage:
    from custom.mission_control.client import DevLayerClient

    client = DevLayerClient(project_name="my-app")

    # Ask human a question
    response = await client.ask_question("Should I use REST or GraphQL?")

    # Report blocker
    await client.report_blocker("Database migration failed - prod DB is read-only")

    # Request credentials
    api_key = await client.request_auth("Stripe", "STRIPE_API_KEY")
"""

import asyncio
import httpx
from datetime import datetime, timezone
from typing import Literal, Optional
from enum import Enum


class RequestType(str, Enum):
    """Types of requests agents can make."""
    QUESTION = "question"
    AUTH_NEEDED = "auth_needed"
    BLOCKER = "blocker"
    DECISION = "decision"


class RequestPriority(str, Enum):
    """Request priority levels."""
    CRITICAL = "critical"
    NORMAL = "normal"
    LOW = "low"


class DevLayerClient:
    """Client for agent-to-human communication via DevLayer."""

    def __init__(
        self,
        project_name: str,
        base_url: str = "http://localhost:8888",
        timeout: int = 300,  # 5 minutes default
        poll_interval: int = 5,  # Check for response every 5 seconds
    ):
        """
        Initialize DevLayer client.

        Args:
            project_name: Name of the project (for routing)
            base_url: Base URL of AutoCoder server
            timeout: Maximum seconds to wait for human response
            poll_interval: Seconds between polling for response
        """
        self.project_name = project_name
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.poll_interval = poll_interval

    async def ask_question(
        self,
        message: str,
        context: Optional[str] = None,
        priority: RequestPriority = RequestPriority.NORMAL,
    ) -> str:
        """
        Ask human a question and wait for response.

        Args:
            message: The question to ask
            context: Optional context/details
            priority: Request priority (critical/normal/low)

        Returns:
            Human's response as string

        Raises:
            TimeoutError: If no response received within timeout
            httpx.HTTPError: If API request fails
        """
        return await self._create_and_wait(
            request_type=RequestType.QUESTION,
            message=message,
            context=context,
            priority=priority,
        )

    async def report_blocker(
        self,
        message: str,
        context: Optional[str] = None,
        priority: RequestPriority = RequestPriority.CRITICAL,
    ) -> str:
        """
        Report blocker and wait for human guidance.

        Args:
            message: Description of the blocker
            context: Optional context/error details
            priority: Priority (defaults to critical)

        Returns:
            Human's guidance/solution

        Raises:
            TimeoutError: If no response received within timeout
        """
        return await self._create_and_wait(
            request_type=RequestType.BLOCKER,
            message=message,
            context=context,
            priority=priority,
        )

    async def request_decision(
        self,
        message: str,
        context: Optional[str] = None,
        priority: RequestPriority = RequestPriority.NORMAL,
    ) -> str:
        """
        Ask human to make a decision.

        Args:
            message: The decision to be made
            context: Optional context/options
            priority: Priority level

        Returns:
            Human's decision
        """
        return await self._create_and_wait(
            request_type=RequestType.DECISION,
            message=message,
            context=context,
            priority=priority,
        )

    async def request_auth(
        self,
        service_name: str,
        key_name: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Request authentication credentials from human.

        Args:
            service_name: Name of service (e.g., "Stripe", "AWS")
            key_name: Name of the key/credential needed
            context: Optional explanation of why it's needed

        Returns:
            The credential value
        """
        message = f"I need {key_name} for {service_name}"
        if context:
            message += f": {context}"

        return await self._create_and_wait(
            request_type=RequestType.AUTH_NEEDED,
            message=message,
            context=context,
            priority=RequestPriority.CRITICAL,
        )

    async def send_chat(self, message: str) -> dict:
        """
        Send chat message (fire-and-forget, no response expected).

        Args:
            message: Message to send

        Returns:
            API response dict with id and created_at
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/api/devlayer/projects/{self.project_name}/chat",
                json={"content": message},
            )
            response.raise_for_status()
            return response.json()

    async def create_annotation(
        self,
        type: Literal["bug", "comment", "workaround", "idea"],
        content: str,
        feature_id: Optional[str] = None,
    ) -> dict:
        """
        Create annotation (bug report, comment, workaround, idea).

        Args:
            type: Type of annotation
            content: Annotation content
            feature_id: Optional feature ID to attach to

        Returns:
            API response dict with id and created_at
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/api/devlayer/projects/{self.project_name}/annotations",
                json={
                    "type": type,
                    "content": content,
                    "feature_id": feature_id,
                },
            )
            response.raise_for_status()
            return response.json()

    async def _create_and_wait(
        self,
        request_type: RequestType,
        message: str,
        context: Optional[str],
        priority: RequestPriority,
    ) -> str:
        """
        Internal: Create request and wait for human response.

        Args:
            request_type: Type of request
            message: Request message
            context: Optional context
            priority: Priority level

        Returns:
            Human's response

        Raises:
            TimeoutError: If no response within timeout
            httpx.HTTPError: If API fails
        """
        # Create request
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/api/devlayer/requests",
                json={
                    "project": self.project_name,
                    "type": request_type.value,
                    "priority": priority.value,
                    "message": message,
                    "context": context,
                },
            )
            response.raise_for_status()
            request_data = response.json()
            request_id = request_data["id"]

        print(f"[DevLayer] Created {request_type.value} request (ID: {request_id})")
        print(f"[DevLayer] Waiting for human response (timeout: {self.timeout}s)...")

        # Poll for response
        start_time = datetime.now(timezone.utc)
        max_polls = self.timeout // self.poll_interval

        for poll_count in range(max_polls):
            # Check if timed out
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed >= self.timeout:
                raise TimeoutError(
                    f"No human response received within {self.timeout}s for request {request_id}"
                )

            # Check for response
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/devlayer/requests"
                )
                response.raise_for_status()
                requests = response.json()

                # Find our request
                for req in requests:
                    if req["id"] == request_id:
                        if req["responded"]:
                            print(f"[DevLayer] Received response from human!")
                            return req["response"]
                        break

            # Wait before next poll
            await asyncio.sleep(self.poll_interval)

        # Timeout
        raise TimeoutError(
            f"No human response received within {self.timeout}s for request {request_id}"
        )


# Convenience functions for quick usage
async def ask_human(
    project: str,
    message: str,
    type: RequestType = RequestType.QUESTION,
    priority: RequestPriority = RequestPriority.NORMAL,
    context: Optional[str] = None,
) -> str:
    """
    Quick helper: Ask human a question.

    Usage:
        response = await ask_human("my-app", "Should I use REST or GraphQL?")
    """
    client = DevLayerClient(project_name=project)
    return await client._create_and_wait(type, message, context, priority)
