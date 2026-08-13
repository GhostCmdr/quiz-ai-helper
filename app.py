import ctypes
import json
import os
import queue
import threading
import tkinter as tk
import urllib.request
import webbrowser
from tkinter import messagebox, ttk

from PIL import Image, ImageGrab, ImageTk

import ocr_engine
import screenshot
import history_store
from mimo_client import MiMoClient, StreamStopped

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
INVITE_IMAGE_PATH = os.path.join(APP_DIR, "invite_poster.png")
HISTORY_PATH = os.path.join(APP_DIR, "history.json")

APP_VERSION = "0.2.0"

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.xiaomimimo.com/v1",
    "model": "mimo-v2.5",
    "temperature": 0.7,
    "max_tokens": 2048,
    "system_prompt": "直接回答用户的问题,不要分析过程,不要输出思考过程,不要给出答案解析,直接给出答案",
    "auto_send": True,
    "auto_region": False,
    "region_stable": 0.6,
    "auto_answer": False,
    "option_zones": [],
    "geometry": "",
    "update_repo": "",
    "update_silent": "",
}


def compare_versions(current, latest):
    def parts(version):
        return [int(p) for p in version.lstrip("vV").replace("-", ".").split(".") if p.isdigit()]

    p1, p2 = parts(current), parts(latest)
    for a, b in zip(p1, p2):
        if a != b:
            return a - b
    return len(p1) - len(p2)

MODEL_CHOICES = ["mimo-v2.5", "mimo-v2.5-pro", "mimo-v2.5-pro-ultraspeed"]

BASE_URL_CHOICES = [
    "https://api.xiaomimimo.com/v1",
    "https://token-plan-cn.xiaomimimo.com/v1",
]

UI_FONT = "Microsoft YaHei UI"


def load_config():
    config = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            config.update(json.load(file))
    except (OSError, json.JSONDecodeError):
        pass
    if not config.get("option_zones") and (config.get("option_correct") or config.get("option_wrong")):
        zones = []
        for label, color, key in (("正确", "#2e7d32", "option_correct"),
                                  ("错误", "#c62828", "option_wrong")):
            bbox = config.get(key)
            if bbox:
                zones.append({"label": label, "bbox": list(bbox), "color": color})
        config["option_zones"] = zones
    return config


