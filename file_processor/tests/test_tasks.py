import asyncio
from pathlib import Path

import pytest

from app import tasks


class FakeStream:
    """Small async stream double for subprocess stdout/stderr."""

    def __init__(self, lines):
        self._lines = [line.encode() for line in lines]

    async def readline(self):
        await asyncio.sleep(0)
        if not self._lines:
            return b""
        return self._lines.pop(0)


class FakeProcess:
    """Subprocess double exposing only the attributes process_file uses."""

    def __init__(self, stdout_lines=None, stderr_lines=None, returncode=0):
        self.stdout = FakeStream(stdout_lines or [])
        self.stderr = FakeStream(stderr_lines or [])
        self.returncode = None
        self._final_returncode = returncode
        self.pid = 12345

    async def wait(self):
        await asyncio.sleep(0)
        self.returncode = self._final_returncode
        return self.returncode


@pytest.mark.asyncio
async def test_process_file_logs_progress_and_moves_outputs(tmp_path, monkeypatch):
    input_file = tmp_path / "input.pdf"
    mono_output = tmp_path / "result_mono.pdf"
    dual_output = tmp_path / "result_dual.pdf"
    log_path = tmp_path / "task.log"
    input_file.write_bytes(b"pdf")

    # process_file expects pdf2zh to leave both translated PDFs in the work dir.
    work_dir = tmp_path / "input_work"
    work_dir.mkdir()
    (work_dir / "input-mono.pdf").write_bytes(b"mono")
    (work_dir / "input-dual.pdf").write_bytes(b"dual")
    progress_updates = []
    captured = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        # Capture subprocess options without launching the real pdf2zh binary.
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        captured["start_new_session"] = kwargs["start_new_session"]
        return FakeProcess(stdout_lines=["Translating 1 / 4 pages\n", "Translating 4 / 4 pages\n"])

    async def progress_callback(progress, message):
        progress_updates.append((progress, message))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await tasks.process_file(
        str(input_file),
        str(mono_output),
        str(dual_output),
        str(log_path),
        "oneapi-key",
        "gpt-5.5",
        progress_callback,
    )

    assert mono_output.read_bytes() == b"mono"
    assert dual_output.read_bytes() == b"dual"
    assert captured["cmd"][-3:] == ("-u", "-c", captured["cmd"][-1])
    assert "callback=progress_bar" in captured["cmd"][-1]
    assert captured["env"]["DUCC_API_KEY"] == "oneapi-key"
    assert captured["env"]["DUCC_MODEL"] == "gpt-5.5"
    assert captured["env"]["PDF2ZH_INPUT_FILE"] == str(input_file)
    assert captured["env"]["PDF2ZH_OUTPUT_DIR"] == str(work_dir)
    assert captured["start_new_session"] is True
    assert progress_updates[0] == (1, "启动翻译任务")
    assert (24, "Translating 1 / 4 pages") in progress_updates
    assert (95, "Translating 4 / 4 pages") in progress_updates
    assert progress_updates[-1] == (100, "翻译完成")
    log_text = log_path.read_text(encoding="utf-8")
    assert "$ python3 -m uv" in log_text
    assert "python -u -c" in log_text
    assert "[stdout] Translating 1 / 4 pages" in log_text
    assert "[app] mono output:" in log_text
    assert "[app] dual output:" in log_text


@pytest.mark.asyncio
async def test_process_file_raises_error_with_log_tail(tmp_path, monkeypatch):
    input_file = tmp_path / "input.pdf"
    mono_output = tmp_path / "result_mono.pdf"
    dual_output = tmp_path / "result_dual.pdf"
    log_path = tmp_path / "task.log"
    input_file.write_bytes(b"pdf")

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return FakeProcess(stderr_lines=["first error\n", "last error\n"], returncode=2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    # Failures should surface useful subprocess output instead of a generic code.
    with pytest.raises(RuntimeError, match="last error"):
        await tasks.process_file(
            str(input_file),
            str(mono_output),
            str(dual_output),
            str(log_path),
            "oneapi-key",
            "gpt-5.5",
        )

    log_text = log_path.read_text(encoding="utf-8")
    assert "[stderr] first error" in log_text
    assert "[stderr] last error" in log_text


@pytest.mark.asyncio
async def test_process_file_requires_both_outputs(tmp_path, monkeypatch):
    input_file = tmp_path / "input.pdf"
    mono_output = tmp_path / "result_mono.pdf"
    dual_output = tmp_path / "result_dual.pdf"
    log_path = tmp_path / "task.log"
    input_file.write_bytes(b"pdf")
    work_dir = tmp_path / "input_work"
    work_dir.mkdir()
    # Only mono exists, so the missing dual file should be named in the error.
    (work_dir / "input-mono.pdf").write_bytes(b"mono")

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(RuntimeError, match="input-dual.pdf"):
        await tasks.process_file(
            str(input_file),
            str(mono_output),
            str(dual_output),
            str(log_path),
            "oneapi-key",
            "gpt-5.5",
        )
