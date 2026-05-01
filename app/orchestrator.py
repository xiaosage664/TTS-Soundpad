import logging
import threading
import time
from enum import Enum, auto
from typing import Callable

from app import SoundpadNotRunningError, TTSSoundpadError
from app.async_bridge import AsyncBridge
from app.audio_player import AudioPlayer
from app.config_manager import ConfigManager
from app.soundpad import SoundpadController

_log = logging.getLogger("orchestrator")


class SpeakStatus(Enum):
    IDLE = auto()
    GENERATING = auto()
    SENDING = auto()
    PLAYING = auto()
    ERROR = auto()


class HistoryItem:
    __slots__ = ("text", "voice", "timestamp", "file_path")

    def __init__(self, text: str, voice: str, file_path: str):
        self.text = text
        self.voice = voice
        self.timestamp = time.strftime("%H:%M:%S")
        self.file_path = file_path


StatusCallback = Callable[[SpeakStatus, str], None]


class Orchestrator:
    """协调多 TTS 引擎和 Soundpad 控制器的完整业务流程。

    支持引擎：Edge TTS / MiniMax / Piper / GPT-SoVITS
    """

    def __init__(
        self,
        tts,            # TTSEngine
        minimax,        # MiniMaxEngine
        soundpad: SoundpadController,
        bridge: AsyncBridge,
        config: ConfigManager,
        piper=None,         # PiperEngine | None
        gpt_sovits=None,    # GPTSoVITSEngine | None
    ):
        self._edge = tts
        self._minimax = minimax
        self._piper = piper
        self._gpt_sovits = gpt_sovits
        self.soundpad = soundpad
        self.bridge = bridge
        self.config = config
        self.player = AudioPlayer()
        self.history: list[HistoryItem] = []
        self._busy = False
        self._speak_gen = 0
        self._soundpad_lock = threading.Lock()
        self._history_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 引擎路由
    # ------------------------------------------------------------------

    def _get_active_engine(self):
        """根据配置返回当前激活的引擎实例。"""
        engine_key = self.config.get("engine", "edge")
        if engine_key == "minimax":
            return self._minimax
        if engine_key == "piper" and self._piper is not None:
            return self._piper
        if engine_key == "gpt-sovits" and self._gpt_sovits is not None:
            return self._gpt_sovits
        return self._edge

    def _get_engine_key(self) -> str:
        return self.config.get("engine", "edge")

    @property
    def engine_key(self) -> str:
        return self._get_engine_key()

    @staticmethod
    def engine_available(engine: str, piper=None, gpt_sovits=None) -> bool:
        """检查指定引擎在当前环境中是否可用。"""
        if engine in ("edge", "minimax"):
            return True
        if engine == "piper":
            return piper is not None
        if engine == "gpt-sovits":
            return gpt_sovits is not None
        return False

    # ------------------------------------------------------------------
    # 参数构建
    # ------------------------------------------------------------------

    def _build_engine_params(self) -> dict:
        """根据当前引擎构建合成参数。"""
        engine = self._get_engine_key()
        if engine == "minimax":
            return {
                "speed": self.config.get("minimax_speed", 1.0),
                "vol": self.config.get("minimax_vol", 1.0),
                "pitch": self.config.get("minimax_pitch", 0),
            }
        if engine == "piper":
            return {
                "quality": self.config.get("piper_quality", "high"),
                "length_scale": self.config.get("piper_length_scale", 1.0),
                "noise_scale": self.config.get("piper_noise_scale", 0.667),
                "noise_w": self.config.get("piper_noise_w", 0.8),
            }
        if engine == "gpt-sovits":
            return {
                "ref_audio_path": self.config.get("gpt_sovits_ref_audio", ""),
                "prompt_text": self.config.get("gpt_sovits_prompt_text", ""),
                "prompt_lang": self.config.get("gpt_sovits_prompt_lang", "zh"),
                "text_lang": self.config.get("gpt_sovits_text_lang", "zh"),
                "top_k": self.config.get("gpt_sovits_top_k", 15),
                "top_p": self.config.get("gpt_sovits_top_p", 0.8),
                "temperature": self.config.get("gpt_sovits_temperature", 0.8),
                "speed_factor": self.config.get("gpt_sovits_speed", 1.0),
            }
        return {
            "rate": self.config.get("rate", "+0%"),
            "pitch": self.config.get("pitch", "+0Hz"),
        }

    @property
    def is_busy(self) -> bool:
        return self._busy

    # ------------------------------------------------------------------
    # 核心方法：文字 → TTS → Soundpad
    # ------------------------------------------------------------------

    def speak(self, text: str, voice: str | None, callback: StatusCallback):
        text = text.strip()
        max_len = self.config.get("max_text_length", 500)
        if not text:
            callback(SpeakStatus.ERROR, "请输入文字")
            return
        if len(text) > max_len:
            callback(SpeakStatus.ERROR, f"文本超过 {max_len} 字限制")
            return

        engine_key = self._get_engine_key()

        # GPT-SoVITS 需要参考音频
        if engine_key == "gpt-sovits" and self._gpt_sovits is not None:
            ref_audio = self.config.get("gpt_sovits_ref_audio", "")
            if not ref_audio:
                callback(SpeakStatus.ERROR, "请先选择参考音频")
                return

        # 新请求覆盖旧请求：递增计数器使旧回调失效
        self._speak_gen += 1
        gen = self._speak_gen

        voice = voice or self.config.get("voice")
        self._busy = True
        callback(SpeakStatus.GENERATING, "正在生成语音...")
        _log.info("speak() gen=%d engine=%s text=%r voice=%s", gen, engine_key, text[:50], voice)

        engine = self._get_active_engine()
        params = self._build_engine_params()
        coro = engine.synthesize(text, voice, **params)

        self.bridge.submit(
            coro,
            on_success=lambda fp: self._on_speak_generated(fp, text, voice, callback, gen),
            on_error=lambda exc: self._on_speak_error(exc, callback, gen),
        )

    def _on_speak_generated(
        self, file_path: str, text: str, voice: str, callback: StatusCallback, gen: int
    ):
        """TTS 生成成功后，在后台线程发送到 Soundpad，避免阻塞 GUI。"""
        if gen != self._speak_gen:
            _log.info("speak gen=%d 已过期 (当前=%d)，忽略", gen, self._speak_gen)
            return
        _log.info("TTS 生成成功: %s", file_path)
        callback(SpeakStatus.SENDING, "正在发送到 Soundpad...")

        def _do_soundpad_io():
            with self._soundpad_lock:
                try:
                    self._send_to_soundpad(file_path)
                    with self._history_lock:
                        self.history.insert(0, HistoryItem(text, voice, file_path))
                    self.config.add_recent_text(text)
                    self.bridge.root.after(0, lambda: self._finish_speak(callback, True, gen=gen))
                except SoundpadNotRunningError as e:
                    _log.error("SoundpadNotRunningError: %s", e)
                    msg = "Soundpad 未运行，请先启动 Soundpad"
                    self.bridge.root.after(0, lambda: self._finish_speak(callback, False, msg, gen=gen))
                except TTSSoundpadError as e:
                    _log.error("TTSSoundpadError: %s", e)
                    msg = str(e)
                    self.bridge.root.after(0, lambda: self._finish_speak(callback, False, msg, gen=gen))
                except Exception as e:
                    _log.error("未知异常: %s", e, exc_info=True)
                    msg = f"发送失败: {e}"
                    self.bridge.root.after(0, lambda: self._finish_speak(callback, False, msg, gen=gen))

        threading.Thread(target=_do_soundpad_io, daemon=True).start()

    def _finish_speak(self, callback: StatusCallback, success: bool, error_msg: str = "", *, gen: int = 0):
        """在主线程上完成 speak 流程的最终回调。"""
        self._busy = False
        if gen != self._speak_gen:
            _log.info("finish_speak gen=%d 已过期 (当前=%d)，忽略", gen, self._speak_gen)
            return
        if success:
            callback(SpeakStatus.PLAYING, "播放中")
        else:
            callback(SpeakStatus.ERROR, error_msg)

    def _on_speak_error(self, exc: Exception, callback: StatusCallback, gen: int):
        self._busy = False
        if gen != self._speak_gen:
            return
        _log.error("TTS 生成失败: %s", exc, exc_info=True)
        callback(SpeakStatus.ERROR, str(exc))

    def _send_to_soundpad(self, file_path: str) -> int:
        speakers = self.config.get("play_on_speakers", False)
        mic = self.config.get("play_on_mic", True)
        _log.info("play_tts_file speakers=%s mic=%s", speakers, mic)
        new_index = self.soundpad.play_tts_file(
            file_path, speakers=speakers, mic=mic
        )
        _log.info("play_tts_file 成功 index=%d", new_index)
        return new_index

    # ------------------------------------------------------------------
    # 停止
    # ------------------------------------------------------------------

    def stop(self):
        self._speak_gen += 1
        try:
            self.soundpad.stop_sound()
        except TTSSoundpadError:
            pass

    # ------------------------------------------------------------------
    # 连接检查
    # ------------------------------------------------------------------

    def check_soundpad(self) -> bool:
        return self.soundpad.is_running()

    def get_latest_history(self):
        with self._history_lock:
            if self.history:
                return self.history[0]
            return None

    # ------------------------------------------------------------------
    # 语音列表
    # ------------------------------------------------------------------

    def get_voices(self, callback: Callable[[list[dict]], None]):
        engine = self._get_active_engine()
        coro = engine.list_voices()
        self.bridge.submit(coro, on_success=callback)

    # ------------------------------------------------------------------
    # MiniMax API Key 验证
    # ------------------------------------------------------------------

    def verify_minimax_key(self, callback: Callable[[bool, str], None]):
        """异步验证 MiniMax API Key。"""
        coro = self._minimax.verify_api_key()
        self.bridge.submit(
            coro,
            on_success=lambda result: callback(result[0], result[1]),
            on_error=lambda exc: callback(False, f"验证异常: {exc}"),
        )

    # ------------------------------------------------------------------
    # GPT-SoVITS 模型初始化（耗时操作，在后台线程执行）
    # ------------------------------------------------------------------

    def init_gpt_sovits_model(self, callback: Callable[[bool, str], None]):
        """在后台线程加载 GPT-SoVITS 模型。"""
        if self._gpt_sovits is None:
            callback(False, "GPT-SoVITS 引擎未安装")
            return

        def _load():
            try:
                self._gpt_sovits.init_model()
                self.bridge.root.after(0, lambda: callback(True, "模型加载完成"))
            except Exception as e:
                _log.error("GPT-SoVITS 模型加载失败: %s", e, exc_info=True)
                self.bridge.root.after(0, lambda: callback(False, str(e)))

        threading.Thread(target=_load, daemon=True).start()

    # ------------------------------------------------------------------
    # 本地预听
    # ------------------------------------------------------------------

    def preview(self, text: str, voice: str | None, callback: StatusCallback):
        if self._busy:
            callback(SpeakStatus.ERROR, "正在处理中，请稍候")
            return

        text = text.strip()
        if not text:
            callback(SpeakStatus.ERROR, "请输入文字")
            return

        engine_key = self._get_engine_key()
        if engine_key == "gpt-sovits" and self._gpt_sovits is not None:
            ref_audio = self.config.get("gpt_sovits_ref_audio", "")
            if not ref_audio:
                callback(SpeakStatus.ERROR, "请先选择参考音频")
                return

        voice = voice or self.config.get("voice")
        self._busy = True
        callback(SpeakStatus.GENERATING, "正在生成预听语音...")

        engine = self._get_active_engine()
        params = self._build_engine_params()
        coro = engine.synthesize(text, voice, **params)

        self.bridge.submit(
            coro,
            on_success=lambda fp: self._on_preview_generated(fp, callback),
            on_error=lambda exc: self._on_preview_error(exc, callback),
        )

    def _on_preview_generated(self, file_path: str, callback: StatusCallback):
        try:
            self.player.play(file_path)
            callback(SpeakStatus.PLAYING, "本地预听中...")
        except Exception as e:
            callback(SpeakStatus.ERROR, f"预听失败: {e}")
        finally:
            self._busy = False

    def _on_preview_error(self, exc: Exception, callback: StatusCallback):
        _log.error("预听 TTS 生成失败: %s", exc, exc_info=True)
        self._busy = False
        callback(SpeakStatus.ERROR, str(exc))

    def stop_preview(self):
        self.player.stop()
