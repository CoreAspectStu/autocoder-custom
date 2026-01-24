#!/usr/bin/env python3
"""
Mission Control MCP Server

Exposes DevLayer capabilities as MCP tools for AutoCoder agents.

Tools provided:
- devlayer_ask_question: Ask human a question
- devlayer_report_blocker: Report blocker and get guidance
- devlayer_request_decision: Request human decision
- devlayer_request_auth: Request credentials
- devlayer_send_chat: Send chat message
- devlayer_create_annotation: Create bug/idea/workaround note
"""

import asyncio
import sys
import os
from pathlib import Path

# Add autocoder root to path for imports
AUTOCODER_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(AUTOCODER_ROOT))

from mcp.server import Server
from mcp.types import Tool, TextContent
from custom.mission_control.client import DevLayerClient, RequestPriority, RequestType

# Get project name from environment (set by client.py)
PROJECT_NAME = os.environ.get("PROJECT_NAME", "unknown")

# Create DevLayer client
devlayer = DevLayerClient(project_name=PROJECT_NAME)

# Initialize MCP server
server = Server("mission-control")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available DevLayer tools."""
    return [
        Tool(
            name="devlayer_ask_question",
            description=(
                "Ask human a question and wait for response. "
                "Use when you need clarification, user input, or guidance. "
                "Examples: 'Should I use REST or GraphQL?', 'Which database should I use?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The question to ask the human"
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context or details"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["critical", "normal", "low"],
                        "description": "Priority level (default: normal)"
                    }
                },
                "required": ["message"]
            }
        ),
        Tool(
            name="devlayer_report_blocker",
            description=(
                "Report blocker and request human guidance. "
                "Use when you're stuck and cannot proceed. "
                "Examples: 'Database migration failed', 'API endpoint returns 404', 'Missing credentials'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Description of the blocker"
                    },
                    "context": {
                        "type": "string",
                        "description": "Error details, stack trace, or context"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["critical", "normal"],
                        "description": "Priority (default: critical)"
                    }
                },
                "required": ["message"]
            }
        ),
        Tool(
            name="devlayer_request_decision",
            description=(
                "Ask human to make a decision between options. "
                "Use when there are multiple valid approaches and you need human input. "
                "Examples: 'Monolith or microservices?', 'TypeScript or JavaScript?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The decision to be made"
                    },
                    "context": {
                        "type": "string",
                        "description": "Options, tradeoffs, or background"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["critical", "normal", "low"],
                        "description": "Priority level (default: normal)"
                    }
                },
                "required": ["message"]
            }
        ),
        Tool(
            name="devlayer_request_auth",
            description=(
                "Request authentication credentials from human. "
                "Use when you need API keys, tokens, or secrets. "
                "Examples: 'STRIPE_API_KEY', 'AWS_ACCESS_KEY_ID', 'DATABASE_PASSWORD'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service (e.g., 'Stripe', 'AWS', 'Database')"
                    },
                    "key_name": {
                        "type": "string",
                        "description": "Name of the credential (e.g., 'STRIPE_API_KEY')"
                    },
                    "context": {
                        "type": "string",
                        "description": "Why you need it"
                    }
                },
                "required": ["service_name", "key_name"]
            }
        ),
        Tool(
            name="devlayer_send_chat",
            description=(
                "Send chat message to human (fire-and-forget, no response expected). "
                "Use for status updates, progress reports, or notifications. "
                "Examples: 'Starting database migration', 'Tests passing', 'Deployment complete'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to send"
                    }
                },
                "required": ["message"]
            }
        ),
        Tool(
            name="devlayer_create_annotation",
            description=(
                "Create annotation (bug, comment, workaround, idea). "
                "Use to document issues, workarounds, or ideas for later. "
                "Examples: 'Bug: auth API is flaky', 'Idea: add dark mode', 'Workaround: retry 3x'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["bug", "comment", "workaround", "idea"],
                        "description": "Type of annotation"
                    },
                    "content": {
                        "type": "string",
                        "description": "Annotation content"
                    },
                    "feature_id": {
                        "type": "string",
                        "description": "Optional feature ID to attach to"
                    }
                },
                "required": ["type", "content"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "devlayer_ask_question":
            message = arguments["message"]
            context = arguments.get("context")
            priority = RequestPriority(arguments.get("priority", "normal"))

            response = await devlayer.ask_question(message, context, priority)
            return [TextContent(type="text", text=f"Human response: {response}")]

        elif name == "devlayer_report_blocker":
            message = arguments["message"]
            context = arguments.get("context")
            priority = RequestPriority(arguments.get("priority", "critical"))

            response = await devlayer.report_blocker(message, context, priority)
            return [TextContent(type="text", text=f"Human guidance: {response}")]

        elif name == "devlayer_request_decision":
            message = arguments["message"]
            context = arguments.get("context")
            priority = RequestPriority(arguments.get("priority", "normal"))

            response = await devlayer.request_decision(message, context, priority)
            return [TextContent(type="text", text=f"Human decision: {response}")]

        elif name == "devlayer_request_auth":
            service_name = arguments["service_name"]
            key_name = arguments["key_name"]
            context = arguments.get("context")

            credential = await devlayer.request_auth(service_name, key_name, context)
            return [TextContent(type="text", text=f"Credential: {credential}")]

        elif name == "devlayer_send_chat":
            message = arguments["message"]
            result = await devlayer.send_chat(message)
            return [TextContent(type="text", text=f"Chat message sent (ID: {result['id']})")]

        elif name == "devlayer_create_annotation":
            ann_type = arguments["type"]
            content = arguments["content"]
            feature_id = arguments.get("feature_id")

            result = await devlayer.create_annotation(ann_type, content, feature_id)
            return [TextContent(type="text", text=f"Annotation created (ID: {result['id']})")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
