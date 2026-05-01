import hashlib
from pathlib import Path


def make_cache_key(engine: str, text: str, voice: str, **params) -> str:
    raw = f"{engine}|{text}|{voice}|" + "|".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def try_cache(cache_dir: Path, key: str, prefix: str) -> str | None:
    cache_path = cache_dir / f"{prefix}_{key}.mp3"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return str(cache_path.resolve())
    return None


def cache_path_for(cache_dir: Path, key: str, prefix: str) -> Path:
    return cache_dir / f"{prefix}_{key}.mp3"
