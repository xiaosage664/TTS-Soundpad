import io
import logging
import wave as wav
from pathlib import Path

from app import TTSGenerationError
from app.audio_cache import cache_path_for, make_cache_key, try_cache
from app.model_downloader import PIPER_ZH_VOICES, ensure_piper_voice

_log = logging.getLogger("piper_engine")

try:
    from piper.voice import PiperVoice

    HAS_PIPER = True
except ImportError:
    HAS_PIPER = False
    PiperVoice = None


class PiperEngine:
    """Piper TTS 本地离线引擎（基于 ONNX Runtime）。"""

    def __init__(
        self,
        cache_dir: Path,
        model_dir: Path | None = None,
        default_voice: str = "yanran",
        quality: str = "high",
    ):
        if not HAS_PIPER:
            raise ImportError(
                "piper-tts 未安装，请执行: pip install piper-tts"
            )

        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._model_dir = Path(model_dir) if model_dir else cache_dir.parent / "models"
        self._default_voice = default_voice
        self._quality = quality
        self._loaded: dict[str, PiperVoice] = {}

    @property
    def default_voice(self) -> str:
        return self._default_voice

    @default_voice.setter
    def default_voice(self, value: str):
        self._default_voice = value

    @property
    def quality(self) -> str:
        return self._quality

    @quality.setter
    def quality(self, value: str):
        if value not in ("high", "medium", "low"):
            raise ValueError(f"无效音质: {value}")
        self._quality = value

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        **kwargs,
    ) -> str:
        """合成语音，返回音频文件路径。

        Piper 特有参数（通过 kwargs）：
            quality       : str  音质 "high"/"medium"/"low"
            length_scale  : float 语速 (默认 1.0)
            noise_scale   : float 表现力 (默认 0.667)
            noise_w       : float 噪声权重 (默认 0.8)
        """
        voice = voice or self._default_voice
        text = text.strip()
        if not text:
            raise TTSGenerationError("文本不能为空")

        quality = kwargs.get("quality", self._quality)
        length_scale = kwargs.get("length_scale", 1.0)
        noise_scale = kwargs.get("noise_scale", 0.667)
        noise_w = kwargs.get("noise_w", 0.8)

        key = make_cache_key(
            "piper", text, voice,
            quality=quality,
            ls=f"{length_scale:.2f}",
            ns=f"{noise_scale:.3f}",
            nw=f"{noise_w:.2f}",
        )
        cached = try_cache(self._cache_dir, key, "piper")
        if cached:
            _log.info("Piper 缓存命中: %s", cached)
            return cached

        # 加载模型
        piper_voice = self._get_or_load_voice(voice, quality)

        # 合成到 WAV buffer
        buf = io.BytesIO()
        with wav.open(buf, "w") as wf:
            piper_voice.synthesize(
                text,
                wf,
                length_scale=length_scale,
                noise_scale=noise_scale,
                noise_w=noise_w,
            )

        # 写入缓存文件
        output_path = cache_path_for(self._cache_dir, key, "piper")
        output_path.write_bytes(buf.getvalue())

        if output_path.stat().st_size == 0:
            raise TTSGenerationError("Piper 生成的文件为空")

        resolved = str(output_path.resolve())
        _log.info("Piper 生成成功: %s", resolved)
        return resolved

    def _get_or_load_voice(self, voice_name: str, quality: str) -> PiperVoice:
        cache_key = f"{voice_name}_{quality}"
        if cache_key in self._loaded:
            return self._loaded[cache_key]

        onnx_path, config_path = ensure_piper_voice(
            self._model_dir, voice_name, quality
        )

        _log.info("加载 Piper 语音: %s", onnx_path)
        try:
            import onnxruntime as ort

            use_cuda = "CUDAExecutionProvider" in ort.get_available_providers()
        except Exception:
            use_cuda = False

        voice = PiperVoice.load(onnx_path, config_path=config_path, use_cuda=use_cuda)
        self._loaded[cache_key] = voice
        return voice

    async def list_voices(self) -> list[dict]:
        return [
            {
                "name": name,
                "friendly_name": desc,
                "gender": "Male" if "男声" in desc else "Female",
            }
            for name, desc in PIPER_ZH_VOICES.items()
        ]
