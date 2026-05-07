import asyncio
import os
from mcp.server.fastmcp import FastMCP
from typing import Dict, List, Optional
import time

mcp = FastMCP("SteadyFlow Lifecycle")

# State to track alarms and wakeups
lifecycle_state = {
    "alarms": {},    # alarm_id -> target_time
    "wakeups": set(), # active wakeup tags
    "sleeping": False
}

@mcp.tool()
async def sleep_task(seconds: int) -> str:
    """Pause execution for a specific number of seconds."""
    lifecycle_state["sleeping"] = True
    start_time = time.time()
    await asyncio.sleep(seconds)
    lifecycle_state["sleeping"] = False
    end_time = time.time()
    return f"Task slept for {seconds}s (Actual: {end_time - start_time:.2f}s). Waking up now."

@mcp.tool()
async def set_alarm(alarm_id: str, delay_seconds: int) -> str:
    """Set an alarm that will 'ring' after a delay."""
    target_time = time.time() + delay_seconds
    lifecycle_state["alarms"][alarm_id] = target_time
    return f"Alarm '{alarm_id}' set for {delay_seconds}s from now."

@mcp.tool()
async def wait_for_alarm(alarm_id: str) -> str:
    """Wait until a specific alarm rings."""
    if alarm_id not in lifecycle_state["alarms"]:
        return f"Error: Alarm '{alarm_id}' not found."
    
    target = lifecycle_state["alarms"][alarm_id]
    now = time.time()
    if now < target:
        wait_time = target - now
        await asyncio.sleep(wait_time)
        del lifecycle_state["alarms"][alarm_id]
        return f"Alarm '{alarm_id}' rang! Waking up."
    else:
        del lifecycle_state["alarms"][alarm_id]
        return f"Alarm '{alarm_id}' already rang. Resuming immediately."

@mcp.tool()
async def register_wakeup(tag: str) -> str:
    """Register a tag that can wake up a waiting task."""
    lifecycle_state["wakeups"].add(tag)
    return f"Wakeup tag '{tag}' registered."

@mcp.tool()
async def wait_for_wakeup(tag: str, timeout: int = 60) -> str:
    """Wait for an external wakeup tag to be registered."""
    start_time = time.time()
    while tag not in lifecycle_state["wakeups"]:
        if time.time() - start_time > timeout:
            return f"Timeout: Wakeup tag '{tag}' not received after {timeout}s."
        await asyncio.sleep(1)
    
    lifecycle_state["wakeups"].remove(tag)
    return f"Wakeup tag '{tag}' received! Resuming task."

if __name__ == "__main__":
    mcp.run()
