import os
import asyncio
from mcp.server.fastmcp import FastMCP
from typing import Dict, List, Optional
import json

mcp = FastMCP("SteadyFlow Log Analyzer")

# Workspace state
workspace = {
    "scratchpad": "",
    "documents": {}, # name -> content
    "marks": [],     # list of {path, line, type, comment}
    "tracked_files": {} # path -> last_seen_size
}

@mcp.tool()
async def follow_log(path: str) -> str:
    """Add a log file to the tracked files list."""
    if not os.path.exists(path):
        return f"Error: File '{path}' does not exist."
    
    workspace["tracked_files"][path] = os.path.getsize(path)
    return f"Now following log: {path}"

@mcp.tool()
async def read_logs(path: str, lines: int = 50) -> str:
    """Read the last N lines from a log file."""
    if not os.path.exists(path):
        return f"Error: File '{path}' does not exist."
    
    try:
        with open(path, 'r') as f:
            content = f.readlines()
            last_lines = content[-lines:]
            return "".join(last_lines)
    except Exception as e:
        return f"Error reading log: {str(e)}"

@mcp.tool()
async def wait_for_pattern(path: str, pattern: str, timeout: int = 10) -> str:
    """Wait for a specific string pattern to appear in a log file."""
    if not os.path.exists(path):
        return f"Error: File '{path}' does not exist."
    
    import re
    start_time = asyncio.get_event_loop().time()
    
    # Get current position
    file_size = os.path.getsize(path)
    
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        if os.path.getsize(path) > file_size:
            with open(path, 'r') as f:
                f.seek(file_size)
                new_content = f.read()
                if re.search(pattern, new_content):
                    return f"Pattern '{pattern}' found in {path}."
            file_size = os.path.getsize(path)
        await asyncio.sleep(0.5)
        
    return f"Timeout: Pattern '{pattern}' not found in {path} after {timeout}s."

@mcp.tool()
async def update_scratchpad(content: str) -> str:
    """Append or update the scratchpad notes."""
    workspace["scratchpad"] += f"\n---\n{content}"
    return "Scratchpad updated."

@mcp.tool()
async def add_document(name: str, content: str) -> str:
    """Save a significant finding or code snippet as a reference document."""
    workspace["documents"][name] = content
    return f"Document '{name}' added to workspace."

@mcp.tool()
async def discard_document(name: str) -> str:
    """Remove a document from the workspace."""
    if name in workspace["documents"]:
        del workspace["documents"][name]
        return f"Document '{name}' removed."
    return f"Document '{name}' not found."

@mcp.tool()
async def mark_log_entry(path: str, line_no: int, entry_type: str, comment: str) -> str:
    """Mark a specific log entry (line) with a comment or tag."""
    mark = {
        "path": path,
        "line": line_no,
        "type": entry_type, # e.g., 'comment', 'code', 'error'
        "comment": comment
    }
    workspace["marks"].append(mark)
    return f"Marked line {line_no} in {path} as {entry_type}."

@mcp.tool()
async def analyze_workspace() -> str:
    """Return a summary of the current workspace state for analysis."""
    report = [
        "# LOG ANALYSIS WORKSPACE REPORT",
        f"\n## SCRATCHPAD\n{workspace['scratchpad']}",
        "\n## DOCUMENTS",
    ]
    for name, content in workspace["documents"].items():
        report.append(f"### {name}\n{content}")
    
    report.append("\n## ANNOTATIONS")
    for mark in workspace["marks"]:
        report.append(f"- [{mark['type'].upper()}] {mark['path']}:L{mark['line']} -> {mark['comment']}")
    
    return "\n".join(report)

if __name__ == "__main__":
    mcp.run()
