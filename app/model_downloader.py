import logging
import threading
from pathlib import Path
from typing import Callable

import requests

_log = logging.getLogger("model_downloader")

# ------------------------------------------------------------------
# Piper TTS 中文语音模型列表
# ------------------------------------------------------------------

PIPER_ZH_VOICES: dict[str, dict[str, str]] = {
    "yanran":         "嫣然 (女声·甜美)",
    "tingting_xin":   "婷婷-欣 (女声·温柔)",
    "xiaobei_local":  "晓北-本地 (女声·东北话)",
    "kefu_gui":       "客服-贵 (女声)",
    "yixuan_cn":      "逸轩 (男声·沉稳)",
}

PIPER_QUALITIES = ("high", "medium", "low")

PIPER_BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN"
)

# ------------------------------------------------------------------
# GPT-SoVITS 预训练模型 (HuggingFace)
# ------------------------------------------------------------------

GPT_SOVITS_REPO = "https://huggingface.co/lj1995/GPT-SoVITS-v2/resolve/main"

GPT_SOVITS_FILES = [
    "gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
    "gsv-v2final-pretrained/s2G2333k-v2.pth",
    "gsv-v2final-pretrained/chinese-roberta-wwm-ext/tokenizer.json",
    "gsv-v2final-pretrained/chinese-roberta-wwm-ext/vocab.txt",
    "gsv-v2final-pretrained/chinese-roberta-wwm-ext/config.json",
    "gsv-v2final-pretrained/chinese-roberta-wwm-ext/pytorch_model.bin",
    "gsv-v2final-pretrained/chinese-hubert-base/config.json",
    "gsv-v2final-pretrained/chinese-hubert-base/preprocessor_config.json",
    "gsv-v2final-pretrained/chinese-hubert-base/pytorch_model.bin",
    "gsv-v2final-pretrained/gsv-tokenizer/special_tokens_map.json",
    "gsv-v2final-pretrained/gsv-tokenizer/tokenizer_config.json",
    "gsv-v2final-pretrained/gsv-tokenizer/vocab.json",
    "gsv-v2final-pretrained/gsv-tokenizer/merges.txt",
]

# ------------------------------------------------------------------
# 下载进度回调
# ------------------------------------------------------------------

ProgressCallback = Callable[[str, int, int, str], None]


def _default_config_path() -> Path:
    import os
    import sys

    if getattr(sys, "frozen", False):
        root = Path(sys.executable).parent.resolve()
    else:
        root = Path(__file__).parent.parent.resolve()
    fallback = Path(
        os.environ.get("ProgramData", "C:/ProgramData")
    ) / "TTS_Soundpad" / "models"
    if all(ord(c) < 128 for c in str(root)):
        return root / "models"
    return fallback


# ------------------------------------------------------------------
# 通用下载工具
# ------------------------------------------------------------------

def _download_file(
    url: str,
    dest: Path,
    callback: ProgressCallback | None = None,
    label: str = "",
):
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        total = dest.stat().st_size
        if total > 0:
            if callback:
                callback(label, total, total, "已完成")
            return

    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))

        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if callback and total > 0:
                        callback(label, downloaded, total, "下载中")

    if callback:
        callback(label, total, total, "已完成")


# ------------------------------------------------------------------
# Piper 下载
# ------------------------------------------------------------------

def _check_piper_model(model_dir: Path, voice: str, quality: str) -> bool:
    onnx = model_dir / "zh_CN" / voice / quality / f"{voice}-{quality}.onnx"
    return onnx.exists() and onnx.stat().st_size > 0


def ensure_piper_voice(
    model_dir: Path,
    voice: str = "yanran",
    quality: str = "high",
    callback: ProgressCallback | None = None,
) -> tuple[str, str]:
    """确保指定 Piper 语音模型已下载。

    Returns:
        (onnx_path, config_path): 模型和配置文件的绝对路径
    """
    model_dir = Path(model_dir)
    dest_dir = model_dir / "zh_CN" / voice / quality
    dest_dir.mkdir(parents=True, exist_ok=True)

    onnx_name = f"{voice}-{quality}.onnx"
    json_name = f"{voice}-{quality}.onnx.json"

    for filename in (onnx_name, json_name):
        url = f"{PIPER_BASE_URL}/{voice}/{quality}/{filename}"
        dest = dest_dir / filename
        _download_file(url, dest, callback, f"Piper:{voice}/{quality}/{filename}")

    return str(dest_dir / onnx_name), str(dest_dir / json_name)


def download_all_piper_voices(
    model_dir: Path,
    quality: str = "high",
    callback: ProgressCallback | None = None,
) -> dict[str, tuple[str, str]]:
    result = {}
    for voice in PIPER_ZH_VOICES:
        try:
            result[voice] = ensure_piper_voice(model_dir, voice, quality, callback)
        except Exception as e:
            _log.warning("Piper 语音 %s 下载失败: %s", voice, e)
    return result


# ------------------------------------------------------------------
# GPT-SoVITS 下载
# ------------------------------------------------------------------

def ensure_gpt_sovits_models(
    model_dir: Path,
    callback: ProgressCallback | None = None,
) -> tuple[str, str]:
    """确保 GPT-SoVITS v2 预训练模型已下载。

    Returns:
        (gpt_ckpt_path, sovits_pth_path)
    """
    model_dir = Path(model_dir)
    dest_dir = model_dir / "gsv-v2final-pretrained"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for rel_path in GPT_SOVITS_FILES:
        url = f"{GPT_SOVITS_REPO}/{rel_path}"
        dest = dest_dir / rel_path.replace("gsv-v2final-pretrained/", "")
        _download_file(url, dest, callback, f"GPT-SoVITS:{rel_path}")

    gpt_ckpt = dest_dir / "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"
    sovits_pth = dest_dir / "s2G2333k-v2.pth"

    return str(gpt_ckpt), str(sovits_pth)


# ------------------------------------------------------------------
# 异步下载封装（在后台线程中执行）
# ------------------------------------------------------------------

def download_models_async(
    model_dir: Path,
    piper_voice: str = "yanran",
    piper_quality: str = "high",
    include_gpt_sovits: bool = True,
    on_progress: ProgressCallback | None = None,
    on_done: Callable[[], None] | None = None,
):
    """在后台线程中下载所有必要的模型。"""

    def _run():
        try:
            # Piper
            _log.info("开始下载 Piper 模型: %s (%s)", piper_voice, piper_quality)
            ensure_piper_voice(model_dir, piper_voice, piper_quality, on_progress)
            _log.info("Piper 模型下载完成")

            # GPT-SoVITS
            if include_gpt_sovits:
                _log.info("开始下载 GPT-SoVITS 预训练模型")
                ensure_gpt_sovits_models(model_dir, on_progress)
                _log.info("GPT-SoVITS 模型下载完成")

        except Exception as e:
            _log.error("模型下载失败: %s", e, exc_info=True)
        finally:
            if on_done:
                on_done()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
