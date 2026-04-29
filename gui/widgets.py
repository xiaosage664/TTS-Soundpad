import customtkinter as ctk

from gui.theme import COLORS, FONTS


class RatePitchControl(ctk.CTkFrame):
    """语速/音调调节面板。"""

    def __init__(self, master, on_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="x")

        # --- 语速行 ---
        rate_row = ctk.CTkFrame(self._content, fg_color="transparent")
        rate_row.pack(fill="x", pady=(4, 2))

        ctk.CTkLabel(
            rate_row, text="语速:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=35,
        ).pack(side="left")

        self._rate_label = ctk.CTkLabel(
            rate_row, text="+0%", font=FONTS["small"],
            text_color=COLORS["accent"], width=45,
        )
        self._rate_label.pack(side="right", padx=(4, 0))

        self._rate_slider = ctk.CTkSlider(
            rate_row, from_=-50, to=100, number_of_steps=30,
            width=200, height=18,
            fg_color=COLORS["accent_dim"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._on_rate_change,
        )
        self._rate_slider.set(0)
        self._rate_slider.pack(side="left", fill="x", expand=True, padx=(4, 4))

        # --- 音调行 ---
        pitch_row = ctk.CTkFrame(self._content, fg_color="transparent")
        pitch_row.pack(fill="x", pady=(2, 4))

        ctk.CTkLabel(
            pitch_row, text="音调:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=35,
        ).pack(side="left")

        self._pitch_label = ctk.CTkLabel(
            pitch_row, text="+0Hz", font=FONTS["small"],
            text_color=COLORS["accent"], width=45,
        )
        self._pitch_label.pack(side="right", padx=(4, 0))

        self._pitch_slider = ctk.CTkSlider(
            pitch_row, from_=-50, to=50, number_of_steps=20,
            width=200, height=18,
            fg_color=COLORS["accent_dim"],
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
    """自动换行的快捷短语面板（含内置标题）。"""

    MAX_PHRASES = 12

    def __init__(self, master, on_send=None, on_edit=None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_send = on_send
        self._on_edit = on_edit
        self._buttons: list[ctk.CTkButton] = []
        self._add_btn: ctk.CTkButton | None = None

        # 标题行
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            header, text="快捷短语", font=FONTS["subtitle"],
            text_color=COLORS["text_primary"],
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="右键删除", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(side="right")

        # 按钮容器 —— 使用 grid 实现自动换行
        self._flow_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._flow_frame.pack(fill="x", padx=8, pady=(0, 8))

    def load_phrases(self, phrases: list[str]):
        for btn in self._buttons:
            btn.destroy()
        self._buttons.clear()
        if self._add_btn is not None:
            self._add_btn.destroy()
            self._add_btn = None
        for w in self._flow_frame.winfo_children():
            w.destroy()

        # 限制最多 MAX_PHRASES 条
        phrases = phrases[:self.MAX_PHRASES]

        cols = 4  # 每行最多4个按钮
        for i, phrase in enumerate(phrases):
            r, c = divmod(i, cols)
            btn = ctk.CTkButton(
                self._flow_frame, text=phrase, height=28,
                font=FONTS["small"], corner_radius=14,
                fg_color=COLORS["bg_secondary"],
                hover_color=COLORS["accent"],
                text_color=COLORS["text_primary"],
                command=lambda p=phrase: self._send_phrase(p),
            )
            btn.grid(row=r, column=c, padx=4, pady=2, sticky="ew")
            btn.bind("<Button-3>", lambda e, p=phrase, b=btn: self._delete_phrase(p, b))
            self._buttons.append(btn)

        # + 按钮放在末尾
        if len(phrases) < self.MAX_PHRASES:
            idx = len(phrases)
            r, c = divmod(idx, cols)
            self._add_btn = ctk.CTkButton(
                self._flow_frame, text="+", width=30, height=28,
                font=FONTS["body"], corner_radius=14,
                fg_color=COLORS["border"],
                hover_color=COLORS["accent"],
                text_color=COLORS["text_dim"],
                command=self._on_add_click,
            )
            self._add_btn.grid(row=r, column=c, padx=4, pady=2, sticky="w")

        # 让列均匀分布
        for c in range(cols):
            self._flow_frame.columnconfigure(c, weight=1)

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
    """历史记录面板（含内置标题）。"""

    def __init__(self, master, on_replay=None, show_title=True, **kwargs):
        super().__init__(master, **kwargs)
        self._on_replay = on_replay
        self._items: list[ctk.CTkFrame] = []
        self._header = None

        if show_title:
            self._header = ctk.CTkFrame(self, fg_color="transparent")
            self._header.pack(fill="x", padx=4, pady=(2, 0))
            ctk.CTkLabel(
                self._header, text="历史记录", font=FONTS["subtitle"],
                text_color=COLORS["text_primary"],
            ).pack(side="left")

    def add_entry(self, timestamp: str, text: str, voice: str):
        # 外层容器 —— 固定行高，禁止子控件撑大
        row = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=4, height=30)
        # 新条目插到标题之后（最新在最上方）
        if self._header:
            row.pack(fill="x", pady=1, padx=4, after=self._header)
        else:
            row.pack(fill="x", pady=1, padx=4)
        row.pack_propagate(False)

        # 左边 accent 装饰线
        accent_bar = ctk.CTkFrame(
            row, width=3, fg_color=COLORS["accent"], corner_radius=1,
        )
        accent_bar.pack(side="left", fill="y")

        # 时间戳
        ctk.CTkLabel(
            row, text=timestamp, font=("Consolas", 10),
            text_color=COLORS["text_dim"],
        ).pack(side="left", padx=(6, 4))

        # 文本
        display = text if len(text) <= 26 else text[:24] + "..."
        ctk.CTkLabel(
            row, text=display, font=("Microsoft YaHei UI", 10),
            text_color=COLORS["text_primary"], anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=4)

        # 语音标签
        voice_short = voice.split("-")[-1].replace("Neural", "") if voice else ""
        if voice_short:
            ctk.CTkLabel(
                row, text=voice_short, font=("Microsoft YaHei UI", 9),
                text_color=COLORS["text_dim"],
            ).pack(side="left", padx=2)

        # 重播按钮
        btn = ctk.CTkButton(
            row, text="\u25b6", width=24, height=22,
            font=("Microsoft YaHei UI", 9), corner_radius=4,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=lambda t=text, v=voice: self._replay(t, v),
        )
        btn.pack(side="right", padx=(2, 4))

        self._items.insert(0, row)
        while len(self._items) > 20:
            old = self._items.pop()
            old.destroy()

    def _replay(self, text: str, voice: str):
        if self._on_replay:
            self._on_replay(text, voice)


class StatusBar(ctk.CTkFrame):
    """底部状态栏。"""

    def __init__(self, master, **kwargs):
        super().__init__(master, height=30, **kwargs)
        self.pack_propagate(False)

        self._dot = ctk.CTkLabel(
            self, text="\u25cf", font=("Arial", 10),
            text_color=COLORS["error"], width=16,
        )
        self._dot.pack(side="left", padx=(10, 0))

        self._conn_label = ctk.CTkLabel(
            self, text="Soundpad 未连接", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        )
        self._conn_label.pack(side="left", padx=4)

        self._status_label = ctk.CTkLabel(
            self, text="", font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self._status_label.pack(side="right", padx=10)

        self._auto_clear_id = None

    def set_connected(self, connected: bool):
        if connected:
            self._dot.configure(text_color=COLORS["success"])
            self._conn_label.configure(text="Soundpad 已连接")
        else:
            self._dot.configure(text_color=COLORS["error"])
            self._conn_label.configure(text="Soundpad 未连接")

    def set_status(self, text: str, is_error: bool = False, auto_clear: int = 0):
        color = COLORS["error"] if is_error else COLORS["text_secondary"]
        self._status_label.configure(text=text, text_color=color)
        if self._auto_clear_id:
            self.after_cancel(self._auto_clear_id)
            self._auto_clear_id = None
        if auto_clear > 0:
            self._auto_clear_id = self.after(
                auto_clear, lambda: self._status_label.configure(text="")
            )
