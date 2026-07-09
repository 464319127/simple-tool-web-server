import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Awaitable, Callable

ProgressCallback = Callable[[int, str], Awaitable[None]]

TRANSLATION_PROGRESS_RE = re.compile(r"Translating\s+(\d+)\s*/\s*(\d+)\s+pages")


async def process_file(
    input_path: str,
    mono_output_path: str,
    dual_output_path: str,
    log_path: str,
    progress_callback: ProgressCallback | None = None,
):
    """
    翻译上传的 PDF 并生成结果文件。

    Args:
        input_path: 上传文件的路径
        mono_output_path: 单语翻译结果的输出路径
        dual_output_path: 双语翻译结果的输出路径
        log_path: 翻译日志的输出路径
        progress_callback: 翻译进度更新回调
    """
    input_file = Path(input_path)
    mono_output_file = Path(mono_output_path)
    dual_output_file = Path(dual_output_path)
    log_file = Path(log_path)
    work_dir = mono_output_file.parent / f"{input_file.stem}_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    project_dir = os.getenv("PDF2ZH_PROJECT_DIR", "/opt/PDFMathTranslate")
    lang_in = os.getenv("PDF2ZH_LANG_IN", "en")
    lang_out = os.getenv("PDF2ZH_LANG_OUT", "zh")
    threads = os.getenv("PDF2ZH_THREADS", "10")
    timeout = int(os.getenv("PDF2ZH_TIMEOUT_SECONDS", "3600"))

    cmd = [
        "python3",
        "-m",
        "uv",
        "--project",
        project_dir,
        "run",
        "--no-sync",
        "pdf2zh",
        str(input_file),
        "-s",
        "ducc",
        "-o",
        str(work_dir),
        "-li",
        lang_in,
        "-lo",
        lang_out,
        "-t",
        threads,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    log_tail: list[str] = []

    async def append_log(stream: asyncio.StreamReader | None, prefix: str):
        if stream is None:
            return
        with open(log_file, "a", encoding="utf-8") as log:
            while line := await stream.readline():
                text = line.decode("utf-8", errors="replace").rstrip()
                log_line = f"[{prefix}] {text}"
                log.write(log_line + "\n")
                log.flush()
                log_tail.append(text)
                del log_tail[:-20]

                match = TRANSLATION_PROGRESS_RE.search(text)
                if match and progress_callback:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    if total > 0:
                        progress = min(95, max(1, round(current / total * 95)))
                        await progress_callback(progress, text)

    with open(log_file, "w", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n")

    if progress_callback:
        await progress_callback(1, "启动翻译任务")

    try:
        await asyncio.wait_for(
            asyncio.gather(
                append_log(process.stdout, "stdout"),
                append_log(process.stderr, "stderr"),
                process.wait(),
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError(f"PDF translation timed out after {timeout} seconds") from exc

    if process.returncode != 0:
        error = "\n".join(line for line in log_tail if line).strip()
        raise RuntimeError(error or f"pdf2zh failed with exit code {process.returncode}")

    mono_file = work_dir / f"{input_file.stem}-mono.pdf"
    dual_file = work_dir / f"{input_file.stem}-dual.pdf"
    missing_files = [path.name for path in (mono_file, dual_file) if not path.exists()]
    if missing_files:
        raise RuntimeError(f"pdf2zh did not produce expected file(s): {', '.join(missing_files)}")

    if progress_callback:
        await progress_callback(98, "保存翻译结果")

    shutil.move(str(mono_file), mono_output_file)
    shutil.move(str(dual_file), dual_output_file)

    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[app] mono output: {mono_output_file}\n")
        log.write(f"[app] dual output: {dual_output_file}\n")

    if progress_callback:
        await progress_callback(100, "翻译完成")
