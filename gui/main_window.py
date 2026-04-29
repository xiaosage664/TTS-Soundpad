import customtkinter as ctk

from app.orchestrator import Orchestrator, SpeakStatus
from gui.theme import COLORS, FONTS, ICONS, WINDOW
from gui.widgets import HistoryPanel, QuickPhrasePanel, RatePitchControl, StatusBar


class MainWindow:
    def __init__(self, root: ctk.CTk, orchestrator: Orchestrator):
        self._root = root
        self._orch = orchestrator
        self._voices: list[dict] = []
        self._topmost = False
        self._on_minimize_to_tray = None
        self._floating_win = None
        self._poll_interval = 5000  # 自适应轮询间隔

        self._setup_window()
        self._build_ui()
        self._load_voices()
        self._poll_soundpad()

    def set_tray_callback(self, callback):
        """设置最小化到托盘的回调。"""
        self._on_minimize_to_tray = callback

    # ------------------------------------------------------------------
    # 窗口初始化
    # ------------------------------------------------------------------

    def _setup_window(self):
        self._root.title(WINDOW["title"])
        geo = self._orch.config.get("window_geometry", WINDOW["default_geometry"])
        self._root.geometry(geo)
        self._root.minsize(WINDOW["min_width"], WINDOW["min_height"])
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

    # ------------------------------------------------------------------
    # UI 构建（拆分为子方法）
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_header()
        self._build_input()
        self._build_phrases()
        self._build_history()
        self._build_status_bar()

    def _build_header(self):
        """顶部设置区域：标题、按钮、语音选择、语速音调。"""
        settings = ctk.CTkFrame(self._root, fg_color="transparent")
        settings.pack(fill="x", padx=12, pady=(12, 4))

        # 标题行
        title_row = ctk.CTkFrame(settings, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row, text="TTS Soundpad", font=FONTS["title"],
            text_color=COLORS["accent"],
        ).pack(side="left")

        # 右侧功能按钮
        self._topmost_btn = ctk.CTkButton(
            title_row, text=ICONS["pin"] + " 置顶", width=56, height=26,
            font=FONTS["small"], corner_radius=4,
            fg_color=COLORS["bg_secondary"],
            hover_color=COLORS["accent"],
            command=self._toggle_topmost,
        )
        self._topmost_btn.pack(side="right")

        self._floating_btn = ctk.CTkButton(
            title_row, text=ICONS["floating"] + " 悬浮", width=56, height=26,
            font=FONTS["small"], corner_radius=4,
            fg_color=COLORS["bg_secondary"],
            hover_color=COLORS["accent"],
            command=self._toggle_floating,
        )
        self._floating_btn.pack(side="right", padx=(0, 6))

        self._tray_btn = ctk.CTkButton(
            title_row, text=ICONS["tray"] + " 托盘", width=56, height=26,
            font=FONTS["small"], corner_radius=4,
            fg_color=COLORS["bg_secondary"],
            hover_color=COLORS["accent"],
            command=self._minimize_to_tray,
        )
        self._tray_btn.pack(side="right", padx=(0, 6))

        # 语音选择行
        voice_row = ctk.CTkFrame(settings, fg_color="transparent")
        voice_row.pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(
            voice_row, text="语音:", font=FONTS["body"],
            text_color=COLORS["text_primary"], width=40,
        ).pack(side="left")

        self._voice_var = ctk.StringVar(value="zh-CN-XiaoxiaoNeural")
        self._voice_combo = ctk.CTkComboBox(
            voice_row, variable=self._voice_var, state="readonly",
            values=["加载中..."], font=FONTS["body"],
            dropdown_font=FONTS["body"], width=320,
        )
        self._voice_combo.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # 语速/音调（可折叠）
        self._rate_pitch = RatePitchControl(
            settings, on_change=self._on_rate_pitch_change,
        )
        self._rate_pitch.pack(fill="x", pady=(6, 0))
        self._rate_pitch.set_rate(self._orch.config.get("rate", "+0%"))
        self._rate_pitch.set_pitch(self._orch.config.get("pitch", "+0Hz"))

        # 输出选项行
        output_row = ctk.CTkFrame(settings, fg_color="transparent")
        output_row.pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(
            output_row, text="输出:", font=FONTS["body"],
            text_color=COLORS["text_primary"], width=40,
        ).pack(side="left")

        self._mic_var = ctk.BooleanVar(
            value=self._orch.config.get("play_on_mic", True)
        )
        ctk.CTkCheckBox(
            output_row, text="麦克风", variable=self._mic_var,
            font=FONTS["body"], command=self._save_output_config,
        ).pack(side="left", padx=(8, 16))

        self._speaker_var = ctk.BooleanVar(
            value=self._orch.config.get("play_on_speakers", False)
        )
        ctk.CTkCheckBox(
            output_row, text="扬声器", variable=self._speaker_var,
            font=FONTS["body"], command=self._save_output_config,
        ).pack(side="left")

        self._cleanup_var = ctk.BooleanVar(
            value=self._orch.config.get("auto_cleanup_soundpad", True)
        )
        ctk.CTkCheckBox(
            output_row, text="自动清理", variable=self._cleanup_var,
            font=FONTS["small"], command=self._save_output_config,
        ).pack(side="right", padx=(8, 0))

    def _build_input(self):
        """文本输入区域 + 按钮行。"""
        input_frame = ctk.CTkFrame(self._root, fg_color="transparent")
        input_frame.pack(fill="both", expand=True, padx=12, pady=8)

        ctk.CTkLabel(
            input_frame, text="输入文字:", font=FONTS["body"],
            text_color=COLORS["text_primary"],
        ).pack(anchor="w")

        self._textbox = ctk.CTkTextbox(
            input_frame, font=FONTS["body"], height=120,
            corner_radius=8, border_width=1,
            border_color=COLORS["border"],
        )
        self._textbox.pack(fill="both", expand=True, pady=(4, 0))
        self._textbox.bind("<Control-Return>", lambda e: self._on_send())
        self._textbox.bind("<KeyRelease>", lambda e: self._update_char_count())

        # placeholder 模拟
        self._placeholder_active = True
        self._placeholder_text = "在此输入要转为语音的文字..."
        self._textbox.insert("1.0", self._placeholder_text)
        self._textbox.configure(text_color=COLORS["text_dim"])
        self._textbox.bind("<FocusIn>", self._on_textbox_focus_in)
        self._textbox.bind("<FocusOut>", self._on_textbox_focus_out)

        # 按钮行
        btn_row = ctk.CTkFrame(input_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 0))

        self._send_btn = ctk.CTkButton(
            btn_row, text=ICONS["send"] + " 发送  Ctrl+Enter", font=FONTS["body"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=36, corner_radius=8, command=self._on_send,
        )
        self._send_btn.pack(side="left", fill="x", expand=True)

        self._stop_btn = ctk.CTkButton(
            btn_row, text="停止", font=FONTS["body"], width=70,
            fg_color=COLORS["error"], hover_color="#ff7777",
            height=36, corner_radius=8, command=self._on_stop,
        )
        self._stop_btn.pack(side="left", padx=(8, 0))

        self._preview_btn = ctk.CTkButton(
            btn_row, text="预听", font=FONTS["body"], width=70,
            fg_color=COLORS["bg_secondary"], hover_color=COLORS["accent"],
            height=36, corner_radius=8, command=self._on_preview,
        )
        self._preview_btn.pack(side="left", padx=(8, 0))

        max_len = self._orch.config.get("max_text_length", 500)
        self._char_label = ctk.CTkLabel(
            btn_row, text=f"0/{max_len}", font=FONTS["small"],
            text_color=COLORS["text_dim"], width=70,
        )
        self._char_label.pack(side="right", padx=(8, 0))

    def _build_phrases(self):
        """快捷短语面板。"""
        ctk.CTkLabel(
            self._root, text="快捷短语 (右键删除):", font=FONTS["body"],
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=12)

        self._phrase_panel = QuickPhrasePanel(
            self._root, on_send=self._on_phrase_send,
            on_edit=self._on_phrase_edit,
            corner_radius=8,
            fg_color=COLORS["bg_primary"],
            border_width=1, border_color=COLORS["border"],
        )
        self._phrase_panel.pack(fill="x", padx=12, pady=(2, 4))
        self._phrase_panel.load_phrases(
            self._orch.config.get("quick_phrases", [])
        )

    def _build_history(self):
        """历史记录面板。"""
        ctk.CTkLabel(
            self._root, text="历史记录:", font=FONTS["body"],
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=12)

        self._history = HistoryPanel(
            self._root, on_replay=self._on_replay,
            height=150, corner_radius=8,
            fg_color=COLORS["bg_primary"],
            border_width=1, border_color=COLORS["border"],
        )
        self._history.pack(fill="x", padx=12, pady=(2, 8))

    def _build_status_bar(self):
        """底部状态栏。"""
        self._status_bar = StatusBar(
            self._root, fg_color=COLORS["bg_secondary"], corner_radius=0,
        )
        self._status_bar.pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    # Placeholder 逻辑
    # ------------------------------------------------------------------

    def _on_textbox_focus_in(self, _event=None):
        if self._placeholder_active:
            self._textbox.delete("1.0", "end")
            self._textbox.configure(text_color=COLORS["text_primary"])
            self._placeholder_active = False

    def _on_textbox_focus_out(self, _event=None):
        text = self._textbox.get("1.0", "end").strip()
        if not text:
            self._placeholder_active = True
            self._textbox.insert("1.0", self._placeholder_text)
            self._textbox.configure(text_color=COLORS["text_dim"])

    def _get_text(self) -> str:
        """获取输入文本（排除 placeholder）。"""
        if self._placeholder_active:
            return ""
        return self._textbox.get("1.0", "end").strip()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_send(self):
        text = self._get_text()
        if not text:
            return
        voice = self._voice_var.get()
        voice_name = self._resolve_voice_name(voice)
        self._orch.speak(text, voice_name, self._on_status)

    def _on_stop(self):
        self._orch.stop()
        self._orch.stop_preview()
        self._status_bar.set_status("")

    def _on_preview(self):
        """本地预听当前文本。"""
        text = self._get_text()
        if not text:
            return
        voice = self._voice_var.get()
        voice_name = self._resolve_voice_name(voice)
        self._orch.preview(text, voice_name, self._on_preview_status)

    def _on_preview_status(self, status: SpeakStatus, detail: str):
        if status == SpeakStatus.GENERATING:
            self._preview_btn.configure(state="disabled", text="生成中...")
            self._status_bar.set_status(detail)
        elif status == SpeakStatus.PLAYING:
            self._preview_btn.configure(state="normal", text="预听")
            self._status_bar.set_status(detail, auto_clear=4000)
        elif status == SpeakStatus.ERROR:
            self._preview_btn.configure(state="normal", text="预听")
            self._status_bar.set_status(detail, is_error=True)

    def _on_replay(self, text: str, voice: str):
        # 清除 placeholder
        self._on_textbox_focus_in()
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", text)
        self._orch.speak(text, voice, self._on_status)

    def _on_status(self, status: SpeakStatus, detail: str):
        if status == SpeakStatus.GENERATING:
            self._send_btn.configure(state="disabled", text="生成中...")
            self._status_bar.set_status(detail)
        elif status == SpeakStatus.SENDING:
            self._status_bar.set_status(detail)
        elif status == SpeakStatus.PLAYING:
            self._send_btn.configure(
                state="normal", text=ICONS["send"] + " 发送  Ctrl+Enter"
            )
            self._status_bar.set_status(detail, auto_clear=3000)
            # 发送成功闪烁
            self._flash_send_btn()
            # 添加到历史面板
            if self._orch.history:
                h = self._orch.history[0]
                self._history.add_entry(h.timestamp, h.text, h.voice)
            # 清空输入框
            self._textbox.delete("1.0", "end")
            self._update_char_count()
        elif status == SpeakStatus.ERROR:
            self._send_btn.configure(
                state="normal", text=ICONS["send"] + " 发送  Ctrl+Enter"
            )
            self._status_bar.set_status(detail, is_error=True)

    def _flash_send_btn(self):
        """发送成功时按钮短暂变绿。"""
        self._send_btn.configure(fg_color=COLORS["btn_send_flash"])
        self._root.after(
            600,
            lambda: self._send_btn.configure(fg_color=COLORS["accent"]),
        )

    def _update_char_count(self):
        text = self._get_text()
        max_len = self._orch.config.get("max_text_length", 500)
        count = len(text)
        self._char_label.configure(text=f"{count}/{max_len}")
        if count > max_len:
            self._char_label.configure(text_color=COLORS["error"])
        else:
            self._char_label.configure(text_color=COLORS["text_dim"])

    # ------------------------------------------------------------------
    # 窗口控件
    # ------------------------------------------------------------------

    def _toggle_topmost(self):
        self._topmost = not self._topmost
        self._root.attributes("-topmost", self._topmost)
        if self._topmost:
            self._topmost_btn.configure(
                fg_color=COLORS["accent"], text=ICONS["pin"] + " 取消"
            )
        else:
            self._topmost_btn.configure(
                fg_color=COLORS["bg_secondary"], text=ICONS["pin"] + " 置顶"
            )

    def _minimize_to_tray(self):
        if self._on_minimize_to_tray:
            self._on_minimize_to_tray()

    def _save_output_config(self):
        self._orch.config.set("play_on_mic", self._mic_var.get())
        self._orch.config.set("play_on_speakers", self._speaker_var.get())
        self._orch.config.set("auto_cleanup_soundpad", self._cleanup_var.get())

    def _on_rate_pitch_change(self, key: str, value: str):
        self._orch.config.set(key, value)

    # ------------------------------------------------------------------
    # 快捷短语
    # ------------------------------------------------------------------

    def _on_phrase_send(self, phrase: str):
        self._on_textbox_focus_in()
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", phrase)
        self._on_send()

    def _on_phrase_edit(self, action: str, phrase: str):
        phrases = self._orch.config.get("quick_phrases", [])
        if action == "delete":
            if phrase in phrases:
                phrases.remove(phrase)
            self._orch.config.set("quick_phrases", phrases)
        elif action == "add":
            self._show_add_phrase_dialog()

    def _show_add_phrase_dialog(self):
        dialog = ctk.CTkInputDialog(
            text="输入快捷短语:", title="添加短语",
        )
        new_phrase = dialog.get_input()
        if new_phrase and new_phrase.strip():
            new_phrase = new_phrase.strip()
            phrases = self._orch.config.get("quick_phrases", [])
            if new_phrase not in phrases:
                phrases.append(new_phrase)
                self._orch.config.set("quick_phrases", phrases)
                self._phrase_panel.load_phrases(phrases)

    # ------------------------------------------------------------------
    # 语音列表
    # ------------------------------------------------------------------

    def _load_voices(self):
        def on_loaded(voices: list[dict]):
            self._voices = voices
            display_names = [f"{v['friendly_name']} ({v['name']})" for v in voices]
            self._voice_combo.configure(values=display_names)
            saved = self._orch.config.get("voice", "zh-CN-XiaoxiaoNeural")
            for i, v in enumerate(voices):
                if v["name"] == saved:
                    self._voice_var.set(display_names[i])
                    break
            else:
                if display_names:
                    self._voice_var.set(display_names[0])

        self._orch.get_voices(on_loaded)

    def _resolve_voice_name(self, display: str) -> str:
        for v in self._voices:
            if v["name"] in display:
                name = v["name"]
                self._orch.config.set("voice", name)
                return name
        return display

    # ------------------------------------------------------------------
    # Soundpad 连接状态轮询（自适应间隔）
    # ------------------------------------------------------------------

    def _poll_soundpad(self):
        try:
            connected = self._orch.check_soundpad()
            self._status_bar.set_connected(connected)
            if connected:
                # 已连接：低频轮询
                self._poll_interval = 8000
                # 只在之前断开时清除提示
            else:
                # 未连接：较快重试
                self._poll_interval = 3000
                self._status_bar.set_status(
                    "请启动 Soundpad 并开启 Remote Control", is_error=True
                )
        except Exception:
            self._status_bar.set_connected(False)
            self._poll_interval = 3000
        self._root.after(self._poll_interval, self._poll_soundpad)

    # ------------------------------------------------------------------
    # 悬浮输入窗口
    # ------------------------------------------------------------------

    def _toggle_floating(self):
        """切换悬浮输入窗口的显示/隐藏。"""
        from gui.floating_input import FloatingInputWindow

        # 窗口不存在或已被销毁 -> 新建
        if self._floating_win is None or not self._floating_win.winfo_exists():
            saved_pos = self._orch.config.get("floating_geometry", "")
            self._floating_win = FloatingInputWindow(
                self._root,
                on_send=self._on_floating_send,
                on_close=self._on_floating_close,
                initial_pos=saved_pos,
            )
            self._floating_btn.configure(
                fg_color=COLORS["accent"],
                text=ICONS["floating"] + " 收起",
            )
            return

        # 当前可见 -> 隐藏
        if self._floating_win.winfo_viewable():
            self._floating_win.withdraw()
            self._floating_btn.configure(
                fg_color=COLORS["bg_secondary"],
                text=ICONS["floating"] + " 悬浮",
            )
        else:
            # 当前隐藏 -> 显示
            self._floating_win.deiconify()
            self._floating_win.focus_entry()
            self._floating_btn.configure(
                fg_color=COLORS["accent"],
                text=ICONS["floating"] + " 收起",
            )

    def _on_floating_send(self, text: str):
        """悬浮窗发送回调：使用主窗口的语音设置。"""
        if not text:
            return
        voice = self._voice_var.get()
        voice_name = self._resolve_voice_name(voice)
        if self._floating_win and self._floating_win.winfo_exists():
            self._floating_win.set_busy(True)
        self._orch.speak(text, voice_name, self._on_floating_status)

    def _on_floating_status(self, status: SpeakStatus, detail: str):
        """悬浮窗发送的状态回调（轻量版）。"""
        if status == SpeakStatus.GENERATING:
            self._status_bar.set_status(detail)
        elif status == SpeakStatus.SENDING:
            self._status_bar.set_status(detail)
        elif status == SpeakStatus.PLAYING:
            self._status_bar.set_status(detail, auto_clear=3000)
            if self._floating_win and self._floating_win.winfo_exists():
                self._floating_win.set_busy(False)
                self._floating_win.clear_entry()
            # 同步更新主窗口历史
            if self._orch.history:
                h = self._orch.history[0]
                self._history.add_entry(h.timestamp, h.text, h.voice)
        elif status == SpeakStatus.ERROR:
            self._status_bar.set_status(detail, is_error=True)
            if self._floating_win and self._floating_win.winfo_exists():
                self._floating_win.set_busy(False)

    def _on_floating_close(self):
        """悬浮窗关闭按钮回调。"""
        if self._floating_win and self._floating_win.winfo_exists():
            self._floating_win.withdraw()
        self._floating_btn.configure(
            fg_color=COLORS["bg_secondary"],
            text=ICONS["floating"] + " 悬浮",
        )

    # ------------------------------------------------------------------
    # 关闭清理
    # ------------------------------------------------------------------

    def save_state(self):
        geo = self._root.geometry()
        self._orch.config.set("window_geometry", geo)
        # 保存悬浮窗位置
        if self._floating_win and self._floating_win.winfo_exists():
            self._orch.config.set(
                "floating_geometry", self._floating_win.get_position()
            )
            self._floating_win.destroy()
        self._orch.config.save()
