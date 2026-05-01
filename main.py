import logging
import os
import sys
from pathlib import Path

import customtkinter as ctk

if getattr(sys, "frozen", False):
    _ROOT = Path(sys.executable).parent.resolve()
else:
    _ROOT = Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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
from app.minimax_engine import MiniMaxEngine
from app.orchestrator import Orchestrator
from app.soundpad import SoundpadController
from app.tts_engine import TTSEngine
from gui.main_window import MainWindow


def _get_cache_dir() -> Path:
    local_cache = _ROOT / "audio_cache"
    if all(ord(c) < 128 for c in str(local_cache)):
        return local_cache
    fallback = (
        Path(os.environ.get("ProgramData", "C:/ProgramData"))
        / "TTS_Soundpad"
        / "audio_cache"
    )
    _log.info("路径含非 ASCII 字符，缓存目录切换为: %s", fallback)
    return fallback


def _get_model_dir() -> Path:
    """选择模型下载目录（本地引擎模型存储）。"""
    local_models = _ROOT / "models"
    if all(ord(c) < 128 for c in str(local_models)):
        return local_models
    fallback = (
        Path(os.environ.get("ProgramData", "C:/ProgramData"))
        / "TTS_Soundpad"
        / "models"
    )
    _log.info("路径含非 ASCII 字符，模型目录切换为: %s", fallback)
    return fallback


def _detect_available_engines(piper, gpt_sovits) -> list[str]:
    """返回当前环境中可用的引擎列表。"""
    engines = ["edge", "minimax"]
    if piper is not None:
        engines.append("piper")
    else:
        _log.info("Piper 引擎不可用（piper-tts 未安装）")
    if gpt_sovits is not None:
        engines.append("gpt-sovits")
    else:
        _log.info("GPT-SoVITS 引擎不可用（未安装）")
    return engines


def main():
    cache_dir = _get_cache_dir()
    model_dir = _get_model_dir()
    config_dir = _ROOT / "config"
    cache_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(exist_ok=True)

    config = ConfigManager(config_dir)

    edge_tts = TTSEngine(cache_dir, default_voice=config.get("voice"))

    mm_cache = cache_dir / "minimax"
    minimax = MiniMaxEngine(
        cache_dir=mm_cache,
        api_key=config.get("minimax_api_key", ""),
        model=config.get("minimax_model", "speech-2.8-hd"),
        default_voice=config.get("minimax_voice_id", "female-shaonv"),
    )

    piper = None
    try:
        from app.piper_engine import PiperEngine

        piper = PiperEngine(
            cache_dir=cache_dir / "piper",
            model_dir=model_dir,
            default_voice=config.get("piper_voice", "yanran"),
            quality=config.get("piper_quality", "high"),
        )
        _log.info("Piper 引擎初始化成功")
    except ImportError as e:
        _log.warning("Piper 引擎初始化失败: %s", e)
    except Exception as e:
        _log.error("Piper 引擎初始化异常: %s", e, exc_info=True)

    gpt_sovits = None
    try:
        from app.gpt_sovits_engine import GPTSoVITSEngine

        gpt_sovits = GPTSoVITSEngine(
            cache_dir=cache_dir / "gpt_sovits",
            model_dir=model_dir,
        )
        _log.info("GPT-SoVITS 引擎初始化成功")
    except ImportError as e:
        _log.warning("GPT-SoVITS 引擎初始化失败: %s", e)
    except Exception as e:
        _log.error("GPT-SoVITS 引擎初始化异常: %s", e, exc_info=True)

    available_engines = _detect_available_engines(piper, gpt_sovits)

    soundpad = SoundpadController()

    root = ctk.CTk()
    bridge = AsyncBridge(root)

    orch = Orchestrator(
        edge_tts, minimax, soundpad, bridge, config,
        piper=piper, gpt_sovits=gpt_sovits,
    )

    window = MainWindow(root, orch, available_engines=available_engines)

    def on_closing():
        window.save_state()
        orch.player.cleanup()
        bridge.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
