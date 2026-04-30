import customtkinter as ctk

from app.orchestrator import Orchestrator, SpeakStatus
from gui.theme import COLORS, FONTS, ICONS, WINDOW
from gui.widgets import HistoryPanel, QuickPhrasePanel, RatePitchControl, StatusBar


def _card(master, **kwargs) -> ctk.CTkFrame:
    """创建统一的卡片容器。"""
    defaults = dict(
        fg_color=COLORS["bg_card"],
        corner_radius=12,
        border_width=1,
        border_color=COLORS["border_light"],
    )
    defaults.update(kwargs)
    return ctk.CTkFrame(master, **defaults)


class MainWindow:
    def __init__(self, root: ctk.CTk, orchestrator: Orchestrator):
        self._root = root
        self._orch = orchestrator
        self._voices: list[dict] = []
        self._floating_win = None
        self._poll_interval = 5000

        self._voice_var = ctk.StringVar()
        self._engine_var = ctk.StringVar(value=self._orch.config.get("engine", "edge"))
        self._engine_var.trace_add("write", lambda *_: self._on_engine_change())

        self._setup_window()
        self._build_ui()
        self._load_voices()
        self._poll_soundpad()

    # ------------------------------------------------------------------
    # 窗口初始化
    # ------------------------------------------------------------------

    def _setup_window(self):
        self._root.title(WINDOW["title"])
        self._root.configure(fg_color=COLORS["bg_dark"])
        geo = self._orch.config.get("window_geometry", WINDOW["default_geometry"])
        self._root.geometry(geo)
        self._root.minsize(WINDOW["min_width"], WINDOW["min_height"])
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_header_card()
        self._build_input_card()
        self._build_phrases_card()
        self._build_history_card()
        self._build_status_bar()
        self._update_engine_ui()

    def _build_header_card(self):
        """设置卡片：引擎选择、语音选择、语速音调、输出。"""
        card = _card(self._root)
        card.pack(fill="x", padx=10, pady=(10, 4))

        # --- 引擎选择行 ---
        engine_row = ctk.CTkFrame(card, fg_color="transparent")
        engine_row.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            engine_row, text="引擎:", font=FONTS["body"],
            text_color=COLORS["text_secondary"], width=40,
        ).pack(side="left")

        self._engine_selector = ctk.CTkSegmentedButton(
            engine_row,
            values=["Edge TTS", "MiniMax"],
            variable=self._engine_var,
            font=FONTS["body"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_engine_switch,
        )
        self._engine_selector.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # --- 语音选择行 ---
        voice_row = ctk.CTkFrame(card, fg_color="transparent")
        voice_row.pack(fill="x", padx=12, pady=(4, 0))

        ctk.CTkLabel(
            voice_row, text="语音:", font=FONTS["body"],
            text_color=COLORS["text_secondary"], width=40,
        ).pack(side="left")

        self._voice_combo = ctk.CTkComboBox(
            voice_row, variable=self._voice_var, state="readonly",
            values=["加载中..."], font=FONTS["body"],
            dropdown_font=FONTS["body"], width=240,
        )
        self._voice_combo.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # --- Edge TTS 控制区 ---
        self._edge_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._edge_frame.pack(fill="x", padx=12, pady=(4, 0))

        self._rate_pitch = RatePitchControl(
            self._edge_frame, on_change=self._on_rate_pitch_change,
        )
        self._rate_pitch.pack(fill="x")
        self._rate_pitch.set_rate(self._orch.config.get("rate", "+0%"))
        self._rate_pitch.set_pitch(self._orch.config.get("pitch", "+0Hz"))

        # --- MiniMax 控制区 ---
        self._minimax_frame = ctk.CTkFrame(card, fg_color="transparent")

        # API Key
        api_row = ctk.CTkFrame(self._minimax_frame, fg_color="transparent")
        api_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(
            api_row, text="API Key:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=55,
        ).pack(side="left")
        self._minimax_api_entry = ctk.CTkEntry(
            api_row, font=FONTS["small"],
            placeholder_text="输入 MiniMax API Key",
            show="*", height=28,
        )
        self._minimax_api_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._minimax_verify_btn = ctk.CTkButton(
            api_row, text="验证", font=FONTS["small"],
            width=50, height=28,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._on_verify_minimax_key,
        )
        self._minimax_verify_btn.pack(side="left", padx=(4, 0))
        saved_key = self._orch.config.get("minimax_api_key", "")
        if saved_key:
            self._minimax_api_entry.insert(0, saved_key)
        self._minimax_api_entry.bind("<FocusOut>", lambda e: self._save_minimax_config())

        # Speed
        speed_row = ctk.CTkFrame(self._minimax_frame, fg_color="transparent")
        speed_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            speed_row, text="语速:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=55,
        ).pack(side="left")
        self._mm_speed_label = ctk.CTkLabel(
            speed_row, text=f'{self._orch.config.get("minimax_speed", 1.0):.1f}',
            font=FONTS["small"], text_color=COLORS["accent"], width=35,
        )
        self._mm_speed_label.pack(side="right", padx=(4, 0))
        self._mm_speed_slider = ctk.CTkSlider(
            speed_row, from_=0.5, to=2.0, number_of_steps=15,
            width=200, height=16,
            fg_color=COLORS["accent_dim"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._on_mm_speed_change,
        )
        self._mm_speed_slider.set(self._orch.config.get("minimax_speed", 1.0))
        self._mm_speed_slider.pack(side="left", fill="x", expand=True, padx=(4, 4))

        # Volume
        vol_row = ctk.CTkFrame(self._minimax_frame, fg_color="transparent")
        vol_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            vol_row, text="音量:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=55,
        ).pack(side="left")
        self._mm_vol_label = ctk.CTkLabel(
            vol_row, text=f'{self._orch.config.get("minimax_vol", 1.0):.1f}',
            font=FONTS["small"], text_color=COLORS["accent"], width=35,
        )
        self._mm_vol_label.pack(side="right", padx=(4, 0))
        self._mm_vol_slider = ctk.CTkSlider(
            vol_row, from_=0, to=10, number_of_steps=20,
            width=200, height=16,
            fg_color=COLORS["accent_dim"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._on_mm_vol_change,
        )
        self._mm_vol_slider.set(self._orch.config.get("minimax_vol", 1.0))
        self._mm_vol_slider.pack(side="left", fill="x", expand=True, padx=(4, 4))

        # Pitch
        pitch_row = ctk.CTkFrame(self._minimax_frame, fg_color="transparent")
        pitch_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            pitch_row, text="音调:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=55,
        ).pack(side="left")
        self._mm_pitch_label = ctk.CTkLabel(
            pitch_row, text=f'{self._orch.config.get("minimax_pitch", 0):+d}',
            font=FONTS["small"], text_color=COLORS["accent"], width=35,
        )
        self._mm_pitch_label.pack(side="right", padx=(4, 0))
        self._mm_pitch_slider = ctk.CTkSlider(
            pitch_row, from_=-12, to=12, number_of_steps=24,
            width=200, height=16,
            fg_color=COLORS["accent_dim"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._on_mm_pitch_change,
        )
        self._mm_pitch_slider.set(self._orch.config.get("minimax_pitch", 0))
        self._mm_pitch_slider.pack(side="left", fill="x", expand=True, padx=(4, 4))

        # --- 输出选项行 ---
        output_row = ctk.CTkFrame(card, fg_color="transparent")
        output_row.pack(fill="x", padx=12, pady=(2, 10))

        ctk.CTkLabel(
            output_row, text="输出:", font=FONTS["body"],
            text_color=COLORS["text_secondary"], width=40,
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

    # ------------------------------------------------------------------
    # 引擎切换
    # ------------------------------------------------------------------

    def _on_engine_switch(self, choice: str):
        engine_key = "minimax" if choice == "MiniMax" else "edge"
        self._orch.config.set("engine", engine_key)
        self._update_engine_ui()
        self._load_voices()

    def _on_engine_change(self):
        """engine_var trace 回调，保持引擎切换时 UI 同步。"""
        # 按键切换由 _on_engine_switch 处理，此处仅用于变量同步
        pass

    def _update_engine_ui(self):
        """切换 Edge / MiniMax 控制面板可见性。"""
        is_minimax = self._engine_var.get() == "MiniMax"
        if is_minimax:
            self._edge_frame.pack_forget()
            self._minimax_frame.pack(fill="x", padx=12, pady=(4, 0))
        else:
            self._minimax_frame.pack_forget()
            self._edge_frame.pack(fill="x", padx=12, pady=(4, 0))

    # ------------------------------------------------------------------
    # MiniMax 控件回调
    # ------------------------------------------------------------------

    def _on_mm_speed_change(self, value):
        v = round(value, 1)
        self._mm_speed_label.configure(text=f"{v:.1f}")
        self._orch.config.set("minimax_speed", v)

    def _on_mm_vol_change(self, value):
        v = round(value, 1)
        self._mm_vol_label.configure(text=f"{v:.1f}")
        self._orch.config.set("minimax_vol", v)

    def _on_mm_pitch_change(self, value):
        v = int(round(value))
        self._mm_pitch_label.configure(text=f"{v:+d}")
        self._orch.config.set("minimax_pitch", v)

    def _save_minimax_config(self):
        api_key = self._minimax_api_entry.get().strip()
        self._orch.config.set("minimax_api_key", api_key)

    def _on_verify_minimax_key(self):
        """验证 MiniMax API Key。"""
        self._save_minimax_config()
        self._minimax_verify_btn.configure(state="disabled", text="验证中...")
        self._orch.verify_minimax_key(self._on_minimax_key_verified)

    def _on_minimax_key_verified(self, success: bool, message: str):
        self._minimax_verify_btn.configure(state="normal", text="验证")
        if success:
            self._status_bar.set_status(message, auto_clear=5000)
        else:
            self._status_bar.set_status(message, is_error=True)

    # ------------------------------------------------------------------
    # Edge TTS 控件回调
    # ------------------------------------------------------------------

    def _on_rate_pitch_change(self, key: str, value: str):
        self._orch.config.set(key, value)

    # ------------------------------------------------------------------
    # 输入区
    # ------------------------------------------------------------------

    def _build_input_card(self):
        """输入卡片：文本框 + 按钮行。"""
        card = _card(self._root)
        card.pack(fill="both", expand=True, padx=10, pady=4)

        self._textbox = ctk.CTkTextbox(
            card, font=FONTS["body"], height=60,
            corner_radius=8, border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["bg_primary"],
        )
        self._textbox.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        self._textbox.bind("<Control-Return>", lambda e: self._on_send())
        self._textbox.bind("<KeyRelease>", lambda e: self._update_char_count())

        # placeholder
        self._placeholder_active = True
        self._placeholder_text = "在此输入要转为语音的文字..."
        self._textbox.insert("1.0", self._placeholder_text)
        self._textbox.configure(text_color=COLORS["text_dim"])
        self._textbox.bind("<FocusIn>", self._on_textbox_focus_in)
        self._textbox.bind("<FocusOut>", self._on_textbox_focus_out)

        # 按钮行
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(8, 12))

        self._send_btn = ctk.CTkButton(
            btn_row, text=ICONS["send"] + " 发送  Ctrl+Enter",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=40, corner_radius=10, command=self._on_send,
        )
        self._send_btn.pack(side="left", fill="x", expand=True)

        self._stop_btn = ctk.CTkButton(
            btn_row, text="停止", font=FONTS["body"], width=70,
            fg_color="transparent", hover_color=COLORS["bg_card"],
            border_width=1, border_color=COLORS["error"],
            text_color=COLORS["error"],
            height=40, corner_radius=10, command=self._on_stop,
        )
        self._stop_btn.pack(side="left", padx=(8, 0))

        self._preview_btn = ctk.CTkButton(
            btn_row, text="预听", font=FONTS["body"], width=70,
            fg_color="transparent", hover_color=COLORS["bg_card"],
            border_width=1, border_color=COLORS["accent"],
            text_color=COLORS["accent"],
            height=40, corner_radius=10, command=self._on_preview,
        )
        self._preview_btn.pack(side="left", padx=(8, 0))

        self._floating_btn = ctk.CTkButton(
            btn_row, text="悬浮", font=FONTS["body"], width=70,
            fg_color="transparent", hover_color=COLORS["bg_card"],
            border_width=1, border_color=COLORS["accent"],
            text_color=COLORS["accent"],
            height=40, corner_radius=10, command=self._toggle_floating,
        )
        self._floating_btn.pack(side="left", padx=(8, 0))

        max_len = self._orch.config.get("max_text_length", 500)
        self._char_label = ctk.CTkLabel(
            btn_row, text=f"0/{max_len}", font=FONTS["small"],
            text_color=COLORS["text_dim"], width=60,
        )
        self._char_label.pack(side="right", padx=(8, 0))

    # ------------------------------------------------------------------
    # 底层卡片
    # ------------------------------------------------------------------

    def _build_phrases_card(self):
        """快捷短语卡片（标题已集成在 QuickPhrasePanel 内部）。"""
        self._phrase_panel = QuickPhrasePanel(
            self._root, on_send=self._on_phrase_send,
            on_edit=self._on_phrase_edit,
            corner_radius=12,
            fg_color=COLORS["bg_card"],
            border_width=1, border_color=COLORS["border_light"],
        )
        self._phrase_panel.pack(fill="x", padx=10, pady=4)
        self._phrase_panel.load_phrases(
            self._orch.config.get("quick_phrases", [])
        )

    def _build_history_card(self):
        """历史记录卡片（标题已集成在 HistoryPanel 内部）。"""
        self._history = HistoryPanel(
            self._root, on_replay=self._on_replay,
            show_title=True,
            height=27, corner_radius=12,
            fg_color=COLORS["bg_card"],
            border_width=1, border_color=COLORS["border_light"],
        )
        self._history.pack(fill="x", padx=10, pady=(4, 8))

    def _build_status_bar(self):
        self._status_bar = StatusBar(
            self._root, fg_color=COLORS["bg_secondary"], corner_radius=0,
        )
        self._status_bar.pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    # Placeholder
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
        text = self._textbox.get("1.0", "end").strip()
        if not text or text == self._placeholder_text:
            return ""
        return text

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
        self._placeholder_active = False
        self._textbox.configure(text_color=COLORS["text_primary"])
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
            self._flash_send_btn()
            h = self._orch.get_latest_history()
            if h:
                self._history.add_entry(h.timestamp, h.text, h.voice)
            self._textbox.delete("1.0", "end")
            self._update_char_count()
            self._placeholder_active = True
            self._textbox.insert("1.0", self._placeholder_text)
            self._textbox.configure(text_color=COLORS["text_dim"])
            self._send_btn.focus_set()
        elif status == SpeakStatus.ERROR:
            self._send_btn.configure(
                state="normal", text=ICONS["send"] + " 发送  Ctrl+Enter"
            )
            self._status_bar.set_status(detail, is_error=True)

    def _flash_send_btn(self):
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

    def _save_output_config(self):
        self._orch.config.set("play_on_mic", self._mic_var.get())
        self._orch.config.set("play_on_speakers", self._speaker_var.get())

    # ------------------------------------------------------------------
    # 快捷短语
    # ------------------------------------------------------------------

    def _on_phrase_send(self, phrase: str):
        self._placeholder_active = False
        self._textbox.configure(text_color=COLORS["text_primary"])
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", phrase)
        voice = self._voice_var.get()
        voice_name = self._resolve_voice_name(voice)
        self._orch.speak(phrase, voice_name, self._on_status)

    def _on_phrase_edit(self, action: str, phrase: str):
        phrases = self._orch.config.get("quick_phrases", [])
        if action == "delete":
            if phrase in phrases:
                phrases.remove(phrase)
            self._orch.config.set("quick_phrases", phrases)
            self._phrase_panel.load_phrases(phrases)
        elif action == "add":
            self._show_add_phrase_dialog()

    def _show_add_phrase_dialog(self):
        phrases = self._orch.config.get("quick_phrases", [])
        if len(phrases) >= QuickPhrasePanel.MAX_PHRASES:
            return
        dialog = ctk.CTkInputDialog(
            text="输入快捷短语:", title="添加短语",
        )
        new_phrase = dialog.get_input()
        if new_phrase and new_phrase.strip():
            new_phrase = new_phrase.strip()
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
            display_names = [v["friendly_name"] for v in voices]
            self._voice_combo.configure(values=display_names)

            # 根据当前引擎选择合适的默认语音
            engine = self._orch.config.get("engine")
            saved_key = "minimax_voice_id" if engine == "minimax" else "voice"
            saved = self._orch.config.get(saved_key, "")
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
            if v["friendly_name"] == display:
                name = v["name"]
                # 保存到对应引擎的配置
                engine = self._orch.config.get("engine")
                key = "minimax_voice_id" if engine == "minimax" else "voice"
                self._orch.config.set(key, name)
                return name
        return display

    # ------------------------------------------------------------------
    # Soundpad 轮询
    # ------------------------------------------------------------------

    def _poll_soundpad(self):
        if self._orch.is_busy:
            self._root.after(1000, self._poll_soundpad)
            return
        try:
            connected = self._orch.check_soundpad()
            self._status_bar.set_connected(connected)
            if connected:
                self._poll_interval = 8000
            else:
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
        from gui.floating_input import FloatingInputWindow

        if self._floating_win is None or not self._floating_win.winfo_exists():
            saved_pos = self._orch.config.get("floating_geometry", "")
            self._floating_win = FloatingInputWindow(
                self._root,
                on_send=self._on_floating_send,
                on_close=self._on_floating_close,
                initial_pos=saved_pos,
            )
            self._floating_btn.configure(text="收起")
            return

        if self._floating_win.winfo_viewable():
            self._floating_win.withdraw()
            self._floating_btn.configure(text="悬浮")
        else:
            self._floating_win.deiconify()
            self._floating_win.lift()
            self._floating_win.focus_entry()
            self._floating_btn.configure(text="收起")

    def _on_floating_send(self, text: str):
        if not text:
            return
        voice = self._voice_var.get()
        voice_name = self._resolve_voice_name(voice)
        if self._floating_win and self._floating_win.winfo_exists():
            self._floating_win.set_busy(True)
        self._orch.speak(text, voice_name, self._on_floating_status)

    def _on_floating_status(self, status: SpeakStatus, detail: str):
        if status in (SpeakStatus.GENERATING, SpeakStatus.SENDING):
            self._status_bar.set_status(detail)
        elif status == SpeakStatus.PLAYING:
            self._status_bar.set_status(detail, auto_clear=3000)
            if self._floating_win and self._floating_win.winfo_exists():
                self._floating_win.set_busy(False)
                self._floating_win.clear_entry()
            h = self._orch.get_latest_history()
            if h:
                self._history.add_entry(h.timestamp, h.text, h.voice)
        elif status == SpeakStatus.ERROR:
            self._status_bar.set_status(detail, is_error=True)
            if self._floating_win and self._floating_win.winfo_exists():
                self._floating_win.set_busy(False)
                self._floating_win.flash_error()

    def _on_floating_close(self):
        if self._floating_win and self._floating_win.winfo_exists():
            self._floating_win.withdraw()
        self._floating_btn.configure(text="悬浮")

    # ------------------------------------------------------------------
    # 关闭清理
    # ------------------------------------------------------------------

    def save_state(self):
        geo = self._root.geometry()
        self._orch.config.set("window_geometry", geo)
        if self._floating_win and self._floating_win.winfo_exists():
            self._orch.config.set(
                "floating_geometry", self._floating_win.get_position()
            )
            self._floating_win.destroy()
        self._orch.config.save()
