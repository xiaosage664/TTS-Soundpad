import asyncio
import binascii
import logging
import time
from pathlib import Path

import aiohttp

from app import TTSGenerationError, TTSNetworkError

_log = logging.getLogger("minimax_engine")

# MiniMax 系统预设音色（API 获取失败时的兜底，基于 Speech 2.8 文档）
_PRESET_VOICES = [
    {"name": "Chinese (Mandarin)_Reliable_Executive", "friendly_name": "沉稳高管 (男声)", "gender": "Male"},
    {"name": "Chinese (Mandarin)_News_Anchor", "friendly_name": "新闻女声 (女声)", "gender": "Female"},
    {"name": "Chinese (Mandarin)_Lyrical_Voice", "friendly_name": "抒情女声", "gender": "Female"},
    {"name": "Chinese (Mandarin)_HK_Flight_Attendant", "friendly_name": "港普空乘 (女声)", "gender": "Female"},
    {"name": "male-qn-qingse", "friendly_name": "青涩 (青年男声)", "gender": "Male"},
    {"name": "female-shaonv", "friendly_name": "少女 (甜美少女)", "gender": "Female"},
    {"name": "English_Graceful_Lady", "friendly_name": "优雅女士 (英文)", "gender": "Female"},
    {"name": "English_Insightful_Speaker", "friendly_name": "洞见演说 (英文)", "gender": "Male"},
    {"name": "English_radiant_girl", "friendly_name": "元气少女 (英文)", "gender": "Female"},
    {"name": "English_Persuasive_Man", "friendly_name": "说服男士 (英文)", "gender": "Male"},
    {"name": "Japanese_Whisper_Belle", "friendly_name": "耳语少女 (日文)", "gender": "Female"},
]


