import logging
from pathlib import Path

from app import TTSGenerationError
from app.audio_cache import cache_path_for, make_cache_key, try_cache
from app.model_downloader import ensure_gpt_sovits_models

_log = logging.getLogger("gpt_sovits_engine")

try:
    import numpy as np
    import soundfile as sf
    import torch
    from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

    HAS_GPT_SOVITS = True
except ImportError:
    HAS_GPT_SOVITS = False
    TTS = None
    TTS_Config = None

_LANG_MAP = {
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "yue": "粤语",
}


class GPTSoVITSEngine:
    """GPT-SoVITS 零样本语音克隆引擎。

    需要先安装 GPT-SoVITS：
      pip install git+https://github.com/RVC-Boss/GPT-SoVITS.git@v2

    模型首次运行自动从 HuggingFace 下载。
    """

    def __init__(
        self,
        cache_dir: Path,
        model_dir: Path | None = None,
        config_path: str = "",
        gpt_model_path: str = "",
        sovits_model_path: str = "",
        device: str = "auto",
    ):
        if not HAS_GPT_SOVITS:
            raise ImportError(
                "GPT-SoVITS 未安装，请执行:\n"
                "  pip install git+https://github.com/RVC-Boss/GPT-SoVITS.git@v2"
            )

        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._model_dir = Path(model_dir) if model_dir else cache_dir.parent / "models"

        if device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device
        self._is_half = self._device == "cuda"

        self._gpt_model_path = gpt_model_path
        self._sovits_model_path = sovits_model_path
        self._config_path = config_path

        self._tts: TTS | None = None
        self._loaded = False

    def _ensure_models(self):
        if self._gpt_model_path and self._sovits_model_path:
            return

        gpt_ckpt = self._model_dir / "gsv-v2final-pretrained" / \
            "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"
        sovits_pth = self._model_dir / "gsv-v2final-pretrained" / \
            "s2G2333k-v2.pth"

        if gpt_ckpt.exists() and sovits_pth.exists():
            self._gpt_model_path = str(gpt_ckpt)
            self._sovits_model_path = str(sovits_pth)
        else:
            _log.info("GPT-SoVITS 模型未找到，开始自动下载...")
            self._gpt_model_path, self._sovits_model_path = \
                ensure_gpt_sovits_models(self._model_dir)

    def _get_config_path(self) -> str:
        if self._config_path and Path(self._config_path).exists():
            return self._config_path

        import GPT_SoVITS

        gpt_sovits_root = Path(GPT_SoVITS.__file__).parent
        config_path = gpt_sovits_root / "configs" / "tts_infer.yaml"
        if config_path.exists():
            return str(config_path)

        raise TTSGenerationError(
            "找不到 GPT-SoVITS 配置文件 configs/tts_infer.yaml\n"
            "请设置 config_path 参数"
        )

    def init_model(self):
        if self._loaded:
            return

        self._ensure_models()

        config = TTS_Config(self._get_config_path())
        config.device = self._device
        config.is_half = self._is_half
        config.gpt_model_path = self._gpt_model_path
        config.sovits_model_path = self._sovits_model_path

        self._tts = TTS(config)
        self._tts.init_model(
            gpt_model_path=self._gpt_model_path,
            sovits_model_path=self._sovits_model_path,
        )
        self._loaded = True
        _log.info(
            "GPT-SoVITS 模型加载完成 (device=%s, half=%s)",
            self._device, self._is_half,
        )

    @property
    def is_ready(self) -> bool:
        return self._loaded and self._tts is not None

    @property
    def device(self) -> str:
        return self._device

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        **kwargs,
    ) -> str:
        """零样本语音合成，返回音频文件路径。

        GPT-SoVITS 特有参数：
            ref_audio_path : str   参考音频路径（必需）
            prompt_text    : str   参考音频对应文本（强烈建议提供）
            prompt_lang    : str   参考音频语言 "zh"/"en"/"ja"/"ko"/"yue"
            text_lang      : str   目标文本语言
            top_k          : int   (默认 15)
            top_p          : float (默认 0.8)
            temperature    : float (默认 0.8)
            speed_factor   : float 语速因子 (默认 1.0)
        """
        text = text.strip()
        if not text:
            raise TTSGenerationError("文本不能为空")

        ref_audio_path = kwargs.get("ref_audio_path", "")
        if not ref_audio_path:
            raise TTSGenerationError("GPT-SoVITS 需要提供参考音频 (ref_audio_path)")

        ref_path = Path(ref_audio_path)
        if not ref_path.exists():
            raise TTSGenerationError(f"参考音频不存在: {ref_audio_path}")

        prompt_text = kwargs.get("prompt_text", "")
        prompt_lang = kwargs.get("prompt_lang", "zh")
        text_lang = kwargs.get("text_lang", "zh")
        top_k = kwargs.get("top_k", 15)
        top_p = kwargs.get("top_p", 0.8)
        temperature = kwargs.get("temperature", 0.8)
        speed_factor = kwargs.get("speed_factor", 1.0)

        key = make_cache_key(
            "gpt-sovits", text, ref_audio_path,
            pt=prompt_text[:100],
            pl=prompt_lang,
            tl=text_lang,
            tk=str(top_k),
            tp=str(top_p),
            te=str(temperature),
            sp=str(speed_factor),
        )
        cached = try_cache(self._cache_dir, key, "gpt-sovits")
        if cached:
            _log.info("GPT-SoVITS 缓存命中: %s", cached)
            return cached

        if not self.is_ready:
            self.init_model()

        _log.info(
            "GPT-SoVITS 合成 text=%r lang=%s ref=%s",
            text[:50], text_lang, ref_path.name,
        )

        sr, audio = self._tts.run(
            text=text,
            text_lang=text_lang,
            ref_audio_path=str(ref_path),
            prompt_lang=prompt_lang,
            prompt_text=prompt_text,
            top_k=top_k,
            top_p=top_p,
            temperature=temperature,
            speed_factor=speed_factor,
        )

        output_path = cache_path_for(self._cache_dir, key, "gpt-sovits")
        sf.write(str(output_path), audio, sr)

        if output_path.stat().st_size == 0:
            raise TTSGenerationError("GPT-SoVITS 生成的文件为空")

        resolved = str(output_path.resolve())
        _log.info("GPT-SoVITS 生成成功: %s", resolved)
        return resolved

    async def list_voices(self) -> list[dict]:
        return [
            {
                "name": "zero-shot-clone",
                "friendly_name": "零样本语音克隆 (通过参考音频)",
                "gender": "Unknown",
            }
        ]

    @staticmethod
    def supported_languages() -> list[dict]:
        return [
            {"code": k, "name": v} for k, v in _LANG_MAP.items()
        ]
