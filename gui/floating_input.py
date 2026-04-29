"""可拖拽的透明悬浮文字输入窗口。"""

from typing import Callable

import customtkinter as ctk

from gui.theme import COLORS, FONTS, ICONS


class FloatingInputWindow(ctk.CTkToplevel):
    """无标题栏、可拖拽、半透明的悬浮输入框。

    仅包含一个文本输入框和发送按钮，用于快速发送 TTS。
    """

    def __init__(
        self,
        master,
        on_send: Callable[[str], None],
        on_close: Callable[[], None],
        initial_pos: str = "",
    ):
        super().__init__(master)
        self._on_send = on_send
        self._on_close = on_close

        # 拖拽状态
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        # --- 防闪烁创建序列 ---
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.85)
        self.resizable(False, False)

        self._build_ui()

        # 定位窗口
        self._apply_position(initial_pos)

        # 显示并聚焦
        self.deiconify()
        self.focus_entry()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        # 外层容器（模拟窗口边框）
        self._outer = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_primary"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["accent"],
        )
        self._outer.pack(fill="both", expand=True, padx=2, pady=2)

        # 拖拽指示器
        self._drag_handle = ctk.CTkLabel(
            self._outer,
            text="\u28FF",  # ⠿
            font=("Arial", 14),
            text_color=COLORS["text_dim"],
            width=20,
            cursor="fleur",
        )
        self._drag_handle.pack(side="left", padx=(8, 2), pady=6)

        # 输入框
        self._entry = ctk.CTkEntry(
            self._outer,
            font=FONTS["body"],
            placeholder_text="\u8f93\u5165\u6587\u672c...",
            height=30,
            corner_radius=6,
            border_width=1,
            border_color=COLORS["border"],
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=4, pady=6)
        self._entry.bind("<Return>", lambda e: self._do_send())

        # 发送按钮
        self._send_btn = ctk.CTkButton(
            self._outer,
            text=ICONS["send"],
            width=36,
            height=30,
            font=FONTS["body"],
            corner_radius=6,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._do_send,
        )
        self._send_btn.pack(side="left", padx=2, pady=6)

        # 关闭按钮
        self._close_btn = ctk.CTkButton(
            self._outer,
            text="\u00d7",  # ×
            width=28,
            height=30,
            font=FONTS["body"],
            corner_radius=6,
            fg_color=COLORS["bg_secondary"],
            hover_color=COLORS["error"],
            text_color=COLORS["text_secondary"],
            command=self._on_close,
        )
        self._close_btn.pack(side="left", padx=(2, 8), pady=6)

        # --- 拖拽事件绑定 ---
        for widget in (self._outer, self._drag_handle):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)

    # ------------------------------------------------------------------
    # 定位
    # ------------------------------------------------------------------

    def _apply_position(self, saved_pos: str):
        """设置窗口位置。优先用保存的位置，否则出现在主窗口右上方。"""
        # 先设定大小让 tkinter 计算
        width = 360
        height = 50
        self.geometry(f"{width}x{height}")

        if saved_pos and saved_pos.startswith("+"):
            self.geometry(f"{width}x{height}{saved_pos}")
            return

        # 默认位置：主窗口右上角偏移
        try:
            master = self.master
            mx = master.winfo_x()
            my = master.winfo_y()
            mw = master.winfo_width()
            x = mx + mw + 10
            y = my
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self.geometry(f"{width}x{height}+100+100")

    # ------------------------------------------------------------------
    # 拖拽
    # ------------------------------------------------------------------

    def _on_drag_start(self, event):
        self._drag_offset_x = event.x
        self._drag_offset_y = event.y

    def _on_drag_motion(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------

    def _do_send(self):
        text = self._entry.get().strip()
        if not text:
            return
        self._on_send(text)

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool):
        """发送中禁用/恢复控件。"""
        if busy:
            self._entry.configure(state="disabled")
            self._send_btn.configure(state="disabled", text="...")
        else:
            self._entry.configure(state="normal")
            self._send_btn.configure(state="normal", text=ICONS["send"])

    def clear_entry(self):
        """清空输入框。"""
        self._entry.delete(0, "end")

    def focus_entry(self):
        """聚焦输入框。"""
        self._entry.focus_force()

    def get_position(self) -> str:
        """返回当前位置字符串 '+x+y'，用于保存。"""
        geo = self.geometry()
        # geometry 格式: WxH+X+Y
        if "+" in geo:
            pos = "+" + geo.split("+", 1)[1]
            return pos
        return ""
