from dataclasses import dataclass
import time
from pathlib import Path
import docker
from docker.errors import DockerException,ImageNotFound,NotFound
import tempfile


from sandbox_runner.config import( 
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CODE_SIZE_BYTES,
    SUPPORTED_LANGUAGES,
    MAX_OUTPUT_SIZE_BYTES,
    CPU_LIMIT,
    MEMORY_LIMIT,
    MAX_TIMEOUT_SECONDS
)

TRUNCATION_MARKER = "\n\n[... OUTPUT TRUNCATED ...]"


@dataclass
class ExecutionResult:
    status:str
    exit_code:int|None
    stdout:str
    stderr:str
    duration_ms:float
    language:str


def _docker_client():
    try:
        client=docker.from_env()
        client.ping()
        return client
    except DockerException as exc:
        raise RuntimeError(
            "Cannot connect to the Docker daemon. "
            "Please make sure Docker Desktop is running and try again.\n"
            f"Details: {exc}"
        ) from exc
    
def _truncate(text: str, max_bytes: int = MAX_OUTPUT_SIZE_BYTES) -> str:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="replace") + TRUNCATION_MARKER

def _run_container(
    client: docker.DockerClient,
    image: str,
    command: list[str],
    volumes: dict,
    timeout: int,
) -> tuple[str, str, int | None, bool]:
    """
    Run a container synchronously and return (stdout, stderr, exit_code, timed_out).
    Returns timed_out=True if the container had to be killed.
    """
    container = client.containers.run(
        image=image,
        command=command,
        volumes=volumes,
        mem_limit=MEMORY_LIMIT,
        nano_cpus=int(float(CPU_LIMIT) * 1e9),
        network_disabled=True,
        read_only=True,
        tmpfs={"/tmp": "size=64m,noexec"},  
        remove=False,
        detach=True,
        stdout=True,
        stderr=True,
    )
    timed_out = False
    try:
        result = container.wait(timeout=timeout)
        exit_code: int | None = result.get("StatusCode")
    except Exception:
        timed_out = True
        exit_code = None
        try:
            container.kill()
        except Exception:
            pass
    try:
        raw_stdout = container.logs(stdout=True, stderr=False)
        raw_stderr = container.logs(stdout=False, stderr=True)
    except Exception:
        raw_stdout = b""
        raw_stderr = b""
    try:
        container.remove(force=True)
    except Exception:
        pass
    stdout = _truncate(raw_stdout.decode("utf-8", errors="replace"))
    stderr = _truncate(raw_stderr.decode("utf-8", errors="replace"))
    return stdout, stderr, exit_code, timed_out


def validate_input(language: str, code: str, timeout_seconds: int) -> None:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language '{language}'. "
            f"Supported: {list(SUPPORTED_LANGUAGES.keys())}"
        )
    if not code.strip():
        raise ValueError("Code must be non-empty.")
    if len(code.encode()) > MAX_CODE_SIZE_BYTES:
        raise ValueError(
            f"Code exceeds maximum size of {MAX_CODE_SIZE_BYTES // 1024} KB."
        )
    if timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"Timeout cannot exceed {MAX_TIMEOUT_SECONDS} seconds."
        )

def _run_python(
    client: docker.DockerClient,
    code: str,
    timeout: int,
    tmpdir: Path,
) -> ExecutionResult:
    lang_cfg = SUPPORTED_LANGUAGES["python"]
    snippet_path = tmpdir / lang_cfg["file_name"]
    snippet_path.write_text(code, encoding="utf-8")
    volumes = {str(tmpdir): {"bind": "/scratch", "mode": "ro"}}
    start = time.monotonic()
    stdout, stderr, exit_code, timed_out = _run_container(
        client,
        image=lang_cfg["image"],
        command=lang_cfg["run_cmd"],
        volumes=volumes,
        timeout=timeout,
    )
    duration_ms = (time.monotonic() - start) * 1000
    if timed_out:
        status = "timeout"
    elif exit_code == 0:
        status = "success"
    else:
        status = "error"
    return ExecutionResult(
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        language="python",
    )

def _run_cpp(
    client:docker.DockerClient,
    code:str,
    timeout:int,
    tmpdir:Path,
)->ExecutionResult:
    lang_cfg = SUPPORTED_LANGUAGES["cpp"]
    source_path = tmpdir / lang_cfg["source_file"]
    source_path.write_text(code, encoding="utf-8")
    volumes = {str(tmpdir): {"bind": "/scratch", "mode": "rw"}}
    start = time.monotonic()
    compile_stdout, compile_stderr, compile_exit,compile_timeout = _run_container(
    client,
    image=lang_cfg["image"],
    command=lang_cfg["compile_cmd"],
    volumes=volumes,
    timeout=timeout,
)

    compile_duration_ms = (time.monotonic() - start) * 1000
    if compile_timeout:
        return ExecutionResult(
            status="timeout",
            exit_code=None,
            stdout=compile_stdout,
            stderr="[COMPILE STAGE TIMED OUT]\n" + compile_stderr,
            duration_ms=compile_duration_ms,
            language="cpp",
        )
    if compile_exit != 0:
        return ExecutionResult(
            status="compile_error",
            exit_code=compile_exit,
            stdout=compile_stdout,
            stderr=compile_stderr,
            duration_ms=compile_duration_ms,
            language="cpp",
        )

    run_volumes = {str(tmpdir): {"bind": "/scratch", "mode": "ro"}}
    run_stdout,run_stderr,run_exit,run_timeout=_run_container(
        client,
        image=lang_cfg["image"],
        command=lang_cfg["run_cmd"],
        volumes=run_volumes,
        timeout=timeout,
    )

    total_duration_ms = (time.monotonic() - start) * 1000
    if run_timeout:
        status = "timeout"
    elif run_exit == 0:
        status = "success"
    else:
        status = "error"
    return ExecutionResult(
        status=status,
        exit_code=run_exit,
        stdout=run_stdout,
        stderr=run_stderr,
        duration_ms=total_duration_ms,
        language="cpp",
    )

#Public API
def execute_code(
    language:str,
    code:str,
    timeout:int=DEFAULT_TIMEOUT_SECONDS,
)->ExecutionResult:
    client=_docker_client()
    validate_input(language,code,timeout)
    with tempfile.TemporaryDirectory(prefix="sandbox_") as td_str:
        tmpdir = Path(td_str)
        if language == "python":
            return  _run_python(client, code, timeout, tmpdir)
        elif language == "cpp":
            return _run_cpp(client, code, timeout, tmpdir)
        else:
            raise ValueError(f"Unsupported language: {language}")

