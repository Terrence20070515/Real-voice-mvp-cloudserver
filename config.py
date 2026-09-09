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

# 数据文件（基于本文件位置计算绝对路径，避免依赖工作目录导致读错文件）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MENU_FILE = os.path.join(BASE_DIR, "menu.json")
ORDERS_FILE = os.path.join(BASE_DIR, "data", "orders.json")
SESSIONS_FILE = os.path.join(BASE_DIR, "data", "sessions.json")
# 对话日志（每次对话追加，排查用）
CONVERSATIONS_FILE = os.path.join(BASE_DIR, "data", "conversations.json")
# 训练样本（入库，AI 回复风格参考）
TRAINING_EXAMPLES_FILE = os.path.join(BASE_DIR, "data", "training_examples.json")
# 对话历史持久化目录（每个 session 一个文件，多实例恢复用）
HISTORY_DIR = os.path.join(BASE_DIR, "data", "sessions")


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