def save_config(config):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
    except OSError:
        pass


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, config, on_save, on_check_update=None):
        super().__init__(master)
        self.config = config
        self.on_save = on_save
        self.on_check_update = on_check_update
        self.title("设置")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        rows = [
            ("Base URL", "base_url", 40),
            ("Key", "api_key", 40),
            ("模型", "model", 30),
            ("Temperature", "temperature", 8),
            ("Max Tokens", "max_tokens", 8),
            ("内容识别延迟(秒)", "region_stable", 8),
        ]
        self.entries = {}
        for row, (label, key, width) in enumerate(rows):
            ttk.Label(frame, text=label, style="Settings.TLabel").grid(
                row=row, column=0, sticky="e", padx=(0, 10), pady=5)
            if key == "model":
                entry = ttk.Combobox(frame, width=width, values=MODEL_CHOICES)
                entry.set(self.config.get("model", ""))
            elif key == "base_url":
                entry = ttk.Combobox(frame, width=width, values=BASE_URL_CHOICES)
                entry.set(self.config.get("base_url", ""))
            else:
                entry = ttk.Entry(frame, width=width)
                entry.insert(0, str(self.config.get(key, "")))
            entry.grid(row=row, column=1, sticky="we", pady=5)
            self.entries[key] = entry
        ttk.Label(frame, text="系统提示词", style="Settings.TLabel").grid(
            row=len(rows), column=0, sticky="ne", padx=(0, 10), pady=5)
        self.prompt_text = tk.Text(frame, width=52, height=5, font=(UI_FONT, 10))
        self.prompt_text.insert("1.0", self.config.get("system_prompt", ""))
        self.prompt_text.grid(row=len(rows), column=1, sticky="we", pady=(5, 1))
        result_row = ttk.Frame(frame)
        result_row.grid(row=len(rows) + 1, column=0, columnspan=2, pady=(2, 0), sticky="w")
        self.test_label = tk.Label(result_row, text="", font=(UI_FONT, 10))
        self.test_label.pack(side="left")
        test_row = ttk.Frame(frame)
        test_row.grid(row=len(rows) + 2, column=0, columnspan=2, pady=(3, 0), sticky="ew")
        self.test_btn = ttk.Button(test_row, text="测试连通", takefocus=0, width=8,
                                   command=self._test_connection)
        self.test_btn.pack(side="left")
        self.invite_btn = ttk.Button(test_row, text="领取￥10", takefocus=0, width=8,
                                     command=self._open_invite)
        self.invite_btn.pack(side="left", padx=(8, 0))
        self.check_btn = ttk.Button(test_row, text="检查更新", takefocus=0, width=8,
                                    command=self._check_update)
        self.check_btn.pack(side="left", padx=(8, 0))
        self._tip_after = None
        self._tip_hide_after = None
        self._tip_win = None
        self._tip_img = None
        self.invite_btn.bind("<Enter>", self._invite_tip_enter)
        self.invite_btn.bind("<Leave>", self._invite_tip_leave)
        spacer = ttk.Frame(test_row)
        spacer.pack(side="left", fill="x", expand=True)
        ttk.Button(test_row, text="保存", takefocus=0, width=8, command=self._save).pack(side="left", padx=4)
        ttk.Button(test_row, text="取消", takefocus=0, width=8, command=self.destroy).pack(side="left")
        frame.columnconfigure(1, weight=1)
        self.update_idletasks()
        self._center_over(master)

    def _test_connection(self):
        self.test_label.configure(text="测试中...", fg="#666666")
        self.test_btn.configure(state="disabled")
        try:
            temperature = float(self.entries["temperature"].get())
            max_tokens = int(self.entries["max_tokens"].get())
        except ValueError:
            self._show_test_result("Temperature / Max Tokens 格式错误", False)
            return
        client = MiMoClient(
            api_key=self.entries["api_key"].get().strip(),
            base_url=self.entries["base_url"].get().strip(),
            model=self.entries["model"].get().strip(),
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=self.prompt_text.get("1.0", "end-1c"),
        )
        self._test_result = None
        threading.Thread(target=self._test_worker, args=(client,), daemon=True).start()
        self.after(150, self._poll_test)

    def _test_worker(self, client):
        try:
            content, elapsed = client.test_connection()
            self._test_result = (True, content, elapsed)
        except Exception as error:
            self._test_result = (False, str(error), None)

    def _poll_test(self):
        if self._test_result is None:
            self.after(150, self._poll_test)
            return
        ok, content, elapsed = self._test_result
        clean = content.strip()
        while clean and clean[-1] in "。.！!～~ ":
            clean = clean[:-1]
        if ok and clean.endswith("1"):
            self._show_test_result("连通成功,响应{:.2f}秒".format(elapsed), True)
        elif ok:
            self._show_test_result("已连通但返回异常: {}".format(content.strip()[:60]), False)
        else:
            self._show_test_result("连通失败: {}".format(content[:100]), False)

    def _show_test_result(self, text, success):
        self.test_label.configure(text=text, fg="#00a000" if success else "#c00000")
        self.test_btn.configure(state="normal")

    def _center_over(self, master):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 3
        self.geometry("+{}+{}".format(max(0, x), max(0, y)))

    def _open_invite(self):
        webbrowser.open("https://platform.xiaomimimo.com?ref=99SDJQ")

    def _check_update(self):
        if self.on_check_update is not None:
            self.on_check_update()

    def _invite_tip_enter(self, _event):
        try:
            self._cancel_tip_hide()
            if self._tip_after is not None:
                self.after_cancel(self._tip_after)
                self._tip_after = None
            self._tip_after = self.after(500, self._show_invite_tip)
        except Exception:
            pass

    def _invite_tip_leave(self, _event):
        try:
            if self._tip_after is not None:
                self.after_cancel(self._tip_after)
                self._tip_after = None
            self._schedule_tip_hide()
        except Exception:
            pass

    def _schedule_tip_hide(self):
        self._cancel_tip_hide()
        try:
            self._tip_hide_after = self.after(150, self._hide_invite_tip)
        except Exception:
            self._tip_hide_after = None

    def _cancel_tip_hide(self):
        if self._tip_hide_after is not None:
            try:
                self.after_cancel(self._tip_hide_after)
            except Exception:
                pass
            self._tip_hide_after = None

    def _hide_invite_tip(self):
        self._tip_hide_after = None
        if self._tip_win is not None:
            try:
                if self._tip_win.winfo_exists():
                    self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None

    def _show_invite_tip(self):
        self._tip_after = None
        if self._tip_win is not None and self._tip_win.winfo_exists():
            return
        try:
            if self._tip_img is None:
                image = Image.open(INVITE_IMAGE_PATH).convert("RGBA")
                image = image.resize((193, 251), Image.Resampling.LANCZOS)
                self._tip_img = ImageTk.PhotoImage(image)
        except Exception:
            return
        try:
            win = tk.Toplevel(self)
            self._tip_win = win
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.0)
            label = tk.Label(win, image=self._tip_img, bd=0, highlightthickness=0)
            label.pack()
            label.bind("<Enter>", lambda _e: self._cancel_tip_hide())
            label.bind("<Leave>", lambda _e: self._schedule_tip_hide())
            win.update_idletasks()
            button = self.invite_btn
            x = button.winfo_rootx() + (button.winfo_width() - win.winfo_reqwidth()) // 2
            y = button.winfo_rooty() - win.winfo_reqheight() - 10
            if y < 0:
                y = button.winfo_rooty() + button.winfo_height() + 10
            win.geometry("+{}+{}".format(max(0, x), max(0, y)))
            win.attributes("-alpha", 0.94)
        except Exception:
            self._hide_invite_tip()

    def _save(self):
        try:
            temperature = float(self.entries["temperature"].get())
            max_tokens = int(self.entries["max_tokens"].get())
            region_stable = float(self.entries["region_stable"].get())
            if region_stable <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("设置", "Temperature 必须是数字,Max Tokens 必须是整数,内容识别延迟必须是正数")
            return
        self.config["api_key"] = self.entries["api_key"].get().strip()
        self.config["base_url"] = self.entries["base_url"].get().strip()
        self.config["model"] = self.entries["model"].get().strip()
        self.config["temperature"] = temperature
        self.config["max_tokens"] = max_tokens
        self.config["region_stable"] = region_stable
        self.config["system_prompt"] = self.prompt_text.get("1.0", "end-1c")
        save_config(self.config)
        self.on_save()
        self.destroy()


