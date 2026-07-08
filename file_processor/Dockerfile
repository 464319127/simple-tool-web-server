FROM docker.1ms.run/library/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --progress-bar off -r requirements.txt \
    --index-url=http://pip.baidu.com/root/baidu/+simple/ \
    --trusted-host pip.baidu.com

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

