import asyncio
import os
from pathlib import Path


async def process_file(input_path: str, output_path: str):
    """
    翻译上传的 PDF 并生成结果文件。

    Args:
        input_path: 上传文件的路径
        output_path: 翻译结果的输出路径
    """
    input_file = Path(input_path)
    output_file = Path(output_path)
    work_dir = output_file.parent / f"{output_file.stem}_work"
    work_dir.mkdir(parents=True, exist_ok=True)

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
        "--no-dual",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError(f"PDF translation timed out after {timeout} seconds") from exc

    if process.returncode != 0:
        error = stderr.decode("utf-8", errors="replace").strip()
        if not error:
            error = stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(error or f"pdf2zh failed with exit code {process.returncode}")

    translated_file = work_dir / f"{input_file.stem}-mono.pdf"
    if not translated_file.exists():
        raise RuntimeError(f"pdf2zh did not produce expected file: {translated_file.name}")

    translated_file.replace(output_file)
