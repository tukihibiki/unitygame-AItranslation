"""Hanhua — GUI Launcher for Unity Mono Game LLM Translation.

Entry: python run_gui.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import threading
import json
import os
import sys
import queue
import time
import asyncio
from urllib.request import urlopen, Request
from urllib.error import URLError

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")

PROVIDERS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-flash",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "Qwen (通义千问)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "env_key": "OPENAI_API_KEY",
    },
    "Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "env_key": "GEMINI_API_KEY",
    },
    "Custom": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3:32b",
        "env_key": "",
    },
}

SERVER_URL = "http://127.0.0.1:56443"
DEFAULT_FONT = ("Microsoft YaHei UI", 10)


class HanhuaGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Hanhua — Unity游戏日语 LLM 实时翻译")
        self.root.geometry("900x620")
        self.root.minsize(800, 520)
        self.root.configure(bg="#1e1e1e")

        self._server_process: subprocess.Popen | None = None
        self._log_queue = queue.Queue()
        self._games: list[dict] = []
        self._stats_update_id: str | None = None

        self._setup_style()
        self._build_ui()
        self._load_config()
        self._load_games()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Defer network polling to avoid blocking startup
        self.root.after(500, self._poll_server_status)
        self.root.after(1000, self._start_history_polling)

    # ─── Style ──────────────────────────────────────────────────

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        bg = "#1e1e1e"
        fg = "#d4d4d4"
        sel = "#264f78"
        style.configure(".", background=bg, foreground=fg, fieldbackground="#2d2d2d")
        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground="#569cd6", font=(DEFAULT_FONT[0], 10, "bold"))
        style.configure("TLabel", background=bg, foreground=fg, font=DEFAULT_FONT)
        style.configure("TButton", background="#333", foreground=fg, font=DEFAULT_FONT, padding=6)
        style.map("TButton", background=[("active", "#444")])
        style.configure("TEntry", foreground=fg, fieldbackground="#2d2d2d", padding=4)
        style.configure("TCombobox", foreground=fg, fieldbackground="#2d2d2d", padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", "#2d2d2d")], foreground=[("readonly", fg)])
        self.root.option_add("*TCombobox*Listbox*Foreground", fg)
        self.root.option_add("*TCombobox*Listbox*Background", "#2d2d2d")
        style.configure("Green.TButton", background="#1a3a1a", foreground="#4ec94e")
        style.configure("Red.TButton", background="#3a1a1a", foreground="#f44747")
        style.configure("Blue.TButton", background="#1a2a3a", foreground="#569cd6")
        style.configure("TNotebook", background=bg)
        style.configure("TNotebook.Tab", background="#2d2d2d", foreground=fg, padding=[12, 4])
        style.map("TNotebook.Tab", background=[("selected", "#3a3a3a")])
        style.configure("Treeview", background="#2d2d2d", foreground=fg, fieldbackground="#2d2d2d")
        style.map("Treeview", background=[("selected", sel)])
        style.configure("TScrollbar", background="#333")
        style.configure("Horizontal.TScale", background=bg)

    # ─── UI Construction ────────────────────────────────────────

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        tab_settings = ttk.Frame(notebook)
        tab_games = ttk.Frame(notebook)
        notebook.add(tab_settings, text="AI 配置 & 服务")
        notebook.add(tab_games, text="游戏管理")

        self._build_settings_tab(tab_settings)
        self._build_games_tab(tab_games)

        # Bottom status bar
        self._status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self._status_var, relief="sunken", anchor="w", padding=(8, 2))
        status_bar.pack(side="bottom", fill="x")

    # ─── Settings Tab ───────────────────────────────────────────

    def _build_settings_tab(self, parent):
        # === AI Config ===
        ai_frame = ttk.LabelFrame(parent, text="AI 配置", padding=10)
        ai_frame.pack(fill="x", padx=6, pady=(6, 4))

        # -- Local AI --
        local_row = ttk.Frame(ai_frame)
        local_row.pack(fill="x", pady=2)
        self._local_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(local_row, text="本地 AI (Ollama)", variable=self._local_enabled_var).pack(side="left")
        self._local_model_var = tk.StringVar(value="qwen3:0.6b")
        self._local_model_cb = ttk.Combobox(local_row, textvariable=self._local_model_var,
            values=["qwen3:0.6b", "qwen3:8b", "qwen3:32b", "gemma3:1b", "gemma3:4b"],
            width=18, state="readonly")
        self._local_model_cb.pack(side="left", padx=4)
        ttk.Label(local_row, text="URL:").pack(side="left")
        self._ollama_url_var = tk.StringVar(value="http://127.0.0.1:11434")
        ttk.Entry(local_row, textvariable=self._ollama_url_var, width=24).pack(side="left", padx=2)
        ttk.Label(local_row, text="超时:").pack(side="left")
        self._ollama_timeout_var = tk.IntVar(value=10)
        ttk.Entry(local_row, textvariable=self._ollama_timeout_var, width=4).pack(side="left", padx=2)
        ttk.Label(local_row, text="s").pack(side="left")
        ttk.Button(local_row, text="检测", command=self._detect_local_models).pack(side="left", padx=4)
        ttk.Label(local_row, text="← 优先", foreground="#4ec94e", font=(DEFAULT_FONT[0], 9, "bold")).pack(side="left", padx=4)

        # -- Cloud AI --
        cloud_row = ttk.Frame(ai_frame)
        cloud_row.pack(fill="x", pady=2)
        self._cloud_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cloud_row, text="云端 AI (API)", variable=self._cloud_enabled_var).pack(side="left")
        self._provider_var = tk.StringVar(value="DeepSeek")
        ttk.Combobox(cloud_row, textvariable=self._provider_var, values=list(PROVIDERS.keys()),
                     state="readonly", width=14).pack(side="left", padx=4)
        ttk.Label(cloud_row, text="Key:").pack(side="left")
        self._apikey_var = tk.StringVar()
        ttk.Entry(cloud_row, textvariable=self._apikey_var, show="•", width=38).pack(side="left", padx=2)
        self._show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cloud_row, text="显示", variable=self._show_key_var, command=self._toggle_show_key).pack(side="left")
        ttk.Label(cloud_row, text="← 兜底", foreground="#f44747", font=(DEFAULT_FONT[0], 9, "bold")).pack(side="left", padx=4)

        # -- Advanced row --
        adv_row = ttk.Frame(ai_frame)
        adv_row.pack(fill="x", pady=2)
        ttk.Label(adv_row, text="模型:").pack(side="left")
        self._model_var = tk.StringVar(value="deepseek-v4-flash")
        ttk.Entry(adv_row, textvariable=self._model_var, width=22).pack(side="left", padx=2)
        ttk.Label(adv_row, text="URL:").pack(side="left")
        self._baseurl_var = tk.StringVar(value="https://api.deepseek.com/v1")
        ttk.Entry(adv_row, textvariable=self._baseurl_var, width=42).pack(side="left", padx=2)
        ttk.Label(adv_row, text="Temp:").pack(side="left", padx=(8, 0))
        self._temp_var = tk.DoubleVar(value=0.1)
        ttk.Scale(adv_row, from_=0.0, to=1.0, variable=self._temp_var, length=80).pack(side="left", padx=2)
        self._temp_label = ttk.Label(adv_row, text="0.1", width=3)
        self._temp_label.pack(side="left")
        self._temp_var.trace_add("write", lambda *_: self._temp_label.configure(text=f"{self._temp_var.get():.1f}"))
        ttk.Label(adv_row, text="端口:").pack(side="left", padx=(8, 0))
        self._port_var = tk.IntVar(value=56443)
        ttk.Entry(adv_row, textvariable=self._port_var, width=6).pack(side="left", padx=2)

        # Save button
        save_btn_row = ttk.Frame(ai_frame)
        save_btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(save_btn_row, text="保存全部配置", command=self._save_config, style="Blue.TButton").pack(side="left")

        # === Server Control ===
        srv_frame = ttk.LabelFrame(parent, text="翻译引擎", padding=10)
        srv_frame.pack(fill="x", padx=6, pady=4)

        status_row = ttk.Frame(srv_frame)
        status_row.pack(fill="x", pady=2)
        ttk.Label(status_row, text="状态:", width=5).pack(side="left")
        self._server_status_var = tk.StringVar(value="检测中...")
        self._server_status_label = ttk.Label(status_row, textvariable=self._server_status_var, foreground="#888")
        self._server_status_label.pack(side="left", padx=4)
        self._server_pid_var = tk.StringVar(value="")
        ttk.Label(status_row, textvariable=self._server_pid_var, foreground="#666", font=(DEFAULT_FONT[0], 8)).pack(side="left", padx=4)

        btn_frame = ttk.Frame(srv_frame)
        btn_frame.pack(fill="x", pady=(4, 0))
        self._start_btn = ttk.Button(btn_frame, text="启动", command=self._start_server, style="Green.TButton", width=8)
        self._start_btn.pack(side="left", padx=2)
        self._stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop_server, style="Red.TButton", width=8, state="disabled")
        self._stop_btn.pack(side="left", padx=2)
        ttk.Button(btn_frame, text="重启", command=self._restart_server, width=8).pack(side="left", padx=2)

        # === Stats ===
        stats_frame = ttk.LabelFrame(parent, text="翻译统计", padding=10)
        stats_frame.pack(fill="x", padx=6, pady=4)

        self._stats_text = tk.Text(stats_frame, height=4, width=60, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4", relief="flat", borderwidth=0)
        self._stats_text.pack(fill="x")

        # Log viewer
        log_frame = ttk.LabelFrame(parent, text="实时翻译日志", padding=10)
        log_frame.pack(fill="both", expand=True, padx=6, pady=(4, 6))

        log_tree_frame = ttk.Frame(log_frame)
        log_tree_frame.pack(fill="both", expand=True)
        columns = ("time", "source", "target")
        self._log_tree = ttk.Treeview(log_tree_frame, columns=columns, show="headings", height=8)
        self._log_tree.heading("time", text="时间")
        self._log_tree.heading("source", text="日语")
        self._log_tree.heading("target", text="中文")
        self._log_tree.column("time", width=80)
        self._log_tree.column("source", width=280)
        self._log_tree.column("target", width=300)
        log_scroll = ttk.Scrollbar(log_tree_frame, orient="vertical", command=self._log_tree.yview)
        self._log_tree.configure(yscrollcommand=log_scroll.set)
        self._log_tree.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        ttk.Button(log_frame, text="清空日志", command=self._clear_log).pack(anchor="e", pady=(4, 0))

    # ─── Games Tab ──────────────────────────────────────────────

    def _build_games_tab(self, parent):
        # Top: add game
        add_frame = ttk.LabelFrame(parent, text="添加游戏", padding=10)
        add_frame.pack(fill="x", padx=6, pady=(6, 4))

        row1 = ttk.Frame(add_frame)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="启动程序:", width=10).pack(side="left")
        self._game_exe_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._game_exe_var, width=58).pack(side="left", padx=4)
        ttk.Button(row1, text="选择...", command=self._browse_exe).pack(side="left", padx=2)
        ttk.Button(row1, text="添加游戏", command=self._add_game, style="Blue.TButton").pack(side="left", padx=4)

        row2 = ttk.Frame(add_frame)
        row2.pack(fill="x", pady=2)
        ttk.Button(row2, text="自动扫描目录...", command=self._scan_for_games).pack(side="left", padx=4)
        ttk.Label(row2, text="（扫描文件夹批量导入Unity Mono游戏）", foreground="#888").pack(side="left")

        # Game list
        list_frame = ttk.LabelFrame(parent, text="已添加游戏", padding=10)
        list_frame.pack(fill="both", expand=True, padx=6, pady=(4, 6))

        # Left-right split: game list | history
        split_pane = ttk.PanedWindow(list_frame, orient="horizontal")
        split_pane.pack(fill="both", expand=True)

        # Left: game list
        left_frame = ttk.Frame(split_pane, width=400)
        split_pane.add(left_frame, weight=2)

        self._game_tree = ttk.Treeview(left_frame, columns=("name", "path", "type", "inj"), show="headings", height=8)
        self._game_tree.heading("name", text="游戏名称")
        self._game_tree.heading("path", text="路径")
        self._game_tree.heading("type", text="类型")
        self._game_tree.heading("inj", text="注入")
        self._game_tree.column("name", width=140)
        self._game_tree.column("path", width=240)
        self._game_tree.column("type", width=70)
        self._game_tree.column("inj", width=50)
        game_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self._game_tree.yview)
        self._game_tree.configure(yscrollcommand=game_scroll.set)
        self._game_tree.pack(side="left", fill="both", expand=True)
        game_scroll.pack(side="right", fill="y")
        self._game_tree.bind("<Double-1>", self._on_game_double_click)
        self._game_tree.bind("<Button-3>", self._on_game_right_click)

        # Right: history
        right_frame = ttk.Frame(split_pane, width=400)
        split_pane.add(right_frame, weight=3)
        ttk.Label(right_frame, text="翻译历史", font=("Microsoft YaHei UI", 9, "bold"),
                  foreground="#569cd6").pack(anchor="w")
        hist_cols = ("time", "model", "source", "dur")
        self._hist_tree = ttk.Treeview(right_frame, columns=hist_cols, show="headings", height=8)
        self._hist_tree.heading("time", text="时间")
        self._hist_tree.heading("model", text="AI")
        self._hist_tree.heading("source", text="原文 → 译文")
        self._hist_tree.heading("dur", text="耗时")
        self._hist_tree.column("time", width=60)
        self._hist_tree.column("model", width=55)
        self._hist_tree.column("source", width=240)
        self._hist_tree.column("dur", width=50)
        hist_scroll = ttk.Scrollbar(right_frame, orient="vertical", command=self._hist_tree.yview)
        self._hist_tree.configure(yscrollcommand=hist_scroll.set)
        self._hist_tree.pack(side="left", fill="both", expand=True)
        hist_scroll.pack(side="right", fill="y")
        ttk.Button(right_frame, text="刷新", command=self._refresh_history).pack(anchor="e", pady=(2, 0))

        self._game_menu = tk.Menu(self.root, tearoff=0, bg="#2d2d2d", fg="#d4d4d4")
        self._game_menu.add_command(label="启动游戏", command=lambda: self._launch_game(auto_start=True))
        self._game_menu.add_command(label="在资源管理器中打开", command=self._open_game_folder)
        self._game_menu.add_separator()
        self._game_menu.add_command(label="删除", command=self._remove_game)

        btn_frame = ttk.Frame(list_frame)
        ttk.Button(btn_frame, text="启动游戏", command=lambda: self._launch_game(auto_start=True), style="Green.TButton").pack(side="left", padx=4)
        ttk.Button(btn_frame, text="移除选中", command=self._remove_game, style="Red.TButton").pack(side="left", padx=4)
        ttk.Button(btn_frame, text="在资源管理器中打开", command=self._open_game_folder).pack(side="left", padx=4)

    # ─── Provider Change ────────────────────────────────────────

    def _on_provider_change(self, event=None):
        provider = self._provider_var.get()
        info = PROVIDERS.get(provider, {})
        self._baseurl_var.set(info.get("base_url", ""))
        self._model_var.set(info.get("model", ""))

        env_key = info.get("env_key", "")
        if env_key:
            existing = self._apikey_var.get()
            if not existing:
                env_val = os.environ.get(env_key, "")
                self._apikey_var.set(env_val)

        self._apikey_var.set("")

    # ─── Toggle Show Key ────────────────────────────────────────

    def _toggle_show_key(self):
        self._apikey_entry.configure(show="" if self._show_key_var.get() else "•")

    # ─── Config Persistence ─────────────────────────────────────

    def _load_config(self):
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception:
            return

        llm = config.get("llm", {})
        self._cloud_enabled_var.set(llm.get("enabled", True) if isinstance(llm, dict) else True)
        server = config.get("server", {})

        # Match provider
        base = llm.get("base_url", "")
        model = llm.get("model", "")
        for name, info in PROVIDERS.items():
            if info["base_url"] == base:
                self._provider_var.set(name)
                break
        else:
            self._provider_var.set("Custom")

        self._baseurl_var.set(base)
        self._model_var.set(model)
        self._temp_var.set(llm.get("temperature", 0.1))
        self._port_var.set(server.get("port", 56422))

        # Load Ollama settings
        ollama = config.get("ollama", {})
        self._local_enabled_var.set(ollama.get("enabled", True) if isinstance(ollama, dict) else True)
        self._local_model_var.set(ollama.get("model", "qwen3:0.6b") if isinstance(ollama, dict) else "qwen3:0.6b")
        self._ollama_url_var.set(ollama.get("base_url", "http://127.0.0.1:11434") if isinstance(ollama, dict) else "http://127.0.0.1:11434")
        self._ollama_timeout_var.set(ollama.get("timeout", 10) if isinstance(ollama, dict) else 10)

        # Attempt to load key from env
        provider = self._provider_var.get()
        env_key = PROVIDERS.get(provider, {}).get("env_key", "")
        if env_key:
            self._apikey_var.set(os.environ.get(env_key, ""))

    def _save_config(self):
        provider = self._provider_var.get()
        info = PROVIDERS.get(provider, {})

        config = {
            "server": {
                "host": "0.0.0.0",
                "port": self._port_var.get(),
            },
            "llm": {
                "enabled": self._cloud_enabled_var.get(),
                "provider": provider.lower().split()[0],
                "api_key": self._apikey_var.get() or self._load_existing_key("api_key"),
                "base_url": self._baseurl_var.get(),
                "model": self._model_var.get(),
                "temperature": self._temp_var.get(),
                "max_tokens": 200,
                "timeout": 15,
                "max_retries": 2,
            },
            "cache": {
                "max_entries": 10000,
                "db_path": "./translations.db",
            },
            "debounce": {
                "window_ms": 500,
                "immediate_on_punctuation": True,
            },
            "language": {
                "model_path": "./lid.176.bin",
                "min_confidence": 0.7,
            },
            "ollama": {
                "enabled": self._local_enabled_var.get(),
                "base_url": self._ollama_url_var.get(),
                "model": self._local_model_var.get(),
                "timeout": self._ollama_timeout_var.get(),
            },
        }

        import yaml
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # Set env var for current session
        env_key = info.get("env_key", "")
        if env_key and self._apikey_var.get():
            os.environ[env_key] = self._apikey_var.get()

        self._set_status("配置已保存")
        messagebox.showinfo("成功", "配置已保存到 config.yaml")

    # ─── Server Control ─────────────────────────────────────────

    def _start_server(self):
        # Check if our managed process is still alive
        if self._server_process is not None:
            if self._server_process.poll() is None:
                messagebox.showwarning("提示", "翻译服务已在运行中")
                return
            else:
                # Process died, clean up
                self._server_process = None

        # Check if a server is already running on the port
        port = self._port_var.get()
        try:
            import urllib.request
            url = f"http://127.0.0.1:{port}/health"
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                self._server_status_var.set("● 运行中")
                self._server_status_label.configure(foreground="#4ec94e")
                self._start_btn.configure(state="disabled")
                self._stop_btn.configure(state="normal")
                self._set_status("翻译服务已在运行中（复用已有服务）")
                self._start_stats_polling()
                return
        except Exception:
            pass

        self._save_config()

        try:
            self._server_process = subprocess.Popen(
                [sys.executable, "-m", "translator"],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            threading.Thread(target=self._read_server_output, daemon=True).start()
            self._start_btn.configure(state="disabled")
            self._stop_btn.configure(state="normal")
            self._server_status_var.set("● 启动中...")
            self._server_status_label.configure(foreground="#e8a91a")
            self._set_status("翻译服务启动中...")

            # Poll until ready
            threading.Thread(target=self._wait_for_server, daemon=True).start()
        except Exception as e:
            messagebox.showerror("错误", f"启动服务失败: {e}")

    def _wait_for_server(self):
        for _ in range(15):
            time.sleep(1)
            try:
                resp = urlopen(f"{SERVER_URL}/health", timeout=2)
                if resp.status == 200:
                    self.root.after(0, self._on_server_ready)
                    return
            except Exception:
                pass
        self.root.after(0, lambda: self._server_status_var.set("● 启动失败"))
        self.root.after(0, lambda: self._server_status_label.configure(foreground="#f44747"))

    def _on_server_ready(self):
        self._server_status_var.set("● 运行中")
        self._server_status_label.configure(foreground="#4ec94e")
        self._set_status("翻译服务已就绪 — 可以启动游戏了")
        self._start_stats_polling()

    def _stop_server(self):
        self._stop_stats_polling()

        # Also kill any external server on our port
        port = self._port_var.get()
        try:
            import subprocess as sp
            r = sp.run(['netstat', '-ano'], capture_output=True, text=True)
            for line in r.stdout.split('\n'):
                if f':{port}' in line and 'LISTENING' in line:
                    pid = line.strip().split()[-1]
                    sp.run(['taskkill', '/F', '/PID', pid], capture_output=True)
        except Exception:
            pass

        if self._server_process is not None:
            try:
                self._server_process.terminate()
                self._server_process.wait(timeout=5)
            except Exception:
                try:
                    self._server_process.kill()
                except Exception:
                    pass

        self._server_process = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._server_status_var.set("● 已停止")
        self._server_status_label.configure(foreground="#888")
        self._server_pid_var.set("")
        self._set_status("翻译引擎已停止")

    def _restart_server(self):
        self._stop_server()
        time.sleep(1)
        self._start_server()

    def _read_server_output(self):
        try:
            for line in iter(self._server_process.stdout.readline, ""):
                if not line:
                    break
                self._log_queue.put(line.strip())
        except Exception:
            pass

    def _poll_server_status(self):
        """Check server status in background thread."""
        def check():
            port = self._port_var.get()
            try:
                import urllib.request
                resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                if resp.status == 200:
                    self.root.after(0, self._on_server_alive)
                    return
            except Exception:
                pass
            self.root.after(0, self._on_server_dead)
        threading.Thread(target=check, daemon=True).start()

        # Process log queue
        while not self._log_queue.empty():
            try:
                line = self._log_queue.get_nowait()
                self._parse_server_log(line)
            except queue.Empty:
                break

        self._status_id = self.root.after(3000, self._poll_server_status)

    def _on_server_alive(self):
        port = self._port_var.get()
        import subprocess as sp
        r = sp.run(['netstat', '-ano'], capture_output=True, text=True)
        pid_str = ""
        for line in r.stdout.split('\n'):
            if f':{port}' in line and 'LISTENING' in line:
                pid_str = f"PID {line.strip().split()[-1]}"
                break
        self._server_status_var.set("● 运行中")
        self._server_status_label.configure(foreground="#4ec94e")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._server_pid_var.set(pid_str)

    def _on_server_dead(self):
        if self._server_status_var.get() != "● 未启动":
            self._server_status_var.set("● 未启动")
            self._server_status_label.configure(foreground="#888")
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._server_pid_var.set("")

    def _on_server_died(self):
        self._server_process = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._server_status_var.set("● 意外停止")
        self._server_status_label.configure(foreground="#f44747")
        self._stop_stats_polling()

    def _parse_server_log(self, line: str):
        """Parse server stdout and add to log tree."""
        if "Received:" in line:
            try:
                text = line.split("Received:", 1)[1].strip().strip("'")
                if len(text) < 3 or text.startswith("[") or text.startswith("\\x"):
                    return
                # Store for pairing with Translated
                self._last_received = text
            except Exception:
                return
        elif "Translated:" in line:
            try:
                text = line.split("Translated:", 1)[1].strip().strip("'")
                if text.startswith("[") and text.endswith("]"):
                    return  # Skip error messages
                source = getattr(self, "_last_received", "") or "..."
                now = time.strftime("%H:%M:%S")
                self.root.after(0, lambda s=source, t=text, n=now: self._add_log_entry(n, s, t))
            except Exception:
                return

    def _add_log_entry(self, time_str: str, source: str, target: str):
        items = self._log_tree.get_children()
        if len(items) >= 200:
            self._log_tree.delete(items[0])
        self._log_tree.insert("", "end", values=(time_str, source[:60], target[:60]))
        self._log_tree.yview_moveto(1.0)

    def _clear_log(self):
        for item in self._log_tree.get_children():
            self._log_tree.delete(item)

    # ─── Stats Polling ──────────────────────────────────────────

    def _start_stats_polling(self):
        self._poll_stats()

    def _stop_stats_polling(self):
        if self._stats_update_id:
            self.root.after_cancel(self._stats_update_id)
            self._stats_update_id = None

    def _poll_stats(self):
        def fetch():
            try:
                import urllib.request, json
                resp = urllib.request.urlopen(f"{SERVER_URL}/stats", timeout=2)
                data = json.loads(resp.read().decode())
                text = (
                    f"请求总数: {data.get('requests', 0):>5}  |  "
                    f"本地AI: {data.get('local_hits', 0):>4}  |  "
                    f"云端AI: {data.get('cloud_hits', 0):>4}  |  "
                    f"缓存命中: {data.get('cache_hits', 0):>5}  |  "
                    f"缓存条目: {data.get('cache_entries', 0):>5}  |  "
                    f"费用: ${data.get('llm_cost', 0):.5f}"
                )
                self.root.after(0, lambda t=text: self._update_stats(t))
            except Exception:
                pass
        threading.Thread(target=fetch, daemon=True).start()
        self._stats_update_id = self.root.after(3000, self._poll_stats)

    def _update_stats(self, text):
        self._stats_text.delete("1.0", "end")
        self._stats_text.insert("1.0", text)

    # ─── Game Management ────────────────────────────────────────

    def _browse_exe(self):
        path = filedialog.askopenfilename(title="选择游戏可执行文件", filetypes=[("EXE files", "*.exe"), ("All files", "*.*")])
        if path:
            self._game_exe_var.set(path)

    def _detect_game_type(self, path: str) -> str:
        data_dir = None
        exe_name = None
        if path.lower().endswith(".exe"):
            exe_name = os.path.splitext(os.path.basename(path))[0]
            data_dir = os.path.join(os.path.dirname(path), f"{exe_name}_Data")
        elif os.path.isdir(path):
            for f in os.listdir(path):
                if f.lower().endswith(".exe") and "unity" not in f.lower():
                    exe_name = os.path.splitext(f)[0]
                    data_dir = os.path.join(path, f"{exe_name}_Data")
                    break

        if data_dir and os.path.isdir(data_dir):
            managed = os.path.join(data_dir, "Managed")
            if os.path.isdir(managed):
                asm = os.path.join(managed, "Assembly-CSharp.dll")
                if os.path.isfile(asm):
                    # Check Mono vs IL2CPP
                    parent = os.path.dirname(data_dir)
                    if os.path.isfile(os.path.join(parent, "mono-2.0-bdwgc.dll")) or \
                       os.path.isfile(os.path.join(parent, "MonoBleedingEdge", "EmbedRuntime", "mono-2.0-bdwgc.dll")):
                        return "Unity Mono"
                    if os.path.isfile(os.path.join(parent, "GameAssembly.dll")):
                        return "Unity IL2CPP"
                    return "Unity (未知)"
        return "未知"

    def _scan_for_games(self):
        folder = filedialog.askdirectory(title="选择扫描根目录")
        if not folder:
            return

        found = 0
        for root, dirs, files in os.walk(folder):
            depth = root[len(folder):].count(os.sep)
            if depth > 3:
                continue

            for f in files:
                if f.lower().endswith(".exe") and "unity" not in f.lower() and "setup" not in f.lower():
                    exe_path = os.path.join(root, f)
                    game_type = self._detect_game_type(exe_path)
                    if "Mono" in game_type:
                        self._games.append({
                            "name": os.path.splitext(f)[0],
                            "folder": root,
                            "exe": exe_path,
                            "type": game_type,
                        })
                        found += 1

        self._save_games()
        self._refresh_game_list()
        self._set_status(f"扫描完成: 找到 {found} 个 Unity Mono 游戏")
        if found == 0:
            messagebox.showinfo("扫描结果", "未找到 Unity Mono 游戏")

    def _add_game(self):
        exe = self._game_exe_var.get().strip()

        if not exe or not os.path.isfile(exe):
            messagebox.showwarning("提示", "请选择游戏的 .exe 文件")
            return

        folder = os.path.dirname(exe)

        game_type = self._detect_game_type(exe)
        name = os.path.splitext(os.path.basename(exe))[0]

        for g in self._games:
            if g["exe"] == exe:
                messagebox.showinfo("提示", "该游戏已存在列表中")
                return

        # Auto-inject: deploy CustomTranslate.dll + Config.ini
        injected = self._auto_inject(folder, name)

        self._games.append({"name": name, "folder": folder, "exe": exe, "type": game_type, "injected": injected})
        self._save_games()
        self._refresh_game_list()
        status = f"已添加: {name} ({game_type})"
        if injected:
            status += " — 翻译组件已部署"
        self._set_status(status)

    def _auto_inject(self, game_folder: str, game_name: str) -> bool:
        """Auto-deploy CustomTranslate.dll + Config.ini to game if AutoTranslator exists."""
        data_dir = os.path.join(game_folder, f"{game_name}_Data")
        if not os.path.isdir(data_dir):
            return False

        translators_dir = os.path.join(data_dir, "Managed", "Translators")
        if not os.path.isdir(translators_dir):
            # Check BepInEx path
            bep_translators = os.path.join(game_folder, "BepInEx", "plugins", "XUnity.AutoTranslator", "Translators")
            if os.path.isdir(bep_translators):
                translators_dir = bep_translators
            else:
                return False

        # Deploy our CustomTranslate.dll
        our_dll = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CustomTranslate.dll")
        if os.path.isfile(our_dll):
            target_dll = os.path.join(translators_dir, "CustomTranslate.dll")
            try:
                import shutil
                # Backup original if not already backed up
                bak = target_dll + ".bak"
                if os.path.isfile(target_dll) and not os.path.isfile(bak):
                    shutil.copy2(target_dll, bak)
                shutil.copy2(our_dll, target_dll)
            except Exception:
                return False

        # Deploy Config.ini
        config_dir = os.path.join(game_folder, "AutoTranslator")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "Config.ini")

        if not os.path.isfile(config_path):
            port = self._port_var.get()
            ini_content = (
                "[Service]\nEndpoint=CustomTranslate\n\n"
                "[General]\nLanguage=zh\nFromLanguage=auto\n\n"
                "[Custom]\n"
                f"Url=http://127.0.0.1:{port}\n"
                "EnableShortDelay=True\nDisableSpamChecks=True\nMaxConcurrency=4\n\n"
                "[Behaviour]\nEnableUGUI=True\nEnableTextMeshPro=True\nEnableNGUI=True\n"
                "EnableSilentMode=True\n"
            )
            try:
                with open(config_path, "w", encoding="utf-8-sig") as f:
                    f.write(ini_content)
            except Exception:
                pass

        return True

    def _remove_game(self):
        selected = self._game_tree.selection()
        if not selected:
            return
        idx = self._game_tree.index(selected[0])
        if idx < len(self._games):
            name = self._games[idx]["name"]
            del self._games[idx]
            self._save_games()
            self._refresh_game_list()
            self._set_status(f"已移除: {name}")

    def _on_game_double_click(self, event):
        """Double-click game to launch with auto-start server."""
        self._launch_game(auto_start=True)

    def _on_game_right_click(self, event):
        """Right-click context menu."""
        item = self._game_tree.identify_row(event.y)
        if item:
            self._game_tree.selection_set(item)
            self._game_menu.post(event.x_root, event.y_root)

    def _launch_game(self, auto_start=True):
        selected = self._game_tree.selection()
        if not selected:
            if self._games:
                game = self._games[0]
            else:
                messagebox.showwarning("提示", "请先添加游戏")
                return
        else:
            idx = self._game_tree.index(selected[0])
            game = self._games[idx]

        # Auto-start server if needed
        if auto_start:
            port = self._port_var.get()
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            except Exception:
                self._set_status("自动启动翻译服务...")
                self._start_server()
                time.sleep(2)

        exe = game["exe"]
        folder = game["folder"]
        self._set_status(f"正在启动: {game['name']}...")

        try:
            subprocess.Popen(exe, cwd=folder)
            self._set_status(f"游戏已启动: {game['name']}")
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动游戏:\n{e}")

    def _open_game_folder(self):
        selected = self._game_tree.selection()
        if not selected:
            return
        idx = self._game_tree.index(selected[0])
        if idx < len(self._games):
            os.startfile(self._games[idx]["folder"])

    def _refresh_game_list(self):
        for item in self._game_tree.get_children():
            self._game_tree.delete(item)
        for g in self._games:
            injected = "已注入" if g.get("injected") else "未注入"
            self._game_tree.insert("", "end", values=(g["name"], g["folder"], g["type"], injected))

    def _refresh_history(self):
        """Load history in background thread."""
        def fetch():
            try:
                import urllib.request, json
                resp = urllib.request.urlopen(f"{SERVER_URL}/history?limit=50", timeout=2)
                rows = json.loads(resp.read().decode())
                self.root.after(0, lambda: self._update_history_tree(rows))
            except Exception:
                pass
        threading.Thread(target=fetch, daemon=True).start()
        self.root.after(5000, self._refresh_history)

    def _update_history_tree(self, rows):
        for item in self._hist_tree.get_children():
            self._hist_tree.delete(item)
        for r in rows:
            source = r["source"][:30]
            target = r["target"][:30]
            display = f"{source} -> {target}"
            model = r.get("model", "")
            ai = "local" if model == "hybrid" else "cloud" if "deepseek" in model else model[:6]
            dur = f"{r.get('duration_ms', 0):.0f}ms"
            self._hist_tree.insert("", "end", values=(r["time"], ai, display, dur))

    def _start_history_polling(self):
        self._refresh_history()

    def _save_games(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "games.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._games, f, ensure_ascii=False, indent=2)

    def _load_games(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "games.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._games = json.load(f)
            except Exception:
                self._games = []
        self._refresh_game_list()

    # ─── Local Model Detection ──────────────────────────────────

    def _detect_local_models(self):
        """Query Ollama for installed models."""
        base_url = self._ollama_url_var.get()
        try:
            import urllib.request, json
            resp = urllib.request.urlopen(f"{base_url}/api/tags", timeout=5)
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            if models:
                self._local_model_cb["values"] = models
                self._local_model_var.set(models[0])
                self._set_status(f"检测到 {len(models)} 个本地模型: {', '.join(models[:5])}")
                messagebox.showinfo("本地模型", f"已找到 {len(models)} 个模型:\n" + "\n".join(models[:10]))
            else:
                self._set_status("未检测到本地模型")
                messagebox.showwarning("提示", "未检测到本地模型。请确认 Ollama 已启动并已下载模型。")
        except Exception as e:
            self._set_status(f"无法连接 Ollama: {e}")
            messagebox.showwarning("连接失败", f"无法连接 Ollama ({base_url}):\n{e}")

    def _load_existing_key(self, key: str) -> str:
        """Load a specific key from existing config file to preserve it."""
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config.get("llm", {}).get(key, "")
        except Exception:
            return ""

    # ─── Helpers ─────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _on_close(self):
        if self._server_process and self._server_process.poll() is None:
            if messagebox.askyesno("确认退出", "翻译服务正在运行。关闭GUI不会停止服务。\n\n是否同时停止翻译服务？"):
                self._stop_server()
        self._stop_stats_polling()
        self.root.destroy()


def main():
    root = tk.Tk()
    HanhuaGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
