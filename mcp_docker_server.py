import os
import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Docker")

def run_docker(args):
    result = subprocess.run(["docker"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout

@mcp.tool()
def list_containers(all: bool = False):
    """List docker containers."""
    args = ["ps"]
    if all: args.append("-a")
    return run_docker(args)

@mcp.tool()
def list_images():
    """List docker images."""
    return run_docker(["images"])

@mcp.tool()
def container_stats():
    """Get real-time stats for containers."""
    return run_docker(["stats", "--no-stream"])

@mcp.tool()
def docker_exec(container_id: str, command: str):
    """Execute a command in a running container."""
    return run_docker(["exec", container_id] + command.split())

if __name__ == "__main__":
    mcp.run()
