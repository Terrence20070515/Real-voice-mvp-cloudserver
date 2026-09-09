# 微信云托管用 Dockerfile
# 构建后端镜像，部署到微信云托管后自动获得 HTTPS 域名

FROM python:3.11-slim

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存层加速构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.tencent.com/pypi/simple/

# 复制项目代码
COPY . .

# 暴露端口（必须与云托管健康检查端口一致）
EXPOSE 8080

# 启动命令
# 注意：端口必须用 8080，与云托管健康检查端口匹配，否则部署会失败
# 云托管环境不要用 --reload，生产环境用多 worker
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
