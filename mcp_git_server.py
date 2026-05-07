import os
import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Git")

def run_git(args, cwd=None):
    if cwd is None:
        cwd = os.getcwd()
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return result.stdout

@mcp.tool()
def git_status(repo_path: str = "."):
    """Get the current status of the git repository."""
    return run_git(["status"], cwd=repo_path)

@mcp.tool()
def git_log(repo_path: str = ".", limit: int = 5):
    """Get the commit history."""
    return run_git(["log", f"-n {limit}", "--oneline"], cwd=repo_path)

@mcp.tool()
def git_diff(repo_path: str = ".", cached: bool = False):
    """Get the changes in the repository."""
    args = ["diff"]
    if cached: args.append("--cached")
    return run_git(args, cwd=repo_path)

@mcp.tool()
def git_add(file_pattern: str, repo_path: str = "."):
    """Stage files for commit."""
    return run_git(["add", file_pattern], cwd=repo_path)

@mcp.tool()
def git_commit(message: str, repo_path: str = "."):
    """Commit staged changes."""
    return run_git(["commit", "-m", message], cwd=repo_path)

if __name__ == "__main__":
    mcp.run()
