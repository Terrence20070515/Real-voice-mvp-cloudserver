"""配置管理"""
import os
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("PROVIDER", "ollama")

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Ollama 本地
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.8.6:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# 多模态模型（图片识别菜单用，通义千问 VL，OpenAI 兼容格式）
# .env 配 MULTIMODAL_API_KEY，未配则图片识别功能不可用（文本解析不受影响）
MULTIMODAL_API_KEY = os.getenv("MULTIMODAL_API_KEY", "")
MULTIMODAL_BASE_URL = os.getenv("MULTIMODAL_BASE_URL", "https://dashscope.aliyun.com/compatible-mode/v1")
MULTIMODAL_MODEL = os.getenv("MULTIMODAL_MODEL", "qwen-vl-max")


def get_multimodal_config() -> dict | None:
    """返回多模态模型配置，未配 key 返回 None（图片功能降级）"""
    if not MULTIMODAL_API_KEY:
        return None
    return {
        "base_url": MULTIMODAL_BASE_URL,
        "api_key": MULTIMODAL_API_KEY,
        "model": MULTIMODAL_MODEL,
    }

# 数据文件（基于本文件位置计算绝对路径，避免依赖工作目录导致读错文件）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
# menu.json 放数据卷：admin 上传的菜单持久化，容器重启不丢
# （镜像里 /app/menu.json 作为首次启动的默认源，main.py startup 复制到 data 卷）
MENU_FILE = os.path.join(DATA_DIR, "menu.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
# 对话日志（每次对话追加，排查用）
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")
# 训练样本（入库，AI 回复风格参考）
TRAINING_EXAMPLES_FILE = os.path.join(DATA_DIR, "training_examples.json")
# 对话历史持久化目录（每个 session 一个文件，多实例恢复用）
HISTORY_DIR = os.path.join(DATA_DIR, "sessions")


def get_llm_config() -> dict:
    """返回当前激活的 LLM 配置"""
    if PROVIDER == "deepseek":
        return {
            "base_url": DEEPSEEK_BASE_URL,
            "api_key": DEEPSEEK_API_KEY,
            "model": DEEPSEEK_MODEL,
        }
    return {
        "base_url": OLLAMA_BASE_URL,
        "api_key": "ollama-local",
        "model": OLLAMA_MODEL,
    }
