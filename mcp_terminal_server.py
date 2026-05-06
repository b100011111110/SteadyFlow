import os
import asyncio
import subprocess
from mcp.server.fastmcp import FastMCP

# Create an MCP server for terminal access
mcp = FastMCP("SteadyFlow Terminal")

@mcp.tool()
async def run_command(command: str) -> str:
    """Execute a shell command in the terminal and return the output."""
    try:
        # Run the command and capture output
        # We use a limited timeout to prevent hanging
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd="/home/neo/Desktop/SteadyFlow"
        )
        
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30.0)
            result = stdout.decode().strip()
            return f"Command: {command}\nOutput:\n{result}"
        except asyncio.TimeoutError:
            process.kill()
            return f"Error: Command '{command}' timed out after 30 seconds."
            
    except Exception as e:
        return f"Error executing command: {str(e)}"

if __name__ == "__main__":
    mcp.run()
