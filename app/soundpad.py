import ctypes
import ctypes.wintypes
import logging
from pathlib import Path

from app import SoundpadCommandError, SoundpadNotRunningError

_log = logging.getLogger("soundpad")

_PIPE_NAME = r"\\.\pipe\sp_remote_control"

# Windows API 常量
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3

_kernel32 = ctypes.windll.kernel32

# 设置正确的函数签名，避免 64-bit 句柄截断问题 (Python 3.14+)
_kernel32.CreateFileW.restype = ctypes.wintypes.HANDLE
_kernel32.CreateFileW.argtypes = [
    ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
    ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
    ctypes.wintypes.HANDLE,
]
_kernel32.WriteFile.restype = ctypes.wintypes.BOOL
_kernel32.WriteFile.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.c_void_p,
]
_kernel32.ReadFile.restype = ctypes.wintypes.BOOL
_kernel32.ReadFile.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.c_void_p,
]
_kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
_kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
_kernel32.GetLastError.restype = ctypes.wintypes.DWORD
_kernel32.WaitNamedPipeW.restype = ctypes.wintypes.BOOL
_kernel32.WaitNamedPipeW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD]
_kernel32.GetShortPathNameW.restype = ctypes.wintypes.DWORD
_kernel32.GetShortPathNameW.argtypes = [
    ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD,
]

_INVALID_HANDLE = ctypes.wintypes.HANDLE(-1).value

_MAX_PIPE_RETRIES = 3
_PIPE_WAIT_MS = 2000  # WaitNamedPipe 超时毫秒


def _to_short_path(long_path: str) -> str:
    """将包含非 ASCII 字符的路径转换为 Windows 8.3 短路径格式。

    Soundpad 的 Named Pipe 接口不支持 Unicode 路径，
    使用 GetShortPathNameW 转换后的短路径全部为 ASCII 字符。
    """
    if all(ord(c) < 128 for c in long_path):
        return long_path  # 纯 ASCII，无需转换

    buf = ctypes.create_unicode_buffer(512)
    result = _kernel32.GetShortPathNameW(long_path, buf, 512)
    if result == 0 or result > 512:
        _log.warning("GetShortPathNameW 失败，使用原始路径: %s", long_path)
        return long_path
    short = buf.value
    _log.info("路径转换: %s -> %s", long_path, short)
    return short


def _send_raw(command: str) -> str:
    """打开管道 -> 发送命令 -> 读取响应 -> 关闭。每次调用独立连接，带 PIPE_BUSY 重试。"""
    _log.debug("_send_raw cmd=%s", command)
    last_err = 0
    for _attempt in range(_MAX_PIPE_RETRIES):
        handle = _kernel32.CreateFileW(
            _PIPE_NAME,
            _GENERIC_READ | _GENERIC_WRITE,
            0,       # no sharing
            None,    # default security
            _OPEN_EXISTING,
            0,       # default attributes
            None,    # no template
        )
        if handle != _INVALID_HANDLE:
            break  # 连接成功

        last_err = _kernel32.GetLastError()
        _log.warning("CreateFileW 失败 attempt=%d err=%d", _attempt, last_err)
        if last_err == 231:  # ERROR_PIPE_BUSY
            _kernel32.WaitNamedPipeW(_PIPE_NAME, _PIPE_WAIT_MS)
            continue
        else:
            break  # 非 PIPE_BUSY 错误，不重试
    else:
        raise SoundpadNotRunningError(
            "Soundpad 管道忙，可能有其他程序正在占用连接，请稍后重试"
        )

    if handle == _INVALID_HANDLE:
        if last_err == 2:
            raise SoundpadNotRunningError(
                "无法连接 Soundpad：管道不存在。\n"
                "请确认：1) Soundpad 已启动  "
                "2) 已在 Soundpad → File → Preferences 中勾选 Remote Control"
            )
        raise SoundpadNotRunningError(
            f"无法连接 Soundpad (错误码: {last_err})，请确认 Soundpad 已启动并启用远程控制"
        )

    try:
        data = (command + "\r\n").encode("utf-8")
        bytes_written = ctypes.wintypes.DWORD(0)
        success = _kernel32.WriteFile(
            handle, data, len(data), ctypes.byref(bytes_written), None
        )
        if not success:
            err = _kernel32.GetLastError()
            _log.error("WriteFile 失败 err=%d", err)
            raise SoundpadCommandError(command, "WRITE_FAIL", f"写入管道失败 (err={err})")

        buf = ctypes.create_string_buffer(4096)
        bytes_read = ctypes.wintypes.DWORD(0)
        success = _kernel32.ReadFile(
            handle, buf, 4096, ctypes.byref(bytes_read), None
        )
        if not success:
            err = _kernel32.GetLastError()
            _log.error("ReadFile 失败 err=%d", err)
            raise SoundpadCommandError(command, "READ_FAIL", f"读取管道响应失败 (err={err})")

        resp = buf.raw[: bytes_read.value].decode("utf-8", errors="replace").strip()
        _log.debug("_send_raw 响应: %s", resp)
        return resp
    finally:
        _kernel32.CloseHandle(handle)


