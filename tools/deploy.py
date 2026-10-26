"""Real-voice 服务器部署脚本（paramiko，替代不稳定的 expect 方案）

用法：python deploy.py
流程：git reset 到 origin/main → docker rm/build/run → 健康检查

🔒 凭据从仓库根目录 .deploy.env 读取（已 gitignore，禁止入库——
   历史上密码曾硬编码于此并进入 git 历史，属于泄露）。
"""
import os
import sys
import time

from dotenv import load_dotenv

import paramiko

# 凭据注入：读取根目录 .deploy.env（不入库）
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".deploy.env"))

HOST = os.getenv("SERVER_HOST", "")
USER = os.getenv("SERVER_USER", "ubuntu")
PASSWORD = os.getenv("SERVER_PASSWORD", "")
REPO = os.getenv("SERVER_REPO", "/home/ubuntu/Real-voice-mvp-cloudserver")

if not HOST or not PASSWORD:
    print("缺少部署凭据：请在仓库根目录创建 .deploy.env（该文件已 gitignore），内容：")
    print("SERVER_HOST=服务器IP")
    print("SERVER_USER=ubuntu")
    print("SERVER_PASSWORD=服务器密码")
    print("SERVER_REPO=/home/ubuntu/Real-voice-mvp-cloudserver")
    sys.exit(1)

GIT_CMD = f"cd {REPO} && git fetch origin && git reset --hard origin/main 2>&1 | tail -1"
DOCKER_CMD = (
    f"echo {PASSWORD!r} | sudo -S docker rm -f real-voice 2>/dev/null; "
    f"sudo docker build -t real-voice {REPO} 2>&1 | tail -2; "
    f"sudo docker run -d --name real-voice -p 8080:8080 "
    f"-v /opt/real-voice/data:/app/data --env-file {REPO}/.env "
    f"--restart always real-voice && echo RUN_OK"
)


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    for name, cmd, timeout in [
        ("GIT", GIT_CMD, 60),
        ("DOCKER build+run", DOCKER_CMD, 420),
    ]:
        print(f"=== {name} ===")
        _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode()
        err = stderr.read().decode()
        print(out.strip()[-600:])
        if err.strip():
            print("STDERR:", err.strip()[-300:])
    c.close()

    # 健康检查
    import urllib.request
    for i in range(10):
        time.sleep(2)
        try:
            r = urllib.request.urlopen(f"http://{HOST}:8080/health", timeout=5)
            print("HEALTH:", r.read().decode())
            print("=== DEPLOY OK ===")
            return
        except Exception:
            continue
    print("=== DEPLOY FAILED: health check timeout ===")
    sys.exit(1)


if __name__ == "__main__":
    main()
