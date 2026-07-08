import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse

from .tasks import process_file

app = FastAPI()

UPLOAD_DIR = Path("/data/uploads")
RESULT_DIR = Path("/data/results")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# 任务状态存储: task_id -> {"status": str, "filename": str, "result_filename": str}
tasks_store: dict = {}


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix
    saved_filename = f"{task_id}{ext}"
    input_path = UPLOAD_DIR / saved_filename

    with open(input_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    result_filename = f"{task_id}_result{ext}"
    output_path = RESULT_DIR / result_filename

    tasks_store[task_id] = {
        "status": "processing",
        "original_filename": file.filename,
        "result_filename": result_filename,
    }

    asyncio.create_task(_run_task(task_id, str(input_path), str(output_path)))

    return {"task_id": task_id, "status": "processing"}


async def _run_task(task_id: str, input_path: str, output_path: str):
    try:
        await process_file(input_path, output_path)
        tasks_store[task_id]["status"] = "done"
    except Exception as e:
        tasks_store[task_id]["status"] = "error"
        tasks_store[task_id]["error"] = str(e)


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks_store:
        return {"status": "not_found"}
    task = tasks_store[task_id]
    return {"status": task["status"], "filename": task.get("original_filename", "")}


@app.get("/api/download/{task_id}")
async def download_file(task_id: str):
    if task_id not in tasks_store:
        return {"error": "task not found"}
    task = tasks_store[task_id]
    if task["status"] != "done":
        return {"error": "file not ready"}
    result_path = RESULT_DIR / task["result_filename"]
    original_name = task.get("original_filename", "result")
    stem = Path(original_name).stem
    ext = Path(original_name).suffix
    download_name = f"{stem}_processed{ext}"
    return FileResponse(path=str(result_path), filename=download_name)
