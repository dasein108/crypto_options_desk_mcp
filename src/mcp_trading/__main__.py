"""Entry point: python -m mcp_trading"""

import logging
import os

# MCP uses stdio for JSON-RPC — all logging must go to file, never console.
_log_file = os.environ.get("MCP_LOG_FILE", "/tmp/mcp-trading.log")
_log_level = logging.DEBUG if os.environ.get("DEBUG_MCP") else logging.WARNING

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=_log_file,
    force=True,
)


def main():
    from .server import mcp
    mcp.run()


if __name__ == "__main__":
    main()
