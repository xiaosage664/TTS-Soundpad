import base64
import ctypes
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_LOCAL_MACHINE = 0x04

_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32

_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_wchar_p,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.POINTER(DATA_BLOB),
]
_crypt32.CryptProtectData.restype = ctypes.c_bool

_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(ctypes.c_wchar_p),
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.POINTER(DATA_BLOB),
]
_crypt32.CryptUnprotectData.restype = ctypes.c_bool

_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _bytes_to_blob(data: bytes) -> DATA_BLOB:
    if not data:
        return DATA_BLOB(0, None)
    buf = (ctypes.c_ubyte * len(data))(*data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.pbData or blob.cbData == 0:
        return b""
    return bytes(ctypes.cast(blob.pbData, ctypes.POINTER(ctypes.c_ubyte * blob.cbData)).contents)


def _protect(plain_text: str) -> bytes:
    in_blob = _bytes_to_blob(plain_text.encode("utf-8"))
    out_blob = DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "TTS_Soundpad_MiniMax_Key",
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN | _LOCAL_MACHINE,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return _blob_to_bytes(out_blob)
    finally:
        if out_blob.pbData:
            _kernel32.LocalFree(out_blob.pbData)


def _unprotect(cipher_bytes: bytes) -> str:
    in_blob = _bytes_to_blob(cipher_bytes)
    out_blob = DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return _blob_to_bytes(out_blob).decode("utf-8")
    finally:
        if out_blob.pbData:
            _kernel32.LocalFree(out_blob.pbData)


def _secret_path(config_dir: Path, name: str) -> Path:
    return config_dir / "secrets" / f"{name}.bin"


def save_secret(config_dir: Path, name: str, plain_text: str):
    path = _secret_path(config_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = _protect(plain_text)
    path.write_text(base64.b64encode(encrypted).decode("ascii"), encoding="utf-8")


def load_secret(config_dir: Path, name: str) -> str:
    path = _secret_path(config_dir, name)
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return ""
    encrypted = base64.b64decode(raw.encode("ascii"))
    return _unprotect(encrypted)


def delete_secret(config_dir: Path, name: str):
    path = _secret_path(config_dir, name)
    if path.exists():
        path.unlink()
