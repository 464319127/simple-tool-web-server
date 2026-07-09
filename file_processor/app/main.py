import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .tasks import process_file

app = FastAPI()

UPLOAD_DIR = Path("/data/uploads")
RESULT_DIR = Path("/data/results")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# 任务状态存储: task_id -> {"status": str, "original_filename": str, "result_filenames": dict}
tasks_store: dict = {}


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    api_key: str = Form(...),
    model: str = Form("gpt-5.5"),
):
    api_key = api_key.strip()
    model = model.strip() or "gpt-5.5"
    if not api_key:
        raise HTTPException(status_code=400, detail="DUCC API Key is required")

    ext = Path(file.filename or "").suffix.lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    task_id = str(uuid.uuid4())
    saved_filename = f"{task_id}{ext}"
    input_path = UPLOAD_DIR / saved_filename

    with open(input_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    result_filenames = {
        "mono": f"{task_id}_mono.pdf",
        "dual": f"{task_id}_dual.pdf",
    }
    output_paths = {kind: RESULT_DIR / filename for kind, filename in result_filenames.items()}
    log_path = RESULT_DIR / f"{task_id}.log"

    tasks_store[task_id] = {
        "status": "processing",
        "original_filename": file.filename,
        "result_filenames": result_filenames,
        "log_path": str(log_path),
        "progress": 0,
        "message": "等待翻译开始",
        "model": model,
    }

    runner = asyncio.create_task(_run_task(task_id, str(input_path), str(output_paths["mono"]), str(output_paths["dual"]), str(log_path), api_key, model))
    tasks_store[task_id]["runner"] = runner

    return {"task_id": task_id, "status": "processing"}


async def _run_task(
    task_id: str,
    input_path: str,
    mono_output_path: str,
    dual_output_path: str,
    log_path: str,
    api_key: str,
    model: str,
):
    async def update_progress(progress: int, message: str):
        task = tasks_store[task_id]
        task["progress"] = progress
        task["message"] = message

    try:
        await process_file(input_path, mono_output_path, dual_output_path, log_path, api_key, model, update_progress)
        tasks_store[task_id]["status"] = "done"
        tasks_store[task_id]["progress"] = 100
    except asyncio.CancelledError:
        tasks_store[task_id]["status"] = "cancelled"
        tasks_store[task_id]["message"] = "任务已终止"
        raise
    except Exception as e:
        tasks_store[task_id]["status"] = "error"
        tasks_store[task_id]["error"] = str(e)
        tasks_store[task_id]["message"] = str(e)
    finally:
        tasks_store[task_id].pop("runner", None)


@app.post("/api/cancel/{task_id}")
async def cancel_task(task_id: str):
    if task_id not in tasks_store:
        return {"status": "not_found"}

    task = tasks_store[task_id]
    if task["status"] != "processing":
        return {"status": task["status"]}

    runner = task.get("runner")
    if runner:
        runner.cancel()
    task["status"] = "cancelling"
    task["message"] = "正在终止任务"

    log_path = task.get("log_path")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as log:
            log.write("[app] cancellation requested\n")

    return {"status": "cancelling"}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks_store:
        return {"status": "not_found"}
    task = tasks_store[task_id]
    response = {
        "status": task["status"],
        "filename": task.get("original_filename", ""),
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
        "log_tail": read_log_tail(task.get("log_path", "")),
    }
    if task["status"] == "error":
        response["error"] = task.get("error", "处理失败")
    return response


@app.get("/api/logs/{task_id}")
async def get_logs(task_id: str):
    if task_id not in tasks_store:
        return {"error": "task not found"}
    task = tasks_store[task_id]
    return {"log": "\n".join(read_log_tail(task.get("log_path", ""), limit=200))}


def read_log_tail(log_path: str, limit: int = 20):
    if not log_path:
        return []
    path = Path(log_path)
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]


@app.get("/api/download/{task_id}/{file_type}")
async def download_file(task_id: str, file_type: str):
    if task_id not in tasks_store:
        return {"error": "task not found"}
    task = tasks_store[task_id]
    if task["status"] != "done":
        return {"error": "file not ready"}
    if file_type not in {"mono", "dual"}:
        raise HTTPException(status_code=404, detail="file type not found")

    result_path = RESULT_DIR / task["result_filenames"][file_type]
    original_name = task.get("original_filename", "result")
    stem = Path(original_name).stem
    suffix = "mono" if file_type == "mono" else "dual"
    download_name = f"{stem}_{suffix}.pdf"
    return FileResponse(path=str(result_path), filename=download_name)
