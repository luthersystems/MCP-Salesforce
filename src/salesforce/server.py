# /// script
# dependencies = [
#   "mcp",
#   "simple-salesforce",
#   "python-dotenv"
# ]
# ///
import asyncio
import json
from typing import Any, Optional
import os
from dotenv import load_dotenv

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

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
            access_token = os.getenv("SALESFORCE_ACCESS_TOKEN")
            instance_url = os.getenv("SALESFORCE_INSTANCE_URL")
            domain = os.getenv("SALESFORCE_DOMAIN")
            if access_token and instance_url:
                self.sf = Salesforce(instance_url=instance_url, session_id=access_token, domain=domain)
                return True

            self.sf = Salesforce(
                username=os.getenv("SALESFORCE_USERNAME"),
                password=os.getenv("SALESFORCE_PASSWORD"),
                security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
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
            fields = sf_object.describe()["fields"]
            filtered_fields = []
            for field in fields:
                filtered_fields.append(
                    {
                        "label": field["label"],
                        "name": field["name"],
                        "updateable": field["updateable"],
                        "type": field["type"],
                        "length": field["length"],
                        "picklistValues": field["picklistValues"],
                    }
                )
            self.sobjects_cache[object_name] = filtered_fields

        return json.dumps(self.sobjects_cache[object_name], indent=2)


# --- Server Setup ---
server = Server("salesforce-mcp")

load_dotenv()

sf_client = SalesforceClient()
if not sf_client.connect():
    print("Failed to initialize Salesforce connection")

# Choose response format
RESPONSE_FORMAT = os.getenv("SALESFORCE_RESPONSE_FORMAT", "text").lower()


def format_response(title: str, data: Any) -> list[types.TextContent]:
    """Return old prefixed text by default, or JSON when configured."""
    if RESPONSE_FORMAT == "json":
        formatted = json.dumps(data, indent=2)
    else:
        formatted = f"{title} (JSON):\n{json.dumps(data, indent=2)}"
    return [types.TextContent(type="text", text=formatted)]


def format_error(err: Exception) -> list[types.TextContent]:
    """Formats errors consistently."""
    if RESPONSE_FORMAT == "json":
        formatted = json.dumps({"error": str(err)}, indent=2)
    else:
        formatted = f"Error: {str(err)}"
    return [types.TextContent(type="text", text=formatted)]


# --- Tools ---
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Salesforce tools."""
    return [
        types.Tool(
            name="run_soql_query",
            description="Executes a SOQL query against Salesforce",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The SOQL query to execute"}},
                "required": ["query"],
            },
        ),
        types.Tool(
            name="run_sosl_search",
            description="Executes a SOSL search against Salesforce",
            inputSchema={
                "type": "object",
                "properties": {"search": {"type": "string", "description": "The SOSL search to execute"}},
                "required": ["search"],
            },
        ),
        types.Tool(
            name="get_object_fields",
            description="Retrieves field Names, labels and types for a specific Salesforce object",
            inputSchema={
                "type": "object",
                "properties": {"object_name": {"type": "string", "description": "Salesforce object name"}},
                "required": ["object_name"],
            },
        ),
        types.Tool(
            name="get_record",
            description="Retrieves a specific record by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "record_id": {"type": "string"},
                },
                "required": ["object_name", "record_id"],
            },
        ),
        types.Tool(
            name="create_record",
            description="Creates a new record",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "data": {"type": "object", "additionalProperties": True},
                },
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
                "properties": {
                    "object_name": {"type": "string"},
                    "record_id": {"type": "string"},
                },
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
    try:
        if not sf_client.sf:
            raise ValueError("Salesforce connection not established.")

        if name == "run_soql_query":
            query = arguments.get("query")
            if not query:
                raise ValueError("Missing 'query' argument")
            results = sf_client.sf.query_all(query)
            return format_response("SOQL Query Results", results)

        elif name == "run_sosl_search":
            search = arguments.get("search")
            if not search:
                raise ValueError("Missing 'search' argument")
            results = sf_client.sf.search(search)
            return format_response("SOSL Search Results", results)

        elif name == "get_object_fields":
            object_name = arguments.get("object_name")
            if not object_name:
                raise ValueError("Missing 'object_name' argument")
            results = sf_client.get_object_fields(object_name)
            return format_response(f"{object_name} Metadata", json.loads(results))

        elif name == "get_record":
            sf_object = getattr(sf_client.sf, arguments["object_name"])
            results = sf_object.get(arguments["record_id"])
            return format_response(f"{arguments['object_name']} Record", results)

        elif name == "create_record":
            sf_object = getattr(sf_client.sf, arguments["object_name"])
            results = sf_object.create(arguments["data"])
            return format_response(f"Create {arguments['object_name']} Record Result", results)

        elif name == "update_record":
            sf_object = getattr(sf_client.sf, arguments["object_name"])
            sf_object.update(arguments["record_id"], arguments["data"])
            return format_response(f"Update {arguments['object_name']} Record Result", {"success": True})

        elif name == "delete_record":
            sf_object = getattr(sf_client.sf, arguments["object_name"])
            sf_object.delete(arguments["record_id"])
            return format_response(f"Delete {arguments['object_name']} Record Result", {"success": True})

        elif name == "tooling_execute":
            results = sf_client.sf.toolingexecute(
                arguments["action"], method=arguments.get("method", "GET"), data=arguments.get("data")
            )
            return format_response("Tooling Execute Result", results)

        elif name == "apex_execute":
            results = sf_client.sf.apexecute(
                arguments["action"], method=arguments.get("method", "GET"), data=arguments.get("data")
            )
            return format_response("Apex Execute Result", results)

        elif name == "restful":
            results = sf_client.sf.restful(
                arguments["path"],
                method=arguments.get("method", "GET"),
                params=arguments.get("params"),
                json=arguments.get("data"),
            )
            return format_response("RESTful API Call Result", results)

        raise ValueError(f"Unknown tool: {name}")

    except SalesforceError as e:
        return format_error(e)
    except Exception as e:
        return format_error(e)


# --- Main Entry ---
async def run():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="salesforce-mcp",
                server_version="0.1.9",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Salesforce MCP server stopped.")
