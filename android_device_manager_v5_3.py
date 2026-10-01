#!/usr/bin/env python3
"""
Android Device Manager V5.3
Safe administrative ADB / Fastboot manager.

Included:
- Connection Monitor / event timeline
- Backup Center (user-data backup + backup manifest)
- Diagnostic Bundle (ZIP)
- Package Manager 2.0
- Startup Health Check
- Real CPU/RAM/device monitor
- Existing safe ADB/Fastboot administrative tools

Safety scope:
- No bootloader unlocking
- No partition flashing
- No partition erasing/formatting
- No arbitrary GSI deployment/boot
"""

import os
import sys
import json
import time
import shutil
import zipfile
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


APP_NAME = "Android Device Manager"
VERSION = "5.3"
BASE = Path.home() / ".android_device_manager"
DATA = BASE / "data"
LOGS = BASE / "logs"
BACKUPS = BASE / "backups"
REPORTS = BASE / "reports"
SCREENSHOTS = BASE / "screenshots"
CONFIG = DATA / "settings.json"
EVENTS = DATA / "events.json"
HISTORY = DATA / "history.json"

for p in (DATA, LOGS, BACKUPS, REPORTS, SCREENSHOTS):
    p.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def run_cmd(args, timeout=20, binary=False):
    try:
        if binary:
            p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", "Tool not found"
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out"
    except Exception as e:
        return 1, "", str(e)


def tool_path(name):
    return shutil.which(name)


def adb(*args, serial=None, timeout=20, binary=False):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return run_cmd(cmd, timeout=timeout, binary=binary)


