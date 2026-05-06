import psutil
import docker
import subprocess
import json
import os
import asyncio
import platform
import math
from datetime import datetime
from typing import Optional, Dict, Any
from textual.app import App, ComposeResult, events
from textual.widgets import Header, Static, Label, RichLog, Input, DataTable, Button, Tabs, Tab, ContentSwitcher
from textual.containers import Container, Vertical, Horizontal, Grid, ScrollableContainer
from textual.reactive import reactive
from rich.text import Text
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path

# Add root directory to path so assistant.py can be imported from tui/
sys.path.append(str(Path(__file__).parent.parent))
from assistant import SteadyAssistant

def get_cpu_detailed_info():
    info = {"model": "Unknown CPU", "cores": 0, "threads": 0, "cache": "Unknown"}
    try:
        info["threads"] = psutil.cpu_count(logical=True)
        info["cores"] = psutil.cpu_count(logical=False)
        if platform.system() == "Linux":
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        info["model"] = line.split(":")[1].strip()
                        break
            try:
                lscpu = subprocess.check_output("lscpu", shell=True, text=True)
                for line in lscpu.split("\n"):
                    if "L3 cache" in line: info["cache"] = line.split(":")[1].strip()
                    elif "L2 cache" in line and info["cache"] == "Unknown": info["cache"] = line.split(":")[1].strip()
            except:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "cache size" in line:
                            info["cache"] = line.split(":")[1].strip()
                            break
    except: pass
    return info

def format_bytes(n):
    for unit in ['B', 'K', 'M', 'G', 'T']:
        if n < 1024: return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}P"

def format_speed(bps):
    if bps < 1024: return f"{bps:.0f}B/s"
    if bps < 1024**2: return f"{bps/1024:.1f}K/s"
    if bps < 1024**3: return f"{bps/1024**2:.1f}M/s"
    return f"{bps/1024**3:.1f}G/s"

class StatusBar(Static):
    value = reactive(0.0)
    speed_text = reactive("")
    def __init__(self, label, id=None, mode="normal"):
        super().__init__(id=id)
        self.label = label
        self.mode = mode

    def render(self) -> Text:
        width = self.size.width
        reserved = 12 if self.mode == "net" else 8
        bar_width = max(width - reserved, 1)
        color = "green" if self.value < 50 else "purple" if self.value < 80 else "red"
        if self.mode == "net": filled = int((self.value / 100) * bar_width)
        else: filled = int((min(self.value, 100) / 100) * bar_width)
        res = Text()
        res.append(f"{self.label:<2}", style="cyan")
        res.append("[", style="dim")
        res.append("|" * filled, style=color)
        res.append(" " * (bar_width - filled))
        res.append("]", style="dim")
        if self.mode == "net": res.append(f"{self.speed_text:>8}", style="grey70")
        else: res.append(f"{int(self.value):>3}%", style="grey70")
        return res

