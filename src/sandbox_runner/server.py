import datetime
from typing import Any
from mcp.server.fastmcp import FastMCP
from sandbox_runner.config import DEFAULT_HISTORY_LIMIT, DEFAULT_TIMEOUT_SECONDS, SUPPORTED_LANGUAGES
from sandbox_runner.database import fetch_history, record_run
from sandbox_runner.execution import ExecutionResult, execute_code
mcp = FastMCP(
    name="SandboxRunner",
    instructions=(
        "Execute Python and C++ code snippets in isolated Docker containers. "
        "Returns stdout, stderr, exit code, and timing information."
    ),
)

def _format_result(result: ExecutionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": round(result.duration_ms, 2),
        "language": result.language,
    }

@mcp.tool()
def run_code(
    language: str,
    code: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        result = execute_code(
            language=language.lower().strip(),
            code=code,
            timeout=timeout_seconds,
        )
    except (ValueError, RuntimeError) as exc:
        return {
            "status": "error",
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": 0.0,
            "language": language,
        }
    try:
        record_run(
            language=result.language,
            code_snippet=code,
            status=result.status,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            stdout_size=result.stdout,
            stderr_size=result.stderr,
        )
    except Exception:
        pass
    return _format_result(result)

@mcp.tool()
def list_supported_languages() -> list[dict[str, str]]:
    return [
        {
            "language": lang,
            "image": cfg["image"],
            "description": cfg["description"],
        }
        for lang, cfg in SUPPORTED_LANGUAGES.items()
    ]
@mcp.tool()
def get_execution_history(limit: int = DEFAULT_HISTORY_LIMIT) -> list[dict[str, Any]]:
    rows = fetch_history(limit=max(1, limit))
    for row in rows:
        row["timestamp"] = datetime.datetime.fromtimestamp(
            row["timestamp"], tz=datetime.timezone.utc
        ).isoformat()
    return rows