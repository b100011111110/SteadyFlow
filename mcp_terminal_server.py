import os
import asyncio
import subprocess
import signal
from mcp.server.fastmcp import FastMCP
from typing import Dict, List

mcp = FastMCP("SteadyFlow Terminal")

# Store session state
# sessions[session_id] = {"cwd": str, "processes": List[asyncio.subprocess.Process]}
sessions: Dict[str, Dict] = {}

@mcp.tool()
async def create_session(session_id: str, cwd: str = "/home/neo/Desktop/SteadyFlow") -> str:
    """Initialize a new terminal session with a specific ID and working directory."""
    if session_id in sessions:
        return f"Session '{session_id}' already exists."
    
    if not os.path.exists(cwd):
        return f"Error: Directory '{cwd}' does not exist."
    
    sessions[session_id] = {"cwd": cwd, "processes": []}
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
            cwd=state["cwd"],
            preexec_fn=os.setsid # Create a new process group to allow killing children
        )
        
        state["processes"].append(process)

        if background:
            return f"[{session_id}] $ {command}\n[Process started in background (PID: {process.pid})]"

        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60.0)
            result = stdout.decode().strip()
            if process in state["processes"]:
                state["processes"].remove(process)
            return f"[{session_id}] $ {command}\n{result}"
        except asyncio.TimeoutError:
            await kill_process_group(process)
            if process in state["processes"]:
                state["processes"].remove(process)
            return f"Error: Command timed out in session '{session_id}'."

    except Exception as e:
        return f"Error: {str(e)}"

async def kill_process_group(process):
    """Kill a process and all its children."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        await asyncio.sleep(0.5)
        if process.returncode is None:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception:
        try: process.kill()
        except: pass

@mcp.tool()
async def close_session(session_id: str) -> str:
    """Close a terminal session and kill all its active processes."""
    if session_id in sessions:
        state = sessions[session_id]
        for p in state["processes"]:
            await kill_process_group(p)
        del sessions[session_id]
        return f"Session '{session_id}' closed and processes terminated."
    return f"Session '{session_id}' not found."

@mcp.tool()
async def cleanup_all() -> str:
    """Kill all processes in all sessions."""
    count = 0
    for session_id in list(sessions.keys()):
        state = sessions[session_id]
        for p in state["processes"]:
            await kill_process_group(p)
            count += 1
        del sessions[session_id]
    return f"Cleanup complete. {count} processes terminated."

@mcp.tool()
async def list_sessions() -> str:
    """List all active terminal sessions and their process counts."""
    if not sessions:
        return "No active sessions."
    res = ["Active sessions:"]
    for s, data in sessions.items():
        res.append(f"- {s} ({data['cwd']}) - {len(data['processes'])} active processes")
    return "\n".join(res)

def run():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Setup signal handlers for graceful shutdown
    async def shutdown_signal():
        print("Received shutdown signal, cleaning up processes...")
        await cleanup_all()
        loop.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown_signal()))

    try:
        mcp.run()
    finally:
        # Final safety cleanup if loop is still running or closed
        if not loop.is_closed():
            loop.run_until_complete(cleanup_all())
            loop.close()

if __name__ == "__main__":
    run()