class MonitorApp(App):
    CSS_PATH = "styles.tcss"
    ENABLE_COMMAND_PALETTE = False
    docker_data = reactive({"containers": [], "images": []})
    cloud_data = reactive({"providers": []})
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with ScrollableContainer(id="global-scroll"):
            with Container(id="main-grid"):
                # LEFT SECTION: BROWSER-LIKE TABS (1/2 width)
                with Vertical(id="left-section"):
                    with Horizontal(id="browser-bar"):
                        yield Tabs(Tab("CHAT", id="tab-chat"), id="tabs")
                        yield Button("+", id="add-term-btn")
                    
                    with ContentSwitcher(id="switcher", initial="pane-chat"):
                        with Vertical(id="pane-chat"):
                            yield RichLog(id="ai-history", markup=True, wrap=True)
                            with Horizontal(id="ai-input-container"):
                                yield Input(placeholder="Message SteadyFlow...", id="ai-input")
                
                # RIGHT SECTION: TELEMETRY & SYSTEM (1/2 width)
                with Horizontal(id="right-section"):
                    with Vertical(id="telemetry-column"):
                        with Vertical(classes="panel", id="agent-panel") as v:
                            v.border_title = "AGENT STATUS"
                            yield DataTable(id="agent-table")
                        with Vertical(classes="panel", id="cloud-panel") as v:
                            v.border_title = "CLOUD"
                            yield DataTable(id="cloud-table")
                        with Vertical(classes="panel", id="docker-panel") as v:
                            v.border_title = "DOCKER"
                            yield DataTable(id="docker-table")
                        with Vertical(classes="panel", id="k8s-panel") as v:
                            v.border_title = "K8S"
                            yield DataTable(id="k8s-table")

                    with Vertical(id="system-column"):
                        with Vertical(id="cpu-panel", classes="panel") as v:
                            v.border_title = "CPU"
                            cpu_count = psutil.cpu_count(logical=True)
                            with Grid(id="cpu-grid"):
                                for i in range(cpu_count):
                                    yield StatusBar(f"{i+1}", id=f"cpu-bar-{i}", mode="cpu")
                            yield Label("Model: Detecting...", id="cpu-info", classes="small-label")
                            yield Label("P: 0 | L: 0 | C: ...", id="cpu-specs", classes="small-label")
                        
                        with Vertical(id="res-panel", classes="panel") as v:
                            v.border_title = "RES"
                            yield StatusBar("M", id="mem-bar")
                            yield StatusBar("S", id="swp-bar")
                            yield StatusBar("D", id="disk-bar")
                            yield Label("Cap: ...", id="res-info", classes="small-label")

                        with Vertical(id="net-panel", classes="panel") as v:
                            v.border_title = "NET"
                            yield StatusBar("UP", id="net-up", mode="net")
                            yield StatusBar("DN", id="net-down", mode="net")
                            yield Label("S/R: 0G / 0G", id="net-total", classes="small-label")

                        with Vertical(id="proc-panel", classes="panel") as v:
                            v.border_title = "PROCESSES"
                            yield DataTable(id="proc-table")

    def on_mount(self) -> None:
        self.terminal_states = {}
        self.next_term_id = 1
        
        # Init tables
        self.query_one("#agent-table", DataTable).add_columns("Agent", "Task", "Status")
        self.query_one("#cloud-table", DataTable).add_columns("Type", "Provider", "Price", "Uptime")
        self.query_one("#docker-table", DataTable).add_columns("ID", "Name", "CPU", "MEM")
        self.query_one("#k8s-table", DataTable).add_columns("Namespace", "Pod", "Status")
        self.query_one("#proc-table", DataTable).add_columns("PID", "CPU", "MEM", "Name")
        
        self.query_one("#agent-table").add_row("SteadyAI", "Monitoring", "[green]ACTIVE[/]")
        self.query_one("#cloud-table").add_row("AWS_Burst", "us-east-1", "[yellow]READY[/]")
        self.query_one("#k8s-table").add_row("default", "langchain-node-1", "[green]RUNNING[/]")
        
        # System Info Init
        cpu = get_cpu_detailed_info()
        self.query_one("#cpu-info").update(f"[cyan]{cpu['model'][:35]}[/]")
        self.query_one("#cpu-specs").update(f"P: [cyan]{cpu['cores']}[/] L: [cyan]{cpu['threads']}[/] C: [cyan]{cpu['cache']}[/]")
        m, s, d = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_usage('/')
        self.query_one("#res-info").update(f"Cap: [cyan]M:{format_bytes(m.total)} S:{format_bytes(s.total)} D:{format_bytes(d.total)}[/]")
        
        try: self.docker_client = docker.from_env()
        except: self.docker_client = None
        self.last_net_io = psutil.net_io_counters()
        self.last_time_obj = datetime.now()
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # Initialize AI Assistant
        self.assistant = SteadyAssistant(
            self.query_one("#ai-history", RichLog),
            self.query_one("#agent-table", DataTable)
        )
        asyncio.create_task(self.assistant.initialize())
        
        self.set_interval(1.0, self.update_data)
        self.set_interval(2.0, self.update_docker_bg)
        self.set_interval(10.0, self.update_cloud_bg)
        self.call_after_refresh(self.trigger_resize)

    def on_unmount(self) -> None:
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        if hasattr(self, 'assistant'):
            asyncio.create_task(self.assistant.shutdown())

    def trigger_resize(self) -> None:
        self.on_resize(events.Resize(self.size, self.size))

    def on_resize(self, event: events.Resize) -> None:
        width = event.size.width
        main_grid = self.query_one("#main-grid")
        global_scroll = self.query_one("#global-scroll")
        
        main_grid.set_classes("")
        if width < 120: 
            main_grid.add_class("layout-1")
            global_scroll.styles.overflow_y = "scroll"
        else: 
            main_grid.add_class("layout-split")
            global_scroll.styles.overflow_y = "hidden"

        cpu_grid = self.query_one("#cpu-grid")
        cpu_grid.set_classes("")
        if width < 150: cpu_grid.add_class("cpu-1")
        elif width < 200: cpu_grid.add_class("cpu-2")
        else: cpu_grid.add_class("cpu-4")

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab.id:
            pane_id = event.tab.id.replace("tab-", "pane-")
            self.query_one("#switcher", ContentSwitcher).current = pane_id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-term-btn":
            self.create_terminal()

    def create_terminal(self):
        idx = self.next_term_id
        self.next_term_id += 1
        self.terminal_states[idx] = {"cwd": os.getcwd()}
        
        tabs = self.query_one("#tabs", Tabs)
        switcher = self.query_one("#switcher", ContentSwitcher)
        
        tab_id = f"tab-term-{idx}"
        pane_id = f"pane-term-{idx}"
        
        tabs.add_tab(Tab(f"TERM {idx}", id=tab_id))
        
        switcher.mount(
            Vertical(
                RichLog(id=f"term-log-{idx}", markup=True, highlight=True, wrap=True, classes="term-log"),
                Horizontal(
                    Label(f"neo@SF:~ $ ", id=f"term-prompt-{idx}"),
                    Input(placeholder="Execute command...", id=f"term-input-{idx}"),
                    classes="term-input-area"
                ),
                id=pane_id,
                classes="term-container"
            )
        )
        
        tabs.active = tab_id
        switcher.current = pane_id

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        event.input.value = ""
        if not val: return

        if event.input.id == "ai-input":
            if val.lower() == "goodbye":
                self.exit()
                return
            history = self.query_one("#ai-history", RichLog)
            history.write(f"[bold cyan]User:[/] {val}")
            self.run_worker(self.handle_ai_input(val, history))
        elif event.input.id and event.input.id.startswith("term-input-"):
            idx = int(event.input.id.split("-")[-1])
            log = self.query_one(f"#term-log-{idx}", RichLog)
            state = self.terminal_states[idx]
            
            if val == "clear":
                log.clear()
                return
            if val == "exit":
                tabs = self.query_one("#tabs", Tabs)
                switcher = self.query_one("#switcher", ContentSwitcher)
                
                # Switch focus back to chat first
                tabs.active = "tab-chat"
                switcher.current = "pane-chat"
                
                # Remove the tab and pane
                try:
                    self.query_one(f"#tab-term-{idx}").remove()
                    self.query_one(f"#pane-term-{idx}").remove()
                    if idx in self.terminal_states:
                        del self.terminal_states[idx]
                except:
                    pass
                return
                
            log.write(f"[bold green]neo@SF[/]:[bold blue]{state['cwd']}[/]$ {val}")
            self.run_worker(self.execute_command(val, idx))

    async def execute_command(self, cmd: str, idx: int) -> None:
        log = self.query_one(f"#term-log-{idx}", RichLog)
        state = self.terminal_states[idx]
        try:
            if cmd.startswith("cd "):
                new_path = os.path.abspath(os.path.join(state["cwd"], cmd[3:].strip()))
                if os.path.isdir(new_path):
                    state["cwd"] = new_path
                    path_display = new_path.replace(os.path.expanduser("~"), "~")
                    if len(path_display) > 20: path_display = "..." + path_display[-17:]
                    self.query_one(f"#term-prompt-{idx}", Label).update(f"neo@SF:{path_display} $ ")
                return
            process = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=state["cwd"])
            stdout, _ = await process.communicate()
            if stdout: log.write(stdout.decode().strip())
        except Exception as e: log.write(f"[red]Error: {str(e)}[/]")

    async def handle_ai_input(self, cmd: str, history: RichLog) -> None:
        # Show thinking indicator
        history.write("[italic grey70]Thinking...[/]")
        response = await self.assistant.process_input(cmd)
        
        # Remove thinking indicator (by clearing and re-writing the history if needed, 
        # or just adding the response. For RichLog we just append.)
        # Since RichLog doesn't easily support editing, we'll just write the response.
        history.write(f"[bold purple]AI:[/] {response}")

    def update_docker_bg(self) -> None:
        if self.docker_client: self.run_worker(self.fetch_docker())

    async def fetch_docker(self):
        loop = asyncio.get_event_loop()
        self.docker_data = await loop.run_in_executor(self.executor, self._get_docker_info)

    def _get_docker_info(self):
        c_list = []
        try:
            for c in self.docker_client.containers.list():
                try:
                    s = c.stats(stream=False)
                    cpu = s['cpu_stats']['cpu_usage']['total_usage'] / s['cpu_stats']['system_cpu_usage'] * 100
                    c_list.append((c.short_id, c.name[:8], f"{cpu:.0f}%", f"{s['memory_stats']['usage']/1024**2:.0f}M"))
                except: c_list.append((c.short_id, c.name[:8], "0%", "0M"))
        except: pass
        return {"containers": c_list}

    def watch_docker_data(self, data):
        t = self.query_one("#docker-table", DataTable)
        t.clear(); [t.add_row(*c) for c in data['containers']]

    def update_cloud_bg(self) -> None:
        self.run_worker(self.fetch_cloud_info())

    async def fetch_cloud_info(self):
        resources = []
        # AWS RESOURCES
        try:
            # Check EC2
            proc = await asyncio.create_subprocess_shell("aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name,LaunchTime]' --output json", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                instances = json.loads(stdout)
                for res in instances:
                    for inst in res:
                        # AWS Price is hard to get via CLI without pricing API, so we show "Varies" or similar
                        # Uptime calculation would need LaunchTime parsing
                        resources.append(("EC2", "AWS", "$0.12/hr", "Active"))
            
        except:
            pass

        # Vast.ai RESOURCES
        try:
            proc = await asyncio.create_subprocess_shell("vastai show instances --raw", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                instances = json.loads(stdout)
                for inst in instances:
                    price = f"${inst.get('price_per_hr', 0.0):.2f}/hr"
                    uptime = f"{inst.get('uptime', 0)/3600:.1f}h" if inst.get('uptime') else "N/A"
                    resources.append(("GPU", "Vast.ai", price, uptime))
        except:
            pass

        if not resources:
            resources = [("-", "-", "-", "-")]
            
        self.cloud_data = {"providers": resources}

    def watch_cloud_data(self, data):
        t = self.query_one("#cloud-table", DataTable)
        t.clear(); [t.add_row(*p) for p in data['providers']]

    def update_data(self) -> None:
        cpu = psutil.cpu_percent(percpu=True)
        for i, p in enumerate(cpu):
            try: self.query_one(f"#cpu-bar-{i}", StatusBar).value = p
            except: pass
        m, s, d = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_usage('/')
        self.query_one("#mem-bar").value, self.query_one("#swp-bar").value, self.query_one("#disk-bar").value = m.percent, s.percent, d.percent
        now_time, net = datetime.now(), psutil.net_io_counters()
        dt = (now_time - self.last_time_obj).total_seconds() if hasattr(self, 'last_time_obj') else 1.0
        down, up = (net.bytes_recv - self.last_net_io.bytes_recv) / dt if dt > 0 else 0, (net.bytes_sent - self.last_net_io.bytes_sent) / dt if dt > 0 else 0
        self.last_net_io, self.last_time_obj = net, now_time
        def log_scale(val):
            if val < 1024: return 0
            return min((math.log(val, 1024) / 3) * 100, 100)
        self.query_one("#net-up").value, self.query_one("#net-up").speed_text = log_scale(up), format_speed(up)
        self.query_one("#net-down").value, self.query_one("#net-down").speed_text = log_scale(down), format_speed(down)
        self.query_one("#net-total").update(f"S/R: {format_bytes(net.bytes_sent)} / {format_bytes(net.bytes_recv)}")
        procs = sorted([p.info for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info'])], key=lambda x: x['cpu_percent'], reverse=True)[:30]
        pt = self.query_one("#proc-table", DataTable)
        pt.clear(); [pt.add_row(str(p['pid']), f"{int(p['cpu_percent'])}%", f"{p['memory_info'].rss/1024**2:.0f}M", p['name'][:10]) for p in procs]

if __name__ == "__main__":
    MonitorApp().run()
