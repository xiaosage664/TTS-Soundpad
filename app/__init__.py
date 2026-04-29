"""TTS Soundpad - 文字转语音并通过 Soundpad 播放至麦克风"""


class TTSSoundpadError(Exception):
    """基础异常类"""


class TTSError(TTSSoundpadError):
    """TTS 相关异常"""


class TTSNetworkError(TTSError):
    """TTS 网络连接失败"""


class TTSGenerationError(TTSError):
    """TTS 语音生成失败"""


class SoundpadError(TTSSoundpadError):
    """Soundpad 相关异常"""


class SoundpadNotRunningError(SoundpadError):
    """Soundpad 未运行"""


class SoundpadCommandError(SoundpadError):
    """Soundpad 命令执行失败"""

    def __init__(self, command: str, error_code: str, message: str = ""):
        self.command = command
        self.error_code = error_code
        super().__init__(message or f"Soundpad 命令失败: {command} (错误码: {error_code})")
