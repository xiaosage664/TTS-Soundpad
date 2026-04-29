"""可拖拽的透明悬浮文字输入窗口。"""

from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageDraw

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
        # 阴影层（深色半透明底层，偏移模拟投影）
        self._shadow = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_dark"],
            corner_radius=12,
            border_width=0,
        )
        self._shadow.pack(fill="both", expand=True, padx=(0, 0), pady=(0, 0))

        # 外层容器（模拟窗口边框）——覆盖在阴影层上
        self._outer = ctk.CTkFrame(
            self._shadow,
            fg_color=COLORS["bg_card"],
            corner_radius=10,
            border_width=2,
            border_color=COLORS["accent"],
        )
        self._outer.pack(fill="both", expand=True, padx=3, pady=(2, 4))

        # 拖拽指示器
        self._drag_handle = ctk.CTkLabel(
            self._outer,
            text="\u28FF",  # ⠿
            font=("Arial", 16),
            text_color=COLORS["text_dim"],
            width=22,
            cursor="fleur",
        )
        self._drag_handle.pack(side="left", padx=(8, 0), pady=8)

        # 置顶按钮 —— 图钉图标，位于拖拽区右侧、输入框左侧
        self._topmost = True  # 初始即置顶
        self._pin_img_on = self._make_pin_icon(COLORS["text_primary"], size=12)
        self._pin_img_off = self._make_pin_icon(COLORS["text_dim"], size=12)
        self._pin_btn = ctk.CTkButton(
            self._outer,
            text="",
            image=self._pin_img_on,
            width=22,
            height=28,
            corner_radius=6,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent"],
            command=self._toggle_topmost,
        )
        self._pin_btn.pack(side="left", padx=(2, 2), pady=8)

        # 输入框 —— 高度增大
        self._entry = ctk.CTkEntry(
            self._outer,
            font=FONTS["body"],
            placeholder_text="\u8f93\u5165\u6587\u672c...",
            height=36,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border_light"],
            fg_color=COLORS["bg_primary"],
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=4, pady=8)
        self._entry.bind("<Return>", lambda e: self._do_send())

        # 发送按钮 —— 与输入框等高
        self._send_btn = ctk.CTkButton(
            self._outer,
            text=ICONS["send"],
            width=40,
            height=36,
            font=(FONTS["body"][0], FONTS["body"][1], "bold"),
            corner_radius=8,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._do_send,
        )
        self._send_btn.pack(side="left", padx=2, pady=8)

        # 关闭按钮 —— 与输入框等高
        self._close_btn = ctk.CTkButton(
            self._outer,
            text="\u00d7",  # ×
            width=30,
            height=36,
            font=(FONTS["body"][0], 14, "bold"),
            corner_radius=8,
            fg_color=COLORS["bg_secondary"],
            hover_color=COLORS["error"],
            text_color=COLORS["text_secondary"],
            command=self._on_close,
        )
        self._close_btn.pack(side="left", padx=(2, 8), pady=8)

        # --- 拖拽事件绑定 ---
        for widget in (self._outer, self._drag_handle, self._shadow):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)

    # ------------------------------------------------------------------
    # 定位
    # ------------------------------------------------------------------

    def _apply_position(self, saved_pos: str):
        """设置窗口位置。优先用保存的位置，否则出现在主窗口右上方。"""
        # 先设定大小让 tkinter 计算
        width = 420
        height = 60
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
        self._drag_offset_x = event.x_root - self.winfo_x()
        self._drag_offset_y = event.y_root - self.winfo_y()

    def _on_drag_motion(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # 置顶
    # ------------------------------------------------------------------

    @staticmethod
    def _make_pin_icon(color: str, size: int = 20) -> ctk.CTkImage:
        """用 PIL 绘制经典图钉图标（push pin）。"""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c = color.lstrip("#")
        rgb = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
        fill = (*rgb, 255)
        # 钉帽（扁椭圆，顶部偏右倾斜感）
        d.ellipse([3, 0, size - 2, int(size * 0.45)], fill=fill)
        # 钉身（梯形，从帽底到针尖上方）
        mid = size // 2
        body_top = int(size * 0.38)
        body_bot = int(size * 0.65)
        d.polygon([
            (mid - 3, body_top), (mid + 3, body_top),
            (mid + 2, body_bot), (mid - 2, body_bot),
        ], fill=fill)
        # 针尖（三角）
        d.polygon([
            (mid - 1, body_bot), (mid + 1, body_bot),
            (mid, size - 1),
        ], fill=fill)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

    def _toggle_topmost(self):
        self._topmost = not self._topmost
        self.attributes("-topmost", self._topmost)
        if self._topmost:
            # 置顶模式：解除主窗口跟随，独立置顶
            self._unbind_master_events()
            self._pin_btn.configure(
                image=self._pin_img_on,
                fg_color=COLORS["accent"],
            )
        else:
            # 非置顶模式：跟随主窗口显示/最小化
            self._bind_master_events()
            self._pin_btn.configure(
                image=self._pin_img_off,
                fg_color=COLORS["bg_secondary"],
            )

    def _bind_master_events(self):
        """绑定主窗口事件，实现悬浮窗跟随主窗口显示/最小化。"""
        master = self.master
        self._map_id = master.bind("<Map>", self._on_master_map, add="+")
        self._unmap_id = master.bind("<Unmap>", self._on_master_unmap, add="+")

    def _unbind_master_events(self):
        """解除主窗口事件绑定。"""
        master = self.master
        if hasattr(self, "_map_id") and self._map_id:
            master.unbind("<Map>", self._map_id)
            self._map_id = None
        if hasattr(self, "_unmap_id") and self._unmap_id:
            master.unbind("<Unmap>", self._unmap_id)
            self._unmap_id = None

    def _on_master_map(self, _event=None):
        """主窗口恢复时，跟随显示悬浮窗。"""
        if not self._topmost and self.winfo_exists():
            self.deiconify()
            self.lift()

    def _on_master_unmap(self, _event=None):
        """主窗口最小化时，跟随隐藏悬浮窗。"""
        if not self._topmost and self.winfo_exists():
            self.withdraw()

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

    def flash_error(self):
        """边框闪烁红色提示发送失败。"""
        self._outer.configure(border_color=COLORS["error"])
        self.after(
            1500,
            lambda: self._outer.configure(border_color=COLORS["accent"]),
        )

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

    def destroy(self):
        """销毁前清理主窗口事件绑定。"""
        self._unbind_master_events()
        super().destroy()
