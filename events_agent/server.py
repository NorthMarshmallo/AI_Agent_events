"""Совместимый импорт серверной стороны MCP."""

from .mcp_server.server import INSTRUCTIONS, Query, build, checked, main

__all__ = ["INSTRUCTIONS", "Query", "build", "checked", "main"]


if __name__ == "__main__":
    main()
