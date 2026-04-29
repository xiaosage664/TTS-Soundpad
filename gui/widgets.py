import customtkinter as ctk

from gui.theme import COLORS, FONTS


class RatePitchControl(ctk.CTkFrame):
    """可折叠的语速/音调调节面板。"""

    def __init__(self, master, on_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change

        # 滑块容器（默认显示）
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="x")

        # --- 语速行 ---
        rate_row = ctk.CTkFrame(self._content, fg_color="transparent")
        rate_row.pack(fill="x", pady=(4, 2))

        ctk.CTkLabel(
            rate_row, text="\u8bed\u901f:", font=FONTS["small"],
            text_color=COLORS["text_primary"], width=35,
        ).pack(side="left")

        self._rate_label = ctk.CTkLabel(
            rate_row, text="+0%", font=FONTS["small"],
            text_color=COLORS["accent"], width=45,
        )
        self._rate_label.pack(side="right", padx=(4, 0))

        self._rate_slider = ctk.CTkSlider(
            rate_row, from_=-50, to=100, number_of_steps=30,
            width=200, height=16,
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._on_rate_change,
        )
        self._rate_slider.set(0)
        self._rate_slider.pack(side="left", fill="x", expand=True, padx=(4, 4))

        # --- 音调行 ---
        pitch_row = ctk.CTkFrame(self._content, fg_color="transparent")
        pitch_row.pack(fill="x", pady=(2, 0))

        ctk.CTkLabel(
            pitch_row, text="\u97f3\u8c03:", font=FONTS["small"],
            text_color=COLORS["text_primary"], width=35,
        ).pack(side="left")

        self._pitch_label = ctk.CTkLabel(
            pitch_row, text="+0Hz", font=FONTS["small"],
            text_color=COLORS["accent"], width=45,
        )
        self._pitch_label.pack(side="right", padx=(4, 0))

        self._pitch_slider = ctk.CTkSlider(
            pitch_row, from_=-50, to=50, number_of_steps=20,
            width=200, height=16,
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._on_pitch_change,
        )
        self._pitch_slider.set(0)
        self._pitch_slider.pack(side="left", fill="x", expand=True, padx=(4, 4))

    def _on_rate_change(self, value):
        v = int(round(value))
        text = f"+{v}%" if v >= 0 else f"{v}%"
        self._rate_label.configure(text=text)
        if self._on_change:
            self._on_change("rate", text)

    def _on_pitch_change(self, value):
        v = int(round(value))
        text = f"+{v}Hz" if v >= 0 else f"{v}Hz"
        self._pitch_label.configure(text=text)
        if self._on_change:
            self._on_change("pitch", text)

    def set_rate(self, rate_str: str):
        try:
            v = int(rate_str.replace("%", "").replace("+", ""))
        except ValueError:
            v = 0
        self._rate_slider.set(v)
        self._rate_label.configure(text=rate_str)

    def set_pitch(self, pitch_str: str):
        try:
            v = int(pitch_str.replace("Hz", "").replace("+", ""))
        except ValueError:
            v = 0
        self._pitch_slider.set(v)
        self._pitch_label.configure(text=pitch_str)


