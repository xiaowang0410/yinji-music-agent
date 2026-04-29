import os
import random
import re
import threading

from env_settings import load_env


load_env()


class _NcmProcessEnv:
    def __init__(self, cnIp: str = "", ANONYMOUS_TOKEN: str = ""):
        self.cnIp = str(cnIp or "").strip()
        self.ANONYMOUS_TOKEN = str(ANONYMOUS_TOKEN or "").strip()


_ENV_LOCK = threading.RLock()
_CACHED_ENV: _NcmProcessEnv | None = None
_TOKEN_RE = re.compile(r"^[A-Fa-f0-9]{32,}$")
_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_MAX_SAFE_ANONYMOUS_TOKEN_LEN = 256
_CN_IP_PREFIXES = (
    1,
    14,
    27,
    36,
    39,
    42,
    43,
    47,
    58,
    59,
    60,
    61,
    101,
    103,
    106,
    110,
    111,
    112,
    113,
    114,
    115,
    116,
    117,
    118,
    119,
    120,
    121,
    122,
    123,
    124,
    125,
    139,
    140,
    144,
    150,
    153,
    163,
    171,
    175,
    180,
    182,
    183,
    202,
    203,
    210,
    211,
    218,
    219,
    220,
    221,
    222,
    223,
)


def _read_env_field(env: _NcmProcessEnv | None, field_name: str) -> str:
    if env is None:
        return ""
    try:
        value = getattr(env, field_name, "")
    except Exception:
        return ""
    return str(value or "").strip()


def _normalize_cn_ip(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if _IP_RE.fullmatch(text) else ""


def _normalize_anonymous_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in {"[object Object]", "undefined", "null"}:
        return ""
    if len(text) > _MAX_SAFE_ANONYMOUS_TOKEN_LEN:
        return ""
    return text if _TOKEN_RE.fullmatch(text) else ""


def _clone_env(env: _NcmProcessEnv | None) -> _NcmProcessEnv:
    return _NcmProcessEnv(
        cnIp=_normalize_cn_ip(_read_env_field(env, "cnIp")),
        ANONYMOUS_TOKEN=_normalize_anonymous_token(_read_env_field(env, "ANONYMOUS_TOKEN")),
    )


def _sync_process_env(env: _NcmProcessEnv | None) -> None:
    anonymous_token = _normalize_anonymous_token(_read_env_field(env, "ANONYMOUS_TOKEN"))
    cn_ip = _normalize_cn_ip(_read_env_field(env, "cnIp"))

    if anonymous_token:
        os.environ["ANONYMOUS_TOKEN"] = anonymous_token
    else:
        os.environ.pop("ANONYMOUS_TOKEN", None)

    if cn_ip:
        os.environ["cnIp"] = cn_ip
    else:
        os.environ.pop("cnIp", None)


def _env_score(env: _NcmProcessEnv | None) -> int:
    score = 0
    if _normalize_cn_ip(_read_env_field(env, "cnIp")):
        score += 1
    if _normalize_anonymous_token(_read_env_field(env, "ANONYMOUS_TOKEN")):
        score += 1
    return score


def _random_cn_ip() -> str:
    return ".".join(
        [
            str(random.choice(_CN_IP_PREFIXES)),
            str(random.randint(0, 255)),
            str(random.randint(0, 255)),
            str(random.randint(1, 254)),
        ]
    )


def _create_ncm_process_env() -> _NcmProcessEnv:
    anonymous_token = _normalize_anonymous_token(os.getenv("ANONYMOUS_TOKEN", ""))
    cn_ip = _normalize_cn_ip(os.getenv("cnIp", "")) or _random_cn_ip()
    env = _NcmProcessEnv(cnIp=cn_ip, ANONYMOUS_TOKEN=anonymous_token)
    _sync_process_env(env)

    print(
        "[NCM] Initialized process env "
        f"(anonymous_token={'yes' if anonymous_token else 'no'}, cnIp={'yes' if cn_ip else 'no'})"
    )
    return env


def get_ncm_process_env(force_refresh: bool = False) -> _NcmProcessEnv:
    global _CACHED_ENV

    try:
        with _ENV_LOCK:
            if not force_refresh and _env_score(_CACHED_ENV) >= 1:
                cached = _clone_env(_CACHED_ENV)
                _sync_process_env(cached)
                return cached

            fresh_env = _create_ncm_process_env()
            if _CACHED_ENV is None or _env_score(fresh_env) >= _env_score(_CACHED_ENV):
                _CACHED_ENV = _clone_env(fresh_env)

            cached = _clone_env(_CACHED_ENV)
            _sync_process_env(cached)
            return cached
    except Exception as exc:
        print(f"[警告] 初始化 NCM 环境失败: {exc}")
        return _NcmProcessEnv()
