import datetime
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from sandbox_runner.config import DEFAULT_HISTORY_LIMIT, DEFAULT_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS, SUPPORTED_LANGUAGES
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
    language: Annotated[
        str,
        Field(
            description=(
                "Programming language of the snippet. Supported values: 'python' "
                "(runs in python:3.12-slim) and 'cpp' (compiled with g++ -std=c++17 -O2 "
                "then run in gcc:14). Case-insensitive."
            )
        ),
    ],
    code: Annotated[
        str,
        Field(
            description=(
                "The full source code to execute, as a single string. Max size 50 KB. "
                "For C++, this must be a complete, compilable program including a main() "
                "function and any necessary #include directives. For Python, this is "
                "executed directly as a standalone script."
            )
        ),
    ],
    timeout_seconds: Annotated[
        int,
        Field(
            description=(
                f"Maximum time in seconds to allow the code to run before it is force-"
                f"killed. Default {DEFAULT_TIMEOUT_SECONDS}, hard ceiling "
                f"{MAX_TIMEOUT_SECONDS} (requests above this are rejected). For C++, "
                f"this timeout applies to the run stage only, not the compile stage."
            )
        ),
    ] = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute a Python or C++ code snippet inside an isolated, network-disabled
    Docker container and return its output.

    Each run happens in a fresh, ephemeral container with no network access, a
    256 MB memory cap, a 0.5 CPU cap, and a read-only root filesystem. The
    container is destroyed immediately after the run. Use this tool to run
    untrusted or exploratory code snippets, verify that code works, or inspect
    program output, without touching the host machine.

    Returns a dict with:
    - status: one of "success", "error", "timeout", or "compile_error" (C++ only)
    - exit_code: the process exit code, or null if it never ran
    - stdout / stderr: captured output, truncated at 100 KB
    - duration_ms: wall-clock execution time in milliseconds
    - language: the normalized language that was actually run

    Note: this sandbox provides Docker-level isolation suitable for personal/
    local use. It is not a hardened multi-tenant sandbox and should not be
    used to run code from untrusted third parties in a production setting.
    """
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
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except Exception:
        pass
    return _format_result(result)


@mcp.tool()
def list_supported_languages() -> list[dict[str, str]]:
    """List every programming language this sandbox can execute, along with
    the Docker image used to run it.

    Call this first if you're unsure what values are valid for the
    `language` parameter of `run_code`. Takes no arguments.

    Returns a list of dicts, each with:
    - language: the identifier to pass to run_code (e.g. "python", "cpp")
    - image: the Docker image used to execute code in this language
    - description: a short human-readable description of the runtime
    """
    return [
        {
            "language": lang,
            "image": cfg["image"],
            "description": cfg["description"],
        }
        for lang, cfg in SUPPORTED_LANGUAGES.items()
    ]


@mcp.tool()
def get_execution_history(
    limit: Annotated[
        int,
        Field(
            description=(
                f"Maximum number of past runs to return, most recent first. "
                f"Default {DEFAULT_HISTORY_LIMIT}. Values below 1 are treated as 1."
            )
        ),
    ] = DEFAULT_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """Retrieve a log of recent code executions performed by run_code, most
    recent first.

    Useful for reviewing what code was run previously, checking whether a
    past run succeeded, or auditing recent sandbox activity. Only a preview
    (first 500 characters) of each snippet's code is stored, not the full
    source, and stdout/stderr are recorded as byte sizes only, not content.

    Returns a list of dicts, each with:
    - id: unique run identifier
    - timestamp: ISO 8601 UTC timestamp of when the run occurred
    - language: language that was executed
    - code_snippet: first 500 characters of the executed code
    - status: "success", "error", "timeout", or "compile_error"
    - exit_code: process exit code, or null
    - duration_ms: how long the run took, in milliseconds
    - stdout_size / stderr_size: byte counts of captured output
    """
    rows = fetch_history(limit=max(1, limit))
    for row in rows:
        row["timestamp"] = datetime.datetime.fromtimestamp(
            row["timestamp"], tz=datetime.timezone.utc
        ).isoformat()
    return rows