class OptionZone:
    def __init__(self, root, label, color, on_change=None, on_close=None,
                 on_label_change=None, on_geometry_changed=None):
        self.root = root
        self.on_change = on_change
        self.on_close = on_close
        self.on_label_change = on_label_change
        self.on_geometry_changed = on_geometry_changed
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=color)
        self.win.attributes("-alpha", 0.45)
        self.label = tk.Label(self.win, text=label, bg=color, fg="white",
                              font=(UI_FONT, 12, "bold"), cursor="fleur")
        self.label.pack(fill="both", expand=True)
        self.label.bind("<Double-Button-1>", lambda e: self._edit_label())
        close_btn = tk.Label(self.win, text="✕", bg=color, fg="white",
                             font=(UI_FONT, 11, "bold"), cursor="hand2")
        close_btn.place(relx=1.0, x=-6, y=2, anchor="ne")
        close_btn.bindtags((close_btn._w, "Label"))
        close_btn.bind("<Button-1>", lambda e: self._close())
        self.win.bind("<ButtonPress-1>", self._start_move)
        self.win.bind("<B1-Motion>", self._move)
        self.win.bind("<ButtonRelease-1>", lambda e: self._changed())
        handle = tk.Label(self.win, text="◢", bg=color, fg="white",
                          font=(UI_FONT, 10), cursor="size_nw_se")
        handle.place(relx=1.0, rely=1.0, anchor="se")
        handle.bindtags((handle._w, "Label"))
        handle.bind("<ButtonPress-1>", self._start_resize)
        handle.bind("<B1-Motion>", self._resize)
        handle.bind("<ButtonRelease-1>", lambda e: self._changed())
        self.win.withdraw()
        self._drag_off = (0, 0)
        self._resize_start = None

    def is_visible(self):
        return bool(self.win.winfo_viewable())

    def set_geometry(self, bbox):
        x1, y1, x2, y2 = bbox
        self.win.geometry("{}x{}+{}+{}".format(max(60, x2 - x1), max(36, y2 - y1), int(x1), int(y1)))

    def bbox(self):
        x = self.win.winfo_x()
        y = self.win.winfo_y()
        return (x, y, x + self.win.winfo_width(), y + self.win.winfo_height())

    def show(self):
        self.win.update_idletasks()
        self.win.deiconify()
        self.win.lift()

    def hide(self, save=True):
        self.win.withdraw()
        if save and self.on_change is not None:
            self.on_change(self.bbox())

    def set_label(self, text):
        self.label.configure(text=text)

    def _close(self):
        if self.on_close is not None:
            self.on_close()

    def _edit_label(self):
        dialog = tk.Toplevel(self.win)
        dialog.title("编辑选项文字")
        dialog.resizable(False, False)
        dialog.transient(self.win)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill="both", expand=True)
        entry = ttk.Entry(frame, width=12)
        entry.insert(0, self.label.cget("text"))
        entry.pack(pady=(0, 8))
        entry.focus_set()
        entry.select_range(0, "end")

        def confirm(event=None):
            new_text = entry.get().strip() or self.label.cget("text")
            self.set_label(new_text)
            dialog.destroy()
            if self.on_label_change is not None:
                self.on_label_change(new_text)

        entry.bind("<Return>", confirm)
        buttons = ttk.Frame(frame)
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(3, weight=1)
        ttk.Button(buttons, text="确定", width=6, takefocus=0, command=confirm).grid(row=0, column=1)
        ttk.Button(buttons, text="取消", width=6, takefocus=0, command=dialog.destroy).grid(row=0, column=2, padx=(6, 0))
        buttons.pack()
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.win.winfo_rootx() + (self.win.winfo_width() - width) // 2
        y = self.win.winfo_rooty() + self.win.winfo_height() + 8
        dialog.geometry("+{}+{}".format(max(0, x), max(0, y)))

    def _start_move(self, event):
        self._drag_off = (event.x_root - self.win.winfo_x(), event.y_root - self.win.winfo_y())

    def _move(self, event):
        x = event.x_root - self._drag_off[0]
        y = event.y_root - self._drag_off[1]
        self.win.geometry("+{}+{}".format(x, y))
        self._notify_geometry()

    def _start_resize(self, event):
        self._resize_start = (event.x_root, event.y_root, self.win.winfo_x(),
                              self.win.winfo_y(), self.win.winfo_width(), self.win.winfo_height())

    def _resize(self, event):
        if self._resize_start is None:
            return
        sx, sy, ox, oy, ow, oh = self._resize_start
        new_w = max(60, ow + (event.x_root - sx))
        new_h = max(36, oh + (event.y_root - sy))
        self.win.geometry("{}x{}+{}+{}".format(new_w, new_h, ox, oy))
        self._notify_geometry()

    def _changed(self):
        if self.on_change is not None:
            self.on_change(self.bbox())

    def _notify_geometry(self):
        if self.on_geometry_changed is not None:
            self.win.update_idletasks()
            self.on_geometry_changed(self.bbox())


