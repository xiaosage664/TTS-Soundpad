import os
import customtkinter as ctk

from app.orchestrator import Orchestrator, SpeakStatus
from gui.theme import COLORS, FONTS, ICONS, WINDOW
from gui.widgets import HistoryPanel, QuickPhrasePanel, RatePitchControl, StatusBar


def _card(master, **kwargs) -> ctk.CTkFrame:
    defaults = dict(
        fg_color=COLORS["bg_card"],
        corner_radius=12,
        border_width=1,
        border_color=COLORS["border_light"],
    )
    defaults.update(kwargs)
    return ctk.CTkFrame(master, **defaults)


ENGINE_LABELS: dict[str, str] = {
    "edge": "Edge TTS",
    "minimax": "MiniMax",
    "piper": "Piper",
    "gpt-sovits": "GPT-SoVITS",
}

ENGINE_KEY_FROM_LABEL = {v: k for k, v in ENGINE_LABELS.items()}

PIPER_VOICE_NAMES: dict[str, str] = {
    "yanran": "嫣然 (女声·甜美)",
    "tingting_xin": "婷婷-欣 (女声·温柔)",
    "xiaobei_local": "晓北-本地 (女声·东北话)",
    "kefu_gui": "客服-贵 (女声)",
    "yixuan_cn": "逸轩 (男声·沉稳)",
}

PIPER_NAME_FROM_DESC = {v: k for k, v in PIPER_VOICE_NAMES.items()}

LANG_NAMES: dict[str, str] = {
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "yue": "粤语",
}

LANG_CODE_FROM_NAME = {v: k for k, v in LANG_NAMES.items()}