class QuickPhrasePanel(ctk.CTkFrame):
    """横向流式快捷短语面板。"""

    def __init__(self, master, on_send=None, on_edit=None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_send = on_send
        self._on_edit = on_edit
        self._buttons: list[ctk.CTkButton] = []
        self._add_btn: ctk.CTkButton | None = None

        # 内部用 wrapping frame
        self._flow_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._flow_frame.pack(fill="x", padx=4, pady=4)

    def load_phrases(self, phrases: list[str]):
        """加载短语列表，横向排列。"""
        for btn in self._buttons:
            btn.destroy()
        self._buttons.clear()
        if self._add_btn is not None:
            self._add_btn.destroy()
            self._add_btn = None

        # 销毁旧 flow_frame 子控件
        for w in self._flow_frame.winfo_children():
            w.destroy()

        for phrase in phrases:
            btn = ctk.CTkButton(
                self._flow_frame, text=phrase, height=28,
                font=FONTS["body"], corner_radius=14,
                fg_color=COLORS["bg_secondary"],
                hover_color=COLORS["accent"],
                text_color=COLORS["text_primary"],
                command=lambda p=phrase: self._send_phrase(p),
            )
            btn.pack(side="left", padx=3, pady=2)
            # 右键删除
            btn.bind("<Button-3>", lambda e, p=phrase, b=btn: self._delete_phrase(p, b))
            self._buttons.append(btn)

        # 添加按钮
        self._add_btn = ctk.CTkButton(
            self._flow_frame, text="+", width=28, height=28,
            font=FONTS["body"], corner_radius=14,
            fg_color=COLORS["border"],
            hover_color=COLORS["accent"],
            text_color=COLORS["text_dim"],
            command=self._on_add_click,
        )
        self._add_btn.pack(side="left", padx=3, pady=2)

    def _send_phrase(self, phrase: str):
        if self._on_send:
            self._on_send(phrase)

    def _delete_phrase(self, phrase: str, btn: ctk.CTkButton):
        btn.destroy()
        self._buttons = [b for b in self._buttons if b.winfo_exists()]
        if self._on_edit:
            self._on_edit("delete", phrase)

    def _on_add_click(self):
        if self._on_edit:
            self._on_edit("add", "")


class HistoryPanel(ctk.CTkScrollableFrame):
    """历史记录面板。"""

    def __init__(self, master, on_replay=None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_replay = on_replay
        self._items: list[ctk.CTkFrame] = []

    def add_entry(self, timestamp: str, text: str, voice: str):
        row = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=6)
        row.pack(fill="x", pady=2, padx=2)

        # 时间
        ctk.CTkLabel(
            row, text=timestamp, font=FONTS["small"],
            text_color=COLORS["text_dim"], width=55,
        ).pack(side="left", padx=(8, 4), pady=4)

        # 文本
        display = text if len(text) <= 28 else text[:26] + "..."
        ctk.CTkLabel(
            row, text=display, font=FONTS["small"],
            text_color=COLORS["text_primary"], anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=4, pady=4)

        # 语音标签
        voice_short = voice.split("-")[-1].replace("Neural", "") if voice else ""
        if voice_short:
            ctk.CTkLabel(
                row, text=voice_short, font=("Microsoft YaHei UI", 9),
                text_color=COLORS["text_dim"], width=45,
            ).pack(side="left", padx=2)

        # 重播按钮
        btn = ctk.CTkButton(
            row, text="\u25b6", width=36, height=24,
            font=FONTS["small"], corner_radius=4,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=lambda t=text, v=voice: self._replay(t, v),
        )
        btn.pack(side="right", padx=6, pady=4)

        self._items.insert(0, row)
        # 限制最多 30 条
        while len(self._items) > 30:
            old = self._items.pop()
            old.destroy()

    def _replay(self, text: str, voice: str):
        if self._on_replay:
            self._on_replay(text, voice)


class StatusBar(ctk.CTkFrame):
    """底部状态栏。"""

    def __init__(self, master, **kwargs):
        super().__init__(master, height=28, **kwargs)
        self.pack_propagate(False)

        self._dot = ctk.CTkLabel(
            self, text="\u25cf", font=("Arial", 12),
            text_color=COLORS["error"], width=18,
        )
        self._dot.pack(side="left", padx=(8, 0))

        self._conn_label = ctk.CTkLabel(
            self, text="Soundpad \u672a\u8fde\u63a5", font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self._conn_label.pack(side="left", padx=4)

        self._status_label = ctk.CTkLabel(
            self, text="", font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self._status_label.pack(side="right", padx=8)

        self._auto_clear_id = None

    def set_connected(self, connected: bool):
        if connected:
            self._dot.configure(text_color=COLORS["success"])
            self._conn_label.configure(text="Soundpad \u5df2\u8fde\u63a5")
        else:
            self._dot.configure(text_color=COLORS["error"])
            self._conn_label.configure(text="Soundpad \u672a\u8fde\u63a5")

    def set_status(self, text: str, is_error: bool = False, auto_clear: int = 0):
        """设置状态文字。auto_clear: 毫秒后自动清除(0=不自动清除)"""
        color = COLORS["error"] if is_error else COLORS["text_secondary"]
        self._status_label.configure(text=text, text_color=color)
        # 取消之前的自动清除
        if self._auto_clear_id:
            self.after_cancel(self._auto_clear_id)
            self._auto_clear_id = None
        if auto_clear > 0:
            self._auto_clear_id = self.after(
                auto_clear, lambda: self._status_label.configure(text="")
            )
