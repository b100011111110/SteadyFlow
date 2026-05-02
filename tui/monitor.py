import psutil
import docker
import subprocess
import json
import os
import asyncio
import platform
import math
from datetime import datetime
from textual.app import App, ComposeResult, events
from textual.widgets import Header, Footer, Static, Label, RichLog, Input, DataTable, Button, ContentSwitcher
from textual.containers import Container, Vertical, Horizontal, Grid, ScrollableContainer
from textual.reactive import reactive
from rich.text import Text
from concurrent.futures import ThreadPoolExecutor

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
    terminal_count = reactive(1)
    active_terminal = reactive(0)
    terminal_ids = reactive([0])

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with ScrollableContainer(id="global-scroll"):
            with Container(id="main-grid"):
                # COLUMN 1: AI
                with Vertical(id="col-ai", classes="column"):
                    with Vertical(classes="panel", id="ai-chat-panel") as v:
                        v.border_title = "AI ORCHESTRATOR"
                        yield RichLog(id="ai-history", markup=True)
                        yield Input(placeholder="Ask AI...", id="ai-input")
                    with Vertical(classes="panel", id="agent-panel") as v:
                        v.border_title = "AGENT STATUS"
                        yield DataTable(id="agent-table")

                # COLUMN 2 & 3: CONTROL
                with Vertical(id="col-control", classes="column"):
                    with Vertical(classes="panel", id="term-panel"):
                        self.term_panel_container = Vertical()
                        self.term_panel_container.border_title = "SYSTEM TERMINAL"
                        with Horizontal(id="term-tabs"):
                            yield Label("1", id="tab-0", classes="term-tab active")
                            yield Button("+", id="add-term", variant="primary")
                        with ContentSwitcher(initial="term-0", id="term-switcher"):
                            yield RichLog(id="term-0", markup=True, highlight=True)
                        with Horizontal(id="input-area"):
                            yield Label("neo@SF:~$ ", id="prompt-label")
                            yield Input(placeholder="...", id="terminal-input")
                    
                    with Horizontal(id="split-area"):
                        with Vertical(classes="panel", id="cloud-panel") as v:
                            v.border_title = "CLOUD"
                            yield DataTable(id="cloud-table")
                        with Vertical(id="stack-panel"):
                            with Vertical(classes="panel", id="docker-panel") as v:
                                v.border_title = "DOCKER"
                                yield DataTable(id="docker-table")
                                yield Label("IMAGES", classes="sub-title")
                                yield DataTable(id="image-table")
                            with Vertical(classes="panel", id="k8s-panel") as v:
                                v.border_title = "K8S"
                                yield DataTable(id="k8s-table")

                # COLUMN 4: SYSTEM
                with Vertical(id="col-system", classes="column"):
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
                        yield StatusBar("UP", id="net-up-bar", mode="net")
                        yield StatusBar("DN", id="net-down-bar", mode="net")
                        yield Label("S/R: 0G / 0G", id="net-total", classes="small-label")
                    with Vertical(id="proc-panel", classes="panel") as v:
                        v.border_title = "PROCESSES"
                        yield DataTable(id="proc-table")

    def on_mount(self) -> None:
        self.terminal_states = {0: {"cwd": os.getcwd(), "history": []}}
        self.next_id = 1
        self.query_one("#agent-table", DataTable).add_columns("Agent", "Task", "Status")
        self.query_one("#cloud-table", DataTable).add_columns("Provider", "Region", "State")
        self.query_one("#docker-table", DataTable).add_columns("ID", "Name", "CPU", "MEM")
        self.query_one("#image-table", DataTable).add_columns("ID", "Repo", "Size")
        self.query_one("#k8s-table", DataTable).add_columns("Namespace", "Pod", "Status")
        self.query_one("#proc-table", DataTable).add_columns("PID", "CPU", "MEM", "Name")
        
        self.query_one("#agent-table").add_row("LangChain_Core", "Orchestrating", "[green]IDLE[/]")
        self.query_one("#cloud-table").add_row("AWS_Burst", "us-east-1", "[yellow]READY[/]")
        self.query_one("#k8s-table").add_row("default", "langchain-node-1", "[green]RUNNING[/]")
        
        cpu = get_cpu_detailed_info()
        self.query_one("#cpu-info").update(f"[cyan]{cpu['model'][:35]}[/]")
        self.query_one("#cpu-specs").update(f"P: [cyan]{cpu['cores']}[/] L: [cyan]{cpu['threads']}[/] C: [cyan]{cpu['cache']}[/]")
        m, s, d = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_usage('/')
        self.query_one("#res-info").update(f"Cap: [cyan]M:{format_bytes(m.total)} S:{format_bytes(s.total)} D:{format_bytes(d.total)}[/]")
        
        try: self.docker_client = docker.from_env()
        except: self.docker_client = None
        self.last_net_io = psutil.net_io_counters()
        self.last_time = datetime.now()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.set_interval(1.0, self.update_data)
        self.set_interval(2.0, self.update_docker_bg)
        self.call_after_refresh(self.trigger_resize)

    def trigger_resize(self) -> None:
        self.on_resize(events.Resize(self.size, self.size))

    def on_resize(self, event: events.Resize) -> None:
        width = event.size.width
        main_grid = self.query_one("#main-grid")
        cpu_grid = self.query_one("#cpu-grid")
        global_scroll = self.query_one("#global-scroll")
        
        main_grid.set_classes("")
        # Only 1-Column and 4-Column logic
        if width < 120: 
            main_grid.add_class("layout-1")
            global_scroll.styles.overflow_y = "scroll"
        else: 
            main_grid.add_class("layout-4")
            global_scroll.styles.overflow_y = "hidden"

        cpu_grid.set_classes("")
        if width < 150: cpu_grid.add_class("cpu-1")
        elif width < 220: cpu_grid.add_class("cpu-2")
        else: cpu_grid.add_class("cpu-4")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-term":
            idx = self.next_id
            self.next_id += 1
            self.terminal_states[idx] = {"cwd": os.getcwd(), "history": []}
            self.terminal_ids.append(idx)
            new_log = RichLog(id=f"term-{idx}", markup=True, highlight=True)
            self.query_one("#term-switcher").mount(new_log)
            new_tab = Label(str(idx+1), id=f"tab-{idx}", classes="term-tab")
            self.query_one("#term-tabs").mount(new_tab, before="#add-term")
            self.switch_terminal(idx)

    async def on_click(self, event) -> None:
        if hasattr(event, "widget") and event.widget.id and event.widget.id.startswith("tab-"):
            idx = int(event.widget.id.split("-")[1])
            self.switch_terminal(idx)

    def switch_terminal(self, idx: int):
        self.active_terminal = idx
        self.query_one("#term-switcher").current = f"term-{idx}"
        for tid in self.terminal_ids:
            try: self.query_one(f"#tab-{tid}").remove_class("active")
            except: pass
        self.query_one(f"#tab-{idx}").add_class("active")
        self.update_prompt()

    def close_terminal(self, idx: int):
        if len(self.terminal_ids) <= 1: return
        self.query_one(f"#tab-{idx}").remove()
        self.query_one(f"#term-{idx}").remove()
        self.terminal_ids.remove(idx)
        del self.terminal_states[idx]
        self.switch_terminal(self.terminal_ids[0])

    def update_prompt(self):
        state = self.terminal_states[self.active_terminal]
        path = state["cwd"].replace(os.path.expanduser("~"), "~")
        short_path = path if len(path) < 12 else f"...{path[-9:]}"
        self.query_one("#prompt-label").update(f"neo@SF:{short_path}$ ")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.value = ""
        if event.input.id == "ai-input":
            history = self.query_one("#ai-history", RichLog)
            history.write(f"[bold cyan]User:[/] {cmd}")
            history.write(f"[bold purple]AI:[/] Removing 2-column split and fixing 1-column panel stacking.")
            return
        log = self.query_one(f"#term-{self.active_terminal}", RichLog)
        state = self.terminal_states[self.active_terminal]
        if not cmd: return
        if cmd == "exit": self.close_terminal(self.active_terminal); return
        if cmd == "clear": log.clear(); return
        if cmd.startswith("cd "):
            path = os.path.abspath(os.path.join(state["cwd"], cmd[3:].strip()))
            if os.path.isdir(path): state["cwd"] = path; self.update_prompt()
            return
        log.write(f"[bold green]neo@SF[/]:[bold blue]{state['cwd']}[/]$ {cmd}")
        self.run_worker(self.execute_command(cmd, log, state))

    async def execute_command(self, cmd: str, log: RichLog, state: dict) -> None:
        try:
            process = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=state["cwd"])
            stdout, _ = await process.communicate()
            if stdout: log.write(stdout.decode().strip())
        except: pass

    def update_docker_bg(self) -> None:
        if self.docker_client: self.run_worker(self.fetch_docker())

    async def fetch_docker(self):
        loop = asyncio.get_event_loop()
        self.docker_data = await loop.run_in_executor(self.executor, self._get_docker_info)

    def _get_docker_info(self):
        c_list, i_list = [], []
        try:
            for c in self.docker_client.containers.list():
                try:
                    s = c.stats(stream=False)
                    cpu = s['cpu_stats']['cpu_usage']['total_usage'] / s['cpu_stats']['system_cpu_usage'] * 100
                    c_list.append((c.short_id, c.name[:8], f"{cpu:.0f}%", f"{s['memory_stats']['usage']/1024**2:.0f}M"))
                except: 
                    c_list.append((c.short_id, c.name[:8], "0%", "0M"))
            for img in self.docker_client.images.list():
                tag = (img.tags[0] if img.tags else "none")[:10]
                i_list.append((img.short_id[7:13], tag, f"{img.attrs['Size']/1024**2:.0f}M"))
        except: pass
        return {"containers": c_list, "images": i_list}

    def watch_docker_data(self, data):
        t1, t2 = self.query_one("#docker-table", DataTable), self.query_one("#image-table", DataTable)
        t1.clear(); [t1.add_row(*c) for c in data['containers']]
        t2.clear(); [t2.add_row(*img) for img in data['images']]

    def update_data(self) -> None:
        cpu = psutil.cpu_percent(percpu=True)
        for i, p in enumerate(cpu):
            try: self.query_one(f"#cpu-bar-{i}", StatusBar).value = p
            except: pass
        m, s, d = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_usage('/')
        self.query_one("#mem-bar").value, self.query_one("#swp-bar").value, self.query_one("#disk-bar").value = m.percent, s.percent, d.percent
        now, net = datetime.now(), psutil.net_io_counters()
        dt = max((now - self.last_time).total_seconds(), 0.1)
        down, up = (net.bytes_recv-self.last_net_io.bytes_recv)/dt, (net.bytes_sent-self.last_net_io.bytes_sent)/dt
        self.last_net_io, self.last_time = net, now
        def log_scale(val):
            if val < 1024: return 0
            return (math.log(val, 1024) / 3) * 100
        self.query_one("#net-up-bar").value, self.query_one("#net-up-bar").speed_text = log_scale(up), format_speed(up)
        self.query_one("#net-down-bar").value, self.query_one("#net-down-bar").speed_text = log_scale(down), format_speed(down)
        self.query_one("#net-total").update(f"S/R: {format_bytes(net.bytes_sent)} / {format_bytes(net.bytes_recv)}")
        procs = sorted([p.info for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info'])], key=lambda x: x['cpu_percent'], reverse=True)[:30]
        pt = self.query_one("#proc-table", DataTable)
        pt.clear(); [pt.add_row(str(p['pid']), f"{int(p['cpu_percent'])}%", f"{p['memory_info'].rss/1024**2:.0f}M", p['name'][:10]) for p in procs]

if __name__ == "__main__":
    MonitorApp().run()
