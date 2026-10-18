import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import font, messagebox, scrolledtext, ttk

# Ensure requests is available, otherwise fail gracefully
try:
    import requests
except ImportError:
    requests = None

if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    # Note: sys.executable is the .exe file. We want the parent directory.
    from pathlib import Path
    PROJECT_ROOT = str(Path(sys.executable).resolve().parent)
else:
    # Running in normal Python environment
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class CodeGateLauncher(tk.Tk):
    def __init__(self, auto_start=False):
        super().__init__()
        self.title("CodeGate Local Pro")
        self.geometry("600x520")
        self.resizable(False, False)
        
        # Paths
        self.runtime_dir = os.path.join(PROJECT_ROOT, ".runtime")
        self.logs_dir = os.path.join(self.runtime_dir, "logs")
        self.launcher_log_file = os.path.join(self.logs_dir, "launcher.log")
        self.compose_file = os.path.join(PROJECT_ROOT, "compose.codegate.yml")
        self.diagnostics_dir = os.path.join(PROJECT_ROOT, "diagnostics")
        
        self._setup_directories()
        
        # State
        self.statuses = {
            "postgres": "UNKNOWN",
            "redis": "UNKNOWN",
            "migrate": "UNKNOWN",
            "backend": "UNKNOWN",
            "worker": "UNKNOWN",
            "frontend": "UNKNOWN"
        }
        self.overall_state = "UNKNOWN"
        
        self.docker_installed = False
        self.docker_running = False
        self.compose_valid = False
        
        self._build_ui()
        self._preflight_checks()
        
        if auto_start:
            self.after(500, self.start_codegate)
            
        self.after(3000, self._poll_health) # Poll every 3 seconds

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_directories(self):
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.diagnostics_dir, exist_ok=True)
        
    def _log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        try:
            with open(self.launcher_log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _build_ui(self):
        # Apply dark theme and professional font
        self.configure(bg="#1e1e1e")
        style = ttk.Style(self)
        style.theme_use('clam')
        
        # Colors
        bg_color = "#1e1e1e"
        fg_color = "#e0e0e0"
        card_bg = "#252526"
        btn_bg = "#0e639c"
        btn_fg = "#ffffff"
        
        style.configure("TFrame", background=bg_color)
        style.configure("Card.TFrame", background=card_bg, relief="flat")
        style.configure("TLabel", background=bg_color, foreground=fg_color, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=card_bg, foreground=fg_color, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=bg_color, foreground=fg_color, font=("Segoe UI", 14, "bold"))
        style.configure("Title.TLabel", background=bg_color, foreground="#4daafc", font=("Segoe UI", 16, "bold"))
        
        style.configure("TButton", background=btn_bg, foreground=btn_fg, font=("Segoe UI", 10, "bold"), borderwidth=0, padding=6)
        style.map("TButton", background=[("active", "#1177bb"), ("disabled", "#333333")], foreground=[("disabled", "#777777")])

        main_frame = ttk.Frame(self, padding="20 20 20 20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(header_frame, text="CodeGate", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header_frame, text="Local Pull Request Quality Platform", style="TLabel").pack(anchor="w")
        
        # Status Grid
        status_frame = ttk.Frame(main_frame, style="Card.TFrame", padding="15 15 15 15")
        status_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Grid layout for statuses
        self.status_labels = {}
        
        services = [
            ("postgres", "PostgreSQL"),
            ("redis", "Redis"),
            ("migrate", "Migration"),
            ("backend", "Backend API"),
            ("worker", "Celery Worker"),
            ("frontend", "Frontend")
        ]
        
        for i, (key, label) in enumerate(services):
            ttk.Label(status_frame, text=label, style="Card.TLabel").grid(row=i//2, column=(i%2)*2, sticky="w", padx=(0, 10), pady=4)
            lbl = ttk.Label(status_frame, text="● UNKNOWN", style="Card.TLabel", foreground="#888888")
            lbl.grid(row=i//2, column=(i%2)*2 + 1, sticky="w", padx=(0, 30), pady=4)
            self.status_labels[key] = lbl

        # Separator
        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Buttons Frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        # Left side buttons
        left_btn_frame = ttk.Frame(btn_frame)
        left_btn_frame.pack(side=tk.LEFT)
        
        self.btn_start = ttk.Button(left_btn_frame, text="Start CodeGate", command=self.start_codegate, width=15)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_stop = ttk.Button(left_btn_frame, text="Stop", command=self.stop_codegate, width=10)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_restart = ttk.Button(left_btn_frame, text="Restart", command=self.restart_codegate, width=10)
        self.btn_restart.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_force_rebuild = ttk.Button(left_btn_frame, text="Force Rebuild", command=self.force_rebuild_codegate, width=15)
        self.btn_force_rebuild.pack(side=tk.LEFT, padx=(0, 10))
        
        # Right side buttons
        right_btn_frame = ttk.Frame(btn_frame)
        right_btn_frame.pack(side=tk.RIGHT)
        
        self.btn_open = ttk.Button(right_btn_frame, text="Open Dashboard", command=self.open_dashboard)
        self.btn_open.pack(side=tk.RIGHT)
        
        # Bottom Utils Frame
        utils_frame = ttk.Frame(main_frame)
        utils_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.btn_diag = ttk.Button(utils_frame, text="Diagnostics", command=self.open_diagnostics)
        self.btn_diag.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_logs = ttk.Button(utils_frame, text="View Logs", command=self.view_logs)
        self.btn_logs.pack(side=tk.LEFT)
        
        self.lbl_overall = ttk.Label(utils_frame, text="Overall Status: UNKNOWN", font=("Segoe UI", 10, "bold"))
        self.lbl_overall.pack(side=tk.RIGHT)

    def _run_cmd(self, cmd, timeout=10, capture=True):
        try:
            kwargs = {
                "creationflags": subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                "cwd": PROJECT_ROOT
            }
            if capture:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
                return res.returncode, res.stdout, res.stderr
            else:
                res = subprocess.run(cmd, timeout=timeout, **kwargs)
                return res.returncode, "", ""
        except Exception as e:
            self._log(f"Command error: {' '.join(cmd)} - {e}")
            return -1, "", str(e)

    def _preflight_checks(self):
        self._log("Running preflight checks...")
        # 1. Docker installed
        code, stdout, _ = self._run_cmd(["docker", "--version"])
        if code == 0:
            self.docker_installed = True
        else:
            self._log("Docker not installed or not in PATH.")
            messagebox.showerror("Docker Missing", "Docker Desktop is required for CodeGate Local Product Mode.\nPlease install it and ensure it's in your PATH.")
            return

        # 2. Docker running
        code, stdout, _ = self._run_cmd(["docker", "info"])
        if code == 0:
            self.docker_running = True
        else:
            self._log("Docker engine not running.")
            messagebox.showerror("Docker Not Running", "Docker is installed but not running.\nPlease start Docker Desktop and retry.")
            return
            
        # 3. Compose valid
        if not os.path.exists(self.compose_file):
            self._log(f"Compose file missing: {self.compose_file}")
            messagebox.showerror("Missing File", "compose.codegate.yml not found.")
            return
            
        code, stdout, stderr = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "config"])
        if code == 0:
            self.compose_valid = True
        else:
            self._log(f"Compose config error: {stderr}")
            messagebox.showerror("Configuration Error", f"compose.codegate.yml is invalid.\nSee logs for details.")
            return

    def _update_ui_state(self):
        # Update labels
        for key, status in self.statuses.items():
            color = "#888888" # Unknown
            if status in ["READY", "PASS", "SUCCESS", "HEALTHY"]: color = "#4caf50"
            elif status in ["ERROR", "FAIL", "UNHEALTHY", "OCCUPIED"]: color = "#f44336"
            elif status in ["STARTING", "PENDING"]: color = "#ff9800"
            elif status in ["STOPPED", "EXITED"]: color = "#888888"
            
            self.status_labels[key].config(text=f"● {status}", foreground=color)
            
        # Overall status logic
        if not self.docker_running:
            self.overall_state = "DOCKER OFFLINE"
        elif any(s == "STARTING" for s in self.statuses.values()):
            self.overall_state = "STARTING"
        elif all(s in ["READY", "SUCCESS", "HEALTHY"] for s in self.statuses.values()):
            self.overall_state = "READY"
        elif self.statuses["postgres"] == "READY" and self.statuses["backend"] == "READY" and self.statuses["frontend"] == "READY":
            if self.statuses["worker"] != "READY":
                self.overall_state = "DEGRADED (Worker Offline)"
            else:
                self.overall_state = "DEGRADED"
        elif all(s in ["STOPPED", "EXITED", "UNKNOWN"] for s in self.statuses.values()):
            self.overall_state = "STOPPED"
        else:
            self.overall_state = "ERROR"
            
        overall_color = "#888888"
        if self.overall_state == "READY": overall_color = "#4caf50"
        elif "DEGRADED" in self.overall_state: overall_color = "#ff9800"
        elif self.overall_state == "ERROR": overall_color = "#f44336"
        
        self.lbl_overall.config(text=f"Overall Status: {self.overall_state}", foreground=overall_color)
        
        # Buttons logic
        if self.overall_state == "STARTING":
            self.btn_start.state(['disabled'])
            self.btn_stop.state(['disabled'])
            self.btn_restart.state(['disabled'])
            self.btn_force_rebuild.state(['disabled'])
        else:
            self.btn_start.state(['!disabled'])
            self.btn_stop.state(['!disabled'])
            self.btn_restart.state(['!disabled'])
            self.btn_force_rebuild.state(['!disabled'])
            
        if self.statuses["frontend"] == "READY":
            self.btn_open.state(['!disabled'])
        else:
            self.btn_open.state(['disabled'])

    def _check_port_available(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            try:
                s.bind(('127.0.0.1', port))
                return True
            except socket.error:
                return False

    def start_codegate(self):
        if self.overall_state in ["STARTING", "READY", "DEGRADED (Worker Offline)", "DEGRADED"]:
            return
            
        if not self.docker_running or not self.compose_valid:
            self._preflight_checks()
            if not self.docker_running or not self.compose_valid:
                return
                
        # Port check before starting
        code, stdout, _ = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "ps", "--format", "json"])
        containers_running = False
        if code == 0 and stdout.strip():
            # some containers are already running, port might be bound by docker itself, so we skip strict check if we own it
            containers_running = True
            
        if not containers_running:
            if not self._check_port_available(5173):
                messagebox.showerror("Port Conflict", "Port 5173 is already in use by another application.\nPlease free this port to start CodeGate.")
                return
            if not self._check_port_available(8000):
                messagebox.showerror("Port Conflict", "Port 8000 is already in use by another application.\nPlease free this port to start CodeGate.")
                return

        for k in self.statuses:
            self.statuses[k] = "STARTING"
        self._update_ui_state()
        
        threading.Thread(target=self._startup_sequence, daemon=True).start()

    def _startup_sequence(self):
        self._log("Starting CodeGate Docker stack...")
        code, stdout, stderr = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "up", "-d", "--build"], timeout=300)
        if code != 0:
            self._log(f"Failed to start stack: {stderr}")
            messagebox.showerror("Startup Error", f"Failed to start containers.\nSee logs for details.\n{stderr[:200]}")
            
        # Give it a moment before polling
        time.sleep(2)
        
        # Initial wait for Postgres and Migration
        # Actually, docker-compose up -d already handles depends_on and wait for healthy if configured correctly.
        # We will just let the normal health poller take over, which updates the UI.
        
        # Auto open dashboard on first run if it becomes ready within 60s
        for _ in range(30):
            if self.statuses["frontend"] == "READY":
                self.after(0, self.open_dashboard)
                break
            time.sleep(2)

    def stop_codegate(self):
        if self.overall_state == "STOPPED": return
        self._log("Stopping CodeGate...")
        for k in self.statuses:
            if self.statuses[k] not in ["STOPPED", "EXITED", "UNKNOWN"]:
                self.statuses[k] = "STOPPING"
        self._update_ui_state()
        
        def _stop():
            self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "stop"], timeout=120)
            self._poll_health_immediate()
            
        threading.Thread(target=_stop, daemon=True).start()

    def restart_codegate(self):
        self._log("Restarting CodeGate...")
        for k in self.statuses:
            self.statuses[k] = "STARTING"
        self._update_ui_state()
        
        def _restart():
            self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "restart"], timeout=120)
            self._poll_health_immediate()
            
        threading.Thread(target=_restart, daemon=True).start()

    def force_rebuild_codegate(self):
        if not self.docker_running or not self.compose_valid:
            self._preflight_checks()
            if not self.docker_running or not self.compose_valid:
                return
        
        res = messagebox.askyesno("Force Rebuild", "This will rebuild all containers without cache and restart CodeGate. Continue?")
        if not res: return
        
        self._log("Force rebuilding CodeGate...")
        for k in self.statuses:
            self.statuses[k] = "STARTING"
        self._update_ui_state()

        def _rebuild():
            self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "build", "--no-cache"], timeout=600)
            code, stdout, stderr = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "up", "-d"], timeout=120)
            if code != 0:
                self._log(f"Failed to start after rebuild: {stderr}")
                messagebox.showerror("Startup Error", f"Failed to start containers.\nSee logs for details.\n{stderr[:200]}")
            self._poll_health_immediate()

        threading.Thread(target=_rebuild, daemon=True).start()

    def _poll_health_immediate(self):
        if not self.docker_running: return
        
        # Get compose ps status
        code, stdout, _ = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "ps", "--format", "json"], timeout=10)
        
        ps_states = {}
        if code == 0 and stdout.strip():
            try:
                for line in stdout.strip().split('\n'):
                    data = json.loads(line)
                    svc = data.get("Service")
                    state = data.get("State")
                    health = data.get("Health", "")
                    ps_states[svc] = {"state": state, "health": health}
            except: pass

        # Postgres
        if ps_states.get("postgres", {}).get("state") == "running":
            if ps_states.get("postgres", {}).get("health") == "healthy":
                self.statuses["postgres"] = "READY"
            else:
                code, _, _ = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "exec", "-T", "postgres", "pg_isready", "-U", "codegate"], timeout=5)
                self.statuses["postgres"] = "READY" if code == 0 else "STARTING"
        else:
            self.statuses["postgres"] = "STOPPED"

        # Redis
        if ps_states.get("redis", {}).get("state") == "running":
            if ps_states.get("redis", {}).get("health") == "healthy":
                self.statuses["redis"] = "READY"
            else:
                code, _, _ = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "exec", "-T", "redis", "redis-cli", "ping"], timeout=5)
                self.statuses["redis"] = "READY" if code == 0 else "STARTING"
        else:
            self.statuses["redis"] = "STOPPED"

        # Migrate
        mig_state = ps_states.get("migrate", {}).get("state")
        if mig_state == "exited":
            # Check exit code
            code, out, _ = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "ps", "-a", "--format", "json"], timeout=10)
            success = False
            try:
                for line in out.strip().split('\n'):
                    d = json.loads(line)
                    if d.get("Service") == "migrate" and "Exit 0" in d.get("Status", ""):
                        success = True
            except: pass
            self.statuses["migrate"] = "SUCCESS" if success else "ERROR"
        elif mig_state == "running":
            self.statuses["migrate"] = "STARTING"
        else:
            self.statuses["migrate"] = "STOPPED"

        # Backend
        if ps_states.get("backend", {}).get("state") == "running":
            if requests:
                try:
                    r = requests.get("http://127.0.0.1:8000/api/v1/system/status", timeout=2)
                    self.statuses["backend"] = "READY" if r.status_code == 200 else "STARTING"
                except:
                    self.statuses["backend"] = "STARTING"
        else:
            self.statuses["backend"] = "STOPPED"

        # Worker
        if ps_states.get("worker", {}).get("state") == "running":
            if ps_states.get("worker", {}).get("health") == "healthy":
                self.statuses["worker"] = "READY"
            else:
                code, _, _ = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "exec", "-T", "worker", "celery", "-A", "codegate.worker.celery_app", "inspect", "ping"], timeout=5)
                self.statuses["worker"] = "READY" if code == 0 else "STARTING"
        else:
            self.statuses["worker"] = "STOPPED"

        # Frontend
        if ps_states.get("frontend", {}).get("state") == "running":
            if requests:
                try:
                    r = requests.get("http://127.0.0.1:5173", timeout=2)
                    self.statuses["frontend"] = "READY" if r.status_code == 200 else "STARTING"
                except:
                    self.statuses["frontend"] = "STARTING"
        else:
            self.statuses["frontend"] = "STOPPED"

        self.after(0, self._update_ui_state)

    def _poll_health(self):
        # Fire and forget thread for polling so UI doesn't lag
        threading.Thread(target=self._poll_health_immediate, daemon=True).start()
        self.after(5000, self._poll_health) # Poll every 5 seconds

    def open_dashboard(self):
        if self.statuses["frontend"] == "READY":
            webbrowser.open("http://127.0.0.1:5173/dashboard")

    def _redact_secrets(self, text):
        if not text: return ""
        # Redact JWTs/Tokens
        text = re.sub(r'gh[pousr]_[A-Za-z0-9_]+', '[REDACTED_GITHUB_TOKEN]', text)
        text = re.sub(r'gsk_[A-Za-z0-9]+', '[REDACTED_GROQ_KEY]', text)
        text = re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED_API_KEY]', text)
        text = re.sub(r'(?i)bearer\s+[a-z0-9\-\._~]+', 'Bearer [REDACTED]', text)
        text = re.sub(r'(?i)password[=:]\s*\S+', 'password=[REDACTED]', text)
        text = re.sub(r'postgresql\+psycopg2://[^:]+:[^@]+@', 'postgresql+psycopg2://[USER]:[REDACTED]@', text)
        return text

    def open_diagnostics(self):
        diag_win = tk.Toplevel(self)
        diag_win.title("Diagnostics")
        diag_win.geometry("500x400")
        diag_win.configure(bg="#1e1e1e")
        
        txt = scrolledtext.ScrolledText(diag_win, bg="#252526", fg="#e0e0e0", font=("Consolas", 9))
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        def run_diag():
            txt.insert(tk.END, "Running diagnostics...\n\n")
            
            # OS/Paths
            txt.insert(tk.END, f"OS: {os.name}\n")
            txt.insert(tk.END, f"Project Root: {PROJECT_ROOT}\n")
            
            # Docker
            code, out, _ = self._run_cmd(["docker", "--version"])
            txt.insert(tk.END, f"Docker Version: {out.strip() if code == 0 else 'Failed'}\n")
            code, out, _ = self._run_cmd(["docker", "compose", "version"])
            txt.insert(tk.END, f"Compose Version: {out.strip() if code == 0 else 'Failed'}\n")
            
            # Ports
            txt.insert(tk.END, f"Port 5173 Available: {self._check_port_available(5173)}\n")
            txt.insert(tk.END, f"Port 8000 Available: {self._check_port_available(8000)}\n")
            
            # Compose PS
            code, out, _ = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "ps", "-a"])
            txt.insert(tk.END, f"\nContainer Status:\n{out}\n")
            
            # Save export
            report = self._redact_secrets(txt.get("1.0", tk.END))
            txt.delete("1.0", tk.END)
            txt.insert(tk.END, report)
            
            filename = f"codegate-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            path = os.path.join(self.diagnostics_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
                
            txt.insert(tk.END, f"\nDiagnostics saved to:\n{path}\n")
            
        threading.Thread(target=run_diag, daemon=True).start()

    def view_logs(self):
        log_win = tk.Toplevel(self)
        log_win.title("Logs")
        log_win.geometry("700x500")
        log_win.configure(bg="#1e1e1e")
        
        top_frame = ttk.Frame(log_win, padding="10")
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="Select Component:").pack(side=tk.LEFT, padx=(0, 10))
        cb = ttk.Combobox(top_frame, values=["backend", "worker", "frontend", "postgres", "redis", "migrate"])
        cb.set("backend")
        cb.pack(side=tk.LEFT)
        
        txt = scrolledtext.ScrolledText(log_win, bg="#1e1e1e", fg="#cccccc", font=("Consolas", 9))
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        def fetch_logs():
            comp = cb.get()
            txt.delete("1.0", tk.END)
            txt.insert(tk.END, f"Fetching logs for {comp}...\n")
            code, out, err = self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "logs", "--tail=200", comp], timeout=15)
            txt.delete("1.0", tk.END)
            if code == 0:
                txt.insert(tk.END, self._redact_secrets(out))
            else:
                txt.insert(tk.END, f"Error fetching logs: {err}")
                
        btn_refresh = ttk.Button(top_frame, text="Refresh", command=lambda: threading.Thread(target=fetch_logs, daemon=True).start())
        btn_refresh.pack(side=tk.LEFT, padx=10)
        
        threading.Thread(target=fetch_logs, daemon=True).start()
        cb.bind("<<ComboboxSelected>>", lambda e: threading.Thread(target=fetch_logs, daemon=True).start())

    def _on_closing(self):
        if self.overall_state not in ["STOPPED", "ERROR", "DOCKER OFFLINE"]:
            res = messagebox.askyesnocancel(
                "Exit CodeGate",
                "Stop CodeGate services before exiting?\n\nYes: Stop and Exit\nNo: Keep running in background\nCancel: Return to Launcher"
            )
            if res is True:
                # Stop and Exit
                self.withdraw() # Hide window while stopping
                self._run_cmd(["docker", "compose", "-f", "compose.codegate.yml", "-p", "codegate", "stop"], timeout=120)
                self.destroy()
            elif res is False:
                # Keep running and exit GUI
                self.destroy()
            else:
                # Cancel
                pass
        else:
            self.destroy()

if __name__ == "__main__":
    auto = "--start" in sys.argv
    app = CodeGateLauncher(auto_start=auto)
    app.mainloop()
