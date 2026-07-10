# 文件处理 Web 服务

一个轻量级的文件上传 + 异步处理 + 下载服务，基于 FastAPI + Nginx + Docker 部署。

## 功能

- 用户通过浏览器上传文件
- 服务端异步处理文件（支持耗时任务）
- 处理完成后用户可直接下载结果文件

## 项目结构

```
file_processor/
├── app/
│   ├── main.py          # FastAPI 应用路由
│   ├── tasks.py         # 文件处理逻辑（在此自定义）
│   └── static/
│       └── index.html   # 前端页面
├── nginx/
│   └── nginx.conf       # Nginx 反向代理配置
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 部署步骤

### 1. 拉取基础镜像

```bash
docker pull docker.1ms.run/library/python:3.11-slim
docker pull docker.1ms.run/library/nginx:alpine-perl
```

### 2. 配置 DUCC 翻译参数

服务会在 app 镜像内安装 PDFMathTranslate/pdf2zh。DUCC API Key 和模型名称由用户在页面上传时填写，模型默认值为 `gpt-5.5`。

可选配置：

```bash
export DUCC_BASE_URL="https://oneapi-comate.baidu-int.com/v1/messages"
```


```bash
export PDF2ZH_LANG_IN="en"
export PDF2ZH_LANG_OUT="zh"
export PDF2ZH_THREADS="10"
export PDF2ZH_TIMEOUT_SECONDS="3600"
```

### 3. 构建并启动服务

```bash
cd file_processor
docker compose up --build -d
```

默认对外端口为 `8999`。部署时可通过 `WEB_PORT` 指定其他端口，例如：

```bash
WEB_PORT=8080 docker compose up --build -d
```

也可以在 `file_processor` 目录创建 `.env` 文件持久化配置：

```dotenv
WEB_PORT=8080
```

### 4. 访问服务

浏览器打开：

```
http://<服务器IP>:8999
```

## 配置说明

| 配置项 | 位置 | 默认值 | 说明 |
|--------|------|--------|------|
| `WEB_PORT` | 部署环境变量或 `.env` | 8999 | 宿主机对外端口；容器内 Nginx 仍监听 8999 |
| 文件大小限制 | nginx/nginx.conf | 500MB | `client_max_body_size` |
| 代理超时 | nginx/nginx.conf | 600s | 长任务处理时间上限 |
| pip 源 | Dockerfile | pip.baidu.com | 百度内网 pip 源 |

## 离线部署

在可构建机器上准备镜像包：

```bash
cd file_processor

docker build -t file_processor-app:latest .
docker pull docker.1ms.run/library/nginx:alpine-perl
docker tag docker.1ms.run/library/nginx:alpine-perl file-processor-nginx:alpine-perl

docker save -o file-processor-images.tar \
  file_processor-app:latest \
  file-processor-nginx:alpine-perl
```

将 `file-processor-images.tar`、`docker-compose.offline.yml` 和 `nginx/nginx.conf` 拷贝到目标服务器后执行：

```bash
docker load -i file-processor-images.tar
WEB_PORT=8080 docker compose -f docker-compose.offline.yml up -d
```

不设置 `WEB_PORT` 时，离线部署同样使用默认端口 `8999`。

## 常用命令

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 重新构建（修改代码后）
docker compose up --build -d

# 运行单元测试
python3 -m pytest file_processor/tests
```

## 注意事项

- 任务状态存储在内存中，重启服务后会丢失未完成的任务
- 上传文件和结果文件存储在 Docker volume 中，`docker compose down` 不会删除数据，`docker compose down -v` 会清除
- 对外端口通过 `WEB_PORT` 配置，无需修改 Compose 或 Nginx 配置文件
