from __future__ import annotations

import argparse
import os

from .server import build_mcp

DEFAULT_ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "dawarich-mcp",
    "dawarich-mcp.dawarich",
    "dawarich-mcp.dawarich.svc",
    "dawarich-mcp.dawarich.svc.cluster.local",
]


def allowed_hosts_from_env() -> list[str]:
    configured = os.environ.get("MCP_ALLOWED_HOSTS")
    if configured is None:
        return DEFAULT_ALLOWED_HOSTS

    return [host.strip() for host in configured.split(",") if host.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Dawarich FastMCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    args = parser.parse_args()

    mcp = build_mcp()
    if args.transport == "http":
        mcp.run(
            transport="http",
            host=args.host,
            port=args.port,
            allowed_hosts=allowed_hosts_from_env(),
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
