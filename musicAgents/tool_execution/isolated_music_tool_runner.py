import contextlib
import json
import sys
from typing import Any

_RESULT_PREFIX = "__CODEx_TOOL_RESULT__="


def _to_jsonable(value: Any):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return str(value)


def _emit(payload: dict[str, Any]) -> int:
    sys.stdout.write(f"{_RESULT_PREFIX}{json.dumps(payload, ensure_ascii=False)}")
    sys.stdout.flush()
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw or "{}")
    except Exception as exc:
        return _emit({"success": False, "error": f"invalid_worker_payload: {exc}"})

    tool_name = str(payload.get("tool_name") or "").strip()
    tool_args = payload.get("tool_args") if isinstance(payload.get("tool_args"), dict) else {}

    if not tool_name:
        return _emit({"success": False, "error": "missing_tool_name"})

    try:
        with contextlib.redirect_stdout(sys.stderr):
            from tools.MusicTools import musicTools

            tool = getattr(musicTools, tool_name, None)
            if tool is None or not hasattr(tool, "invoke"):
                raise RuntimeError(f"tool_not_found: {tool_name}")

            result = tool.invoke(tool_args)
        return _emit({"success": True, "result": _to_jsonable(result)})
    except BaseException as exc:
        return _emit(
            {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


if __name__ == "__main__":
    raise SystemExit(main())