class MiniMaxEngine:
    """MiniMax TTS 引擎（纯 aiohttp，无需额外 SDK）。"""

    # MiniMax API 限制：单次最多 10000 字符
    MAX_TEXT_LENGTH = 10000

    def __init__(
        self,
        cache_dir: Path,
        api_key: str = "",
        model: str = "speech-2.8-hd",
        default_voice: str = "Chinese (Mandarin)_Reliable_Executive",
    ):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._api_key = api_key
        self._model = model
        self._default_voice = default_voice
        self._file_counter = 0

    @property
    def api_key(self) -> str:
        return self._api_key

    @api_key.setter
    def api_key(self, value: str):
        self._api_key = value

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str):
        self._model = value

    # ------------------------------------------------------------------
    # 核心：语音合成
    # ------------------------------------------------------------------

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        **kwargs,
    ) -> str:
        """将文字转为语音，返回音频文件绝对路径。

        MiniMax 特有参数（通过 kwargs 传入）：
            speed : float  语速 0.5~2.0（默认 1.0）
            vol   : float  音量 0~10（默认 1.0）
            pitch : int    音调 -12~+12（默认 0）
        """
        voice = voice or self._default_voice
        text = text.strip()
        if not text:
            raise TTSGenerationError("文本不能为空")
        if len(text) > self.MAX_TEXT_LENGTH:
            raise TTSGenerationError(f"文本超过 {self.MAX_TEXT_LENGTH} 字符限制")

        if not self._api_key:
            raise TTSGenerationError("请先配置 MiniMax API Key")

        speed = kwargs.get("speed", 1.0)
        vol = kwargs.get("vol", 1.0)
        pitch = kwargs.get("pitch", 0)

        url = "https://api.minimaxi.com/v1/t2a_v2"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {
            "model": self._model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
            },
            "audio_setting": {
                "format": "mp3",
                "sample_rate": 32000,
            },
            "output_format": "hex",
        }

        _log.info(
            "MiniMax TTS text=%r voice=%s speed=%s vol=%s pitch=%s",
            text[:50], voice, speed, vol, pitch,
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise TTSGenerationError(
                            f"MiniMax API 返回 {resp.status}: {body[:200]}"
                        )
                    data = await resp.json()
        except aiohttp.ClientError as e:
            raise TTSNetworkError(f"MiniMax 网络请求失败: {e}") from e
        except TTSGenerationError:
            raise
        except Exception as e:
            raise TTSGenerationError(f"MiniMax 请求异常: {e}") from e

        # 检查业务状态码
        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code", -1)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "未知错误")
            raise TTSGenerationError(f"MiniMax API 错误 [{status_code}]: {status_msg}")

        # 解码 hex 音频
        try:
            audio_hex = data["data"]["audio"]
            audio_bytes = binascii.unhexlify(audio_hex)
        except (KeyError, binascii.Error, ValueError) as e:
            raise TTSGenerationError(f"MiniMax 音频解码失败: {e}") from e

        # 写入文件
        self._file_counter += 1
        filename = f"minimax_{int(time.time())}_{self._file_counter}.mp3"
        output_path = self._cache_dir / filename
        try:
            output_path.write_bytes(audio_bytes)
        except OSError as e:
            raise TTSGenerationError(f"音频文件写入失败: {e}") from e

        if output_path.stat().st_size == 0:
            raise TTSGenerationError("MiniMax 生成的文件为空")

        resolved = str(output_path.resolve())
        _log.info("MiniMax 生成成功: %s", resolved)
        return resolved

    # ------------------------------------------------------------------
    # 语音列表
    # ------------------------------------------------------------------

    async def list_voices(self) -> list[dict]:
        """返回 MiniMax 可用音色列表（从 API 动态获取，带本地缓存）。"""
        voices = await self._fetch_system_voices()
        if voices:
            return voices
        return list(_PRESET_VOICES)

    async def _fetch_system_voices(self) -> list[dict]:
        """调用 /v1/get_voice API 获取系统音色列表。"""
        if not self._api_key:
            return []
        url = "https://api.minimaxi.com/v1/get_voice"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {"voice_type": "system"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload
                ) as resp:
                    if resp.status != 200:
                        _log.warning("获取音色列表失败 HTTP %d", resp.status)
                        return []
                    data = await resp.json()
        except Exception as e:
            _log.warning("获取音色列表异常: %s", e)
            return []
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", -1) != 0:
            _log.warning("获取音色列表 API 错误: %s", base_resp)
            return []
        voices = []
        for v in data.get("system_voice", []):
            voice_id = v.get("voice_id", "")
            # voice_name 为空时用 voice_id 截取后半部分
            friendly = v.get("voice_name", "") or voice_id.rsplit("_", 1)[-1]
            voices.append({
                "name": voice_id,
                "friendly_name": f"{friendly} ({voice_id[:20]}...)",
                "gender": "Unknown",
            })
        return voices

    # ------------------------------------------------------------------
    # API Key 验证
    # ------------------------------------------------------------------

    async def verify_api_key(self) -> tuple[bool, str]:
        """验证 MiniMax API Key 是否有效。

        Returns:
            (True, "验证成功") 或 (False, "错误信息")
        """
        if not self._api_key:
            return False, "请先输入 API Key"

        url = "https://api.minimaxi.com/v1/t2a_v2"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {
            "model": self._model,
            "text": "测试",
            "stream": False,
            "voice_setting": {
                "voice_id": self._default_voice,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {"format": "mp3", "sample_rate": 32000},
            "output_format": "hex",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 401:
                        return False, "API Key 无效（401 未授权）"
                    if resp.status == 403:
                        return False, "API Key 无权限（403 禁止访问）"
                    if resp.status != 200:
                        return False, f"API 返回异常状态码: {resp.status}"

                    data = await resp.json()
                    base_resp = data.get("base_resp", {})
                    code = base_resp.get("status_code", -1)
                    if code == 0:
                        return True, "API Key 验证成功"
                    msg = base_resp.get("status_msg", "未知错误")
                    if code == 2054:
                        return True, "API Key 有效（音色 ID 需更新）"
                    return False, f"API 返回错误 [{code}]: {msg}"
        except aiohttp.ClientError as e:
            return False, f"网络请求失败: {e}"
        except Exception as e:
            return False, f"验证异常: {e}"

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def cleanup_old_files(self, max_age_hours: int = 24):
        """清理过期的 MiniMax 临时音频文件。"""
        cutoff = time.time() - max_age_hours * 3600
        for f in self._cache_dir.glob("minimax_*.mp3"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    import sys

    api_key = sys.argv[1] if len(sys.argv) > 1 else ""
    text = sys.argv[2] if len(sys.argv) > 2 else "你好，这是一个测试"
    engine = MiniMaxEngine(
        cache_dir=Path(__file__).parent.parent / "audio_cache",
        api_key=api_key,
    )

    async def _test():
        if not api_key:
            print("请提供 API Key: python minimax_engine.py <你的API_KEY>")
            return
        print("可用音色:")
        for v in await engine.list_voices():
            print(f"  {v['name']} - {v['friendly_name']} ({v['gender']})")
        path = await engine.synthesize(text, speed=1.0)
        print(f"\n生成音频: {path}")

    asyncio.run(_test())
