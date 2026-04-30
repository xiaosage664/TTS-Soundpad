import asyncio
import logging
import time
from pathlib import Path

import edge_tts

from app import TTSGenerationError, TTSNetworkError

_log = logging.getLogger("tts_engine")

# zh-CN 语音中文友好名映射（API 返回的 LocalName 为空）
_FRIENDLY_NAMES: dict[str, str] = {
    "zh-CN-XiaoxiaoNeural":           "晓晓 (女声·温柔)",
    "zh-CN-XiaoyiNeural":             "晓伊 (女声·活泼)",
    "zh-CN-YunjianNeural":            "云健 (男声·沉稳)",
    "zh-CN-YunxiNeural":              "云希 (男声·年轻)",
    "zh-CN-YunxiaNeural":             "云夏 (男声·少年)",
    "zh-CN-YunyangNeural":            "云扬 (男声·新闻)",
    "zh-CN-liaoning-XiaobeiNeural":   "晓北 (女声·东北话)",
    "zh-CN-shaanxi-XiaoniNeural":     "晓妮 (女声·陕西话)",
}

# 中文语音预设 (离线 fallback)
_CHINESE_VOICES_FALLBACK = [
    {"name": k, "friendly_name": v, "gender": "Female" if "女声" in v else "Male"}
    for k, v in _FRIENDLY_NAMES.items()
]


class TTSEngine:
    def __init__(self, cache_dir: Path, default_voice: str = "zh-CN-XiaoxiaoNeural"):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._default_voice = default_voice
        self._voices_cache: list[dict] | None = None
        self._file_counter = 0

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> str:
        """将文字转换为语音 mp3 文件，返回绝对路径。"""
        voice = voice or self._default_voice
        text = text.strip()
        if not text:
            raise TTSGenerationError("文本不能为空")

        self._file_counter += 1
        filename = f"tts_{int(time.time())}_{self._file_counter}.mp3"
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
                    short = v["ShortName"]
                    friendly = _FRIENDLY_NAMES.get(short) or v.get("LocalName") or short
                    chinese_voices.append({
                        "name": short,
                        "friendly_name": friendly,
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
