import os
import asyncio
from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("SteadyFlow Filesystem")

@mcp.tool()
async def read_file(path: str) -> str:
    """Read the contents of a file."""
    # Ensure the path is within the workspace
    abs_path = os.path.abspath(path)
    if not abs_path.startswith("/home/neo/Desktop/SteadyFlow"):
        return "Error: Access denied. Path is outside workspace."
    
    try:
        with open(abs_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    abs_path = os.path.abspath(path)
    if not abs_path.startswith("/home/neo/Desktop/SteadyFlow"):
        return "Error: Access denied. Path is outside workspace."
    
    try:
        with open(abs_path, "w") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

@mcp.tool()
async def list_directory(path: str = ".") -> str:
    """List contents of a directory."""
    abs_path = os.path.abspath(path)
    if not abs_path.startswith("/home/neo/Desktop/SteadyFlow"):
        return "Error: Access denied. Path is outside workspace."
    
    try:
        items = os.listdir(abs_path)
        return "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {str(e)}"

if __name__ == "__main__":
    mcp.run()
