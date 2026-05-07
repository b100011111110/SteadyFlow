# SteadyFlow Meta-Orchestrator

SteadyFlow is a high-performance agentic AI orchestrator designed to handle complex system tasks through a suite of specialized Model Context Protocol (MCP) servers. It operates on a **Plan-Confirm-Execute** workflow, ensuring transparency and safety during autonomous operations.

## 🚀 Features

- **Strategic Planning**: Automatically formulates multi-step execution strategies for complex requests.
- **Interactive TUI/CLI**: Real-time observability of agent actions, logs, and terminal sessions.
- **Advanced Lifecycle Management**: Tracks and terminates all background processes and containers started during a session to prevent resource leaks.
- **Multi-Server Orchestration**:
    - **Terminal**: Parallel session management with full process group tracking and cleanup.
    - **Docker**: Container lifecycle management (list, run, exec, and automated cleanup).
    - **Log Analysis**: Real-time log following, pattern matching, and workspace annotation.
    - **API Workbench**: Environment-aware HTTP client with history and analysis tools.
    - **Git**: Integrated repository management.
    - **Filesystem**: Safe and efficient file operations.
    - **Memory/Thinking**: Specialized servers for long-term state and sequential reasoning.

## 🛠 Architecture

SteadyFlow uses a modular architecture where the core assistant orchestrates multiple independent MCP servers:

- `assistant.py`: The core logic using LangGraph for state management and workflow routing.
- `cli.py`: The command-line interface entry point.

### Project Structure

- `mcp_terminal_server.py`: Manages terminal sessions and process groups.
- `mcp_docker_server.py`: Interfaces with Docker for container operations.
- `mcp_log_server.py`: specialized for log monitoring and annotation.
- `mcp_api_server.py`: Advanced HTTP client with environment variable support.
- `mcp_filesystem_server.py`: Standard file operations.
- `mcp_git_server.py`: Git repository management.
- `mcp_lifecycle_server.py`: Handles timeouts, alarms, and wait states.
- `mcp_memory_server.py`: Persistent context management.
- `mcp_http_server.py`: Basic HTTP requests.


## 🏃 Getting Started

### Prerequisites

- Python 3.10+
- OpenAI API Key (or compatible provider via `assistant.py` config)
- Docker (optional, for container features)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/SteadyFlow.git
   cd SteadyFlow
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment:
   Create a `.env` file with your API keys:
   ```env
   CEREBRAS_API_KEY=your_key_here
   ```

### Usage

Start the CLI assistant:
```bash
python3 cli.py
```

Type your request (e.g., "Analyze the build logs and fix any errors"). SteadyFlow will generate a plan and wait for your `confirm` before execution.

## 🔒 Safety & Cleanup

SteadyFlow is built with system safety in mind:
- **Confirmation Required**: No destructive actions or system changes are performed without explicit user approval.
- **Process Isolation**: Terminal commands run in dedicated process groups.
- **Automatic Cleanup**: Upon exit (or SIGINT), the agent automatically calls `cleanup_all` on all servers to kill background processes and remove temporary containers.

## 📜 License

[MIT License](LICENSE)
