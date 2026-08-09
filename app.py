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
from mimo_client import MiMoClient, StreamStopped

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
INVITE_IMAGE_PATH = os.path.join(APP_DIR, "invite_poster.png")

APP_VERSION = "1.0.0"

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.xiaomimimo.com/v1",
    "model": "mimo-v2.5",
    "temperature": 0.7,
    "max_tokens": 2048,
    "system_prompt": "你是MiMo,小米公司研发的AI智能助手,请根据用户提供的OCR识别文本回答问题。",
    "auto_send": True,
    "geometry": "",
    "update_repo": "",
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
    def __init__(self, master, config, on_save):
        super().__init__(master)
        self.config = config
        self.on_save = on_save
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
        self.prompt_text.grid(row=len(rows), column=1, sticky="we", pady=5)
        result_row = ttk.Frame(frame)
        result_row.grid(row=len(rows) + 1, column=0, columnspan=2, pady=(10, 0), sticky="w")
        self.test_label = tk.Label(result_row, text="", font=(UI_FONT, 10))
        self.test_label.pack(side="left")
        test_row = ttk.Frame(frame)
        test_row.grid(row=len(rows) + 2, column=0, columnspan=2, pady=(8, 0), sticky="ew")
        self.test_btn = ttk.Button(test_row, text="测试连通", takefocus=0, command=self._test_connection)
        self.test_btn.pack(side="left")
        self.invite_btn = ttk.Button(test_row, text="免费领取10体验金", takefocus=0,
                                     command=self._open_invite)
        self.invite_btn.pack(side="left", padx=(12, 0))
        self._tip_after = None
        self._tip_hide_after = None
        self._tip_win = None
        self._tip_img = None
        self.invite_btn.bind("<Enter>", self._invite_tip_enter)
        self.invite_btn.bind("<Leave>", self._invite_tip_leave)
        spacer = ttk.Frame(test_row)
        spacer.pack(side="left", fill="x", expand=True)
        ttk.Button(test_row, text="保存", takefocus=0, command=self._save).pack(side="left", padx=4)
        ttk.Button(test_row, text="取消", takefocus=0, command=self.destroy).pack(side="left")
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
        except ValueError:
            messagebox.showerror("设置", "Temperature 必须是数字,Max Tokens 必须是整数")
            return
        self.config["api_key"] = self.entries["api_key"].get().strip()
        self.config["base_url"] = self.entries["base_url"].get().strip()
        self.config["model"] = self.entries["model"].get().strip()
        self.config["temperature"] = temperature
        self.config["max_tokens"] = max_tokens
        self.config["system_prompt"] = self.prompt_text.get("1.0", "end-1c")
        save_config(self.config)
        self.on_save()
        self.destroy()


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
        self.cur_image = None
        self.stats = None
        self._stop_event = threading.Event()
        self._req_id = 0
        self._build_ui()
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
        ttk.Button(toolbar, text="截图识别 (F2)", takefocus=0, command=self.capture_ocr).pack(side="left")
        ttk.Button(toolbar, text="打开图片", takefocus=0, command=self.open_file_ocr).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="识别剪贴板", takefocus=0, command=self.clipboard_ocr).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="清空", takefocus=0, command=self.clear_all).pack(side="left", padx=(6, 0))
        send_frame = ttk.Frame(toolbar)
        ttk.Button(send_frame, text="发送给 MiMo", takefocus=0, command=self.send_to_mimo).pack()
        self.auto_var = tk.BooleanVar(value=self.config.get("auto_send", True))
        ttk.Checkbutton(send_frame, text="识别后自动发送", variable=self.auto_var).pack(pady=(3, 0))
        send_frame.pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="设置", takefocus=0, command=self.open_settings).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="检查更新", takefocus=0, command=lambda: self.check_update(True)).pack(side="left", padx=(6, 0))
        spacer = ttk.Frame(toolbar)
        spacer.pack(side="left", fill="x", expand=True)

        paned = ttk.PanedWindow(self.root, orient="vertical")
        self.paned = paned
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        ocr_frame = ttk.LabelFrame(paned, text="OCR 识别结果 (可编辑)")
        self.ocr_text = tk.Text(ocr_frame, wrap="word", font=(UI_FONT, 10), undo=True)
        self.ocr_scroll = ttk.Scrollbar(ocr_frame, command=self.ocr_text.yview)
        self.ocr_text.configure(yscrollcommand=self.ocr_scroll.set)
        self.ocr_text.pack(side="left", fill="both", expand=True)
        self.ocr_scroll.pack(side="right", fill="y")

        result_head = ttk.Frame(paned)
        ttk.Label(result_head, text="MiMo 回复").pack(side="left")
        self.speed_label = tk.Label(result_head, text="", fg="#888888", font=(UI_FONT, 9))
        self.speed_label.pack(side="left", padx=(8, 0))
        result_frame = ttk.LabelFrame(paned, labelwidget=result_head)
        self.result_text = tk.Text(result_frame, wrap="word", font=(UI_FONT, 10),
                                   state="disabled", cursor="arrow")
        self.result_scroll = ttk.Scrollbar(result_frame, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=self.result_scroll.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        self.result_scroll.pack(side="right", fill="y")

        paned.add(ocr_frame, weight=2)
        paned.add(result_frame, weight=3)
        self.root.after(150, self._init_sash)

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
        self.root.after(80, self._poll_queue)

    def _handle_event(self, event, args):
        if event == "ocr_done":
            self._set_status("OCR 完成")
            self.ocr_text.delete("1.0", "end")
            self.ocr_text.insert("1.0", args[0])
            if self.auto_var.get() and args[0].strip():
                self.send_to_mimo()
        elif event == "ocr_error":
            self._set_status("OCR 失败")
            messagebox.showerror("OCR 识别", args[0])
        elif event == "token":
            if args[0] != self._req_id:
                return
            self.result_text.configure(state="normal")
            self.result_text.insert("end", args[1])
            self.result_text.see("end")
            self.result_text.configure(state="disabled")
        elif event == "stream_start":
            if args[0] != self._req_id:
                return
            self.streaming = True
            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", "end")
            self.result_text.configure(state="disabled")
            self._set_status("MiMo 生成中...")
            self.speed_label.configure(text="响应速度：--")
        elif event == "stream_done":
            if args[0] != self._req_id:
                return
            self.streaming = False
            self._set_status("完成 ({} 字)".format(args[1]))
            self._show_final_speed()
        elif event == "stream_stopped":
            if args[0] != self._req_id:
                return
            self.streaming = False
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
                    messagebox.showinfo("检查更新", "检查失败(网络异常或仓库地址错误)")
                return
            if tag and compare_versions(APP_VERSION, tag) < 0:
                if messagebox.askyesno(
                    "发现新版本",
                    "新版本 {} 已发布\n当前版本 {}\n\n是否前往 GitHub 下载?".format(tag, APP_VERSION),
                ):
                    webbrowser.open(url)
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
        except Exception:
            data, tag, url = None, "", ""
        self._push("update_result", data is not None, tag, url, manual)

    def capture_ocr(self):
        if self.streaming:
            return
        self._set_status("请拖拽框选识别区域")
        selector = screenshot.RegionSelector(self.root, on_done=self._on_region_selected,
                                             on_cancel=lambda: self._set_status("已取消"))
        selector.start()

    def _on_region_selected(self, bbox):
        try:
            image = screenshot.grab_region(*bbox)
            self._start_ocr(image)
        except Exception as error:
            messagebox.showerror("截图", str(error))
            self._set_status("截图失败")

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
        self.stream_thread = threading.Thread(target=self._stream_worker, args=(text, req_id, stop_event), daemon=True)
        self.stream_thread.start()

    def _stream_worker(self, text, req_id, stop_event):
        import time
        self.stats = {"start": time.monotonic(), "first": None, "chars": 0, "total": None}
        self._push("stream_start", req_id)
        client = MiMoClient(
            api_key=self.config["api_key"],
            base_url=self.config["base_url"],
            model=self.config["model"],
            temperature=self.config["temperature"],
            max_tokens=self.config["max_tokens"],
            system_prompt=self.config["system_prompt"],
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
            self._push("stream_done", req_id, count)
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

    def open_settings(self):
        SettingsDialog(self.root, self.config, on_save=self._on_settings_saved)

    def _on_settings_saved(self):
        self._set_status("设置已保存")

    def _on_close(self):
        self.config["auto_send"] = self.auto_var.get()
        self.config["geometry"] = self.root.geometry()
        save_config(self.config)
        self.root.destroy()


def main():
    enable_dpi_awareness()
    app = App()
    app.root.mainloop()


if __name__ == "__main__":
    main()
