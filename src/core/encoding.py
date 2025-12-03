import unicodedata
import json
from typing import Any


def _norm_str(s: Any) -> Any:
    if isinstance(s, str):
        try:
            return unicodedata.normalize("NFC", s)
        except Exception:
            return s
    return s


def normalize_obj(obj: Any) -> Any:
    """Recursively normalize all strings in obj to Unicode NFC."""
    if isinstance(obj, dict):
        return {k: normalize_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_obj(v) for v in obj]
    return _norm_str(obj)


def dumps_utf8(obj: Any) -> bytes:
    """Return UTF-8 bytes of JSON representation with normalized strings."""
    norm = normalize_obj(obj)
    return json.dumps(norm, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
