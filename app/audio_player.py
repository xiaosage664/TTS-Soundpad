"""本地音频预听模块，使用 Windows MCI (winmm.dll) 播放 mp3，无需额外依赖。"""

import ctypes
import threading


def _mci_send(command: str) -> str:
    """发送 MCI 命令字符串并返回结果。"""
    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(command, buf, 255, 0)
    if err:
        # 获取错误描述
        err_buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.winmm.mciGetErrorStringW(err, err_buf, 255)
        raise RuntimeError(f"MCI 错误: {err_buf.value}")
    return buf.value


class AudioPlayer:
    """本地音频播放器，使用 Windows MCI 播放 mp3。"""

    _ALIAS = "tts_preview"

    def __init__(self):
        self._playing = False
        self._lock = threading.Lock()

    def play(self, file_path: str):
        """播放指定音频文件。"""
        with self._lock:
            # 先关闭之前的
            try:
                _mci_send(f"close {self._ALIAS}")
            except RuntimeError:
                pass
            try:
                _mci_send(f'open "{file_path}" alias {self._ALIAS}')
                _mci_send(f"play {self._ALIAS}")
                self._playing = True
            except RuntimeError as e:
                raise RuntimeError(f"播放失败: {e}") from e

    def stop(self):
        """停止播放。"""
        with self._lock:
            if self._playing:
                try:
                    _mci_send(f"stop {self._ALIAS}")
                    _mci_send(f"close {self._ALIAS}")
                except RuntimeError:
                    pass
                self._playing = False

    @property
    def is_playing(self) -> bool:
        if not self._playing:
            return False
        try:
            status = _mci_send(f"status {self._ALIAS} mode")
            return "playing" in status.lower()
        except RuntimeError:
            return False

    def cleanup(self):
        """释放资源。"""
        self.stop()
