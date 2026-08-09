import ctypes
import tkinter as tk
from PIL import ImageGrab

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

HINT_FONT = "Microsoft YaHei UI"


def virtual_screen():
    user32 = ctypes.windll.user32
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def grab_region(x, y, x2, y2):
    vx, vy, vw, vh = virtual_screen()
    full = ImageGrab.grab(all_screens=True)
    left = max(0, x - vx)
    top = max(0, y - vy)
    right = max(left, min(x2 - vx, vw))
    bottom = max(top, min(y2 - vy, vh))
    return full.crop((left, top, right, bottom))


class RegionSelector:
    def __init__(self, master, on_done, on_cancel=None):
        self.master = master
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.start_pos = None
        self.rect_id = None
        self.overlay = None

    def start(self):
        vx, vy, vw, vh = virtual_screen()
        overlay = tk.Toplevel(self.master)
        self.overlay = overlay
        overlay.overrideredirect(True)
        overlay.geometry("+{}+{}".format(vx, vy))
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.28)
        overlay.grab_set()
        overlay.focus_force()
        canvas = tk.Canvas(overlay, width=vw, height=vh, bg="black",
                           highlightthickness=0, cursor="crosshair")
        canvas.pack()
        canvas.create_text(vw // 2, 24, fill="white", font=(HINT_FONT, 11),
                           text="按住鼠标左键拖拽框选识别区域, 双击 / Esc / 鼠标右键 取消")
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<Double-Button-1>", lambda e: self._cancel())
        canvas.bind("<Button-3>", lambda e: self._cancel())
        overlay.bind("<Escape>", lambda e: self._cancel())

    def _on_press(self, event):
        self.start_pos = (event.x_root, event.y_root)

    def _on_drag(self, event):
        if self.start_pos is None:
            return
        x, y = self.start_pos
        x2, y2 = event.x_root, event.y_root
        canvas = self.overlay.winfo_children()[0]
        if self.rect_id is not None:
            canvas.delete(self.rect_id)
        self.rect_id = canvas.create_rectangle(x, y, x2, y2,
                                               outline="#00a0e9", width=2)

    def _on_release(self, event):
        if self.start_pos is None:
            return
        x, y = self.start_pos
        x2, y2 = event.x_root, event.y_root
        if abs(x2 - x) < 5 or abs(y2 - y) < 5:
            self._cancel()
            return
        self._finish((min(x, x2), min(y, y2), max(x, x2), max(y, y2)))

    def _finish(self, bbox):
        overlay = self.overlay
        self.overlay = None
        overlay.grab_release()
        overlay.destroy()
        self.on_done(bbox)

    def _cancel(self):
        if self.overlay is None:
            return
        overlay = self.overlay
        self.overlay = None
        overlay.grab_release()
        overlay.destroy()
        if self.on_cancel is not None:
            self.on_cancel()
