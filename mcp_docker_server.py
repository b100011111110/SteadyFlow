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

# Store containers started by this server
started_containers = []

@mcp.tool()
def run_container(image: str, name: str = None, command: str = None):
    """Run a new docker container and track it for cleanup."""
    args = ["run", "-d"]
    if name: args.extend(["--name", name])
    args.append(image)
    if command: args.extend(command.split())
    
    res = run_docker(args)
    if not res.startswith("Error"):
        container_id = res.strip()
        started_containers.append(container_id)
        return f"Container started: {container_id}"
    return res

@mcp.tool()
def cleanup_all():
    """Stop and remove all containers started by this server."""
    count = 0
    for container_id in started_containers:
        run_docker(["stop", container_id])
        run_docker(["rm", container_id])
        count += 1
    started_containers.clear()
    return f"Cleanup complete. {count} containers removed."

if __name__ == "__main__":
    mcp.run()