class MainWindow:
    def __init__(
        self,
        root: ctk.CTk,
        orchestrator: Orchestrator,
        available_engines: list[str] | None = None,
    ):
        self._root = root
        self._orch = orchestrator
        self._voices: list[dict] = []
        self._floating_win = None
        self._poll_interval = 5000

        self._available_engines = available_engines or ["edge", "minimax"]
        current_engine = self._orch.config.get("engine", "edge")
        if current_engine not in self._available_engines:
            current_engine = self._available_engines[0]
            self._orch.config.set("engine", current_engine)

        self._voice_var = ctk.StringVar()
        self._engine_var = ctk.StringVar(value=ENGINE_LABELS.get(current_engine, "Edge TTS"))

        self._setup_window()
        self._build_ui()
        self._load_voices()
        self._poll_soundpad()

    def _setup_window(self):
        self._root.title(WINDOW["title"])
        self._root.configure(fg_color=COLORS["bg_dark"])
        geo = self._orch.config.get("window_geometry", WINDOW["default_geometry"])
        self._root.geometry(geo)
        self._root.minsize(WINDOW["min_width"], WINDOW["min_height"])
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

    def _build_ui(self):
        self._build_header_card()
        self._build_input_card()
        self._build_phrases_card()
        self._build_history_card()
        self._build_status_bar()

    def _build_header_card(self):
        card = _card(self._root)
        card.pack(fill="x", padx=10, pady=(10, 4))

        engine_row = ctk.CTkFrame(card, fg_color="transparent")
        engine_row.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            engine_row, text="引擎:", font=FONTS["body"],
            text_color=COLORS["text_secondary"], width=40,
        ).pack(side="left")

        engine_values = [ENGINE_LABELS[e] for e in self._available_engines]
        self._engine_selector = ctk.CTkSegmentedButton(
            engine_row,
            values=engine_values,
            variable=self._engine_var,
            font=FONTS["body"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_engine_switch,
        )
        self._engine_selector.pack(side="left", fill="x", expand=True, padx=(8, 0))

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

        self._edge_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._edge_frame.pack(fill="x", padx=12, pady=(4, 0))
        self._edge_frame_visible = True

        self._rate_pitch = RatePitchControl(
            self._edge_frame, on_change=self._on_rate_pitch_change,
        )
        self._rate_pitch.pack(fill="x")
        self._rate_pitch.set_rate(self._orch.config.get("rate", "+0%"))
        self._rate_pitch.set_pitch(self._orch.config.get("pitch", "+0Hz"))

        self._minimax_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._minimax_frame_visible = False
        self._build_minimax_panel()

        self._piper_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._piper_frame_visible = False
        self._build_piper_panel()

        self._gpt_sovits_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._gpt_sovits_frame_visible = False
        self._build_gpt_sovits_panel()

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

    def _build_minimax_panel(self):
        parent = self._minimax_frame

        api_row = ctk.CTkFrame(parent, fg_color="transparent")
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

        self._mm_speed_label = self._add_slider_row(parent, "语速:", 0.5, 2.0, 15,
            self._on_mm_speed_change, "minimax_speed", 1.0, fmt_key="mm_speed_slider")
        self._mm_vol_label = self._add_slider_row(parent, "音量:", 0, 10, 20,
            self._on_mm_vol_change, "minimax_vol", 1.0, fmt_key="mm_vol_slider")
        self._mm_pitch_label = self._add_slider_row(parent, "音调:", -12, 12, 24,
            self._on_mm_pitch_change, "minimax_pitch", 0, is_int=True, fmt_key="mm_pitch_slider")

    def _add_slider_row(self, parent, label_text, from_v, to_v, steps, command,
                        config_key, default_v, is_int=False, fmt_key=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            row, text=label_text, font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=55,
        ).pack(side="left")
        val = self._orch.config.get(config_key, default_v)
        if is_int:
            display = f"{int(val):+d}"
        else:
            display = f"{val:.1f}"
        value_label = ctk.CTkLabel(
            row, text=display, font=FONTS["small"],
            text_color=COLORS["accent"], width=38,
        )
        value_label.pack(side="right", padx=(4, 0))
        slider = ctk.CTkSlider(
            row, from_=from_v, to=to_v, number_of_steps=steps,
            width=200, height=16,
            fg_color=COLORS["accent_dim"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=command,
        )
        slider.set(val)
        slider.pack(side="left", fill="x", expand=True, padx=(4, 4))
        if fmt_key:
            setattr(self, fmt_key, slider)
        return value_label

    def _build_piper_panel(self):
        parent = self._piper_frame

        voice_row = ctk.CTkFrame(parent, fg_color="transparent")
        voice_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(
            voice_row, text="语音:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=55,
        ).pack(side="left")
        piper_names = list(PIPER_VOICE_NAMES.values())
        default_piper = PIPER_VOICE_NAMES.get(
            self._orch.config.get("piper_voice", "yanran"), piper_names[0])
        self._piper_voice_var = ctk.StringVar(value=default_piper)
        self._piper_voice_combo = ctk.CTkComboBox(
            voice_row, variable=self._piper_voice_var, state="readonly",
            values=piper_names, font=FONTS["small"],
            dropdown_font=FONTS["small"], width=160,
            command=self._on_piper_voice_change,
        )
        self._piper_voice_combo.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            voice_row, text="音质:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=40,
        ).pack(side="left", padx=(8, 0))
        self._piper_quality_var = ctk.StringVar(
            value=self._orch.config.get("piper_quality", "high"))
        self._piper_quality_combo = ctk.CTkComboBox(
            voice_row, variable=self._piper_quality_var, state="readonly",
            values=["high", "medium", "low"], font=FONTS["small"],
            dropdown_font=FONTS["small"], width=80,
            command=self._on_piper_quality_change,
        )
        self._piper_quality_combo.pack(side="left", padx=(4, 0))

        self._piper_speed_label = self._add_slider_row(
            parent, "语速:", 0.5, 2.0, 30, self._on_piper_speed_change,
            "piper_length_scale", 1.0, fmt_key="_piper_speed_slider")
        self._piper_noise_label = self._add_slider_row(
            parent, "表现力:", 0.0, 1.0, 100, self._on_piper_noise_change,
            "piper_noise_scale", 0.667, fmt_key="_piper_noise_slider")

    def _build_gpt_sovits_panel(self):
        parent = self._gpt_sovits_frame

        ref_row = ctk.CTkFrame(parent, fg_color="transparent")
        ref_row.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(
            ref_row, text="参考音频:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=60,
        ).pack(side="left")
        self._ref_audio_entry = ctk.CTkEntry(
            ref_row, font=FONTS["small"], height=28,
            placeholder_text="选择 3~10 秒参考音频...")
        saved_ref = self._orch.config.get("gpt_sovits_ref_audio", "")
        if saved_ref:
            self._ref_audio_entry.insert(0, saved_ref)
        self._ref_audio_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._ref_audio_btn = ctk.CTkButton(
            ref_row, text="选择", font=FONTS["small"],
            width=50, height=28,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._on_select_ref_audio,
        )
        self._ref_audio_btn.pack(side="left", padx=(4, 0))

        prompt_row = ctk.CTkFrame(parent, fg_color="transparent")
        prompt_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            prompt_row, text="参考文本:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=60,
        ).pack(side="left")
        self._prompt_text_entry = ctk.CTkEntry(
            prompt_row, font=FONTS["small"], height=28,
            placeholder_text="参考音频说的内容（可选，强烈建议填写）")
        saved_prompt = self._orch.config.get("gpt_sovits_prompt_text", "")
        if saved_prompt:
            self._prompt_text_entry.insert(0, saved_prompt)
        self._prompt_text_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._prompt_text_entry.bind("<FocusOut>", lambda e: self._save_gpt_sovits_config())

        lang_row = ctk.CTkFrame(parent, fg_color="transparent")
        lang_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            lang_row, text="语言:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=60,
        ).pack(side="left")
        lang_names = list(LANG_NAMES.values())

        default_tl = self._orch.config.get("gpt_sovits_text_lang", "zh")
        self._text_lang_var = ctk.StringVar(value=LANG_NAMES.get(default_tl, "中文"))
        ctk.CTkLabel(
            lang_row, text="文本:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=35,
        ).pack(side="left")
        self._text_lang_combo = ctk.CTkComboBox(
            lang_row, variable=self._text_lang_var, state="readonly",
            values=lang_names, font=FONTS["small"],
            dropdown_font=FONTS["small"], width=70,
            command=self._on_text_lang_change,
        )
        self._text_lang_combo.pack(side="left", padx=(2, 8))

        default_pl = self._orch.config.get("gpt_sovits_prompt_lang", "zh")
        self._prompt_lang_var = ctk.StringVar(value=LANG_NAMES.get(default_pl, "中文"))
        ctk.CTkLabel(
            lang_row, text="参考:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=35,
        ).pack(side="left")
        self._prompt_lang_combo = ctk.CTkComboBox(
            lang_row, variable=self._prompt_lang_var, state="readonly",
            values=lang_names, font=FONTS["small"],
            dropdown_font=FONTS["small"], width=70,
            command=self._on_prompt_lang_change,
        )
        self._prompt_lang_combo.pack(side="left", padx=(2, 0))

        model_row = ctk.CTkFrame(parent, fg_color="transparent")
        model_row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            model_row, text="模型:", font=FONTS["small"],
            text_color=COLORS["text_secondary"], width=60,
        ).pack(side="left")
        self._gpt_model_status = ctk.CTkLabel(
            model_row, text="未加载", font=FONTS["small"],
            text_color=COLORS["warning"],
        )
        self._gpt_model_status.pack(side="left", padx=(4, 0))
        self._gpt_load_btn = ctk.CTkButton(
            model_row, text="加载模型", font=FONTS["small"],
            width=80, height=28,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._on_load_gpt_sovits_model,
        )
        self._gpt_load_btn.pack(side="right", padx=(8, 0))

        self._gpt_temp_label = self._add_slider_row(
            parent, "温度:", 0.1, 1.5, 28, self._on_gpt_temp_change,
            "gpt_sovits_temperature", 0.8, fmt_key="_gpt_temp_slider")
        self._gpt_topk_label = self._add_slider_row(
            parent, "Top-K:", 1, 50, 49, self._on_gpt_topk_change,
            "gpt_sovits_top_k", 15, is_int=True, fmt_key="_gpt_topk_slider")
        self._gpt_topp_label = self._add_slider_row(
            parent, "Top-P:", 0.1, 1.0, 18, self._on_gpt_topp_change,
            "gpt_sovits_top_p", 0.8, fmt_key="_gpt_topp_slider")

    def _on_engine_switch(self, choice: str):
        engine_key = ENGINE_KEY_FROM_LABEL.get(choice, "edge")
        self._orch.config.set("engine", engine_key)
        self._update_engine_ui()
        self._load_voices()

    def _update_engine_ui(self):
        engine = self._orch.config.get("engine", "edge")
        panels = [
            (self._edge_frame, "_edge_frame_visible"),
            (self._minimax_frame, "_minimax_frame_visible"),
            (self._piper_frame, "_piper_frame_visible"),
            (self._gpt_sovits_frame, "_gpt_sovits_frame_visible"),
        ]
        for frame, attr in panels:
            if getattr(self, attr, False):
                frame.pack_forget()
                setattr(self, attr, False)

        map_engine = {
            "edge": (self._edge_frame, "_edge_frame_visible"),
            "minimax": (self._minimax_frame, "_minimax_frame_visible"),
            "piper": (self._piper_frame, "_piper_frame_visible"),
            "gpt-sovits": (self._gpt_sovits_frame, "_gpt_sovits_frame_visible"),
        }
        if engine in map_engine:
            frame, attr = map_engine[engine]
            frame.pack(fill="x", padx=12, pady=(4, 0))
            setattr(self, attr, True)

    def _on_rate_pitch_change(self, key: str, value: str):
        self._orch.config.set(key, value)

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
        self._orch.config.set("minimax_api_key", self._minimax_api_entry.get().strip())

    def _on_verify_minimax_key(self):
        self._save_minimax_config()
        self._minimax_verify_btn.configure(state="disabled", text="验证中...")
        self._orch.verify_minimax_key(self._on_minimax_key_verified)

    def _on_minimax_key_verified(self, success: bool, message: str):
        self._minimax_verify_btn.configure(state="normal", text="验证")
        if success:
            self._status_bar.set_status(message, auto_clear=5000)
        else:
            self._status_bar.set_status(message, is_error=True)

    def _on_piper_voice_change(self, choice: str):
        name = PIPER_NAME_FROM_DESC.get(choice, "yanran")
        self._orch.config.set("piper_voice", name)

    def _on_piper_quality_change(self, choice: str):
        self._orch.config.set("piper_quality", choice)

    def _on_piper_speed_change(self, value):
        v = round(value, 2)
        self._piper_speed_label.configure(text=f"{v:.1f}")
        self._orch.config.set("piper_length_scale", v)

    def _on_piper_noise_change(self, value):
        v = round(value, 3)
        self._piper_noise_label.configure(text=f"{v:.2f}")
        self._orch.config.set("piper_noise_scale", v)

    def _on_select_ref_audio(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="选择参考音频",
            filetypes=[
                ("音频文件", "*.wav *.mp3 *.flac *.ogg *.m4a"),
                ("WAV 文件", "*.wav"),
                ("MP3 文件", "*.mp3"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self._ref_audio_entry.delete(0, "end")
            self._ref_audio_entry.insert(0, path)
            self._save_gpt_sovits_config()

    def _on_load_gpt_sovits_model(self):
        self._gpt_load_btn.configure(state="disabled", text="加载中...")
        self._gpt_model_status.configure(text="正在加载模型...", text_color=COLORS["warning"])
        self._save_gpt_sovits_config()
        self._orch.init_gpt_sovits_model(self._on_gpt_model_loaded)

    def _on_gpt_model_loaded(self, success: bool, msg: str):
        self._gpt_load_btn.configure(state="normal", text="加载模型")
        if success:
            self._gpt_model_status.configure(text=msg, text_color=COLORS["success"])
        else:
            self._gpt_model_status.configure(text=msg, text_color=COLORS["error"])

    def _on_text_lang_change(self, choice: str):
        code = LANG_CODE_FROM_NAME.get(choice, "zh")
        self._orch.config.set("gpt_sovits_text_lang", code)

    def _on_prompt_lang_change(self, choice: str):
        code = LANG_CODE_FROM_NAME.get(choice, "zh")
        self._orch.config.set("gpt_sovits_prompt_lang", code)

    def _on_gpt_temp_change(self, value):
        v = round(value, 1)
        self._gpt_temp_label.configure(text=f"{v:.1f}")
        self._orch.config.set("gpt_sovits_temperature", v)

    def _on_gpt_topk_change(self, value):
        v = int(round(value))
        self._gpt_topk_label.configure(text=str(v))
        self._orch.config.set("gpt_sovits_top_k", v)

    def _on_gpt_topp_change(self, value):
        v = round(value, 1)
        self._gpt_topp_label.configure(text=f"{v:.1f}")
        self._orch.config.set("gpt_sovits_top_p", v)

    def _save_gpt_sovits_config(self):
        self._orch.config.set("gpt_sovits_ref_audio", self._ref_audio_entry.get().strip())
        self._orch.config.set("gpt_sovits_prompt_text", self._prompt_text_entry.get().strip())

    def _build_input_card(self):
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

        self._placeholder_active = True
        self._placeholder_text = "在此输入要转为语音的文字..."
        self._textbox.insert("1.0", self._placeholder_text)
        self._textbox.configure(text_color=COLORS["text_dim"])
        self._textbox.bind("<FocusIn>", self._on_textbox_focus_in)
        self._textbox.bind("<FocusOut>", self._on_textbox_focus_out)

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

    def _build_phrases_card(self):
        self._phrase_panel = QuickPhrasePanel(
            self._root, on_send=self._on_phrase_send,
            on_edit=self._on_phrase_edit,
            corner_radius=12,
            fg_color=COLORS["bg_card"],
            border_width=1, border_color=COLORS["border_light"],
        )
        self._phrase_panel.pack(fill="x", padx=10, pady=4)
        self._phrase_panel.load_phrases(self._orch.config.get("quick_phrases", []))

    def _build_history_card(self):
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
                state="normal", text=ICONS["send"] + " 发送  Ctrl+Enter")
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
                state="normal", text=ICONS["send"] + " 发送  Ctrl+Enter")
            self._status_bar.set_status(detail, is_error=True)

    def _flash_send_btn(self):
        self._send_btn.configure(fg_color=COLORS["btn_send_flash"])
        self._root.after(600, lambda: self._send_btn.configure(fg_color=COLORS["accent"]))

    def _update_char_count(self):
        text = self._get_text()
        max_len = self._orch.config.get("max_text_length", 500)
        count = len(text)
        self._char_label.configure(text=f"{count}/{max_len}")
        if count > max_len:
            self._char_label.configure(text_color=COLORS["error"])
        else:
            self._char_label.configure(text_color=COLORS["text_dim"])

    def _save_output_config(self):
        self._orch.config.set("play_on_mic", self._mic_var.get())
        self._orch.config.set("play_on_speakers", self._speaker_var.get())

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
        dialog = ctk.CTkInputDialog(text="输入快捷短语:", title="添加短语")
        new_phrase = dialog.get_input()
        if new_phrase and new_phrase.strip():
            new_phrase = new_phrase.strip()
            if new_phrase not in phrases:
                phrases.append(new_phrase)
                self._orch.config.set("quick_phrases", phrases)
                self._phrase_panel.load_phrases(phrases)

    def _load_voices(self):
        def on_loaded(voices: list[dict]):
            self._voices = voices
            display_names = [v["friendly_name"] for v in voices]
            self._voice_combo.configure(values=display_names)
            engine = self._orch.config.get("engine")
            if engine == "minimax":
                saved_key = "minimax_voice_id"
            elif engine == "piper":
                saved_key = "piper_voice"
            elif engine == "gpt-sovits":
                saved_key = None
            else:
                saved_key = "voice"
            if saved_key:
                saved = self._orch.config.get(saved_key, "")
                for i, v in enumerate(voices):
                    if v["name"] == saved:
                        self._voice_var.set(display_names[i])
                        break
                else:
                    if display_names:
                        self._voice_var.set(display_names[0])
            else:
                if display_names:
                    self._voice_var.set(display_names[0])
        self._orch.get_voices(on_loaded)

    def _resolve_voice_name(self, display: str) -> str:
        for v in self._voices:
            if v["friendly_name"] == display:
                name = v["name"]
                engine = self._orch.config.get("engine")
                key_map = {"minimax": "minimax_voice_id", "piper": "piper_voice"}
                self._orch.config.set(key_map.get(engine, "voice"), name)
                return name
        return display

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
                    "请启动 Soundpad 并开启 Remote Control", is_error=True)
        except Exception:
            self._status_bar.set_connected(False)
            self._poll_interval = 3000
        self._root.after(self._poll_interval, self._poll_soundpad)

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

    def save_state(self):
        geo = self._root.geometry()
        self._orch.config.set("window_geometry", geo)
        if self._floating_win and self._floating_win.winfo_exists():
            self._orch.config.set("floating_geometry", self._floating_win.get_position())
            self._floating_win.destroy()
        self._orch.config.save()
