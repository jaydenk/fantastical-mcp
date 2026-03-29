"""FastMCP server with tool definitions for Fantastical calendar."""

import os
from fastmcp import FastMCP

TRANSPORT = os.environ.get("FANTASTICAL_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("FANTASTICAL_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("FANTASTICAL_MCP_PORT", "8000"))

mcp = FastMCP("Fantastical")


def main():
    if TRANSPORT == "sse":
        mcp.run(transport="sse", host=HTTP_HOST, port=HTTP_PORT)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
