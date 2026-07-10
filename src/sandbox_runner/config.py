"""
Configuration and hardcoded limits for SandboxRunner.
All tunable settings live here so they are easy to find and adjust.
"""
# ── Language / image registry ────────────────────────────────────────────────
SUPPORTED_LANGUAGES: dict[str, dict] = {
    "python": {
        "image": "python:3.12-slim",
        "description": "CPython 3.12 (slim)",
        "run_cmd": ["python", "/scratch/snippet.py"],
        "file_name": "snippet.py",
    },
    "cpp": {
        "image": "gcc:14",
        "description": "GCC 14 (C++17)",
        "source_file": "snippet.cpp",
        "compile_cmd": [
            "g++", "-std=c++17", "-O2",
            "/scratch/snippet.cpp",
            "-o", "/scratch/a.out",
        ],
        "run_cmd": ["/scratch/a.out"],
    },
}
# ── Resource limits ──────────────────────────────────────────────────────────
DEFAULT_TIMEOUT_SECONDS: int = 10
MAX_TIMEOUT_SECONDS: int = 30
MEMORY_LIMIT: str = "256m"
CPU_LIMIT: str = "0.5"
MAX_CODE_SIZE_BYTES: int = 50 * 1024
MAX_OUTPUT_SIZE_BYTES: int = 100 * 1024
DB_FILE: str = "sandbox_history.db"
DEFAULT_HISTORY_LIMIT: int = 20