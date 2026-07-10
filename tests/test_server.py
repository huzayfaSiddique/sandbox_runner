from unittest.mock import patch
from sandbox_runner.execution import ExecutionResult

def _make_result(status="success", exit_code=0, stdout="ok\n", stderr="", duration_ms=120.0):
    return ExecutionResult(
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        language="python",
    )

@patch("sandbox_runner.server.record_run")
@patch("sandbox_runner.server.execute_code")
def test_run_code_success(mock_exec, mock_record):
    mock_exec.return_value = _make_result()
    mock_record.return_value = 1

    from sandbox_runner.server import run_code
    result = run_code(language="python", code="print('ok')", timeout_seconds=10)

    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert "ok" in result["stdout"]
    mock_exec.assert_called_once()
    mock_record.assert_called_once()

@patch("sandbox_runner.server.record_run")
@patch("sandbox_runner.server.execute_code")
def test_run_code_invalid_language(mock_exec, mock_record):
    mock_exec.side_effect = ValueError("Unsupported language 'ruby'.")

    from sandbox_runner.server import run_code
    result = run_code(language="ruby", code="puts 'hi'", timeout_seconds=10)

    assert result["status"] == "error"
    assert "Unsupported language" in result["stderr"]
    mock_record.assert_not_called()

def test_list_supported_languages():
    from sandbox_runner.server import list_supported_languages
    langs = list_supported_languages()
    lang_names = [l["language"] for l in langs]
    assert "python" in lang_names
    assert "cpp" in lang_names

@patch("sandbox_runner.server.fetch_history")
def test_get_execution_history(mock_fetch):
    mock_fetch.return_value = [
        {
            "id": 1,
            "timestamp": 1700000000.0,
            "language": "python",
            "code_snippet": "print(1)",
            "status": "success",
            "exit_code": 0,
            "duration_ms": 110.5,
            "stdout_size": 3,
            "stderr_size": 0,
        }
    ]

    from sandbox_runner.server import get_execution_history
    history = get_execution_history(limit=1)

    assert len(history) == 1
    assert history[0]["language"] == "python"
    assert "T" in history[0]["timestamp"]
