"""
MCP Server management for boomtick-cli.
"""
import subprocess
from dev_tools.utils import resolve_resource_path

class NodeNotFoundError(RuntimeError):
    """Raised when Node.js is not found on the PATH."""


def start_mcp_server():
    """
    Spawns the TypeScript MCP server as a Node.js subprocess.
    """
    try:
        server_js = resolve_resource_path("dist/index.js")
    except FileNotFoundError as e:
        raise RuntimeError(
            f"MCP server source file not found: {e}. "
            "Ensure the package is correctly installed with bundled JS artifacts."
        ) from e

    # Spawn Node subprocess to communicate via standard I/O pipes
    try:
        return subprocess.Popen(
            ["node", server_js],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except FileNotFoundError as e:
        raise NodeNotFoundError(
            "Node.js is required to run the MCP server but was not found on the PATH. "
            "Please install Node.js 24+ and try again."
        ) from e
