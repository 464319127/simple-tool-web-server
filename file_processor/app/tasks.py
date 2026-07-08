import asyncio
import shutil
from pathlib import Path


async def process_file(input_path: str, output_path: str):
    """
    处理上传的文件并生成结果文件。
    在这里替换为你的实际处理逻辑。

    Args:
        input_path: 上传文件的路径
        output_path: 处理结果的输出路径
    """
    # TODO: 替换为实际的文件处理逻辑
    # 当前为演示：等待 10 秒后复制文件作为结果
    await asyncio.sleep(10)
    shutil.copy2(input_path, output_path)