class AddZoneButton:
    """圆形加号按钮,跟随最后一个选项框下方。"""

    SIZE = 30

    def __init__(self, root, on_add=None):
        self.on_add = on_add
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.95)
        size = self.SIZE
        self.canvas = tk.Canvas(self.win, width=size, height=size, bg="#2e7d32",
                                highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.create_oval(1, 1, size - 1, size - 1, fill="#2e7d32", outline="white", width=2)
        c = size // 2
        t, b = c - 6, c + 6
        self.canvas.create_line(c, t, c, b, fill="white", width=3)
        self.canvas.create_line(t, c, b, c, fill="white", width=3)
        self.canvas.bind("<Button-1>", lambda e: self._click())
        self.win.withdraw()

    def _click(self):
        if self.on_add is not None:
            self.on_add()

    def follow(self, bbox):
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) // 2
        self.win.geometry("+{}+{}".format(cx - self.SIZE // 2, int(y2) + 8))

    def show(self):
        self.win.update_idletasks()
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self.win.lift()
        self.win.update_idletasks()
        self.win.lift()

    def hide(self):
        self.win.withdraw()


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.config = load_config()
        dpi = 96
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
        except (AttributeError, OSError):
            pass
        self.root.tk.call("tk", "scaling", dpi / 96.0)
        self.root.title("快速问答助手")
        self.root.geometry(self.config.get("geometry") or "760x640")
        self.root.minsize(680, 420)
        self.queue = queue.Queue()
        self.ocr_thread = None
        self.stream_thread = None
        self.streaming = False
        self._token_count = 0
        self.cur_image = None
        self.stats = None
        self._stop_event = threading.Event()
        self._req_id = 0
        self.region_bbox = None
        self._monitor_thread = None
        self._monitor_stop = threading.Event()
        self._pending_region_change = False
        self.option_zones = [dict(z) for z in (self.config.get("option_zones") or [])]
        self._zones = None
        self._add_btn = None
        self.history_records = history_store.load_history(HISTORY_PATH)
        self.root.option_add("*TButton.takeFocus", "0")
        self.root.option_add("*TCheckbutton.takeFocus", "0")
        self._build_ui()
        self._refresh_history_list()
        self.root.after(200, self._finalize_min_width)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_queue)
        self.root.after(200, self._update_speed)
        if (self.config.get("update_repo") or "").strip():
            self.root.after(4000, lambda: self.check_update(False))

    def _finalize_min_width(self):
        required = self.toolbar.winfo_reqwidth() + 8
        self.root.minsize(required, 420)
        if self.root.winfo_width() < required:
            self.root.geometry("{}x{}".format(required, max(self.root.winfo_height(), 420)))

    def _build_ui(self):
        style = ttk.Style(self.root)
        style.configure("TButton", font=(UI_FONT, 11), padding=(12, 8))
        style.configure("TCheckbutton", font=(UI_FONT, 10))
        style.configure("TLabel", font=(UI_FONT, 10))
        style.configure("TLabelframe.Label", font=(UI_FONT, 10))
        style.configure("TEntry", font=(UI_FONT, 10))
        style.configure("Settings.TLabel", font=(UI_FONT, 11))
        toolbar = ttk.Frame(self.root, padding=(8, 8))
        self.toolbar = toolbar
        toolbar.pack(fill="x")
        capture_frame = ttk.Frame(toolbar)
        ttk.Button(capture_frame, text="截图识别 (F2)", takefocus=0, command=self.capture_ocr).pack()
        self.region_var = tk.BooleanVar(value=self.config.get("auto_region", False))
        ttk.Checkbutton(capture_frame, text="区域自动识别", variable=self.region_var, takefocus=0,
                        command=self._on_region_var_toggle).pack(pady=(3, 0))
        capture_frame.pack(side="left")
        ttk.Button(toolbar, text="打开图片", takefocus=0, command=self.open_file_ocr).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="识别剪贴板", takefocus=0, command=self.clipboard_ocr).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="清空", takefocus=0, command=self.clear_all).pack(side="left", padx=(6, 0))
        send_frame = ttk.Frame(toolbar)
        ttk.Button(send_frame, text="发送给 MiMo", takefocus=0, command=self.send_to_mimo).pack()
        self.auto_var = tk.BooleanVar(value=self.config.get("auto_send", True))
        ttk.Checkbutton(send_frame, text="识别后自动发送", variable=self.auto_var, takefocus=0).pack(pady=(3, 0))
        send_frame.pack(side="left", padx=(6, 0))
        answer_frame = ttk.Frame(toolbar)
        ttk.Button(answer_frame, text="选项区域", takefocus=0, command=self._on_option_region).pack()
        self.auto_answer_var = tk.BooleanVar(value=self.config.get("auto_answer", False))
        ttk.Checkbutton(answer_frame, text="全自动答题", variable=self.auto_answer_var, takefocus=0,
                        command=self._on_auto_answer_toggle).pack(pady=(3, 0))
        answer_frame.pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="设置", takefocus=0, command=self.open_settings).pack(side="left", padx=(6, 0))
        spacer = ttk.Frame(toolbar)
        spacer.pack(side="left", fill="x", expand=True)

        self.paned_h = tk.PanedWindow(self.root, orient="horizontal", sashwidth=6, sashrelief="flat")
        self.paned_h.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        left_area = ttk.Frame(self.paned_h)
        self.paned = ttk.PanedWindow(left_area, orient="vertical")
        self.paned.pack(fill="both", expand=True)

        ocr_frame = ttk.LabelFrame(self.paned, text="识别结果 (可编辑)")
        self.ocr_text = tk.Text(ocr_frame, wrap="word", font=(UI_FONT, 10), undo=True)
        self.ocr_scroll = ttk.Scrollbar(ocr_frame, command=self.ocr_text.yview)
        self.ocr_text.configure(yscrollcommand=self.ocr_scroll.set)
        self.ocr_text.pack(side="left", fill="both", expand=True)
        self.ocr_scroll.pack(side="right", fill="y")

        result_head = ttk.Frame(self.paned)
        ttk.Label(result_head, text="答案").pack(side="left")
        self.speed_label = tk.Label(result_head, text="", fg="#888888", font=(UI_FONT, 9))
        self.speed_label.pack(side="left", padx=(8, 0))
        result_frame = ttk.LabelFrame(self.paned, labelwidget=result_head)
        self.result_text = tk.Text(result_frame, wrap="word", font=(UI_FONT, 10),
                                   state="disabled", cursor="arrow")
        self.result_scroll = ttk.Scrollbar(result_frame, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=self.result_scroll.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        self.result_scroll.pack(side="right", fill="y")

        self.paned.add(ocr_frame, weight=2)
        self.paned.add(result_frame, weight=3)

        self.history_frame = ttk.LabelFrame(self.paned_h, text="历史库")
        history_btns = ttk.Frame(self.history_frame)
        history_btns.columnconfigure(0, weight=1)
        history_btns.columnconfigure(3, weight=1)
        ttk.Button(history_btns, text="删除选中", takefocus=0, width=8,
                   command=self._history_delete).grid(row=0, column=1)
        ttk.Button(history_btns, text="清空历史", takefocus=0, width=8,
                   command=self._history_clear).grid(row=0, column=2, padx=(8, 0))
        history_btns.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        self.history_list = tk.Listbox(self.history_frame, font=(UI_FONT, 10),
                                       exportselection=False, activestyle="none")
        self.history_scroll = ttk.Scrollbar(self.history_frame, command=self.history_list.yview)
        self.history_list.configure(yscrollcommand=self.history_scroll.set)
        self.history_scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.history_list.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(8, 0))
        self.history_list.bind("<ButtonRelease-1>", self._history_select)

        self.paned_h.add(left_area, minsize=280)
        self.paned_h.add(self.history_frame, minsize=220)
        self.root.after(150, self._init_sash)
        self.root.after(150, self._init_sash_h)

        self.status = ttk.Label(self.root, text="就绪", anchor="w", relief="sunken", padding=(6, 2))
        self.status.pack(fill="x", side="bottom")

        self.root.bind_all("<F2>", lambda e: self.capture_ocr())
        self.root.bind_all("<F3>", lambda e: self.clipboard_ocr())

    def _set_status(self, text):
        self.status.configure(text=text)

    def _init_sash(self):
        height = self.paned.winfo_height()
        if height > 50:
            self.paned.sashpos(0, int(height * 0.4))

    def _init_sash_h(self):
        width = self.paned_h.winfo_width()
        if width > 100:
            self.paned_h.sash_place(0, int(width * 0.74), -1)

    def _update_speed(self):
        if self.streaming and self.stats is not None:
            import time
            elapsed = time.monotonic() - self.stats["start"]
            self.speed_label.configure(text="响应速度：{:.2f}秒".format(elapsed))
        self.root.after(200, self._update_speed)

    def _show_final_speed(self):
        stats = self.stats
        if stats is None or stats["total"] is None:
            return
        self.speed_label.configure(text="响应速度：{:.2f}秒".format(stats["total"]))

    def _push(self, event, *args):
        self.queue.put((event,) + args)

    def _poll_queue(self):
        try:
            while True:
                event, *args = self.queue.get_nowait()
                self._handle_event(event, args)
        except queue.Empty:
            pass
        self.root.after(30, self._poll_queue)

    def _handle_event(self, event, args):
        if event == "ocr_done":
            self._set_status("OCR 完成")
            self.ocr_text.delete("1.0", "end")
            self.ocr_text.insert("1.0", args[0])
            if self.auto_var.get() and args[0].strip():
                self.send_to_mimo()
        elif event == "region_changed":
            if not self.region_var.get():
                return
            if self.streaming:
                self._pending_region_change = True
                self._set_status("新题出现,等待当前生成完成")
            else:
                self._region_changed_proc()
        elif event == "ocr_error":
            self._set_status("OCR 失败")
            messagebox.showerror("OCR 识别", args[0])
        elif event == "token":
            if args[0] != self._req_id:
                return
            self.result_text.insert("end", args[1])
            self._token_count += 1
            if self._token_count % 10 == 0:
                self.result_text.see("end")
        elif event == "stream_start":
            if args[0] != self._req_id:
                return
            self.streaming = True
            self._token_count = 0
            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", "end")
            self._set_status("MiMo 生成中...")
            self.speed_label.configure(text="响应速度：--")
        elif event == "stream_done":
            if args[0] != self._req_id:
                return
            self.streaming = False
            self.result_text.configure(state="disabled")
            self.result_text.see("end")
            self._set_status("完成 ({} 字)".format(args[1]))
            self._show_final_speed()
            if len(args) > 2:
                answer = self.result_text.get("1.0", "end-1c")
                updated = history_store.add_record(HISTORY_PATH, self.history_records, args[2], answer)
                if updated is not None:
                    self.history_records = updated
                    self._refresh_history_list()
                sel = self._auto_answer_match(answer)
                if sel and updated is not None:
                    self.history_records[0]["sel"] = sel
                    history_store.save_history(HISTORY_PATH, self.history_records)
            if self._pending_region_change:
                self._pending_region_change = False
                self._region_changed_proc()
        elif event == "stream_stopped":
            if args[0] != self._req_id:
                return
            self.streaming = False
            self.result_text.configure(state="disabled")
            self._set_status("已停止生成")
            self._show_final_speed()
        elif event == "stream_error":
            if args[0] != self._req_id:
                return
            self.streaming = False
            self._set_status("调用失败")
            self.result_text.configure(state="normal")
            self.result_text.insert("end", "\n\n[错误] " + args[1] + "\n")
            self.result_text.configure(state="disabled")
        elif event == "update_result":
            found, tag, url, manual = args
            if not found:
                if manual:
                    self._set_status("检查更新失败")
                    messagebox.showinfo("检查更新", "检查失败(仓库暂未发布版本或网络异常)")
                return
            if tag and compare_versions(APP_VERSION, tag) < 0:
                if not manual and tag == (self.config.get("update_silent") or ""):
                    return
                self._show_update_dialog(tag, url)
            elif manual:
                self._set_status("已是最新版本")
                messagebox.showinfo("检查更新", "当前已是最新版本 ({})".format(APP_VERSION))

    def check_update(self, manual=False):
        repo = (self.config.get("update_repo") or "").strip()
        if not repo:
            if manual:
                messagebox.showinfo("检查更新", "未配置更新仓库\n请在 config.json 中填写 update_repo,\n例如 \"你的用户名/quiz-ai-helper\"")
            return
        if manual:
            self._set_status("正在检查更新...")
        threading.Thread(target=self._update_worker, args=(repo, manual), daemon=True).start()

    def _update_worker(self, repo, manual):
        try:
            request = urllib.request.Request(
                "https://api.github.com/repos/" + repo + "/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "quiz-ai-helper"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            tag = data.get("tag_name", "")
            url = data.get("html_url", "")
            found = bool(tag)
        except Exception:
            tag, url = self._latest_release_fallback(repo)
            found = bool(tag)
        self._push("update_result", found, tag, url, manual)

    def _latest_release_fallback(self, repo):
        try:
            request = urllib.request.Request(
                "https://github.com/" + repo + "/releases/latest",
                headers={"User-Agent": "quiz-ai-helper"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                location = response.geturl()
            marker = "/releases/tag/"
            index = location.rfind(marker)
            if index < 0:
                return "", ""
            tag = location[index + len(marker):].rstrip("/")
            if not tag:
                return "", ""
            return tag, "https://github.com/" + repo + "/releases/tag/" + tag
        except Exception:
            return "", ""

    def capture_ocr(self):
        if self.streaming:
            return
        self._set_status("请拖拽框选识别区域")
        selector = screenshot.RegionSelector(self.root, on_done=self._on_region_selected,
                                             on_cancel=lambda: self._set_status("已取消"))
        selector.start()

    def _on_region_selected(self, bbox):
        was_visible = self._zones_visible()
        self._hide_zones_ui()
        try:
            image = screenshot.grab_region(*bbox)
        except Exception as error:
            if was_visible:
                self._show_zones_ui()
            messagebox.showerror("截图", str(error))
            self._set_status("截图失败")
            return
        if was_visible:
            self._show_zones_ui()
        self._start_ocr(image)
        self.region_bbox = bbox
        if self.region_var.get():
            self._start_region_monitor()

    def _on_region_var_toggle(self):
        if self.region_var.get():
            if self.region_bbox is None:
                self._set_status("区域自动识别已开启,请按 F2 框选识别区域")
            else:
                self._start_region_monitor()
                self._set_status("区域自动识别已开启")
        else:
            self._stop_region_monitor()
            self._set_status("区域自动识别已关闭")

    def _on_option_region(self):
        if self._zones and any(zone.is_visible() for zone in self._zones):
            self._hide_option_zones()
        else:
            self._show_option_zones()

    def _on_auto_answer_toggle(self):
        if self.auto_answer_var.get():
            if not self.option_zones or any(not zone.get("bbox") for zone in self.option_zones):
                self._show_option_zones()

    def _show_option_zones(self):
        if not self.option_zones:
            self.option_zones = [
                {"label": "正确", "bbox": None, "color": "#2e7d32"},
                {"label": "错误", "bbox": None, "color": "#c62828"},
            ]
        self._rebuild_zones()
        self._set_status("拖动/缩放调整选项框,双击改文字,点 + 增加选项,点第一个框 ✕ 完成")

    def _rebuild_zones(self):
        for zone in self._zones or []:
            zone.win.destroy()
        self._zones = []
        width, height, gap = 260, 70, 24
        vx = ctypes.windll.user32.GetSystemMetrics(76)
        vy = ctypes.windll.user32.GetSystemMetrics(77)
        vw = ctypes.windll.user32.GetSystemMetrics(78)
        vh = ctypes.windll.user32.GetSystemMetrics(79)
        x = vx + (vw - width) // 2
        y_top = vy + (vh - height * 2 - gap) // 2
        prev_bottom = None
        for index, data in enumerate(self.option_zones):
            bbox = data.get("bbox")
            if bbox is None:
                if prev_bottom is None:
                    bbox = (x, y_top, x + width, y_top + height)
                else:
                    bbox = (x, prev_bottom + gap, x + width, prev_bottom + gap + height)
            else:
                bbox = list(bbox)
            zone = OptionZone(self.root, data["label"], data["color"],
                              on_change=lambda bbox2, i=index: self._set_option_bbox(i, bbox2),
                              on_close=lambda i=index: self._close_zone(i),
                              on_label_change=lambda text, i=index: self._set_option_label(i, text),
                              on_geometry_changed=self._refresh_add_btn)
            zone.set_geometry(bbox)
            zone.show()
            self._zones.append(zone)
            prev_bottom = bbox[3]
        if self._add_btn is None:
            self._add_btn = AddZoneButton(self.root, on_add=self._add_option_zone)
        self._refresh_add_btn()

    def _refresh_add_btn(self):
        if self._add_btn is None:
            return
        if self._zones and any(zone.is_visible() for zone in self._zones):
            last = self._zones[-1]
            last.win.update_idletasks()
            self._add_btn.follow(last.bbox())
            self._add_btn.show()
        else:
            self._add_btn.hide()

    def _zones_visible(self):
        return bool(self._zones) and any(zone.is_visible() for zone in self._zones)

    def _hide_zones_ui(self):
        if self._zones:
            for zone in self._zones:
                zone.hide(save=False)
        if self._add_btn:
            self._add_btn.hide()

    def _show_zones_ui(self):
        if self._zones:
            for zone in self._zones:
                zone.show()
        if self._add_btn:
            self._refresh_add_btn()

    def _add_option_zone(self):
        if not self._zones:
            return
        last = self._zones[-1]
        x1, y1, x2, y2 = last.bbox()
        gap = 24
        bbox = [x1, y2 + gap, x2, y2 + gap + (y2 - y1)]
        self.option_zones.append({"label": self._next_zone_label(), "bbox": bbox, "color": "#1565c0"})
        self._rebuild_zones()
        self._save_option_zones()

    def _next_zone_label(self):
        used = {(zone.get("label") or "").strip().upper() for zone in self.option_zones}
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if letter not in used:
                return letter
        return "选项{}".format(len(self.option_zones) + 1)

    def _close_zone(self, index):
        if index == 0:
            self._hide_option_zones()
        else:
            self._delete_option_zone(index)

    def _delete_option_zone(self, index):
        if index >= len(self.option_zones):
            return
        del self.option_zones[index]
        self._rebuild_zones()
        self._save_option_zones()

    def _hide_option_zones(self):
        for zone in self._zones or []:
            zone.hide(save=True)
        if self._add_btn:
            self._add_btn.hide()
        self._save_option_zones()
        self._set_status("选项区域已保存")

    def _set_option_bbox(self, index, bbox):
        if 0 <= index < len(self.option_zones):
            self.option_zones[index]["bbox"] = list(bbox)

    def _set_option_label(self, index, text):
        if 0 <= index < len(self.option_zones):
            self.option_zones[index]["label"] = text
            if self._zones and index < len(self._zones):
                self._zones[index].set_label(text)
        self._save_option_zones()

    def _save_option_zones(self):
        zones = [{"label": zone["label"], "bbox": zone.get("bbox"), "color": zone["color"]}
                 for zone in self.option_zones]
        self.config["option_zones"] = zones
        self.config.pop("option_correct", None)
        self.config.pop("option_wrong", None)
        save_config(self.config)

    def _stop_region_monitor(self):
        self._monitor_stop.set()
        if self._monitor_thread is not None:
            self._monitor_thread = None

    def _region_changed_proc(self):
        was_visible = self._zones_visible()
        self._hide_zones_ui()
        try:
            image = screenshot.grab_region(*self.region_bbox)
        except Exception as error:
            if was_visible:
                self._show_zones_ui()
            self._set_status("区域截图失败")
            return
        if was_visible:
            self._show_zones_ui()
        self._start_ocr(image)

    def _zone_keywords(self, zone):
        label = (zone.get("label") or "").strip()
        if "正确" in label or "对" in label:
            return ["正确", "对", "是", "TRUE", "YES"]
        if "错误" in label or "错" in label or "否" in label:
            return ["错误", "错", "否", "FALSE", "NO"]
        return None

    def _zone_is_literal(self, zone):
        label = (zone.get("label") or "").strip()
        return len(label) == 1 and (label.isalpha() or label.isdigit())

    def _zone_matches(self, zone, text, text_upper):
        label = (zone.get("label") or "").strip()
        if not label:
            return False
        keywords = self._zone_keywords(zone)
        if keywords is not None:
            return any(kw in text for kw in keywords)
        if len(label) == 1 and (label.isalpha() or label.isdigit()):
            return label.upper() in text_upper
        return label in text

    def _auto_answer_match(self, answer_text):
        text = (answer_text or "").strip()
        if not text:
            return
        if not self.auto_answer_var.get():
            return
        if not self.option_zones or not any(zone.get("bbox") for zone in self.option_zones):
            self._set_status("选项区域未设置完整,未自动点击")
            return
        was_visible = self._zones_visible()
        self._hide_zones_ui()
        text_upper = text.upper()
        letter_hits = [zone for zone in self.option_zones
                       if zone.get("bbox") and self._zone_is_literal(zone)
                       and self._zone_matches(zone, text, text_upper)]
        if letter_hits:
            hits = letter_hits
        else:
            hits = [zone for zone in self.option_zones
                    if zone.get("bbox") and self._zone_matches(zone, text, text_upper)]
        if not hits:
            self._set_status("未匹配到选项,未自动点击")
            return
        labels = [(zone.get("label") or "").strip() for zone in hits]
        self._auto_click_boxes(hits, 0, restore=was_visible)
        summary = "、".join(labels)
        self._set_status("已自动选择 {}".format(summary))
        return summary

    def _auto_click_boxes(self, hits, index, restore=False):
        if index >= len(hits):
            if restore:
                self._show_zones_ui()
            return
        bbox = hits[index]["bbox"]
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        self._click_at(cx, cy)
        if index + 1 < len(hits):
            self.root.after(150, lambda: self._auto_click_boxes(hits, index + 1, restore))
        elif restore:
            self.root.after(150, self._show_zones_ui)

    def _click_at(self, x, y):
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

    def _start_region_monitor(self):
        self._monitor_stop.set()
        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._region_monitor, args=(self.region_bbox, self._monitor_stop), daemon=True)
        self._monitor_thread.start()

    def _region_monitor(self, bbox, stop):
        import time as _time
        interval = 0.3
        baseline = None
        changed_ticks = 0
        while not stop.is_set():
            _time.sleep(interval)
            try:
                frame = screenshot.grab_region(*bbox)
                thumb = frame.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
                pixels = list(thumb.getdata())
                if baseline is None:
                    baseline = pixels
                    continue
                diff = 0.0
                for old, new in zip(baseline, pixels):
                    diff += abs(old - new)
                diff /= len(pixels)
                stable = float(self.config.get("region_stable", 0.6) or 0.6)
                needed = max(1, int(round(stable / interval)))
                if diff > 6.0:
                    changed_ticks += 1
                    if changed_ticks >= needed:
                        baseline = pixels
                        changed_ticks = 0
                        self._push("region_changed")
                else:
                    changed_ticks = 0
            except Exception:
                pass

    def open_file_ocr(self):
        if self.streaming:
            return
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            with Image.open(path) as image:
                image = image.convert("RGB").copy()
            self._start_ocr(image)
        except Exception as error:
            messagebox.showerror("打开图片", str(error))

    def clipboard_ocr(self):
        if self.streaming:
            return
        image = ImageGrab.grabclipboard()
        if isinstance(image, Image.Image):
            self._start_ocr(image.convert("RGB"))
        else:
            self._set_status("剪贴板中没有图片")

    def _start_ocr(self, image):
        self.cur_image = image
        self._set_status("OCR 识别中...")
        self.ocr_thread = threading.Thread(target=self._ocr_worker, args=(image,), daemon=True)
        self.ocr_thread.start()

    def _ocr_worker(self, image):
        try:
            text = ocr_engine.ocr_image(image)
            self._push("ocr_done", text)
        except Exception as error:
            self._push("ocr_error", str(error))

    def send_to_mimo(self):
        if self.streaming:
            return
        text = self.ocr_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showinfo("提示", "请先识别或输入文本")
            return
        if not self.config.get("api_key"):
            messagebox.showinfo("提示", "请先在 设置 中填写 MiMo API Key")
            self.open_settings()
            return
        self.auto_var_value = self.auto_var.get()
        stop_event = threading.Event()
        self._stop_event = stop_event
        self._req_id += 1
        req_id = self._req_id
        auto_answer = self.auto_answer_var.get()
        self.stream_thread = threading.Thread(
            target=self._stream_worker, args=(text, req_id, stop_event, auto_answer), daemon=True)
        self.stream_thread.start()

    def _stream_worker(self, text, req_id, stop_event, auto_answer):
        import time
        self.stats = {"start": time.monotonic(), "first": None, "chars": 0, "total": None}
        self._push("stream_start", req_id)
        system_prompt = self.config["system_prompt"]
        if auto_answer:
            system_prompt += "\n如果是判断题,只回答正确或错误,不要输出其他内容。"
        client = MiMoClient(
            api_key=self.config["api_key"],
            base_url=self.config["base_url"],
            model=self.config["model"],
            temperature=self.config["temperature"],
            max_tokens=self.config["max_tokens"],
            system_prompt=system_prompt,
        )
        count = 0
        try:
            for chunk in client.stream_chat(text, stop_event=stop_event):
                stats = self.stats
                if stats:
                    if stats["first"] is None:
                        stats["first"] = time.monotonic()
                    stats["chars"] += len(chunk)
                self._push("token", req_id, chunk)
                count += len(chunk)
            if self.stats is not None:
                self.stats["total"] = time.monotonic() - self.stats["start"]
            self._push("stream_done", req_id, count, text)
        except StreamStopped:
            if self.stats is not None:
                self.stats["total"] = time.monotonic() - self.stats["start"]
            self._push("stream_stopped", req_id, count)
        except Exception as error:
            self._push("stream_error", req_id, str(error))

    def clear_all(self):
        self._stop_event.set()
        self.streaming = False
        self.ocr_text.delete("1.0", "end")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        self.speed_label.configure(text="")
        self.stats = None

    def _refresh_history_list(self):
        self.history_list.delete(0, "end")
        for record in self.history_records:
            question = (record.get("q") or "").replace("\n", " ")
            if len(question) > 40:
                question = question[:40] + "…"
            self.history_list.insert("end", question)

    def _history_select(self, event):
        if self.streaming:
            return
        selection = self.history_list.curselection()
        if not selection:
            return
        record = self.history_records[selection[0]]
        self.ocr_text.delete("1.0", "end")
        self.ocr_text.insert("1.0", record.get("q", ""))
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", record.get("a", ""))
        self.result_text.configure(state="disabled")
        self.speed_label.configure(text="")
        self.stats = None
        self._set_status("已载入历史")

    def _history_delete(self):
        selection = self.history_list.curselection()
        if not selection:
            return
        del self.history_records[selection[0]]
        history_store.save_history(HISTORY_PATH, self.history_records)
        self._refresh_history_list()
        self._set_status("已删除历史条目")

    def _history_clear(self):
        if not self.history_records:
            return
        self._confirm_clear_history()

    def _confirm_clear_history(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("清空历史")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="确定要清空全部历史记录吗?").pack(pady=(0, 14))
        buttons = ttk.Frame(frame)
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(3, weight=1)
        ttk.Button(buttons, text="确定", width=8, takefocus=0,
                   command=lambda: (dialog.destroy(), self._do_clear_history())).grid(row=0, column=1)
        ttk.Button(buttons, text="取消", width=8, takefocus=0,
                   command=dialog.destroy).grid(row=0, column=2, padx=(8, 0))
        buttons.pack()
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        dialog.geometry("+{}+{}".format(max(0, x), max(0, y)))

    def _show_update_dialog(self, tag, url):
        dialog = tk.Toplevel(self.root)
        dialog.title("发现新版本")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="新版本 {} 已发布\n当前版本 {}\n\n是否前往 GitHub 下载?".format(tag, APP_VERSION),
                  justify="center").pack(pady=(0, 14))
        buttons = ttk.Frame(frame)
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(4, weight=1)
        ttk.Button(buttons, text="前往下载", width=8, takefocus=0,
                   command=lambda: (webbrowser.open(url), dialog.destroy())).grid(row=0, column=1)
        ttk.Button(buttons, text="不再提醒", width=8, takefocus=0,
                   command=lambda: (self._silence_update(tag), dialog.destroy())).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(buttons, text="以后再说", width=8, takefocus=0,
                   command=dialog.destroy).grid(row=0, column=3, padx=(8, 0))
        buttons.pack()
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        dialog.geometry("+{}+{}".format(max(0, x), max(0, y)))
        return dialog

    def _silence_update(self, tag):
        self.config["update_silent"] = tag
        save_config(self.config)
        self._set_status("已忽略版本 {} 的更新提醒".format(tag))

    def _do_clear_history(self):
        self.history_records = []
        history_store.save_history(HISTORY_PATH, self.history_records)
        self._refresh_history_list()
        self._set_status("历史已清空")

    def open_settings(self):
        SettingsDialog(self.root, self.config, on_save=self._on_settings_saved,
                       on_check_update=lambda: self.check_update(True))

    def _on_settings_saved(self):
        self._set_status("设置已保存")

    def _on_close(self):
        self.config["auto_send"] = self.auto_var.get()
        self.config["auto_region"] = self.region_var.get()
        self.config["auto_answer"] = self.auto_answer_var.get()
        self.config["option_zones"] = [{"label": zone["label"], "bbox": zone.get("bbox"), "color": zone["color"]}
                                       for zone in self.option_zones]
        self.config.pop("option_correct", None)
        self.config.pop("option_wrong", None)
        self.config["geometry"] = self.root.geometry()
        self._monitor_stop.set()
        if self._zones:
            for zone in self._zones:
                zone.hide(save=True)
        if self._add_btn:
            self._add_btn.hide()
        save_config(self.config)
        self.root.destroy()


def main():
    enable_dpi_awareness()
    app = App()
    app.root.mainloop()


if __name__ == "__main__":
    main()
