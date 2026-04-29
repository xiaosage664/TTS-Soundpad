import asyncio
import hashlib
import logging
import time
from pathlib import Path

import edge_tts

from app import TTSGenerationError, TTSNetworkError

_log = logging.getLogger("tts_engine")

# 中文语音预设 (离线 fallback)
_CHINESE_VOICES_FALLBACK = [
    {"name": "zh-CN-XiaoxiaoNeural", "friendly_name": "晓晓 (女声, 温柔)", "gender": "Female"},
    {"name": "zh-CN-YunxiNeural", "friendly_name": "云希 (男声, 年轻)", "gender": "Male"},
    {"name": "zh-CN-YunjianNeural", "friendly_name": "云健 (男声, 沉稳)", "gender": "Male"},
    {"name": "zh-CN-XiaoyiNeural", "friendly_name": "晓伊 (女声, 活泼)", "gender": "Female"},
    {"name": "zh-CN-YunyangNeural", "friendly_name": "云扬 (男声, 新闻)", "gender": "Male"},
    {"name": "zh-CN-XiaochenNeural", "friendly_name": "晓辰 (女声, 休闲)", "gender": "Female"},
]


def _cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
    """生成缓存键：text+voice+rate+pitch 的 md5。"""
    raw = f"{text}|{voice}|{rate}|{pitch}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class TTSEngine:
    def __init__(self, cache_dir: Path, default_voice: str = "zh-CN-XiaoxiaoNeural"):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._default_voice = default_voice
        self._voices_cache: list[dict] | None = None
        # 内存缓存: cache_key -> file_path
        self._file_cache: dict[str, str] = {}
        self._build_file_cache()

    def _build_file_cache(self):
        """启动时扫描已有缓存文件，建立索引。"""
        for f in self._cache_dir.glob("tts_*.mp3"):
            # 文件名格式: tts_{cache_key}.mp3
            stem = f.stem  # tts_{cache_key}
            if stem.startswith("tts_") and len(stem) == 36:  # tts_ + 32 hex
                key = stem[4:]
                self._file_cache[key] = str(f.resolve())

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> str:
        """将文字转换为语音 mp3 文件，返回绝对路径。支持缓存命中。"""
        voice = voice or self._default_voice
        text = text.strip()
        if not text:
            raise TTSGenerationError("文本不能为空")

        # 缓存命中检查
        key = _cache_key(text, voice, rate, pitch)
        cached = self._file_cache.get(key)
        if cached and Path(cached).exists() and Path(cached).stat().st_size > 0:
            _log.info("缓存命中: %s", cached)
            return cached

        # 缓存未命中，生成新文件
        filename = f"tts_{key}.mp3"
        output_path = self._cache_dir / filename

        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicate.save(str(output_path))
        except Exception as e:
            err_msg = str(e).lower()
            if "connect" in err_msg or "timeout" in err_msg or "network" in err_msg:
                raise TTSNetworkError(f"网络连接失败: {e}") from e
            raise TTSGenerationError(f"语音生成失败: {e}") from e

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise TTSGenerationError("语音文件生成失败 (文件为空)")

        resolved = str(output_path.resolve())
        self._file_cache[key] = resolved
        _log.info("新生成: %s", resolved)
        return resolved

    async def list_voices(self) -> list[dict]:
        """获取中文语音列表 (zh-CN-*)，带缓存。"""
        if self._voices_cache is not None:
            return self._voices_cache

        try:
            all_voices = await edge_tts.list_voices()
            chinese_voices = []
            for v in all_voices:
                if v.get("Locale", "").startswith("zh-CN"):
                    chinese_voices.append({
                        "name": v["ShortName"],
                        "friendly_name": v.get("LocalName", v["ShortName"]),
                        "gender": v.get("Gender", "Unknown"),
                    })
            if chinese_voices:
                self._voices_cache = chinese_voices
                return chinese_voices
        except Exception:
            pass

        # 网络不可用时返回预设列表
        self._voices_cache = _CHINESE_VOICES_FALLBACK
        return self._voices_cache

    def cleanup_old_files(self, max_age_hours: int = 24):
        """清理过期的临时音频文件。"""
        cutoff = time.time() - max_age_hours * 3600
        for f in self._cache_dir.glob("tts_*.mp3"):
            try:
                if f.stat().st_mtime < cutoff:
                    # 同步清理内存缓存
                    stem = f.stem
                    if stem.startswith("tts_"):
                        key = stem[4:]
                        self._file_cache.pop(key, None)
                    f.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    import sys

    text = sys.argv[1] if len(sys.argv) > 1 else "你好，这是一个测试"
    engine = TTSEngine(Path(__file__).parent.parent / "audio_cache")

    async def _test():
        voices = await engine.list_voices()
        print(f"可用中文语音 ({len(voices)} 个):")
        for v in voices:
            print(f"  {v['name']} - {v['friendly_name']} ({v['gender']})")
        path = await engine.synthesize(text)
        print(f"\n生成音频: {path}")

    asyncio.run(_test())
