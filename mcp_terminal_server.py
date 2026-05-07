import os
import asyncio
import subprocess
from mcp.server.fastmcp import FastMCP
from typing import Dict

mcp = FastMCP("SteadyFlow Terminal")

# Store session state (cwd for now, but can be expanded)
sessions: Dict[str, Dict] = {}

@mcp.tool()
async def create_session(session_id: str, cwd: str = "/home/neo/Desktop/SteadyFlow") -> str:
    """Initialize a new terminal session with a specific ID and working directory."""
    if session_id in sessions:
        return f"Session '{session_id}' already exists."
    
    if not os.path.exists(cwd):
        return f"Error: Directory '{cwd}' does not exist."
    
    sessions[session_id] = {"cwd": cwd, "history": []}
    return f"Session '{session_id}' created at {cwd}."

@mcp.tool()
async def run_in_session(session_id: str, command: str, background: bool = False) -> str:
    """Execute a command. If background=True, it starts long-running processes without waiting."""
    if session_id not in sessions:
        return f"Error: Session '{session_id}' not found."
    
    state = sessions[session_id]
    try:
        if command.startswith("cd "):
            new_path = os.path.abspath(os.path.join(state["cwd"], command[3:].strip()))
            if os.path.isdir(new_path):
                state["cwd"] = new_path
                return f"Changed directory to {new_path}"
            return f"Error: {new_path} is not a directory."

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=state["cwd"]
        )
        
        if background:
            # For background tasks, we don't wait for completion
            state["history"].append({"cmd": command, "output": "[Background Process Started]"})
            return f"[{session_id}] $ {command}\n[Process started in background]"

        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30.0)
        result = stdout.decode().strip()
        state["history"].append({"cmd": command, "output": result})
        return f"[{session_id}] $ {command}\n{result}"
    except asyncio.TimeoutError:
        try: process.kill()
        except: pass
        return f"Error: Command timed out in session '{session_id}'."
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def close_session(session_id: str) -> str:
    """Close a terminal session and clean up its resources."""
    if session_id in sessions:
        del sessions[session_id]
        return f"Session '{session_id}' closed."
    return f"Session '{session_id}' not found."

@mcp.tool()
async def list_sessions() -> str:
    """List all active terminal sessions."""
    if not sessions:
        return "No active sessions."
    return "Active sessions:\n" + "\n".join([f"- {s} ({sessions[s]['cwd']})" for s in sessions])

if __name__ == "__main__":
    mcp.run()
