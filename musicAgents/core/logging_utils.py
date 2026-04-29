import logging
import os
from logging.handlers import TimedRotatingFileHandler


def setup_logging(
    *,
    log_dir: str | None = None,
    level: str | None = None,
    console: bool = True,
) -> None:
    """
    全局日志初始化（幂等）。
    - level: 默认读取环境变量 LOG_LEVEL，否则 INFO
    - log_dir: 默认 <repo>/logs
    """
    root = logging.getLogger()
    if root.handlers:
        return

    lvl = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    root.setLevel(getattr(logging, lvl, logging.INFO))

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)

    if log_dir is None:
        # <repo>/musicAgents/core/logging_utils.py -> <repo>/logs
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(repo_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "music_agent.log")

    fh = TimedRotatingFileHandler(log_path, when="midnight", backupCount=7, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

