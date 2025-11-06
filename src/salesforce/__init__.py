from . import server
import asyncio


def main():
    """Main entry point for the Salesforce MCP package."""
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("Salesforce MCP server stopped.")
    except Exception as e:
        print(f"Server exited with error: {e}")


__all__ = ["main", "server"]
