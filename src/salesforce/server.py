# /// script
# dependencies = [
#   "mcp",
#   "simple-salesforce",
#   "python-dotenv"
# ]
# ///
import asyncio
import json
import os
from typing import Any, Optional
from dotenv import load_dotenv

from simple_salesforce import Salesforce, SalesforceError

import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio


class SalesforceClient:
    """Handles Salesforce operations and caching."""

    def __init__(self):
        self.sf: Optional[Salesforce] = None
        self.sobjects_cache: dict[str, Any] = {}

    def connect(self) -> bool:
        """Establishes connection to Salesforce using environment variables."""
        try:
            access_token = os.getenv('SALESFORCE_ACCESS_TOKEN')
            instance_url = os.getenv('SALESFORCE_INSTANCE_URL')
            domain = os.getenv('SALESFORCE_DOMAIN')

            if access_token and instance_url:
                self.sf = Salesforce(instance_url=instance_url, session_id=access_token, domain=domain)
                return True

            self.sf = Salesforce(
                username=os.getenv('SALESFORCE_USERNAME'),
                password=os.getenv('SALESFORCE_PASSWORD'),
                security_token=os.getenv('SALESFORCE_SECURITY_TOKEN'),
                domain=domain,
            )
            return True
        except Exception as e:
            print(f"Salesforce connection failed: {str(e)}")
            return False

    def get_object_fields(self, object_name: str) -> str:
        """Retrieves field metadata for a specific Salesforce object."""
        if not self.sf:
            raise ValueError("Salesforce connection not established.")
        if object_name not in self.sobjects_cache:
            sf_object = getattr(self.sf, object_name)
            fields = sf_object.describe()['fields']
            filtered_fields = [
                {
                    'label': f['label'],
                    'name': f['name'],
                    'updateable': f['updateable'],
                    'type': f['type'],
                    'length': f['length'],
                    'picklistValues': f['picklistValues'],
                }
                for f in fields
            ]
            self.sobjects_cache[object_name] = filtered_fields
        return json.dumps(self.sobjects_cache[object_name], indent=2)


# --- MCP Server Setup ---
server = Server("salesforce-mcp")
load_dotenv()

sf_client = SalesforceClient()
sf_client.connect()

# Choose output mode
RESPONSE_FORMAT = os.getenv("SALESFORCE_RESPONSE_FORMAT", "text").lower()


def format_response(data: Any) -> list[types.TextContent]:
    """Formats output as JSON or text depending on env var."""
    if RESPONSE_FORMAT == "json":
        formatted = json.dumps(data, indent=2)
    else:
        formatted = str(data)
    return [types.TextContent(type="text", text=formatted)]


def format_error(err: Exception) -> list[types.TextContent]:
    """Formats errors consistently based on env var."""
    if RESPONSE_FORMAT == "json":
        formatted = json.dumps({"error": str(err)}, indent=2)
    else:
        formatted = f"Error: {str(err)}"
    return [types.TextContent(type="text", text=formatted)]

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List all available Salesforce tools."""
    return [
        types.Tool(
            name="run_soql_query",
            description="Executes a SOQL query against Salesforce",
            inputSchema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        ),
        types.Tool(
            name="run_sosl_search",
            description="Executes a SOSL search against Salesforce",
            inputSchema={"type": "object", "properties": {"search": {"type": "string"}}, "required": ["search"]},
        ),
        types.Tool(
            name="get_object_fields",
            description="Retrieves field metadata for a Salesforce object",
            inputSchema={"type": "object", "properties": {"object_name": {"type": "string"}}, "required": ["object_name"]},
        ),
        types.Tool(
            name="get_record",
            description="Retrieves a record by ID",
            inputSchema={
                "type": "object",
                "properties": {"object_name": {"type": "string"}, "record_id": {"type": "string"}},
                "required": ["object_name", "record_id"],
            },
        ),
        types.Tool(
            name="create_record",
            description="Creates a new record",
            inputSchema={
                "type": "object",
                "properties": {"object_name": {"type": "string"}, "data": {"type": "object", "additionalProperties": True}},
                "required": ["object_name", "data"],
            },
        ),
        types.Tool(
            name="update_record",
            description="Updates an existing record",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "record_id": {"type": "string"},
                    "data": {"type": "object", "additionalProperties": True},
                },
                "required": ["object_name", "record_id", "data"],
            },
        ),
        types.Tool(
            name="delete_record",
            description="Deletes a record",
            inputSchema={
                "type": "object",
                "properties": {"object_name": {"type": "string"}, "record_id": {"type": "string"}},
                "required": ["object_name", "record_id"],
            },
        ),
        types.Tool(
            name="tooling_execute",
            description="Executes a Tooling API request",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PATCH", "DELETE"], "default": "GET"},
                    "data": {"type": "object", "additionalProperties": True},
                },
                "required": ["action"],
            },
        ),
        types.Tool(
            name="apex_execute",
            description="Executes an Apex REST request",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PATCH", "DELETE"], "default": "GET"},
                    "data": {"type": "object", "additionalProperties": True},
                },
                "required": ["action"],
            },
        ),
        types.Tool(
            name="restful",
            description="Makes a direct REST API call to Salesforce",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PATCH", "DELETE"], "default": "GET"},
                    "params": {"type": "object", "additionalProperties": True},
                    "data": {"type": "object", "additionalProperties": True},
                },
                "required": ["path"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls dynamically with clean, optionally JSON responses."""
    try:
        if not sf_client.sf:
            raise ValueError("Salesforce connection not established.")

        sf = sf_client.sf

        if name == "run_soql_query":
            return format_response(sf.query_all(arguments["query"]))

        elif name == "run_sosl_search":
            return format_response(sf.search(arguments["search"]))

        elif name == "get_object_fields":
            return format_response(json.loads(sf_client.get_object_fields(arguments["object_name"])))

        elif name == "get_record":
            sf_object = getattr(sf, arguments["object_name"])
            return format_response(sf_object.get(arguments["record_id"]))

        elif name == "create_record":
            sf_object = getattr(sf, arguments["object_name"])
            return format_response(sf_object.create(arguments["data"]))

        elif name == "update_record":
            sf_object = getattr(sf, arguments["object_name"])
            sf_object.update(arguments["record_id"], arguments["data"])
            return format_response({"success": True})

        elif name == "delete_record":
            sf_object = getattr(sf, arguments["object_name"])
            sf_object.delete(arguments["record_id"])
            return format_response({"success": True})

        elif name == "tooling_execute":
            return format_response(
                sf.toolingexecute(arguments["action"], method=arguments.get("method", "GET"), data=arguments.get("data"))
            )

        elif name == "apex_execute":
            return format_response(
                sf.apexecute(arguments["action"], method=arguments.get("method", "GET"), data=arguments.get("data"))
            )

        elif name == "restful":
            return format_response(
                sf.restful(
                    arguments["path"],
                    method=arguments.get("method", "GET"),
                    params=arguments.get("params"),
                    json=arguments.get("data"),
                )
            )

        raise ValueError(f"Unknown tool: {name}")

    except SalesforceError as e:
        return format_error(e)
    except Exception as e:
        return format_error(e)


async def run():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="salesforce-mcp",
                server_version="0.1.7",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run())
