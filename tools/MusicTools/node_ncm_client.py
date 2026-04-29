import atexit
import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from env_settings import load_env


load_env()


_HOST = os.getenv("NCM_RPC_HOST", "127.0.0.1").strip() or "127.0.0.1"
_PORT = int(os.getenv("NCM_RPC_PORT", "37231").strip() or "37231")
_HEALTH_URL = f"http://{_HOST}:{_PORT}/health"
_CALL_URL = f"http://{_HOST}:{_PORT}/call"
_STARTUP_TIMEOUT_SECONDS = 20.0
_REQUEST_TIMEOUT = (10, 120)
_LOCK = threading.RLock()
_PROCESS: subprocess.Popen[str] | None = None

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_APP_ROOT = _REPO_ROOT / "agent_app"
_SIDECAR_SCRIPT = _AGENT_APP_ROOT / "scripts" / "ncm_rpc_server.mjs"
_LOG_DIR = _REPO_ROOT / "logs"
_STDOUT_LOG = _LOG_DIR / "ncm-node-provider.out.log"
_STDERR_LOG = _LOG_DIR / "ncm-node-provider.err.log"
_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
)


@dataclass
class Response:
    status: int
    body: Any
    cookie: Any = None


def _ensure_log_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _is_sidecar_ready() -> bool:
    try:
        response = requests.get(_HEALTH_URL, timeout=1.0)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _sanitized_sidecar_env() -> dict[str, str]:
    env = os.environ.copy()
    env["NCM_RPC_HOST"] = _HOST
    env["NCM_RPC_PORT"] = str(_PORT)
    env["NCM_RPC_DISABLE_PROXY"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for key in _PROXY_ENV_KEYS:
        env[key] = ""

    no_proxy_values = {
        value.strip()
        for value in str(env.get("NO_PROXY") or env.get("no_proxy") or "").split(",")
        if value.strip()
    }
    no_proxy_values.update({"127.0.0.1", "localhost"})
    env["NO_PROXY"] = ",".join(sorted(no_proxy_values))
    env["no_proxy"] = env["NO_PROXY"]
    return env


def _spawn_sidecar() -> subprocess.Popen[str]:
    if not _SIDECAR_SCRIPT.exists():
        raise RuntimeError(f"ncm_rpc_script_not_found: {_SIDECAR_SCRIPT}")

    _ensure_log_dir()
    stdout_handle = open(_STDOUT_LOG, "a", encoding="utf-8")
    stderr_handle = open(_STDERR_LOG, "a", encoding="utf-8")

    try:
        process = subprocess.Popen(
            ["node", str(_SIDECAR_SCRIPT)],
            cwd=str(_AGENT_APP_ROOT),
            env=_sanitized_sidecar_env(),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
    except Exception:
        stdout_handle.close()
        stderr_handle.close()
        raise
    stdout_handle.close()
    stderr_handle.close()
    return process


def _wait_for_sidecar(process: subprocess.Popen[str] | None) -> None:
    deadline = time.time() + _STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        if _is_sidecar_ready():
            return
        if process is not None and process.poll() is not None:
            if _is_sidecar_ready():
                return
            raise RuntimeError(f"ncm_sidecar_exited_early: returncode={process.returncode}")
        time.sleep(0.25)

    if _is_sidecar_ready():
        return
    raise RuntimeError("ncm_sidecar_start_timeout")


def ensure_sidecar() -> None:
    global _PROCESS

    with _LOCK:
        if _is_sidecar_ready():
            return

        if _PROCESS is not None and _PROCESS.poll() is None:
            _wait_for_sidecar(_PROCESS)
            return

        if _is_port_open(_HOST, _PORT):
            _wait_for_sidecar(None)
            return

        _PROCESS = _spawn_sidecar()
        _wait_for_sidecar(_PROCESS)


def shutdown_sidecar() -> None:
    global _PROCESS

    with _LOCK:
        process = _PROCESS
        _PROCESS = None
        if process is None:
            return
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


atexit.register(shutdown_sidecar)


def _prepare_params(params: dict[str, Any] | None, env: Any) -> dict[str, Any]:
    payload = dict(params or {})
    if env is not None:
        payload["__env"] = {
            "cnIp": str(getattr(env, "cnIp", "") or "").strip(),
            "ANONYMOUS_TOKEN": str(getattr(env, "ANONYMOUS_TOKEN", "") or "").strip(),
        }
    return payload


def call_method(method: str, params: dict[str, Any] | None = None, env: Any = None) -> Response:
    ensure_sidecar()

    request_payload = {
        "method": str(method or "").strip(),
        "params": _prepare_params(params, env),
    }

    try:
        response = requests.post(_CALL_URL, json=request_payload, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"ncm_sidecar_request_failed: {exc}") from exc

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ncm_sidecar_invalid_json: {response.text[:200]}") from exc

    if response.status_code >= 400 or not bool(payload.get("ok")):
        error_message = str(payload.get("error") or f"http_{response.status_code}").strip()
        raise RuntimeError(f"ncm_sidecar_call_failed: {error_message}")

    return Response(
        status=int(payload.get("status") or 200),
        body=payload.get("body"),
        cookie=payload.get("cookie"),
    )


class NeteaseCloudMusicApi:
    def __init__(self, env: Any = None):
        self.env = env
        self.cookie: Any = {}

    def set_cookie(self, cookie: Any):
        self.cookie = cookie or {}

    def destroy(self):
        return None

    def request(self, path, cookie=None, env=None, **query) -> Response:
        method = str(path or "").strip().strip("/").replace("/", "_")
        if not method:
            raise ValueError("missing_request_path")

        params = dict(query)
        effective_cookie = self.cookie if cookie in (None, {}) else cookie
        if effective_cookie:
            params["cookie"] = effective_cookie
        return call_method(method, params=params, env=env or self.env)

    def __getattr__(self, method_name: str):
        if not str(method_name or "").strip():
            raise AttributeError(method_name)

        def _call(*args, **kwargs):
            if args:
                if method_name == "set_cookie" and len(args) == 1 and not kwargs:
                    self.set_cookie(args[0])
                    return None
                raise TypeError(
                    f"{method_name} only supports keyword arguments in the node compatibility client"
                )

            params = dict(kwargs)
            if "cookie" not in params and self.cookie:
                params["cookie"] = self.cookie
            return call_method(method_name, params=params, env=self.env)

        return _call
