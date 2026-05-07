import os
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()
from typing import Optional, List, Any
from contextlib import AsyncExitStack
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_classic.memory import ConversationBufferWindowMemory
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import Annotated, TypedDict
import operator

class TaskRegistry:
    def __init__(self, status_table):
        self.status_table = status_table
        self.tasks = {}

    def add_task(self, task_id, name, effort="Low", detail=""):
        row_key = f"task_{task_id}"
        self.tasks[task_id] = {"name": name, "effort": effort, "detail": detail}
        effort_style = "[cyan]Low[/]" if effort == "Low" else "[bold orange3]High[/]"
        try:
            self.status_table.add_row(
                "SteadyAI", 
                f"{name} ({detail})" if detail else name, 
                f"{effort_style} [yellow]RUNNING[/]", 
                key=row_key
            )
        except: pass
        return row_key

    def update_task(self, task_id, status, success=True):
        row_key = f"task_{task_id}"
        color = "green" if success else "red"
        status_text = f"[{color}]{status}[/]"
        try:
            self.status_table.update_cell(row_key, "Status", status_text)
        except: pass

    def remove_task(self, task_id):
        try: self.status_table.remove_row(f"task_{task_id}")
        except: pass

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    current_task_context: str # Added for just-in-time context

class SteadyAssistant:
    def __init__(self, log_widget, status_table, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("CEREBRAS_API_KEY")
        self.log_widget = log_widget
        self.status_table = status_table
        self.task_registry = TaskRegistry(status_table)
        
        if self.api_key:
            self.llm = ChatOpenAI(
                model="qwen-3-235b-a22b-instruct-2507", 
                openai_api_key=self.api_key, 
                openai_api_base="https://api.cerebras.ai/v1",
                temperature=0.2,
                max_tokens=2048
            )
        else:
            self.llm = None

        self.memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)
        self.system_prompt = "SteadyFlow AI Assistant. Identify as SteadyFlow AI Assistant."
        self.mcp_sessions: List[ClientSession] = []
        self.tool_to_session: dict[str, ClientSession] = {}
        self._exit_stack = None
        self.history_file = os.path.join(os.path.dirname(__file__), "chat_history.json")

    async def initialize(self):
        """Init LLM, MCP, and history."""
        if not self.llm:
            self.log_widget.write("[red]Warning: API Key missing.[/]")
            return

        self._load_history()

        try:
            self._exit_stack = AsyncExitStack()
            self.tools = []
            
            # MCP Server configurations
            server_configs = [
                {
                    "name": "filesystem",
                    "command": "python3",
                    "args": [os.path.join(os.path.dirname(__file__), "mcp_filesystem_server.py")]
                },
                {
                    "name": "terminal",
                    "command": "python3",
                    "args": [os.path.join(os.path.dirname(__file__), "mcp_terminal_server.py")]
                },
                {
                    "name": "memory",
                    "command": "python3",
                    "args": [os.path.join(os.path.dirname(__file__), "mcp_memory_server.py")]
                },
                {
                    "name": "git",
                    "command": "python3",
                    "args": [os.path.join(os.path.dirname(__file__), "mcp_git_server.py")]
                },
                {
                    "name": "docker",
                    "command": "python3",
                    "args": [os.path.join(os.path.dirname(__file__), "mcp_docker_server.py")]
                },
                {
                    "name": "thinking",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
                }
            ]
            
            for config in server_configs:
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    env=os.environ.copy()
                )
                
                read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
                session = await self._exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                
                self.mcp_sessions.append(session)
                mcp_tools = await session.list_tools()
                
                for tool in mcp_tools.tools:
                    self.tool_to_session[tool.name] = session
                    self.tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description[:50],
                            "parameters": tool.inputSchema
                        }
                    })
            
            self.llm = self.llm.bind_tools(self.tools)
            
            workflow = StateGraph(AgentState)
            
            from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
            
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type(Exception), # Catch all for API errors
                reraise=True
            )
            async def _call_llm_with_retry(msgs):
                return await self.llm.ainvoke(msgs)

            self.tool_cache = {}
            
            async def get_world_state():
                """Fetch a summary of the current environment state."""
                state_bits = []
                try:
                    # Files
                    files = os.listdir(".")[:10]
                    state_bits.append(f"Files: {', '.join(files)}")
                    # Docker
                    docker_p = await self.tool_to_session["docker"].call_tool("list_containers", {})
                    state_bits.append(f"Docker: {docker_p.content[0].text[:100]}")
                    # Git
                    git_p = await self.tool_to_session["git"].call_tool("git_status", {})
                    state_bits.append(f"Git: {git_p.content[0].text[:100]}")
                except: pass
                return "\n".join(state_bits)

            async def call_model(state: AgentState):
                self.log_widget.write("[italic grey70]Thinking...[/]")
                world_state = await get_world_state()
                system_msg = SystemMessage(content=f"{self.system_prompt}\n\nCURRENT STATE:\n{world_state}")
                
                # Context Optimization: Filter history for relevance
                user_msg = state["messages"][-1].content if state["messages"] else ""
                messages = [system_msg]
                
                for msg in state["messages"][1:-1]:
                    if msg in state["messages"][-5:]: messages.append(msg)
                    elif any(word.lower() in msg.content.lower() for word in user_msg.split() if len(word) > 4):
                        messages.append(msg)
                
                messages.append(state["messages"][-1])
                
                try:
                    response = await _call_llm_with_retry(messages)
                    if response.tool_calls:
                        for tc in response.tool_calls:
                            self.log_widget.write(f"[dim]Planned: {tc['name']}[/]")
                    return {"messages": [response]}
                except Exception as e:
                    self.log_widget.write(f"[red]LLM Error: {str(e)}[/]")
                    raise e

            async def execute_single_tool(tool_call):
                name, args, tool_id = tool_call["name"], tool_call["args"], tool_call["id"]
                
                # Deduplication Check (Skip for side-effect tools)
                cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                side_effect_tools = ["run_command", "write_file", "git_add", "git_commit", "docker_exec", "think"]
                
                if cache_key in self.tool_cache and name not in side_effect_tools:
                    self.log_widget.write(f"[dim]Using cached result for {name}[/]")
                    return ToolMessage(tool_call_id=tool_id, content=f"CACHED RESULT: {self.tool_cache[cache_key]}")
                
                effort = "High" if name in ["run_command", "write_file"] else "Low"
                detail = args.get("command") or args.get("path") or args.get("thought") or ""
                self.task_registry.add_task(tool_id, name, effort, detail)
                
                self.log_widget.write(f"[bold cyan]Action:[/] {name} [grey50]({detail})[/]")
                
                try:
                    session = self.tool_to_session.get(name)
                    r = await session.call_tool(name, args)
                    res = "".join([i.text if hasattr(i, 'text') else str(i.get('text', '')) for i in r.content])
                    self.tool_cache[cache_key] = res # Cache result
                    self.task_registry.update_task(tool_id, "DONE", True)
                except Exception as e: 
                    res = f"Error: {str(e)}"
                    self.task_registry.update_task(tool_id, "FAIL", False)
                
                await asyncio.sleep(0.5)
                self.task_registry.remove_task(tool_id)
                return ToolMessage(tool_call_id=tool_id, content=res)

            async def call_tools(state: AgentState):
                last_message = state["messages"][-1]
                # Run all tool calls sequentially
                tool_results = []
                for tc in last_message.tool_calls:
                    res = await execute_single_tool(tc)
                    tool_results.append(res)
                return {"messages": tool_results}

            def should_continue(state: AgentState):
                last_message = state["messages"][-1]
                return "continue" if last_message.tool_calls else "end"

            workflow.add_node("agent", call_model)
            workflow.add_node("tools", call_tools)
            workflow.set_entry_point("agent")
            workflow.add_conditional_edges("agent", should_continue, {"continue": "tools", "end": END})
            workflow.add_edge("tools", "agent")
            self.graph = workflow.compile()
            self.log_widget.write("[green]SteadyFlow Graph Initialized.[/]")
        except Exception as e:
            self.log_widget.write(f"[yellow]Graph init failed: {str(e)}[/]")

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    for item in data[-5:]: # Only load last 5
                        self.memory.save_context({"input": item["input"]}, {"output": item["output"]})
            except: pass

    def _save_history(self, user_input: str, ai_output: str):
        history = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    history = json.load(f)
            except: pass
        history.append({"input": user_input, "output": ai_output})
        history = history[-50:]
        try:
            with open(self.history_file, "w") as f:
                json.dump(history, f, indent=2)
        except: pass

    async def _parse_json_tool_calls(self, content: str) -> List[dict]:
        import re
        tool_calls = []
        potential_objects = []
        start_indices = [m.start() for m in re.finditer(r'\{', content)]
        for start in start_indices:
            stack = 0
            for i in range(start, len(content)):
                if content[i] == '{': stack += 1
                elif content[i] == '}':
                    stack -= 1
                    if stack == 0:
                        potential_objects.append(content[start:i+1])
                        break
        for obj_str in potential_objects:
            try:
                parsed = json.loads(obj_str)
                if isinstance(parsed, dict) and ("name" in parsed or "function" in parsed):
                    name = parsed.get("name") or parsed.get("function", {}).get("name")
                    args = parsed.get("arguments") or parsed.get("args") or parsed.get("function", {}).get("arguments") or {}
                    if any(tc["name"] == name and tc["args"] == args for tc in tool_calls): continue
                    if name:
                        tool_calls.append({
                            "name": name,
                            "args": args,
                            "id": f"call_{int(asyncio.get_event_loop().time() * 1000)}_{len(tool_calls)}"
                        })
            except: continue
        return tool_calls

    async def process_input(self, user_input: str):
        if not self.llm: return "Error: API key missing."
        if not hasattr(self, "graph"): return "Error: Assistant graph not initialized. Check logs for startup errors."
        try:
            history = self.memory.load_memory_variables({})["chat_history"]
            initial_messages = [SystemMessage(content=self.system_prompt)] + history + [HumanMessage(content=user_input)]
            
            # Execute via LangGraph
            final_state = await self.graph.ainvoke({"messages": initial_messages})
            
            final_response = final_state["messages"][-1].content
            self.memory.save_context({"input": user_input}, {"output": final_response})
            self._save_history(user_input, final_response)
            return final_response
        except Exception as e: return f"Assistant Error: {str(e)}"

    async def shutdown(self):
        if self._exit_stack: await self._exit_stack.aclose()
