# SandboxRunner 🐳

**SandboxRunner** is a custom [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that enables AI assistants and MCP-compatible clients to securely execute **Python** and **C++** code snippets inside disposable, isolated Docker containers — and receive back structured results (stdout, stderr, exit code, and timing) in real time.

> Built to understand MCP server design, Docker-based process isolation, and security-boundary thinking from the ground up.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [MCP Tools](#mcp-tools)
- [Isolation & Resource Limits](#isolation--resource-limits)
- [Execution History](#execution-history)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [Known Limitations](#known-limitations)
- [Contributing](#contributing)

---

## Features

- ✅ **Python execution** — runs snippets inside `python:3.12-slim`
- ✅ **C++ execution** — two-stage compile (`g++ -std=c++17 -O2`) + run, using `gcc:14`
- ✅ **Strong isolation per run**:
  - No network access (`--network none`)
  - Hard memory cap (default `256m`)
  - Hard CPU cap (default `0.5` cores)
  - Read-only root filesystem with a temporary scratch-only mount
  - `noexec` tmpfs for `/tmp`
  - Containers are ephemeral — deleted after every run
- ✅ **Independent timeout enforcement** — a hung snippet cannot hang the MCP server; the container is force-killed on timeout
- ✅ **Output size capping** — stdout/stderr truncated at 100 KB with a clear marker
- ✅ **Distinct compile vs. runtime errors** for C++ — compiler errors are surfaced separately from runtime crashes
- ✅ **Local execution history** — every run is logged to a local SQLite database and queryable via MCP
- ✅ **Actionable Docker errors** — clear error message if Docker is not running, instead of a silent hang
- ✅ **All tunables in one place** — `config.py` is the single source of truth for limits, images, and settings

---

## Architecture

```
MCP Client ──(stdio / sse)──▶  SandboxRunner (FastMCP)
                                       │
                                       ▼
                             execution.py (orchestration)
                                       │
                         ┌─────────────┴─────────────┐
                         ▼                           ▼
              Docker (Python)              Docker (C++)
           python:3.12-slim             gcc:14 container
           --network none               --network none
           --memory 256m                --memory 256m
           --cpus 0.5                   --cpus 0.5
           --read-only                  Stage 1: compile (rw /scratch)
                                        Stage 2: run     (ro /scratch)
                                       │
                                       ▼
                          database.py → sandbox_history.db (SQLite)
```

### Per-execution flow (`run_code`)

1. Validates input — language, code size, timeout ceiling
2. Writes code to a temporary host directory
3. Mounts that directory into a fresh Docker container as `/scratch`
4. **Python**: runs `python /scratch/snippet.py` directly
5. **C++**: compiles to `/scratch/a.out` (read-write mount), then runs the binary (read-only mount) in a second container — compile errors are returned distinctly from runtime errors
6. Enforces timeout at the server level; kills the container if exceeded
7. Captures and truncates stdout/stderr
8. Logs run metadata to SQLite
9. Returns a structured result to the MCP client

---

## Requirements

- **Python ≥ 3.12**
- **[uv](https://docs.astral.sh/uv/)** — package manager (`pip install uv` or see [uv docs](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker Desktop or Docker Engine** — must be installed and running
- Docker images (pre-pull recommended):
  - `python:3.12-slim`
  - `gcc:14`

### Python Dependencies

| Package | Purpose |
|---|---|
| `mcp[cli] >= 1.28.1` | Official MCP SDK (FastMCP server + CLI) |
| `docker >= 7.1.0` | Docker SDK — container orchestration |

**Dev only:**

| Package | Purpose |
|---|---|
| `pytest >= 9.1.1` | Test runner |
| `pytest-asyncio >= 1.4.0` | Async test support |

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/sandbox-runner.git
cd sandbox-runner

# 2. Ensure Docker is running
docker ps

# 3. Install dependencies and create the virtual environment
uv sync

# 4. Pre-pull the Docker images (avoids slow cold start on first run)
docker pull python:3.12-slim
docker pull gcc:14
```

The `sandbox-runner` console script is installed automatically via `[project.scripts]` in `pyproject.toml`.

---

## Configuration

All tunables live in **`src/sandbox_runner/config.py`**. No environment variables are required beyond the optional transport flag.

| Setting | Default | Description |
|---|---|---|
| `DEFAULT_TIMEOUT_SECONDS` | `10` | Default execution timeout |
| `MAX_TIMEOUT_SECONDS` | `30` | Hard ceiling — cannot be exceeded by callers |
| `MEMORY_LIMIT` | `"256m"` | Per-container memory cap |
| `CPU_LIMIT` | `"0.5"` | Per-container CPU share (in cores) |
| `MAX_CODE_SIZE_BYTES` | `51200` (50 KB) | Maximum allowed snippet size |
| `MAX_OUTPUT_SIZE_BYTES` | `102400` (100 KB) | Output truncation threshold |
| `DB_FILE` | `"sandbox_history.db"` | SQLite file for execution history |
| `DEFAULT_HISTORY_LIMIT` | `20` | Default rows returned by history tool |

To **add a new language**, add an entry to `SUPPORTED_LANGUAGES` in `config.py` with an `image`, `run_cmd`, and optionally `compile_cmd` / `source_file` for compiled languages.

---

## MCP Tools

| Tool | Description | Inputs | Outputs |
|---|---|---|---|
| `run_code` | Execute a code snippet in an isolated container | `language` (`python`\|`cpp`), `code`, `timeout_seconds` (opt, default `10`, max `30`) | `status`, `exit_code`, `stdout`, `stderr`, `duration_ms`, `language` |
| `list_supported_languages` | List available languages and Docker images | — | `[{language, image, description}]` |
| `get_execution_history` | Retrieve recent run records | `limit` (opt, default `20`) | `[{id, timestamp, language, code_snippet, status, exit_code, duration_ms, stdout_size, stderr_size}]` |

**`status` values:** `success` · `error` · `timeout` · `compile_error` (C++ only)

**Example `run_code` response:**

```json
{
  "status": "success",
  "exit_code": 0,
  "stdout": "The sum of elements is: 15\n",
  "stderr": "",
  "duration_ms": 1823.47,
  "language": "cpp"
}
```

---

## Isolation & Resource Limits

Each run is sandboxed with the following Docker constraints:

| Constraint | Value | Effect |
|---|---|---|
| `--network none` | Enforced | No outbound or inbound network access |
| `--memory 256m` | Configurable | Hard memory ceiling per container |
| `--cpus 0.5` | Configurable | CPU share cap |
| `--read-only` | Always on | Root filesystem is immutable |
| `tmpfs /tmp` | `size=64m,noexec` | Small, non-executable temp space |
| `--rm` | Always on | Container is deleted after each run |
| Timeout kill | Server-level | Server kills container if it exceeds timeout |

> ⚠️ This uses Docker-level isolation — suitable for personal/local use. It is **not** a hardened multi-tenant sandbox (e.g. gVisor, Firecracker) and is **not** intended for running untrusted third-party code.

---

## Execution History

Every run is stored in a local SQLite database (`sandbox_history.db`):

```sql
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    REAL    NOT NULL,
    language     TEXT    NOT NULL,
    code_snippet TEXT    NOT NULL,   -- first 500 chars only
    status       TEXT    NOT NULL,
    exit_code    INTEGER,
    duration_ms  REAL    NOT NULL,
    stdout_size  INTEGER NOT NULL DEFAULT 0,
    stderr_size  INTEGER NOT NULL DEFAULT 0
);
```

- Only the **first 500 characters** of each snippet are persisted as a preview.
- `stdout_size` / `stderr_size` store byte counts, not the full content.
- Timestamps are returned as **ISO 8601 UTC** strings via the `get_execution_history` tool.

---

## Usage

### Registering with an MCP Client

Add SandboxRunner to your MCP client's configuration. Example for **Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sandbox-runner": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/sandbox-runner",
        "run",
        "sandbox-runner"
      ]
    }
  }
}
```

> Replace `/absolute/path/to/sandbox-runner` with your actual cloned directory path.  
> On Windows: `C:\\Users\\YourName\\path\\to\\sandbox-runner`

Restart the MCP client after saving the config. The three tools will become available immediately.

### Running Standalone

```bash
# Start with stdio transport (default — for MCP clients like Claude Desktop)
uv run sandbox-runner

# Start with SSE transport (for web-based or HTTP MCP clients)
uv run sandbox-runner --transport sse

# View CLI help
uv run sandbox-runner --help
```

---

## Project Structure

```
sandbox-runner/
├── src/
│   └── sandbox_runner/
│       ├── __init__.py       # Package version
│       ├── config.py         # All tunables — limits, images, DB path
│       ├── database.py       # SQLite connection, record_run, fetch_history
│       ├── execution.py      # Docker orchestration, validation, truncation
│       ├── main.py           # CLI entrypoint (argparse + transport)
│       └── server.py         # FastMCP server + tool definitions
├── tests/
│   ├── test_execution.py     # Input validation + mocked Docker execution tests
│   └── test_server.py        # Mocked MCP tool-level tests
├── pyproject.toml            # Project metadata, deps, build config
├── uv.lock                   # Locked dependency tree
├── .python-version           # Pinned Python version
├── sandbox_history.db        # SQLite history (auto-created at runtime)
└── README.md
```

---

## Testing

The test suite uses mocked Docker calls — **Docker does not need to be running** to run the tests.

```bash
uv run pytest
```

**Current coverage:**

- `test_execution.py`
  - Valid input passes without errors
  - Unsupported language raises `ValueError`
  - Empty code raises `ValueError`
  - Oversized code raises `ValueError`
  - Timeout exceeding max raises `ValueError`
  - Mocked end-to-end Python execution — asserts `status == "success"` and correct stdout

- `test_server.py`
  - `run_code` success path — verifies result format and DB logging call
  - `run_code` invalid language — verifies error response and that DB is **not** written
  - `list_supported_languages` — returns entries for both `python` and `cpp`
  - `get_execution_history` — timestamps formatted as ISO 8601 strings

---

## Roadmap

- [ ] Mocked tests for the C++ two-stage compile/run flow
- [ ] Mocked timeout/kill path tests
- [ ] Per-request resource overrides within a configurable ceiling
- [ ] Support for additional languages (Node.js, Rust, Go)
- [ ] Optional full stdout/stderr retention in history
- [ ] CI pipeline (GitHub Actions)
- [ ] Container pre-warming to reduce cold-start latency

---

## Known Limitations

- **Docker must be running.** The server returns a clear error if the Docker daemon is unreachable — no silent hangs.
- **Docker-level isolation only.** Not a hardened cloud-grade sandbox. Designed for single-user, local use.
- **No multi-tenancy.** No auth, no rate limiting — assumes a single trusted operator.
- **Fixed resource limits by default.** 256 MB / 0.5 CPU / 10s default timeout may be restrictive for heavy compute workloads.
- **History stores only snippet previews.** Full code content is not persisted; only the first 500 characters are stored.

---

## Contributing

Contributions are welcome!

1. Fork the repo and create a feature branch
2. Run `uv run pytest` and ensure all tests pass
3. Keep new tunables in `config.py` — avoid hardcoding values elsewhere
4. Open a Pull Request with a clear description of the change and its motivation

---

