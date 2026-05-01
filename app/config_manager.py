import json
import threading
from pathlib import Path

from app.secret_store import delete_secret, load_secret, save_secret

_DEFAULTS = {
    # 引擎选择
    "engine": "edge",
    # Edge TTS 配置
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+0%",
    "pitch": "+0Hz",
    # MiniMax 配置
    "minimax_api_key": "",
    "minimax_voice_id": "female-shaonv",
    "minimax_model": "speech-2.8-hd",
    "minimax_speed": 1.0,
    "minimax_vol": 1.0,
    "minimax_pitch": 0,
    # 通用
    "play_on_speakers": False,
    "play_on_mic": True,
    "max_text_length": 500,
    "window_geometry": "500x780",
    "window_topmost": False,
    "theme": "dark",
    "recent_texts": [],
    "max_recent_texts": 20,
    "quick_phrases": [],
    "floating_geometry": "",
}

_DEBOUNCE_MS = 500  # 防抖延迟（毫秒）


class ConfigManager:
    def __init__(self, config_dir: Path):
        self._config_dir = config_dir
        self._path = config_dir / "settings.json"
        self._data: dict = {}
        self._save_timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self.load()

    def load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        # 用默认值填充缺失的 key
        for key, default in _DEFAULTS.items():
            self._data.setdefault(key, default)
        self._load_minimax_key()

    def _load_minimax_key(self):
        """优先从安全存储读取密钥，并兼容旧版 settings.json 明文字段迁移。"""
        secret_key = load_secret(self._config_dir, "minimax_api_key")
        if secret_key:
            self._data["minimax_api_key"] = secret_key
            return
        legacy_key = self._data.get("minimax_api_key", "")
        if legacy_key:
            save_secret(self._config_dir, "minimax_api_key", legacy_key)
            self._data["minimax_api_key"] = legacy_key
            # 明文字段迁移后立即清空并落盘，避免继续以明文保存
            self._do_save()

    def save(self):
        """立即写入磁盘（取消挂起的 debounce）。"""
        self._cancel_pending_save()
        self._do_save()

    def _do_save(self):
        with self._lock:
            persisted = dict(self._data)
            persisted["minimax_api_key"] = ""
            snapshot = json.dumps(persisted, ensure_ascii=False, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot, encoding="utf-8")

    def _schedule_save(self):
        """防抖保存：连续快速修改时只在最后一次修改后写入。"""
        self._cancel_pending_save()
        self._save_timer = threading.Timer(_DEBOUNCE_MS / 1000.0, self._do_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _cancel_pending_save(self):
        if self._save_timer is not None:
            self._save_timer.cancel()
            self._save_timer = None

    def get(self, key: str, default=None):
        return self._data.get(key, default if default is not None else _DEFAULTS.get(key))

    def set(self, key: str, value):
        self._data[key] = value
        if key == "minimax_api_key":
            if value:
                save_secret(self._config_dir, "minimax_api_key", value)
            else:
                delete_secret(self._config_dir, "minimax_api_key")
        self._schedule_save()

    def add_recent_text(self, text: str):
        recents = self._data.get("recent_texts", [])
        if text in recents:
            recents.remove(text)
        recents.insert(0, text)
        max_count = self._data.get("max_recent_texts", 20)
        self._data["recent_texts"] = recents[:max_count]
        self._schedule_save()
