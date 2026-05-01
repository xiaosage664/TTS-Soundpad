import json
from pathlib import Path

import app.config_manager as config_module
from app.config_manager import ConfigManager


def test_load_uses_defaults_when_file_missing(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    assert manager.get("engine") == "edge"
    assert manager.get("voice") == "zh-CN-XiaoxiaoNeural"


def test_load_recovers_from_invalid_json(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text("{not-json}", encoding="utf-8")

    manager = ConfigManager(tmp_path)
    assert manager.get("engine") == "edge"
    assert manager.get("minimax_api_key") == ""


def test_save_writes_data_to_disk(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    manager.set("engine", "minimax")
    manager.save()

    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["engine"] == "minimax"


def test_add_recent_text_deduplicates_and_limits(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    manager._schedule_save = lambda: None
    manager.set("max_recent_texts", 2)
    manager._schedule_save = lambda: None

    manager.add_recent_text("hello")
    manager.add_recent_text("world")
    manager.add_recent_text("hello")
    manager.add_recent_text("third")

    assert manager.get("recent_texts") == ["third", "hello"]


def test_set_minimax_key_persists_to_secret_store(tmp_path: Path, monkeypatch):
    calls = {"saved": None}

    monkeypatch.setattr(config_module, "load_secret", lambda *_args: "")
    monkeypatch.setattr(
        config_module, "save_secret", lambda *_args: calls.__setitem__("saved", _args[-1])
    )
    monkeypatch.setattr(config_module, "delete_secret", lambda *_args: None)

    manager = ConfigManager(tmp_path)
    manager.set("minimax_api_key", "my-secret")
    assert calls["saved"] == "my-secret"


def test_load_migrates_legacy_plaintext_key(tmp_path: Path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"minimax_api_key": "legacy-key"}), encoding="utf-8")
    migrated = {"value": ""}

    monkeypatch.setattr(config_module, "load_secret", lambda *_args: "")
    monkeypatch.setattr(
        config_module, "save_secret", lambda *_args: migrated.__setitem__("value", _args[-1])
    )
    monkeypatch.setattr(config_module, "delete_secret", lambda *_args: None)

    manager = ConfigManager(tmp_path)
    assert manager.get("minimax_api_key") == "legacy-key"
    assert migrated["value"] == "legacy-key"
    persisted = json.loads(settings.read_text(encoding="utf-8"))
    assert persisted["minimax_api_key"] == ""
