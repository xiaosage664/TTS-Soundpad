from pathlib import Path

from app.audio_cache import cache_path_for, make_cache_key, try_cache


def test_make_cache_key_is_stable_for_same_params_different_order():
    key1 = make_cache_key("edge", "hello", "voice-a", rate="+0%", pitch="+0Hz")
    key2 = make_cache_key("edge", "hello", "voice-a", pitch="+0Hz", rate="+0%")
    assert key1 == key2


def test_make_cache_key_changes_when_input_changes():
    key1 = make_cache_key("edge", "hello", "voice-a", rate="+0%")
    key2 = make_cache_key("edge", "hello!", "voice-a", rate="+0%")
    assert key1 != key2


def test_try_cache_returns_file_path_only_for_non_empty_file(tmp_path: Path):
    key = "abc123"
    prefix = "edge"
    cache_file = tmp_path / f"{prefix}_{key}.mp3"
    cache_file.write_bytes(b"audio")

    hit = try_cache(tmp_path, key, prefix)
    assert hit is not None
    assert Path(hit) == cache_file.resolve()


def test_try_cache_returns_none_for_missing_or_empty_file(tmp_path: Path):
    key = "abc123"
    prefix = "edge"
    assert try_cache(tmp_path, key, prefix) is None

    cache_file = tmp_path / f"{prefix}_{key}.mp3"
    cache_file.write_bytes(b"")
    assert try_cache(tmp_path, key, prefix) is None


def test_cache_path_for_builds_expected_path(tmp_path: Path):
    key = "k1"
    prefix = "mini"
    expected = tmp_path / "mini_k1.mp3"
    assert cache_path_for(tmp_path, key, prefix) == expected
