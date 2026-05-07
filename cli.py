import asyncio
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from assistant import SteadyAssistant

console = Console()

class CLIApp:
    """Mock app to interface between SteadyAssistant and CLI."""
    def write_log(self, text: str):
        console.print(text)
    
    def display_plan(self, plan_text: str):
        console.print(Panel(Markdown(plan_text), title="[bold yellow]STRATEGIC PLAN[/]", border_style="yellow"))
    
    def clear(self):
        # No-op for CLI log clearing usually, or console.clear()
        pass

    # UI Hooks (No-op or simple prints for CLI)
    def create_terminal(self, session_id): console.print(f"[dim]Terminal Created: {session_id}[/]")
    def append_to_terminal(self, session_id, cmd, output): console.print(f"[dim]Term[{session_id}] > {cmd}[/]")
    def remove_terminal(self, session_id): console.print(f"[dim]Terminal Closed: {session_id}[/]")
    def add_log_to_workspace(self, path): console.print(f"[dim]Tracking Log: {path}[/]")
    def update_workspace_scratchpad(self, content): console.print(Panel(content, title="SCRATCHPAD", border_style="cyan"))
    def add_workspace_document(self, name, content): console.print(f"[dim]Document Added: {name}[/]")
    def add_api_to_workspace(self, url, method, res): console.print(f"[dim]API {method} {url}[/]")
    def update_api_env(self, key, value): console.print(f"[dim]API ENV: {key}={value}[/]")

class LogWidgetMock:
    def write(self, text: str):
        console.print(text)
    def clear(self):
        pass

async def main():
    console.print(Panel("[bold green]SteadyFlow CLI Meta-Orchestrator v3.0[/]\nType your request to begin.", border_style="green"))
    
    app_mock = CLIApp()
    log_mock = LogWidgetMock()
    
    assistant = SteadyAssistant(
        log_widget=log_mock,
        agent_table=None, # Not used in CLI
        app=app_mock
    )
    
    await assistant.initialize()
    
    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]User[/]")
            if user_input.lower() in ["exit", "quit"]:
                break
                
            response = await assistant.process_input(user_input)
            
            # If it's a plan, assistant.py already printed it via app.display_plan
            # We just print the text response
            console.print(f"\n[bold purple]AI:[/] {response}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            
    await assistant.shutdown()
    console.print("[yellow]SteadyFlow Offline.[/]")

if __name__ == "__main__":
    asyncio.run(main())
