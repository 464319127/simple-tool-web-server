FROM docker.1ms.run/library/python:3.11-slim-bookworm

ARG HTTP_PROXY=http://agent.baidu.com:8891
ARG HTTPS_PROXY=http://agent.baidu.com:8891
ARG NO_PROXY=pip.baidu.com,oneapi-comate.baidu-int.com
ARG PDF2ZH_ARCHIVE_URL=https://github.com/464319127/PDFMathTranslate/archive/refs/heads/main.zip
ARG PDF2ZH_PROJECT_DIR=/opt/PDFMathTranslate

ENV PDF2ZH_ARCHIVE_URL=${PDF2ZH_ARCHIVE_URL}
ENV PDF2ZH_PROJECT_DIR=${PDF2ZH_PROJECT_DIR}
ENV PIP_PROGRESS_BAR=off
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --progress-bar off -r requirements.txt \
    --index-url=http://pip.baidu.com/root/baidu/+simple/ \
    --trusted-host pip.baidu.com \
    && pip install --no-cache-dir --progress-bar off uv \
    --index-url=http://pip.baidu.com/root/baidu/+simple/ \
    --trusted-host pip.baidu.com

RUN env \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY} \
    python3 -c "import os, shutil, urllib.request, zipfile; archive='/tmp/pdf2zh.zip'; urllib.request.urlretrieve(os.environ['PDF2ZH_ARCHIVE_URL'], archive); shutil.rmtree(os.environ['PDF2ZH_PROJECT_DIR'], ignore_errors=True); zipfile.ZipFile(archive).extractall('/tmp'); extracted=next(name for name in os.listdir('/tmp') if name.startswith('PDFMathTranslate-')); shutil.move('/tmp/' + extracted, os.environ['PDF2ZH_PROJECT_DIR'])" \
    && env \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY} \
    UV_INDEX_URL=http://pip.baidu.com/root/baidu/+simple/ \
    UV_TRUSTED_HOST=pip.baidu.com \
    python3 -m uv --project ${PDF2ZH_PROJECT_DIR} sync \
    && python3 -m uv --project ${PDF2ZH_PROJECT_DIR} run --no-sync python -c "from babeldoc.assets.assets import get_font_and_metadata; print(get_font_and_metadata('SourceHanSerifCN-Regular.ttf'))" \
    && python3 -m uv --project ${PDF2ZH_PROJECT_DIR} run --no-sync python -c "from babeldoc.assets.assets import get_doclayout_onnx_model_path; print(get_doclayout_onnx_model_path())"

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

