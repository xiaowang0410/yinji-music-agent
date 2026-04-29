from __future__ import annotations

import os
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_ENV_FILES = (
    _REPO_ROOT / ".env",
    _REPO_ROOT / "agent_app" / ".env",
)
_DEFAULT_LOADED = False


def _strip_wrapping_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _parse_env_line(line: str) -> tuple[str, str] | None:
    text = str(line or "").strip()
    if not text or text.startswith("#"):
        return None
    if text.startswith("export "):
        text = text[7:].strip()
    if "=" not in text:
        return None

    key, value = text.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, _strip_wrapping_quotes(value)


def _iter_existing_env_files(*extra_files: str | os.PathLike[str]) -> list[Path]:
    files: list[Path] = [*(_DEFAULT_ENV_FILES)]
    for extra in extra_files:
        if extra:
            files.append(Path(extra))
    return [path for path in files if path.exists() and path.is_file()]


def load_env(*extra_files: str | os.PathLike[str]) -> None:
    global _DEFAULT_LOADED

    if not extra_files and _DEFAULT_LOADED:
        return

    for env_file in _iter_existing_env_files(*extra_files):
        try:
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                parsed = _parse_env_line(raw_line)
                if not parsed:
                    continue
                key, value = parsed
                os.environ.setdefault(key, value)
        except OSError:
            continue

    if not extra_files:
        _DEFAULT_LOADED = True


def get_first_env(*names: str, default: str = "") -> str:
    load_env()
    for name in names:
        if not name:
            continue
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default