def _parse_response(command: str, raw: str) -> str:
    """
    解析 Soundpad Named Pipe 响应。
    响应格式 (类似 HTTP 状态码):
      - R-200 = 成功 (OK)
      - R-404 = 命令未找到
      - R-4xx/5xx = 错误
      - 纯数值 = 查询结果 (如 GetSoundFileCount 返回 "0")
    """
    if not raw:
        raise SoundpadCommandError(command, "EMPTY", "空响应")

    first_line = raw.splitlines()[0].strip()

    # R-xxx 格式的响应码 (可能带描述: "R-204: File does not exist")
    if first_line.startswith("R-"):
        after_prefix = first_line[2:]
        # 提取数字部分 (冒号前)
        code_part = after_prefix.split(":")[0].strip()
        try:
            code = int(code_part)
        except ValueError:
            raise SoundpadCommandError(command, first_line, f"未知响应: {first_line}")
        # 2xx = 成功
        if 200 <= code < 300:
            return ""
        # 0 也视为成功
        if code == 0:
            return ""
        # 其他为错误
        _ERROR_MESSAGES = {
            204: "文件不存在",
            400: "请求无效",
            403: "操作被拒绝 (可能需要 Soundpad 完整版)",
            404: "命令未找到",
            500: "Soundpad 内部错误",
        }
        # 优先使用 Soundpad 返回的描述信息
        sp_detail = after_prefix.split(":", 1)[1].strip() if ":" in after_prefix else ""
        msg = sp_detail or _ERROR_MESSAGES.get(code, f"错误码 {code}")
        raise SoundpadCommandError(command, first_line, msg)

    # 纯数值：查询结果
    return first_line


class SoundpadController:
    """通过 Windows Named Pipe 控制 Soundpad。"""

    def is_running(self) -> bool:
        try:
            _send_raw("GetSoundFileCount()")
            return True
        except (SoundpadNotRunningError, OSError):
            return False

    def add_sound(self, file_path: str) -> None:
        """添加音频文件到 Soundpad 列表。"""
        abs_path = str(Path(file_path).resolve())
        # Soundpad 不支持 Unicode 路径，转换为 8.3 短路径
        safe_path = _to_short_path(abs_path)
        raw = _send_raw(f"DoAddSound({safe_path})")
        _parse_response("DoAddSound", raw)

    def get_sound_count(self) -> int:
        """获取 Soundpad 音频列表中的文件数量。"""
        raw = _send_raw("GetSoundFileCount()")
        data = _parse_response("GetSoundFileCount", raw)
        try:
            return int(data)
        except ValueError:
            return 0

    def play_sound(self, index: int, speakers: bool = False, mic: bool = True) -> None:
        """播放指定索引的音频。"""
        sp = "true" if speakers else "false"
        mc = "true" if mic else "false"
        raw = _send_raw(f"DoPlaySound({index},{sp},{mc})")
        _parse_response("DoPlaySound", raw)

    def stop_sound(self) -> None:
        """停止当前播放。"""
        raw = _send_raw("DoStopSound()")
        _parse_response("DoStopSound", raw)

    def select_index(self, index: int) -> None:
        """选中指定索引的音频条目。"""
        raw = _send_raw(f"DoSelectIndex({index})")
        _parse_response("DoSelectIndex", raw)

    def remove_selected(self) -> None:
        """从列表中移除当前选中的条目。"""
        raw = _send_raw("DoRemoveSelectedEntries()")
        _parse_response("DoRemoveSelectedEntries", raw)

    def play_tts_file(self, file_path: str, speakers: bool = False, mic: bool = True) -> int:
        """
        组合操作：添加音频文件 -> 等待列表更新 -> 播放。
        返回音频在 Soundpad 列表中的索引。
        """
        import time

        _log.info("play_tts_file file=%s speakers=%s mic=%s", file_path, speakers, mic)
        count_before = self.get_sound_count()
        _log.info("  count_before=%d", count_before)
        self.add_sound(file_path)

        # 等待 Soundpad 内部列表更新完成 (最多等 2 秒)
        new_index = count_before + 1
        for i in range(20):
            count_after = self.get_sound_count()
            if count_after >= new_index:
                new_index = count_after
                _log.info("  更新完成 count=%d index=%d wait=%dms", count_after, new_index, i*100)
                break
            time.sleep(0.1)
        else:
            _log.warning("  等待超时! count=%d", self.get_sound_count())

        _log.info("  play_sound index=%d", new_index)
        self.play_sound(new_index, speakers=speakers, mic=mic)
        return new_index


if __name__ == "__main__":
    ctrl = SoundpadController()
    if ctrl.is_running():
        print("Soundpad 已连接")
        count = ctrl.get_sound_count()
        print(f"音频列表数量: {count}")
    else:
        print("Soundpad 未运行")
