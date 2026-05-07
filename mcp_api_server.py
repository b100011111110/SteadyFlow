import asyncio
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional, Dict, Any, List
import json
import os

mcp = FastMCP("SteadyFlow API (Curl+)")

# API Workspace State
workspace = {
    "env": {},       # key -> value (e.g. BASE_URL)
    "history": [],   # list of {request, response}
    "collections": {} # name -> list of requests
}

@mcp.tool()
async def api_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[str] = None,
    use_env: bool = True
) -> str:
    """Make an HTTP request, optionally using environment variables (e.g. {{BASE_URL}})."""
    
    # Process env variables in URL
    processed_url = url
    if use_env:
        for k, v in workspace["env"].items():
            processed_url = processed_url.replace(f"{{{{{k}}}}}", v)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            start_time = asyncio.get_event_loop().time()
            response = await client.request(
                method=method.upper(),
                url=processed_url,
                headers=headers,
                content=data,
                timeout=30.0
            )
            duration = asyncio.get_event_loop().time() - start_time
            
            res_data = {
                "status": response.status_code,
                "body": response.text[:1000], # Cap for history
                "headers": dict(response.headers),
                "duration": f"{duration:.2f}s"
            }
            
            entry = {
                "url": processed_url,
                "method": method,
                "response": res_data
            }
            workspace["history"].append(entry)
            
            return f"Status: {response.status_code}\nDuration: {duration:.2f}s\n\n{response.text}"
        except Exception as e:
            return f"Error: {str(e)}"

@mcp.tool()
async def manage_env(action: str, key: str, value: Optional[str] = None) -> str:
    """Manage API environment variables. action: 'set', 'get', 'list'."""
    if action == "set":
        workspace["env"][key] = value
        return f"Env {key} set to {value}"
    elif action == "get":
        return workspace["env"].get(key, "Not found")
    elif action == "list":
        return json.dumps(workspace["env"], indent=2)
    return "Invalid action"

@mcp.tool()
async def get_api_history() -> str:
    """Get a list of recent API requests."""
    return json.dumps(workspace["history"][-10:], indent=2)

@mcp.tool()
async def analyze_response(index: int = -1) -> str:
    """Prepare the last API response for AI analysis."""
    if not workspace["history"]:
        return "No history found."
    entry = workspace["history"][index]
    return f"URL: {entry['url']}\nMethod: {entry['method']}\nResponse Body:\n{entry['response']['body']}"

if __name__ == "__main__":
    mcp.run()
