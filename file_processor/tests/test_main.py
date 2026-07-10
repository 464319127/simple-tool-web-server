import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app import main


class ImmediateTask:
    def __init__(self, coro):
        self._task = asyncio.get_event_loop().create_task(coro)

    def cancel(self):
        self._task.cancel()


async def fake_process_file(input_path, mono_output_path, dual_output_path, log_path, api_key, model, progress_callback=None):
    assert api_key == "test-key"
    assert model == "gpt-5.5"
    if progress_callback:
        await progress_callback(50, "Translating 1 / 2 pages")
    Path(mono_output_path).write_bytes(b"mono")
    Path(dual_output_path).write_bytes(b"dual")
    Path(log_path).write_text("[stdout] Translating 1 / 2 pages\n", encoding="utf-8")


def make_client(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    result_dir = tmp_path / "results"
    upload_dir.mkdir()
    result_dir.mkdir()

    main.UPLOAD_DIR = upload_dir
    main.RESULT_DIR = result_dir
    main.tasks_store.clear()
    monkeypatch.setattr(main, "process_file", fake_process_file)

    return TestClient(main.app), upload_dir, result_dir


def test_upload_starts_task_and_status_reports_completion(tmp_path, monkeypatch):
    client, upload_dir, result_dir = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/upload",
        data={"api_key": "test-key", "model": ""},
        files={"file": ("paper.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 200
    task_id = response.json()["task_id"]
    assert (upload_dir / f"{task_id}.pdf").read_bytes() == b"%PDF-1.4"

    status = client.get(f"/api/status/{task_id}").json()
    assert status["status"] == "done"
    assert status["progress"] == 100
    assert status["message"] == "Translating 1 / 2 pages"
    assert status["log_tail"] == ["[stdout] Translating 1 / 2 pages"]

    assert (result_dir / f"{task_id}_mono.pdf").read_bytes() == b"mono"
    assert (result_dir / f"{task_id}_dual.pdf").read_bytes() == b"dual"


def test_upload_rejects_missing_api_key(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/upload",
        data={"api_key": " ", "model": "gpt-5.5"},
        files={"file": ("paper.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "DUCC API Key is required"


def test_upload_rejects_non_pdf(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/upload",
        data={"api_key": "test-key", "model": "gpt-5.5"},
        files={"file": ("paper.txt", b"text", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported"


def test_download_returns_requested_output_type(tmp_path, monkeypatch):
    client, _, _ = make_client(tmp_path, monkeypatch)
    task_id = client.post(
        "/api/upload",
        data={"api_key": "test-key", "model": "gpt-5.5"},
        files={"file": ("paper.pdf", b"%PDF-1.4", "application/pdf")},
    ).json()["task_id"]

    mono = client.get(f"/api/download/{task_id}/mono")
    dual = client.get(f"/api/download/{task_id}/dual")
    missing = client.get(f"/api/download/{task_id}/unknown")

    assert mono.status_code == 200
    assert mono.content == b"mono"
    assert "paper_mono.pdf" in mono.headers["content-disposition"]
    assert dual.status_code == 200
    assert dual.content == b"dual"
    assert missing.status_code == 404


def test_cancel_processing_task(tmp_path, monkeypatch):
    client, _, result_dir = make_client(tmp_path, monkeypatch)
    task_id = "task-1"
    cancelled = {"value": False}

    class Runner:
        def cancel(self):
            cancelled["value"] = True

    main.tasks_store[task_id] = {
        "status": "processing",
        "original_filename": "paper.pdf",
        "result_filenames": {},
        "log_path": str(result_dir / f"{task_id}.log"),
        "progress": 10,
        "message": "running",
        "runner": Runner(),
    }

    response = client.post(f"/api/cancel/{task_id}")

    assert response.json() == {"status": "cancelling"}
    assert cancelled["value"] is True
    assert main.tasks_store[task_id]["status"] == "cancelling"
    assert "cancellation requested" in (result_dir / f"{task_id}.log").read_text(encoding="utf-8")


def test_get_logs_returns_tail(tmp_path, monkeypatch):
    client, _, result_dir = make_client(tmp_path, monkeypatch)
    task_id = "task-1"
    log_path = result_dir / f"{task_id}.log"
    log_path.write_text("line 1\nline 2\n", encoding="utf-8")
    main.tasks_store[task_id] = {"status": "done", "log_path": str(log_path)}

    response = client.get(f"/api/logs/{task_id}")

    assert response.json() == {"log": "line 1\nline 2"}
