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
    current_task_context: str
    plan: str
    approved: bool
    task_graph: list # Dynamic tasks

class SteadyAssistant:
    def __init__(self, log_widget, agent_table=None, app=None):
        self.api_key = os.getenv("CEREBRAS_API_KEY")
        self.log_widget = log_widget
        self.agent_table = agent_table
        self.app = app
        self.task_registry = TaskRegistry(agent_table)
        
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
        self.system_prompt = """SteadyFlow AI Assistant. 
You have advanced capabilities for log analysis and terminal management.

GUIDELINES:
1. Use 'mcp_terminal_server' to manage parallel tasks. Create named sessions for different logical tasks (e.g., 'build', 'test', 'monitor').
2. Use 'mcp_log_server' for deep analysis. Follow logs, take notes in the scratchpad, and mark critical lines as 'comment' or 'code'.
3. Use 'analyze_workspace' to synthesize your findings before giving a final answer for complex debugging tasks.
4. You can create and destroy terminals as needed. The user will see your work in real-time in the TUI.
"""
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
                    "name": "log",
                    "command": "python3",
                    "args": [os.path.join(os.path.dirname(__file__), "mcp_log_server.py")]
                },
                {
                    "name": "api",
                    "command": "python",
                    "args": ["mcp_api_server.py"]
                },
                {
                    "name": "lifecycle",
                    "command": "python",
                    "args": ["mcp_lifecycle_server.py"]
                },
                {
                    "name": "thinking",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
                }
            ]
            
            for config in server_configs:
                self.log_widget.write(f"[dim]Initializing MCP server: {config['name']}...[/]")
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    env=os.environ.copy()
                )
                
                try:
                    read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
                    session = await self._exit_stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    
                    self.mcp_sessions.append(session)
                    mcp_tools = await session.list_tools()
                    
                    for tool in mcp_tools.tools:
                        self.tool_to_session[tool.name] = session
                        
                        # Inject Lifecycle Parameters into every tool schema
                        schema = tool.inputSchema
                        if "properties" not in schema: schema["properties"] = {}
                        schema.setdefault("required", [])
                        schema["properties"].update({
                            "sleep": {"type": "integer", "description": "Seconds to sleep before execution"},
                            "alarm": {"type": "string", "description": "Alarm ID to wait for before execution"},
                            "wakeup": {"type": "string", "description": "Wakeup tag to wait for before execution"}
                        })

                        self.tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description[:100],
                                "parameters": schema
                            }
                        })
                    self.log_widget.write(f"[green]Server {config['name']} ready.[/]")
                except Exception as e:
                    self.log_widget.write(f"[red]Failed to start {config['name']}: {str(e)}[/]")
                    # Continue with other servers instead of failing the whole graph
                    continue
            
            # Isolation: Create a dedicated LLM with tools for execution
            # and keep a clean one for reasoning (planning/routing)
            self.llm_with_tools = self.llm.bind_tools(self.tools)
            self.planner_llm = self.llm
            
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
                    # Sessions
                    term_p = await self.tool_to_session["terminal"].call_tool("list_sessions", {})
                    state_bits.append(f"Terminals: {term_p.content[0].text[:100]}")
                    # API
                    api_p = await self.tool_to_session["api"].call_tool("get_api_history", {})
                    state_bits.append(f"API History: {api_p.content[0].text[:100]}")
                except: pass
                return "\n".join(state_bits)

            # Intent Filtering Chain
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate
            
            router_prompt = ChatPromptTemplate.from_messages([
                ("system", """Classify the user intent into one of three categories:
CONVERSATIONAL: Greetings, thanks, small talk, or questions about YOUR capabilities (e.g. 'what can you do', 'who are you').
SIMPLE: Single-step informational questions about the project, listing files, or checking a status.
COMPLEX: Requests involving system changes, debugging multiple files, multi-step execution, or anything requiring a strategic approach.

Output ONLY the category name."""),
                ("human", "{input}")
            ])
            router_chain = router_prompt | self.planner_llm | StrOutputParser()

            async def call_orchestrator(state: AgentState):
                is_approved = state.get("approved", False)
                has_plan = bool(state.get("plan", "").strip())
                
                if is_approved:
                    return await dynamic_compiler(state)
                
                if has_plan:
                    return {"messages": [AIMessage(content="Waiting for plan approval.")]}
                
                # Intent Filtering Layer
                input_text = state["messages"][-1].content
                intent_raw = await router_chain.ainvoke({"input": input_text})
                intent = intent_raw.upper().strip()
                
                # OPTIMIZATION: If it's a simple status check, don't plan.
                if any(word in input_text.lower() for word in ["what", "list", "show", "status", "check"]) and len(input_text.split()) < 10:
                    intent = "SIMPLE"

                if "CONVERSATIONAL" in intent:
                    messages = [SystemMessage(content="Reply briefly.")] + state["messages"][-3:]
                    response = await self.planner_llm.ainvoke(messages)
                    return {"messages": [response], "plan": "", "approved": False}
                
                if "SIMPLE" in intent:
                    self.log_widget.write("[dim]Direct Execution...[/]")
                    messages = [SystemMessage(content=self.system_prompt)] + state["messages"][-5:]
                    response = await self.llm_with_tools.ainvoke(messages)
                    return {"messages": [response], "plan": "", "approved": False}
                
                return await call_planner(state)

            async def call_planner(state: AgentState):
                self.log_widget.write("[bold yellow]Formulating Strategy...[/]")
                world_state = await get_world_state()
                user_request = state["messages"][-1].content
                
                # Simplified but strict prompt
                prompt = f"""Identify the GOAL, STEPS, and VERIFICATION for this request: "{user_request}"
                
You must use these tools if needed: create_session, run_in_session, read_file, list_containers.

FORMAT:
# GOAL
[Text]
# STEPS
1. [Step]
2. [Step]
# VERIFICATION
[Text]

SYSTEM STATE:
{world_state}"""
                
                response = await self.planner_llm.ainvoke([HumanMessage(content=prompt)])
                
                if not response.content.strip() or len(response.content) < 50:
                    self.log_widget.write("[dim]Plan was too short. Retrying with history...[/]")
                    messages = [SystemMessage(content="Provide a detailed multi-step plan for the user's request.")] + state["messages"][-3:]
                    response = await self.planner_llm.ainvoke(messages)

                if self.app:
                    self.app.display_plan(response.content)
                
                return {"messages": [response], "plan": response.content.strip(), "approved": False}

            async def dynamic_compiler(state: AgentState):
                self.log_widget.write("[bold purple]Executing Plan...[/]")
                plan = state.get("plan", "")
                prompt = f"""The plan is APPROVED. You MUST follow it strictly step-by-step.
PLAN:
{plan}

INSTRUCTIONS:
1. Execute the next logical step in the plan using the available tools.
2. After EACH significant tool call, use 'update_scratchpad' to log your current progress and any findings.
3. If you finish all steps, provide a final summary of the verification results.
"""
                messages = [SystemMessage(content=prompt)] + state["messages"][-10:]
                response = await self.llm_with_tools.ainvoke(messages)
                return {"messages": [response], "plan": plan, "approved": True}

            async def execute_tool_logic(state: AgentState):
                last_message = state["messages"][-1]
                tool_results = []
                plan = state.get("plan", "")
                approved = state.get("approved", False)
                
                for tc in last_message.tool_calls:
                    name, args, tool_id = tc["name"], tc["args"], tc["id"]
                    
                    # Intercept Lifecycle Parameters
                    if "sleep" in args:
                        s_time = args.pop("sleep")
                        self.log_widget.write(f"[yellow]Lifecycle: Sleeping for {s_time}s...[/]")
                        await self.tool_to_session["lifecycle"].call_tool("sleep_task", {"seconds": s_time})
                    
                    if "alarm" in args:
                        a_id = args.pop("alarm")
                        self.log_widget.write(f"[yellow]Lifecycle: Waiting for alarm '{a_id}'...[/]")
                        await self.tool_to_session["lifecycle"].call_tool("wait_for_alarm", {"alarm_id": a_id})
                    
                    if "wakeup" in args:
                        w_tag = args.pop("wakeup")
                        self.log_widget.write(f"[yellow]Lifecycle: Waiting for wakeup signal '{w_tag}'...[/]")
                        await self.tool_to_session["lifecycle"].call_tool("wait_for_wakeup", {"tag": w_tag})

                    self.log_widget.write(f"[bold cyan]Action:[/] {name}")
                    
                    try:
                        session = self.tool_to_session.get(name)
                        r = await session.call_tool(name, args)
                        res = "".join([i.text if hasattr(i, 'text') else str(i.get('text', '')) for i in r.content])
                        
                        # UI HOOKS
                        if self.app:
                            if name in ["create_session", "run_in_session", "close_session"]:
                                if name == "create_session": self.app.create_terminal(args.get("session_id"))
                                elif name == "run_in_session": self.app.append_to_terminal(args.get("session_id"), args.get("command"), res)
                                elif name == "close_session": self.app.remove_terminal(args.get("session_id"))
                            elif name in ["follow_log", "update_scratchpad", "add_document"]:
                                if name == "follow_log": self.app.add_log_to_workspace(args.get("path"))
                                elif name == "update_scratchpad": self.app.update_workspace_scratchpad(args.get("content"))
                                elif name == "add_document": self.app.add_workspace_document(args.get("name"), args.get("content"))
                            elif name in ["api_request", "manage_env"]:
                                if name == "api_request": self.app.add_api_to_workspace(args.get("url"), args.get("method"), res)
                                elif name == "manage_env": self.app.update_api_env(args.get("key"), args.get("value"))

                        tool_results.append(ToolMessage(tool_call_id=tool_id, content=res))
                    except Exception as e:
                        tool_results.append(ToolMessage(tool_call_id=tool_id, content=f"Error: {str(e)}"))
                
                return {"messages": tool_results, "plan": plan, "approved": approved}

            def route_orchestrator(state: AgentState):
                # 1. If we have a plan but no approval, stop and wait for user
                if state.get("plan") and not state.get("approved"):
                    return "end"
                
                # 2. Check the last message from the assistant
                last_msg = state["messages"][-1]
                
                # 3. If the agent called tools, execute them
                if last_msg.tool_calls:
                    return "execute"
                
                # 4. If no tools and no plan, we are done (Conversational turn)
                if not state.get("plan"):
                    return "end"
                
                # 5. If we were approved and finished, we are done
                if state.get("approved"):
                    return "end"
                
                # 6. Default to orchestration loop
                return "orchestrate"

            workflow.add_node("orchestrator", call_orchestrator)
            workflow.add_node("tool_executor", execute_tool_logic)
            workflow.set_entry_point("orchestrator")
            workflow.add_conditional_edges("orchestrator", route_orchestrator, {"execute": "tool_executor", "orchestrate": "orchestrator", "end": END})
            workflow.add_edge("tool_executor", "orchestrator")
            
            self.graph = workflow.compile()
            self.state = {"messages": [], "plan": "", "approved": False, "task_graph": []}
            self.log_widget.clear()
            self.log_widget.write("[bold green]SteadyFlow Meta-Orchestration v2.3 (Strict Text Approval) Live.[/]")
        except Exception as e:
            self.log_widget.write(f"[yellow]Graph init failed: {str(e)}[/]")

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    for item in data[-5:]:
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

    async def process_input(self, user_input: str):
        if not self.llm: return "Error: API key missing."
        if not hasattr(self, "graph"): return "Error: Assistant graph not initialized."
        
        try:
            # Handle approval signal
            if user_input.lower() in ["confirm", "approve", "yes"]:
                if self.state.get("plan") and not self.state.get("approved"):
                    self.state["approved"] = True
                    self.log_widget.write("[bold green]Plan Approved. Starting Execution...[/]")
                else:
                    return "Nothing to approve at the moment."
            elif user_input.lower() in ["reject", "no"]:
                self.state["plan"] = ""
                self.state["approved"] = False
                return "Plan rejected. What would you like me to do instead?"
            else:
                # New task or follow-up
                self.state["messages"].append(HumanMessage(content=user_input))
                self.state["plan"] = "" # Reset plan for new task
                self.state["approved"] = False

            # Execute graph
            self.log_widget.clear() # Clear for new turn
            final_state = await self.graph.ainvoke(self.state)
            self.state.update(final_state)
            
            # Reset approved state if the task is finished (graph returned to END)
            if self.state.get("approved"):
                self.state["plan"] = ""
                self.state["approved"] = False
            
            final_response = self.state["messages"][-1].content
            if self.state["plan"] and not self.state["approved"]:
                return f"I have generated a plan. Please review it on the right and type 'confirm' to proceed.\n\n{final_response}"
            
            return final_response
        except Exception as e: return f"Assistant Error: {str(e)}"

    async def shutdown(self):
        """Cleanup all resources and shutdown MCP servers."""
        if self.log_widget:
            self.log_widget.write("[bold yellow]Shutting down and cleaning up...[/]")
        
        # Call cleanup_all on every session that has it
        for session in self.mcp_sessions:
            try:
                tools = await session.list_tools()
                if any(t.name == "cleanup_all" for t in tools.tools):
                    await session.call_tool("cleanup_all", {})
            except Exception:
                pass

        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except: pass
        
        if self.log_widget:
            self.log_widget.write("[green]Shutdown complete.[/]")



