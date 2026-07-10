import pytest
from unittest.mock import MagicMock,patch
from sandbox_runner.execution import execute_code
from sandbox_runner.execution import (
    validate_input,
    MAX_CODE_SIZE_BYTES,
    MAX_TIMEOUT_SECONDS,
)


def test_valid_input_succeeds():
    validate_input("python", "print('hello')", 10)

def test_unsupported_language_raises_error():
    with pytest.raises(ValueError, match="Unsupported language"):
        validate_input("ruby", "puts 'hi'", 10)

def test_empty_code_raises_error():
    with pytest.raises(ValueError, match="Code must be non-empty"):
        validate_input("python", "   ", 10)

def test_code_too_large_raises_error():
    large_code = "a" * (MAX_CODE_SIZE_BYTES + 1)
    with pytest.raises(ValueError, match="Code exceeds maximum size"):
        validate_input("python", large_code, 10)

def test_timeout_too_large_raises_error():
    with pytest.raises(ValueError, match="Timeout cannot exceed"):
        validate_input("python", "print(1)", MAX_TIMEOUT_SECONDS + 1)

@patch("sandbox_runner.execution.docker")
def test_execute_python_mocked(mock_docker):
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.ping.return_value = True
    
    mock_container = MagicMock()
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = lambda **kwargs: b"Hello Mocked" if kwargs.get("stdout") else b""
    mock_client.containers.run.return_value = mock_container

    from sandbox_runner.execution import execute_code
    result = execute_code("python", "print('Hello Mocked')", 10)
    
    assert result.status == "success"
    assert result.exit_code == 0
    assert "Hello Mocked" in result.stdout




