import asyncio
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional, Dict, Any

mcp = FastMCP("SteadyFlow HTTP")

@mcp.tool()
async def http_request(
    url: str, 
    method: str = "GET", 
    headers: Optional[Dict[str, str]] = None, 
    data: Optional[str] = None,
    json_data: Optional[Dict[str, Any]] = None
) -> str:
    """Make an HTTP request (curl-like) and return the response."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                content=data,
                json=json_data,
                timeout=30.0
            )
            
            # Format output
            status_line = f"HTTP {response.status_code} {response.reason_phrase}"
            try:
                body = response.json()
                import json
                body_str = json.dumps(body, indent=2)
            except:
                body_str = response.text
                
            return f"{status_line}\n\n{body_str}"
        except Exception as e:
            return f"Error making request to {url}: {str(e)}"

if __name__ == "__main__":
    mcp.run()
