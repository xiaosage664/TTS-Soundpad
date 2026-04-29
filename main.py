import logging
import sys
from pathlib import Path

import customtkinter as ctk

# 确保项目根目录在 sys.path 中
# PyInstaller --onefile 模式下 __file__ 指向临时解压目录，
# 需要用 sys.executable 的目录作为项目根目录
if getattr(sys, "frozen", False):
    _ROOT = Path(sys.executable).parent.resolve()
else:
    _ROOT = Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 全局日志 -> 文件 (仅记录 INFO 及以上)
_LOG_FILE = _ROOT / "tts_debug.log"
logging.basicConfig(
    filename=str(_LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    encoding="utf-8",
)
_log = logging.getLogger("main")

from app.async_bridge import AsyncBridge
from app.config_manager import ConfigManager
from app.orchestrator import Orchestrator
from app.soundpad import SoundpadController
from app.tray_manager import TrayManager
from app.tts_engine import TTSEngine
from gui.main_window import MainWindow


def _get_cache_dir() -> Path:
    """选择音频缓存目录。

    Soundpad Named Pipe 不支持 Unicode 路径，
    如果 exe 所在目录包含非 ASCII 字符（如中文用户名），
    则将缓存放到 C:\\ProgramData\\TTS_Soundpad\\audio_cache。
    """
    local_cache = _ROOT / "audio_cache"
    if all(ord(c) < 128 for c in str(local_cache)):
        return local_cache
    # 路径含非 ASCII，使用 ProgramData（始终纯 ASCII）
    fallback = Path("C:/ProgramData/TTS_Soundpad/audio_cache")
    _log.info("路径含非 ASCII 字符，缓存目录切换为: %s", fallback)
    return fallback


def main():
    # 目录准备
    cache_dir = _get_cache_dir()
    config_dir = _ROOT / "config"
    cache_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(exist_ok=True)

    # 初始化各模块
    config = ConfigManager(config_dir)
    tts = TTSEngine(cache_dir, default_voice=config.get("voice"))
    soundpad = SoundpadController()

    # 创建 tkinter 根窗口
    root = ctk.CTk()

    # 初始化异步桥接 (需要 root 用于线程安全回调)
    bridge = AsyncBridge(root)

    # 初始化协调器
    orch = Orchestrator(tts, soundpad, bridge, config)

    # 启动时清理旧缓存
    tts.cleanup_old_files()

    # 创建主窗口
    window = MainWindow(root, orch)

    # --- 系统托盘 ---
    def show_window():
        root.after(0, _restore_window)

    def _restore_window():
        root.deiconify()
        root.lift()
        root.focus_force()

    def quit_app():
        root.after(0, _do_quit)

    def _do_quit():
        window.save_state()
        tray.stop()
        orch.player.cleanup()
        bridge.shutdown()
        root.destroy()

    def minimize_to_tray():
        root.withdraw()

    tray = TrayManager(on_show=show_window, on_quit=quit_app)
    tray.start()

    # 设置托盘最小化回调（用户点击"托盘"按钮时触发）
    window.set_tray_callback(minimize_to_tray)

    # 关闭窗口时真正退出程序
    def on_closing():
        _do_quit()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # 启动主循环
    root.mainloop()


if __name__ == "__main__":
    main()