def fastboot(*args, serial=None, timeout=20):
    cmd = ["fastboot"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return run_cmd(cmd, timeout=timeout)


class ADM(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} V{VERSION}")
        self.geometry("1280x800")
        self.minsize(1050, 680)

        self.settings = load_json(CONFIG, {
            "dark": False,
            "auto_refresh": True,
            "refresh_seconds": 3,
            "confirm_delete": True
        })
        self.events = load_json(EVENTS, [])
        self.history = load_json(HISTORY, [])
        self.devices = []
        self.selected_serial = None
        self.selected_transport = None
        self.current_page = "Overview"
        self.log_process = None
        self.log_stop = False
        self.monitor_stop = False
        self.last_cpu = None
        self.last_net = None

        self.apply_theme()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_shell()
        self.startup_health_check()
        self.show_page("Overview")
        self.after(800, self.refresh_devices)
        self.after(1500, self.monitor_tick)

    # ---------- theme ----------
    def apply_theme(self):
        dark = bool(self.settings.get("dark"))
        self.bg = "#111318" if dark else "#f5f7fa"
        self.panel = "#191c22" if dark else "#ffffff"
        self.panel2 = "#22262e" if dark else "#eef2f6"
        self.fg = "#f1f3f5" if dark else "#16181d"
        self.muted = "#aeb5c0" if dark else "#68717d"
        self.accent = "#4c8dff"
        self.ok = "#2fbf71"
        self.warn = "#e6a23c"
        self.bad = "#e55353"

        self.configure(bg=self.bg)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=self.bg)
        style.configure("Panel.TFrame", background=self.panel)
        style.configure("TLabel", background=self.bg, foreground=self.fg)
        style.configure("Panel.TLabel", background=self.panel, foreground=self.fg)
        style.configure("Muted.TLabel", background=self.panel, foreground=self.muted)
        style.configure("Title.TLabel", background=self.bg, foreground=self.fg,
                        font=("TkDefaultFont", 20, "bold"))
        style.configure("Card.TFrame", background=self.panel)
        style.configure("TButton", padding=(10, 7))
        style.configure("Accent.TButton", padding=(12, 8))
        style.configure("Treeview", background=self.panel, fieldbackground=self.panel,
                        foreground=self.fg, rowheight=27)
        style.configure("Treeview.Heading", background=self.panel2, foreground=self.fg)
        style.map("Treeview", background=[("selected", "#315b9d")],
                  foreground=[("selected", "#ffffff")])

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.apply_theme()
        self.build_shell()
        self.show_page(self.current_page)

    # ---------- shell ----------
    def build_shell(self):
        root = tk.Frame(self, bg=self.bg)
        root.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(root, bg=self.panel, width=210)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=self.panel)
        brand.pack(fill="x", padx=18, pady=(22, 16))
        tk.Label(brand, text="Android Device", bg=self.panel, fg=self.fg,
                 font=("TkDefaultFont", 15, "bold")).pack(anchor="w")
        tk.Label(brand, text=f"Manager  V{VERSION}", bg=self.panel, fg=self.muted,
                 font=("TkDefaultFont", 9)).pack(anchor="w", pady=(2, 0))

        pages = [
            ("Overview", "▦"),
            ("Devices", "▣"),
            ("ADB Tools", "⌁"),
            ("Backup Center", "▤"),
            ("Package Manager", "▥"),
            ("Diagnostics", "◇"),
            ("Diagnostic Bundle", "◈"),
            ("Logs", "≡"),
            ("Connection Monitor", "◉"),
            ("Restart", "↻"),
            ("Settings", "⚙"),
            ("About", "?")
        ]
        for name, icon in pages:
            b = tk.Button(self.sidebar, text=f"  {icon}  {name}", anchor="w",
                          relief="flat", bd=0, cursor="hand2",
                          bg=self.panel, fg=self.fg, activebackground=self.panel2,
                          activeforeground=self.fg,
                          command=lambda n=name: self.show_page(n))
            b.pack(fill="x", padx=10, pady=2, ipady=7)

        self.content = tk.Frame(root, bg=self.bg)
        self.content.pack(side="left", fill="both", expand=True)

        self.status = tk.Label(self, text="Starting...", anchor="w",
                               bg=self.panel, fg=self.muted)
        self.status.pack(side="bottom", fill="x")

    def clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def show_page(self, page):
        self.current_page = page
        self.clear_content()
        getattr(self, "page_" + page.lower().replace(" ", "_"))()

    def header(self, title, subtitle=""):
        f = tk.Frame(self.content, bg=self.bg)
        f.pack(fill="x", padx=26, pady=(22, 10))
        tk.Label(f, text=title, bg=self.bg, fg=self.fg,
                 font=("TkDefaultFont", 21, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(f, text=subtitle, bg=self.bg, fg=self.muted,
                     font=("TkDefaultFont", 9)).pack(anchor="w", pady=(3, 0))

    def card(self, parent, title, value="", width=180):
        f = tk.Frame(parent, bg=self.panel, highlightthickness=1,
                     highlightbackground=self.panel2, width=width)
        f.pack_propagate(False)
        tk.Label(f, text=title.upper(), bg=self.panel, fg=self.muted,
                 font=("TkDefaultFont", 8, "bold")).pack(anchor="w", padx=13, pady=(11, 2))
        lbl = tk.Label(f, text=value, bg=self.panel, fg=self.fg,
                       font=("TkDefaultFont", 16, "bold"))
        lbl.pack(anchor="w", padx=13)
        return f, lbl

    # ---------- device discovery ----------
    def discover(self):
        found = []
        rc, out, err = adb("devices", "-l", timeout=8)
        if rc == 0:
            for line in out.splitlines()[1:]:
                line = line.strip()
                if not line or line.startswith("*"):
                    continue
                parts = line.split()
                if not parts:
                    continue
                serial = parts[0]
                state = parts[1] if len(parts) > 1 else "unknown"
                model = ""
                for x in parts[2:]:
                    if x.startswith("model:"):
                        model = x.split(":", 1)[1].replace("_", " ")
                found.append({
                    "serial": serial, "state": state, "transport": "ADB",
                    "model": model or "Android device"
                })

        rc, out, err = fastboot("devices", timeout=8)
        if rc == 0:
            for line in out.splitlines():
                parts = line.split()
                if parts:
                    found.append({
                        "serial": parts[0], "state": "fastboot",
                        "transport": "Fastboot", "model": "Fastboot device"
                    })
        return found

    def refresh_devices(self):
        old = {(d["serial"], d["transport"], d["state"]) for d in self.devices}
        self.devices = self.discover()
        new = {(d["serial"], d["transport"], d["state"]) for d in self.devices}

        for item in sorted(new - old):
            self.add_event("connected", item[0], f"{item[1]} / {item[2]}")

        for item in sorted(old - new):
            self.add_event("disconnected", item[0], f"{item[1]} / {item[2]}")

        if self.selected_serial and not any(d["serial"] == self.selected_serial
                                           for d in self.devices):
            self.selected_serial = None
            self.selected_transport = None

        if hasattr(self, "device_tree") and self.device_tree.winfo_exists():
            self.populate_device_tree()

        if self.settings.get("auto_refresh", True):
            self.after(max(1000, int(self.settings.get("refresh_seconds", 3)) * 1000),
                       self.refresh_devices)

    def populate_device_tree(self):
        for i in self.device_tree.get_children():
            self.device_tree.delete(i)
        for d in self.devices:
            self.device_tree.insert("", "end",
                                    values=(d["serial"], d["model"], d["transport"],
                                            d["state"]))

    def select_from_tree(self, event=None):
        sel = self.device_tree.selection()
        if not sel:
            return
        vals = self.device_tree.item(sel[0], "values")
        self.selected_serial = vals[0]
        self.selected_transport = vals[2]
        self.status.config(text=f"Selected: {self.selected_serial} ({self.selected_transport})")
        self.update_selected_panels()

    def selected(self):
        if not self.selected_serial:
            return None
        return next((d for d in self.devices if d["serial"] == self.selected_serial), None)

    def require_adb(self):
        d = self.selected()
        if not d or d["transport"] != "ADB":
            messagebox.showinfo("ADB device required", "Connect and select an ADB device.")
            return None
        return d

    # ---------- events ----------
    def add_event(self, kind, serial, detail=""):
        entry = {"time": now(), "kind": kind, "serial": serial, "detail": detail}
        self.events.insert(0, entry)
        self.events = self.events[:500]
        save_json(EVENTS, self.events)
        self.refresh_event_views()

    def refresh_event_views(self):
        if hasattr(self, "event_list") and self.event_list.winfo_exists():
            self.event_list.delete(0, "end")
            for e in self.events[:100]:
                self.event_list.insert("end",
                    f'{e["time"]}  |  {e["kind"].upper():12} | {e["serial"]} | {e["detail"]}')

    # ---------- overview ----------
    def page_overview(self):
        self.header("Device Overview", "Live device status and administrative controls")

        row = tk.Frame(self.content, bg=self.bg)
        row.pack(fill="x", padx=26, pady=8)
        self.cpu_card, self.cpu_lbl = self.card(row, "CPU", "—")
        self.ram_card, self.ram_lbl = self.card(row, "RAM", "—")
        self.bat_card, self.bat_lbl = self.card(row, "Battery", "—")
        self.storage_card, self.storage_lbl = self.card(row, "Storage", "—")
        self.net_card, self.net_lbl = self.card(row, "Network", "—")
        for c in (self.cpu_card, self.ram_card, self.bat_card,
                  self.storage_card, self.net_card):
            c.pack(side="left", padx=(0, 10), fill="x", expand=True)

        body = tk.Frame(self.content, bg=self.bg)
        body.pack(fill="both", expand=True, padx=26, pady=12)

        left = tk.Frame(body, bg=self.panel)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(left, text="Selected device", bg=self.panel, fg=self.fg,
                 font=("TkDefaultFont", 13, "bold")).pack(anchor="w", padx=16, pady=14)
        self.overview_info = tk.Text(left, bg=self.panel, fg=self.fg, bd=0,
                                     height=12, wrap="word")
        self.overview_info.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        right = tk.Frame(body, bg=self.panel, width=330)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)
        tk.Label(right, text="Recent connection events", bg=self.panel, fg=self.fg,
                 font=("TkDefaultFont", 12, "bold")).pack(anchor="w", padx=14, pady=14)
        self.overview_events = tk.Listbox(right, bg=self.panel, fg=self.fg,
                                          bd=0, highlightthickness=0)
        self.overview_events.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.refresh_overview_events()
        self.update_selected_panels()

    def refresh_overview_events(self):
        if hasattr(self, "overview_events") and self.overview_events.winfo_exists():
            self.overview_events.delete(0, "end")
            for e in self.events[:15]:
                self.overview_events.insert("end", f'{e["time"]}  {e["kind"]}: {e["serial"]}')

    # ---------- devices ----------
    def page_devices(self):
        self.header("Devices", "ADB and Fastboot transports currently visible to the computer")
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=12)

        cols = ("serial", "model", "transport", "state")
        self.device_tree = ttk.Treeview(box, columns=cols, show="headings")
        for c, t, w in [("serial", "Serial", 220), ("model", "Device", 250),
                        ("transport", "Transport", 130), ("state", "State", 150)]:
            self.device_tree.heading(c, text=t)
            self.device_tree.column(c, width=w)
        self.device_tree.pack(fill="both", expand=True, padx=12, pady=12)
        self.device_tree.bind("<<TreeviewSelect>>", self.select_from_tree)
        self.populate_device_tree()

        bottom = tk.Frame(box, bg=self.panel)
        bottom.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(bottom, text="Refresh", command=self.refresh_devices).pack(side="left")
        tk.Button(bottom, text="Device Inspector", command=self.show_inspector).pack(side="left", padx=8)

    def show_inspector(self):
        if not self.selected():
            messagebox.showinfo("Device Inspector", "Select a device first.")
            return
        self.show_page("Overview")

    # ---------- ADB tools ----------
    def page_adb_tools(self):
        self.header("ADB Tools", "Common administrative ADB actions")
        d = self.require_adb()
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=12)

        actions = [
            ("Install APK", self.install_apk),
            ("Uninstall App", self.uninstall_app),
            ("Package List", lambda: self.show_page("Package Manager")),
            ("Launch App", self.launch_app),
            ("Screenshot", self.take_screenshot),
            ("Pull File", self.pull_file),
            ("Push File", self.push_file),
            ("Properties", self.show_properties),
            ("Connection Test", self.connection_test),
            ("ADB Shell", self.adb_shell),
        ]
        for i, (text, cmd) in enumerate(actions):
            b = tk.Button(box, text=text, command=cmd, width=20)
            b.grid(row=i//3, column=i%3, padx=10, pady=10, sticky="ew")
        for i in range(3):
            box.grid_columnconfigure(i, weight=1)

        if not d:
            tk.Label(box, text="Connect an ADB device to enable ADB tools.",
                     bg=self.panel, fg=self.muted,
                     font=("TkDefaultFont", 12)).grid(row=5, column=0,
                                                       columnspan=3, pady=35)

    def install_apk(self):
        if not self.require_adb(): return
        p = filedialog.askopenfilename(filetypes=[("Android APK", "*.apk")])
        if not p: return
        rc, out, err = adb("install", p, serial=self.selected_serial, timeout=120)
        self.finish_command("Install APK", rc, out, err)

    def uninstall_app(self):
        if not self.require_adb(): return
        pkg = self.ask_text("Uninstall App", "Package name:")
        if not pkg: return
        rc, out, err = adb("uninstall", pkg, serial=self.selected_serial, timeout=60)
        self.finish_command("Uninstall", rc, out, err)

    def launch_app(self):
        if not self.require_adb(): return
        pkg = self.ask_text("Launch App", "Package name:")
        if not pkg: return
        rc, out, err = adb("shell", "monkey", "-p", pkg, "1",
                           serial=self.selected_serial, timeout=30)
        self.finish_command("Launch", rc, out, err)

    def take_screenshot(self):
        if not self.require_adb(): return
        target = SCREENSHOTS / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        rc, out, err = adb("exec-out", "screencap", "-p",
                           serial=self.selected_serial, timeout=30, binary=True)
        if rc == 0 and out:
            target.write_bytes(out)
            self.add_history("Screenshot", str(target))
            messagebox.showinfo("Screenshot", f"Saved:\n{target}")
        else:
            self.error_box("Screenshot", err)

    def pull_file(self):
        if not self.require_adb(): return
        remote = self.ask_text("Pull File", "Remote path, e.g. /sdcard/file.txt:")
        if not remote: return
        dest = filedialog.askdirectory()
        if not dest: return
        rc, out, err = adb("pull", remote, dest, serial=self.selected_serial, timeout=120)
        self.finish_command("Pull", rc, out, err)

    def push_file(self):
        if not self.require_adb(): return
        src = filedialog.askopenfilename()
        if not src: return
        remote = self.ask_text("Push File", "Remote destination:")
        if not remote: return
        rc, out, err = adb("push", src, remote, serial=self.selected_serial, timeout=120)
        self.finish_command("Push", rc, out, err)

    def show_properties(self):
        if not self.require_adb(): return
        rc, out, err = adb("shell", "getprop", serial=self.selected_serial, timeout=30)
        self.output_window("Android Properties", out if rc == 0 else err)

    def connection_test(self):
        d = self.require_adb()
        if not d: return
        rc, out, err = adb("shell", "echo", "ADB connection OK",
                           serial=self.selected_serial, timeout=10)
        self.finish_command("Connection Test", rc, out, err)

    def adb_shell(self):
        if not self.require_adb(): return
        command = self.ask_text("ADB Shell", "Read-only/administrative command:")
        if not command: return
        rc, out, err = adb("shell", command, serial=self.selected_serial, timeout=30)
        self.output_window("ADB Shell Result", (out or "") + ("\n" + err if err else ""))

    # ---------- package manager ----------
    def page_package_manager(self):
        self.header("Package Manager 2.0", "Search, inspect and launch installed Android packages")
        top = tk.Frame(self.content, bg=self.bg)
        top.pack(fill="x", padx=26, pady=8)
        self.pkg_search = tk.StringVar()
        tk.Entry(top, textvariable=self.pkg_search, width=40).pack(side="left")
        tk.Button(top, text="Search / Refresh", command=self.load_packages).pack(side="left", padx=8)
        self.pkg_status = tk.Label(top, text="", bg=self.bg, fg=self.muted)
        self.pkg_status.pack(side="left", padx=8)

        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=10)
        cols = ("package", "path", "uid")
        self.pkg_tree = ttk.Treeview(box, columns=cols, show="headings")
        self.pkg_tree.heading("package", text="Package")
        self.pkg_tree.heading("path", text="Install path")
        self.pkg_tree.heading("uid", text="UID")
        self.pkg_tree.column("package", width=350)
        self.pkg_tree.column("path", width=430)
        self.pkg_tree.column("uid", width=120)
        self.pkg_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.pkg_tree.bind("<Double-1>", lambda e: self.package_info())
        btn = tk.Frame(box, bg=self.panel)
        btn.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btn, text="Refresh", command=self.load_packages).pack(side="left")
        tk.Button(btn, text="Package Info", command=self.package_info).pack(side="left", padx=7)
        tk.Button(btn, text="Launch", command=self.launch_selected_package).pack(side="left")
        self.load_packages()

    def load_packages(self):
        d = self.require_adb()
        if not d: return
        rc, out, err = adb("shell", "pm", "list", "packages", "-f", "-U",
                           serial=self.selected_serial, timeout=60)
        if rc != 0:
            self.error_box("Package Manager", err)
            return
        query = self.pkg_search.get().lower().strip()
        for i in self.pkg_tree.get_children():
            self.pkg_tree.delete(i)
        count = 0
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            raw = line[8:]
            uid = ""
            if " uid:" in raw:
                raw, uid = raw.rsplit(" uid:", 1)
            if "=" in raw:
                path, pkg = raw.rsplit("=", 1)
            else:
                path, pkg = "", raw
            if query and query not in pkg.lower() and query not in path.lower():
                continue
            self.pkg_tree.insert("", "end", values=(pkg, path, uid))
            count += 1
        self.pkg_status.config(text=f"{count} packages")

    def selected_package(self):
        sel = self.pkg_tree.selection()
        if not sel:
            return None
        return self.pkg_tree.item(sel[0], "values")[0]

    def package_info(self):
        pkg = self.selected_package()
        if not pkg or not self.require_adb(): return
        rc, out, err = adb("shell", "dumpsys", "package", pkg,
                           serial=self.selected_serial, timeout=60)
        self.output_window(f"Package: {pkg}", out if rc == 0 else err)

    def launch_selected_package(self):
        pkg = self.selected_package()
        if not pkg or not self.require_adb(): return
        rc, out, err = adb("shell", "monkey", "-p", pkg, "1",
                           serial=self.selected_serial, timeout=30)
        self.finish_command("Launch package", rc, out, err)

    # ---------- backup ----------
    def page_backup_center(self):
        self.header("Backup Center", "Protect user data before upgrades, resets or administrative work")
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=14)

        tk.Label(box, text="Choose a backup type", bg=self.panel, fg=self.fg,
                 font=("TkDefaultFont", 15, "bold")).pack(anchor="w", padx=20, pady=(22, 8))
        tk.Label(box, text="User-data backup copies accessible files from /sdcard. "
                          "A complete OS image is device-dependent and is not guaranteed by ADB.",
                 bg=self.panel, fg=self.muted, wraplength=850,
                 justify="left").pack(anchor="w", padx=20, pady=(0, 20))

        b1 = tk.Button(box, text="1  •  User Data Backup",
                       command=self.user_backup, width=28, height=2)
        b1.pack(anchor="w", padx=20, pady=7)

        b2 = tk.Button(box, text="2  •  OS / System Backup Check",
                       command=self.os_backup_check, width=28, height=2)
        b2.pack(anchor="w", padx=20, pady=7)

        tk.Label(box, text="Recommended contents", bg=self.panel, fg=self.fg,
                 font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=20, pady=(25, 8))
        tk.Label(box, text="DCIM • Pictures • Movies • Music • Documents • Download • "
                          "other accessible user storage",
                 bg=self.panel, fg=self.muted).pack(anchor="w", padx=20)

    def user_backup(self):
        d = self.require_adb()
        if not d: return
        dest = filedialog.askdirectory(title="Choose backup destination")
        if not dest: return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = Path(dest) / f"AndroidBackup_{self.selected_serial}_{stamp}"
        target.mkdir(parents=True, exist_ok=True)

        # Pull user storage as one directory. adb pull preserves accessible files.
        self.status.config(text="Creating user-data backup...")
        rc, out, err = adb("pull", "/sdcard/", str(target),
                           serial=self.selected_serial, timeout=900)
        manifest = {
            "created": now(),
            "device": self.selected_serial,
            "type": "user-data",
            "source": "/sdcard/",
            "destination": str(target),
            "returncode": rc,
            "output": out[-4000:],
            "error": err[-4000:]
        }
        save_json(target / "backup_manifest.json", manifest)
        if rc == 0:
            self.add_history("User data backup", str(target))
            messagebox.showinfo("Backup complete", f"Backup saved to:\n{target}")
        else:
            self.error_box("Backup failed", err)

    def os_backup_check(self):
        d = self.require_adb()
        if not d: return
        props = {}
        for key in [
            "ro.build.version.release", "ro.build.version.sdk",
            "ro.product.device", "ro.product.model",
            "ro.boot.slot_suffix", "ro.boot.verifiedbootstate",
            "ro.boot.flash.locked"
        ]:
            rc, out, err = adb("shell", "getprop", key,
                               serial=self.selected_serial, timeout=10)
            props[key] = out.strip() if rc == 0 else ""
        text = (
            "OS BACKUP CAPABILITY CHECK\n\n"
            "ADB does not provide a universal full partition/ROM image backup.\n"
            "This report records useful system state before administrative work.\n\n"
            + json.dumps(props, indent=2, ensure_ascii=False)
        )
        self.output_window("OS / System Backup Check", text)

    # ---------- diagnostics ----------
    def page_diagnostics(self):
        self.header("Diagnostics", "Read-only device diagnostics")
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=14)
        buttons = [
            ("Run Full Diagnostics", self.full_diagnostics),
            ("Battery", lambda: self.diag_cmd(["dumpsys", "battery"])),
            ("Memory", lambda: self.diag_cmd(["dumpsys", "meminfo"])),
            ("Storage", lambda: self.diag_cmd(["df", "-h"])),
            ("Network", lambda: self.diag_cmd(["cat", "/proc/net/dev"])),
        ]
        for i, (t, c) in enumerate(buttons):
            tk.Button(box, text=t, command=c, width=25).grid(
                row=i//2, column=i%2, padx=15, pady=12, sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(1, weight=1)

    def diag_cmd(self, args):
        if not self.require_adb(): return
        rc, out, err = adb("shell", *args, serial=self.selected_serial, timeout=60)
        self.output_window("Diagnostic", out if rc == 0 else err)

    def collect_diagnostics(self, include_log=True):
        d = self.require_adb()
        if not d: return None
        result = {
            "created": now(),
            "application_version": VERSION,
            "device": d,
            "tools": {
                "adb": tool_path("adb"),
                "fastboot": tool_path("fastboot"),
                "heimdall": tool_path("heimdall")
            }
        }
        commands = {
            "properties": ["getprop"],
            "battery": ["dumpsys", "battery"],
            "memory": ["dumpsys", "meminfo"],
            "storage": ["df", "-h"],
            "network": ["cat", "/proc/net/dev"],
            "mounts": ["mount"],
        }
        for name, cmd in commands.items():
            rc, out, err = adb("shell", *cmd, serial=self.selected_serial, timeout=60)
            result[name] = out if rc == 0 else err
        if include_log:
            rc, out, err = adb("logcat", "-d", "-t", "1500",
                               serial=self.selected_serial, timeout=60)
            result["logcat"] = out if rc == 0 else err
        return result

    def full_diagnostics(self):
        data = self.collect_diagnostics()
        if data is None: return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = REPORTS / f"diagnostics_{stamp}.json"
        save_json(path, data)
        self.add_history("Diagnostics", str(path))
        self.output_window("Diagnostics", json.dumps(data, indent=2, ensure_ascii=False))

    # ---------- diagnostic bundle ----------
    def page_diagnostic_bundle(self):
        self.header("Diagnostic Bundle", "Create one portable ZIP containing device diagnostics and recent events")
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=20)
        tk.Label(box, text="The bundle includes read-only diagnostic data, recent logcat output, "
                          "connection events and a device manifest.",
                 bg=self.panel, fg=self.muted, wraplength=850).pack(anchor="w", padx=20, pady=20)
        tk.Button(box, text="Create Diagnostic Bundle",
                  command=self.create_bundle, width=30, height=2).pack(anchor="w", padx=20)
        self.bundle_status = tk.Label(box, text="", bg=self.panel, fg=self.muted)
        self.bundle_status.pack(anchor="w", padx=20, pady=15)

    def create_bundle(self):
        data = self.collect_diagnostics(include_log=True)
        if data is None: return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        work = REPORTS / f"bundle_{stamp}"
        work.mkdir(parents=True, exist_ok=True)

        save_json(work / "diagnostics.json", data)
        save_json(work / "connection_events.json", self.events[:200])
        save_json(work / "application_settings.json", self.settings)

        txt = [
            f"{APP_NAME} V{VERSION}",
            f"Created: {now()}",
            "",
            "SAFETY SCOPE",
            "No bootloader unlocking, partition flashing, partition erasing or arbitrary GSI deployment.",
            "",
            "DEVICE",
            json.dumps(data.get("device", {}), indent=2),
            "",
            "PROPERTIES",
            data.get("properties", ""),
            "",
            "BATTERY",
            data.get("battery", ""),
            "",
            "MEMORY",
            data.get("memory", ""),
            "",
            "STORAGE",
            data.get("storage", ""),
            "",
            "NETWORK",
            data.get("network", ""),
        ]
        (work / "summary.txt").write_text("\n".join(txt), encoding="utf-8")
        (work / "logcat.txt").write_text(data.get("logcat", ""), encoding="utf-8")

        zip_path = REPORTS / f"AndroidDeviceManager_Diagnostic_{stamp}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in work.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(work))
        shutil.rmtree(work, ignore_errors=True)

        self.add_history("Diagnostic Bundle", str(zip_path))
        self.bundle_status.config(text=f"Created: {zip_path}")
        messagebox.showinfo("Diagnostic Bundle", f"Bundle created:\n{zip_path}")

    # ---------- logs ----------
    def page_logs(self):
        self.header("Logs", "Live logcat and saved diagnostic logs")
        top = tk.Frame(self.content, bg=self.bg)
        top.pack(fill="x", padx=26, pady=8)
        tk.Button(top, text="Start Live Logcat", command=self.start_logcat).pack(side="left")
        tk.Button(top, text="Stop", command=self.stop_logcat).pack(side="left", padx=8)
        tk.Button(top, text="Clear", command=lambda: self.log_text.delete("1.0", "end")).pack(side="left")

        self.log_text = tk.Text(self.content, bg=self.panel, fg=self.fg, insertbackground=self.fg)
        self.log_text.pack(fill="both", expand=True, padx=26, pady=10)

    def start_logcat(self):
        d = self.require_adb()
        if not d: return
        self.stop_logcat()
        self.log_stop = False

        def worker():
            try:
                self.log_process = subprocess.Popen(
                    ["adb", "-s", self.selected_serial, "logcat"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace"
                )
                for line in self.log_process.stdout:
                    if self.log_stop:
                        break
                    self.after(0, lambda s=line: self.append_log(s))
            except Exception as e:
                self.after(0, lambda: self.append_log(str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def append_log(self, text):
        if hasattr(self, "log_text") and self.log_text.winfo_exists():
            self.log_text.insert("end", text)
            self.log_text.see("end")

    def stop_logcat(self):
        self.log_stop = True
        if self.log_process:
            try:
                self.log_process.terminate()
            except Exception:
                pass
            self.log_process = None

    # ---------- connection monitor ----------
    def page_connection_monitor(self):
        self.header("Connection Monitor", "ADB/Fastboot connection events")
        self.event_list = tk.Listbox(self.content, bg=self.panel, fg=self.fg,
                                     bd=0, highlightthickness=0)
        self.event_list.pack(fill="both", expand=True, padx=26, pady=14)
        self.refresh_event_views()
        bottom = tk.Frame(self.content, bg=self.bg)
        bottom.pack(fill="x", padx=26, pady=(0, 12))
        tk.Button(bottom, text="Refresh", command=self.refresh_event_views).pack(side="left")
        tk.Button(bottom, text="Clear Events", command=self.clear_events).pack(side="left", padx=8)
        tk.Button(bottom, text="Export Events", command=self.export_events).pack(side="left")

    def clear_events(self):
        if not messagebox.askyesno("Clear events", "Clear connection history?"):
            return
        self.events = []
        save_json(EVENTS, self.events)
        self.refresh_event_views()

    def export_events(self):
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                         filetypes=[("JSON", "*.json")])
        if p:
            save_json(Path(p), self.events)

    # ---------- restart / fastboot ----------
    def page_restart(self):
        self.header("Restart & Fastboot Tools", "Safe reboot controls and read-only Fastboot information")
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=14)

        row = tk.Frame(box, bg=self.panel)
        row.pack(fill="x", padx=18, pady=18)
        actions = [
            ("Normal", lambda: self.reboot("")),
            ("Recovery", lambda: self.reboot("recovery")),
            ("Fastbootd", lambda: self.reboot("fastboot")),
            ("Bootloader", lambda: self.reboot("bootloader"))
        ]
        for t, c in actions:
            tk.Button(row, text=t, command=c, width=16).pack(side="left", padx=5)

        tk.Label(box, text="Fastboot Tools", bg=self.panel, fg=self.fg,
                 font=("TkDefaultFont", 14, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        tk.Label(box, text="Available only for a selected Fastboot device. These actions do not unlock, flash or erase.",
                 bg=self.panel, fg=self.muted).pack(anchor="w", padx=18, pady=(0, 12))

        fbrow = tk.Frame(box, bg=self.panel)
        fbrow.pack(fill="x", padx=18)
        for t, c in [
            ("Fastboot Devices", self.fb_devices),
            ("Product", self.fb_product),
            ("Current Slot", self.fb_slot),
            ("Slot Count", self.fb_slot_count),
            ("Reboot System", self.fb_reboot),
            ("Reboot Bootloader", self.fb_reboot_bootloader),
            ("Continue", self.fb_continue)
        ]:
            tk.Button(fbrow, text=t, command=c).pack(side="left", padx=4, pady=5)

        self.fb_status = tk.Label(box, text="", bg=self.panel, fg=self.muted)
        self.fb_status.pack(anchor="w", padx=18, pady=12)

    def reboot(self, mode):
        d = self.require_adb()
        if not d: return
        args = ["reboot"] + ([mode] if mode else [])
        rc, out, err = adb(*args, serial=self.selected_serial, timeout=30)
        self.finish_command("Reboot", rc, out, err)

    def require_fastboot(self):
        d = self.selected()
        if not d or d["transport"] != "Fastboot":
            messagebox.showinfo("Fastboot device required", "Select a Fastboot device first.")
            return None
        return d

    def fb_devices(self):
        rc, out, err = fastboot("devices")
        self.output_window("Fastboot Devices", out if rc == 0 else err)

    def fb_var(self, name):
        d = self.require_fastboot()
        if not d: return
        rc, out, err = fastboot("getvar", name, serial=d["serial"])
        self.output_window(f"Fastboot {name}", (out or "") + ("\n" + err if err else ""))

    def fb_product(self): self.fb_var("product")
    def fb_slot(self): self.fb_var("current-slot")
    def fb_slot_count(self): self.fb_var("slot-count")

    def fb_reboot(self):
        d = self.require_fastboot()
        if not d: return
        rc, out, err = fastboot("reboot", serial=d["serial"])
        self.finish_command("Fastboot reboot", rc, out, err)

    def fb_reboot_bootloader(self):
        d = self.require_fastboot()
        if not d: return
        rc, out, err = fastboot("reboot-bootloader", serial=d["serial"])
        self.finish_command("Fastboot reboot bootloader", rc, out, err)

    def fb_continue(self):
        d = self.require_fastboot()
        if not d: return
        rc, out, err = fastboot("continue", serial=d["serial"])
        self.finish_command("Fastboot continue", rc, out, err)

    # ---------- settings ----------
    def page_settings(self):
        self.header("Settings", "Application preferences and automatic configuration protection")
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=14)

        self.dark_var = tk.BooleanVar(value=self.settings.get("dark", False))
        self.auto_var = tk.BooleanVar(value=self.settings.get("auto_refresh", True))
        self.interval_var = tk.IntVar(value=int(self.settings.get("refresh_seconds", 3)))
        self.confirm_var = tk.BooleanVar(value=self.settings.get("confirm_delete", True))

        tk.Checkbutton(box, text="Dark mode", variable=self.dark_var,
                       command=self.save_settings, bg=self.panel, fg=self.fg,
                       selectcolor=self.panel2, activebackground=self.panel).pack(anchor="w", padx=20, pady=10)
        tk.Checkbutton(box, text="Automatic device refresh", variable=self.auto_var,
                       command=self.save_settings, bg=self.panel, fg=self.fg,
                       selectcolor=self.panel2, activebackground=self.panel).pack(anchor="w", padx=20, pady=10)

        row = tk.Frame(box, bg=self.panel)
        row.pack(anchor="w", padx=20, pady=8)
        tk.Label(row, text="Refresh seconds:", bg=self.panel, fg=self.fg).pack(side="left")
        tk.Spinbox(row, from_=1, to=30, width=6, textvariable=self.interval_var,
                   command=self.save_settings).pack(side="left", padx=8)

        tk.Checkbutton(box, text="Confirm destructive file operations",
                       variable=self.confirm_var, command=self.save_settings,
                       bg=self.panel, fg=self.fg, selectcolor=self.panel2,
                       activebackground=self.panel).pack(anchor="w", padx=20, pady=10)

        tk.Button(box, text="Backup Settings Now", command=self.backup_settings).pack(
            anchor="w", padx=20, pady=18)

        tk.Label(box, text=f"Config: {CONFIG}", bg=self.panel, fg=self.muted).pack(
            anchor="w", padx=20, pady=5)

    def save_settings(self):
        self.settings.update({
            "dark": self.dark_var.get(),
            "auto_refresh": self.auto_var.get(),
            "refresh_seconds": max(1, int(self.interval_var.get())),
            "confirm_delete": self.confirm_var.get()
        })
        save_json(CONFIG, self.settings)
        if self.settings["dark"] != getattr(self, "_old_dark", self.settings["dark"]):
            self._old_dark = self.settings["dark"]
            self.rebuild()

    def backup_settings(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = BACKUPS / f"settings_backup_{stamp}.json"
        save_json(p, self.settings)
        messagebox.showinfo("Settings backup", f"Saved:\n{p}")

    # ---------- about ----------
    def page_about(self):
        self.header(f"{APP_NAME} V{VERSION}", "Release build information")
        box = tk.Frame(self.content, bg=self.panel)
        box.pack(fill="both", expand=True, padx=26, pady=14)

        text = (
            f"{APP_NAME}\n"
            f"Version {VERSION}\n\n"
            "Purpose\n"
            "The purpose of this application is to enable users who are less experienced "
            "with ADB and Android operations to control their devices without risking a brick; "
            "for security reasons, operations such as partition changes, flashing, or bootloader "
            "unlocking are not available.\n\n"
            "Safety scope\n"
            "ADB is used for ordinary administrative tasks. Fastboot is limited to device "
            "information and safe reboot/boot-control actions. No unlocking, partition flashing, "
            "partition erasing, or arbitrary GSI deployment is provided.\n\n"
            "Included in V5.3\n"
            "• Connection Monitor\n"
            "• Backup Center\n"
            "• Diagnostic Bundle\n"
            "• Package Manager 2.0\n"
            "• Startup Health Check\n"
            "• Real CPU / RAM device monitoring\n"
            "• Improved device information\n\n"
            "Release type: Administrative desktop utility"
        )
        tk.Label(box, text=text, bg=self.panel, fg=self.fg, justify="left",
                 anchor="nw", font=("TkDefaultFont", 11), wraplength=900).pack(
                     fill="both", expand=True, padx=24, pady=24)

    # ---------- startup self-test ----------
    def startup_health_check(self):
        checks = [
            ("Python", sys.version.split()[0], sys.version_info >= (3, 9)),
            ("ADB", tool_path("adb") or "Not found", bool(tool_path("adb"))),
            ("Fastboot", tool_path("fastboot") or "Not found", bool(tool_path("fastboot"))),
            ("Heimdall", tool_path("heimdall") or "Not found", bool(tool_path("heimdall"))),
            ("Data directory", str(DATA), DATA.exists()),
            ("Logs directory", str(LOGS), LOGS.exists()),
            ("Backup directory", str(BACKUPS), BACKUPS.exists()),
            ("Configuration", str(CONFIG), CONFIG.exists() or DATA.exists()),
        ]
        win = tk.Toplevel(self)
        win.title("Startup Health Check")
        win.geometry("620x440")
        win.configure(bg=self.panel)
        tk.Label(win, text="Startup Health Check", bg=self.panel, fg=self.fg,
                 font=("TkDefaultFont", 16, "bold")).pack(anchor="w", padx=22, pady=18)
        tree = ttk.Treeview(win, columns=("item", "value", "state"), show="headings")
        for c, t, w in [("item", "Component", 170), ("value", "Details", 300), ("state", "Status", 90)]:
            tree.heading(c, text=t)
            tree.column(c, width=w)
        tree.pack(fill="both", expand=True, padx=18, pady=8)
        for item, value, ok in checks:
            tree.insert("", "end", values=(item, value, "READY" if ok else "MISSING"))
        tk.Button(win, text="Continue", command=win.destroy).pack(pady=12)
        self.status.config(text="Startup self-test completed")

    # ---------- real monitor ----------
    def monitor_tick(self):
        try:
            self.update_monitor()
        except Exception:
            pass
        self.after(1500, self.monitor_tick)

    def update_monitor(self):
        d = self.selected()
        if not d or d["transport"] != "ADB":
            if hasattr(self, "cpu_lbl") and self.cpu_lbl.winfo_exists():
                self.cpu_lbl.config(text="—")
                self.ram_lbl.config(text="—")
                self.bat_lbl.config(text="—")
                self.storage_lbl.config(text="—")
                self.net_lbl.config(text="—")
            return

        # CPU: two /proc/stat samples on the Android device.
        def read_cpu():
            rc, out, err = adb("shell", "cat", "/proc/stat",
                               serial=d["serial"], timeout=8)
            if rc != 0:
                return None
            for line in out.splitlines():
                if line.startswith("cpu "):
                    nums = [int(x) for x in line.split()[1:8]]
                    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
                    total = sum(nums)
                    return total, idle
            return None

        cur = read_cpu()
        cpu = None
        if cur and self.last_cpu:
            dt = cur[0] - self.last_cpu[0]
            di = cur[1] - self.last_cpu[1]
            if dt > 0:
                cpu = max(0, min(100, (1 - di / dt) * 100))
        self.last_cpu = cur

        rc, out, err = adb("shell", "cat", "/proc/meminfo",
                           serial=d["serial"], timeout=8)
        ram = "—"
        if rc == 0:
            vals = {}
            for line in out.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    parts = v.strip().split()
                    if parts:
                        try: vals[k] = int(parts[0])
                        except Exception: pass
            total = vals.get("MemTotal")
            avail = vals.get("MemAvailable")
            if total and avail:
                used = total - avail
                ram = f"{used/total*100:.0f}%"

        rc, out, err = adb("shell", "dumpsys", "battery",
                           serial=d["serial"], timeout=8)
        battery = "—"
        if rc == 0:
            level = None
            temp = None
            for line in out.splitlines():
                if "level:" in line:
                    try: level = int(line.split(":", 1)[1].strip())
                    except Exception: pass
                if "temperature:" in line:
                    try: temp = int(line.split(":", 1)[1].strip()) / 10
                    except Exception: pass
            battery = f"{level}%" if level is not None else "—"
            if hasattr(self, "bat_lbl") and temp is not None:
                self.bat_lbl.config(text=f"{battery} / {temp:.1f}°C")

        rc, out, err = adb("shell", "df", "-P", "/data",
                           serial=d["serial"], timeout=8)
        storage = "—"
        if rc == 0:
            lines = [x for x in out.splitlines() if x.strip()]
            if len(lines) >= 2:
                parts = lines[-1].split()
                if len(parts) >= 5:
                    storage = parts[4]

        rx, tx = self.network_sample(d["serial"])
        net = f"RX {rx:.1f} KB/s  TX {tx:.1f} KB/s"

        if hasattr(self, "cpu_lbl") and self.cpu_lbl.winfo_exists():
            self.cpu_lbl.config(text=f"{cpu:.0f}%" if cpu is not None else "Sampling…")
            self.ram_lbl.config(text=ram)
            if not hasattr(self, "bat_lbl") or not self.bat_lbl.winfo_exists():
                return
            if " / " not in self.bat_lbl.cget("text"):
                self.bat_lbl.config(text=battery)
            self.storage_lbl.config(text=storage)
            self.net_lbl.config(text=net)

        self.update_overview_info(d, cpu, ram, battery, storage, net)

    def network_sample(self, serial):
        rc, out, err = adb("shell", "cat", "/proc/net/dev",
                           serial=serial, timeout=8)
        if rc != 0:
            return 0.0, 0.0
        rx = tx = 0
        for line in out.splitlines():
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            iface = iface.strip()
            if iface == "lo":
                continue
            parts = data.split()
            if len(parts) >= 9:
                try:
                    rx += int(parts[0])
                    tx += int(parts[8])
                except Exception:
                    pass
        cur = (rx, tx, time.time())
        speed_rx = speed_tx = 0.0
        if self.last_net and self.last_net[2] < cur[2]:
            dt = cur[2] - self.last_net[2]
            speed_rx = max(0, (cur[0] - self.last_net[0]) / 1024 / dt)
            speed_tx = max(0, (cur[1] - self.last_net[1]) / 1024 / dt)
        self.last_net = cur
        return speed_rx, speed_tx

    def update_overview_info(self, d, cpu, ram, battery, storage, net):
        if not hasattr(self, "overview_info") or not self.overview_info.winfo_exists():
            return
        rc, out, err = adb("shell", "getprop", "ro.build.version.release",
                           serial=d["serial"], timeout=8)
        android = out.strip() if rc == 0 else "—"
        rc, model, err = adb("shell", "getprop", "ro.product.model",
                             serial=d["serial"], timeout=8)
        model = model.strip() if rc == 0 else d["model"]

        text = (
            f"Model: {model}\n"
            f"Serial: {d['serial']}\n"
            f"Transport: {d['transport']}\n"
            f"State: {d['state']}\n"
            f"Android: {android}\n\n"
            f"CPU: {cpu:.1f}%" if cpu is not None else "CPU: Sampling…"
        )
        text += (
            f"\nRAM: {ram}\n"
            f"Battery: {battery}\n"
            f"Storage: {storage}\n"
            f"Network: {net}\n"
        )
        self.overview_info.delete("1.0", "end")
        self.overview_info.insert("1.0", text)
        self.refresh_overview_events()

    def update_selected_panels(self):
        self.last_cpu = None
        self.last_net = None

    # ---------- helpers ----------
    def finish_command(self, title, rc, out, err):
        self.add_history(title, (out or err or "").strip()[-500:])
        if rc == 0:
            self.status.config(text=f"{title}: success")
            if out:
                self.output_window(title, out)
        else:
            self.error_box(title, err or out)

    def add_history(self, action, detail):
        self.history.insert(0, {"time": now(), "action": action, "detail": detail})
        self.history = self.history[:500]
        save_json(HISTORY, self.history)

    def output_window(self, title, text):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("900x600")
        win.configure(bg=self.panel)
        box = tk.Text(win, bg=self.panel, fg=self.fg, insertbackground=self.fg)
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", text or "(no output)")
        box.config(state="disabled")

    def error_box(self, title, msg):
        clean = msg or "Unknown error"
        if "unauthorized" in clean.lower():
            clean += "\n\nUnlock the device and accept the ADB authorization prompt."
        elif "offline" in clean.lower():
            clean += "\n\nReconnect the device and try again."
        elif "not found" in clean.lower():
            clean += "\n\nCheck that the required platform tool is installed and in PATH."
        messagebox.showerror(title, clean)

    def ask_text(self, title, prompt):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("430x150")
        win.configure(bg=self.panel)
        tk.Label(win, text=prompt, bg=self.panel, fg=self.fg).pack(pady=(18, 6))
        ent = tk.Entry(win, width=45)
        ent.pack()
        result = {"v": None}
        def ok():
            result["v"] = ent.get().strip()
            win.destroy()
        tk.Button(win, text="OK", command=ok).pack(pady=12)
        ent.focus_set()
        self.wait_window(win)
        return result["v"]

    def on_close(self):
        self.stop_logcat()
        self.destroy()


if __name__ == "__main__":
    app = ADM()
    app.mainloop()
