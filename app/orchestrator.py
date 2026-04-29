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
from app.tts_engine import TTSEngine

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
    """协调 TTS 引擎和 Soundpad 控制器的完整业务流程。"""

    def __init__(
        self,
        tts: TTSEngine,
        soundpad: SoundpadController,
        bridge: AsyncBridge,
        config: ConfigManager,
    ):
        self.tts = tts
        self.soundpad = soundpad
        self.bridge = bridge
        self.config = config
        self.player = AudioPlayer()
        self.history: list[HistoryItem] = []
        self._busy = False
        self._speak_gen = 0
        self._tts_indices: list[int] = []

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

        # 新请求覆盖旧请求：递增计数器使旧回调失效
        self._speak_gen += 1
        gen = self._speak_gen

        voice = voice or self.config.get("voice")
        rate = self.config.get("rate", "+0%")
        pitch = self.config.get("pitch", "+0Hz")
        self._busy = True
        callback(SpeakStatus.GENERATING, "正在生成语音...")
        _log.info("speak() gen=%d text=%r voice=%s rate=%s pitch=%s", gen, text, voice, rate, pitch)

        coro = self.tts.synthesize(text, voice, rate=rate, pitch=pitch)
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
            try:
                self._cleanup_old_indices()
                new_index = self._send_to_soundpad(file_path)
                self._tts_indices.append(new_index)
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
        if gen != self._speak_gen:
            _log.info("finish_speak gen=%d 已过期 (当前=%d)，忽略", gen, self._speak_gen)
            return
        self._busy = False
        if success:
            callback(SpeakStatus.PLAYING, "播放中")
        else:
            callback(SpeakStatus.ERROR, error_msg)

    def _on_speak_error(self, exc: Exception, callback: StatusCallback, gen: int):
        if gen != self._speak_gen:
            return
        _log.error("TTS 生成失败: %s", exc, exc_info=True)
        self._busy = False
        callback(SpeakStatus.ERROR, str(exc))

    def _cleanup_old_indices(self):
        """清理 Soundpad 中之前的 TTS 条目。"""
        if not self.config.get("auto_cleanup_soundpad", True):
            return
        if not self._tts_indices:
            return
        _log.info("清理旧索引: %s", self._tts_indices)
        for idx in sorted(self._tts_indices, reverse=True):
            try:
                self.soundpad.select_index(idx)
                self.soundpad.remove_selected()
            except Exception as e:
                _log.warning("清理索引 %d 失败: %s", idx, e)
        self._tts_indices.clear()

    def _send_to_soundpad(self, file_path: str) -> int:
        """发送文件到 Soundpad 并播放，返回新索引。"""
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
        try:
            self.soundpad.stop_sound()
        except TTSSoundpadError:
            pass

    # ------------------------------------------------------------------
    # 连接检查
    # ------------------------------------------------------------------

    def check_soundpad(self) -> bool:
        return self.soundpad.is_running()

    # ------------------------------------------------------------------
    # 语音列表
    # ------------------------------------------------------------------

    def get_voices(self, callback: Callable[[list[dict]], None]):
        self.bridge.submit(self.tts.list_voices(), on_success=callback)

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

        voice = voice or self.config.get("voice")
        rate = self.config.get("rate", "+0%")
        pitch = self.config.get("pitch", "+0Hz")
        self._busy = True
        callback(SpeakStatus.GENERATING, "正在生成预听语音...")

        coro = self.tts.synthesize(text, voice, rate=rate, pitch=pitch)
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
