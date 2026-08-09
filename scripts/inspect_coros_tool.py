from __future__ import annotations

import argparse
import asyncio
import json

from runcrew.providers.coros.mcp import CorosMcpClient
from runcrew.providers.coros.oauth import CorosOAuthClient


async def inspect_tool(tool_name: str) -> int:
    token = await CorosOAuthClient().authorize()
    client = CorosMcpClient(token.access_token)
    try:
        await client.initialize()
        tools = await client.list_tools()
        matches = [tool for tool in tools if tool.get("name") == tool_name]
        if not matches:
            print(f"COROS MCP tool not found: {tool_name}")
            return 1
        print(json.dumps(matches[0], ensure_ascii=False, indent=2))
        return 0
    finally:
        await client.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print one COROS MCP tool schema without calling the tool."
    )
    parser.add_argument("tool_name")
    arguments = parser.parse_args()
    return asyncio.run(inspect_tool(arguments.tool_name))


if __name__ == "__main__":
    raise SystemExit(main())
