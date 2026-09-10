"""Real Voice MVP — 后端 API"""
import json
import os
import threading
import time as _time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import requests

from agent import DiningAgent
from tools import query_menu_list, list_orders, pay_order, clear_orders, delete_legacy_orders, checkout_session
from config import MENU_FILE

app = FastAPI(title="Real Voice MVP", version="1.0.14")
agent = DiningAgent()

# ─── 云托管保活机制 ───
# 免费版云托管会在闲置 10-30 分钟后回收容器（即使 minRunningCount=1）
# 用后台线程每 4 分钟 ping 自己的 /health 端点，防止被回收
def _keepalive_worker():
    """后台线程：定时 ping 自己，保持容器活跃"""
    _time.sleep(30)
    port = int(os.getenv("PORT", "8080"))
    interval = 4 * 60
    while True:
        try:
            requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
        except Exception:
            pass
        _time.sleep(interval)

@app.on_event("startup")
def start_keepalive():
    # 初始化 menu.json：数据卷里没有就从镜像默认菜单复制过去
    # 这样 admin 上传的菜单持久化在卷里，容器重启不丢
    default_menu = os.path.join(os.path.dirname(__file__), "menu.json")
    try:
        if not os.path.exists(MENU_FILE) and os.path.exists(default_menu):
            os.makedirs(os.path.dirname(MENU_FILE), exist_ok=True)
            with open(default_menu, encoding="utf-8") as src, open(MENU_FILE, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            print(f"[STARTUP] 已从默认菜单初始化 {MENU_FILE}", flush=True)
    except Exception as e:
        print(f"[STARTUP] menu.json 初始化失败: {e}", flush=True)

    t = threading.Thread(target=_keepalive_worker, daemon=True)
    t.start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 数据模型 ───

class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


class LoginRequest(BaseModel):
    code: str


# ─── 微信小程序配置（生产环境用 .env 配 secret）───
import os
from dotenv import load_dotenv
load_dotenv()

WX_APPID = os.getenv("WX_APPID", "wx8d06ce349f238f91")
WX_SECRET = os.getenv("WX_SECRET", "")


# ─── API ───

@app.get("/")
@app.get("/health")
def root():
    """根路径 + 健康检查端点，云托管探针用"""
    return {"service": "Real Voice MVP", "status": "running", "version": "1.0.14"}


@app.get("/api/menu")
def api_menu(
    category: str | None = Query(default=None, description="按分类筛选"),
    keyword: str | None = Query(default=None, description="按菜名搜索"),
):
    """查询菜单，直接返回 list[dict]"""
    return query_menu_list(category=category, keyword=keyword)


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest):
    """AI 对话接口"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    reply = agent.chat(session_id=req.session_id, message=req.message)
    return ChatResponse(reply=reply)


@app.post("/api/session/clear")
def clear_session(session_id: str = Query(..., description="要清除的会话 ID")):
    """清除对话历史"""
    agent.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


# ─── 微信登录 ───

@app.post("/api/login")
def api_login(req: LoginRequest):
    """微信登录：用 wx.login() 拿到的 code 换 openid

    如果没配置 WX_SECRET，就用 code 当作 mock openid（开发期间够用）
    如果配置了 WX_SECRET，调用微信官方接口换真实 openid
    """
    if not req.code:
        raise HTTPException(status_code=400, detail="code 不能为空")

    if WX_SECRET:
        # 真实场景：调用微信 code2Session 接口
        try:
            url = (
                f"https://api.weixin.qq.com/sns/jscode2session"
                f"?appid={WX_APPID}&secret={WX_SECRET}"
                f"&js_code={req.code}&grant_type=authorization_code"
            )
            resp = requests.get(url, timeout=5).json()
            openid = resp.get("openid", "")
            if not openid:
                return {
                    "openid": "",
                    "session_id": "",
                    "error": resp.get("errmsg", "登录失败")
                }
            session_id = "wx_" + openid
            return {"openid": openid, "session_id": session_id}
        except Exception as e:
            return {"openid": "", "session_id": "", "error": str(e)[:80]}
    else:
        # Mock 模式：直接用 code 当 openid
        mock_openid = "mock_" + req.code[:16]
        session_id = "wx_" + mock_openid
        return {
            "openid": mock_openid,
            "session_id": session_id,
            "mock": True,
            "hint": "未配置 WX_SECRET，使用 mock openid。配置后可获取真实 openid。"
        }


# ─── 订单查询 ───

@app.get("/api/orders/all")
def api_all_orders():
    """返回所有订单，店家后台看板用"""
    orders = list_orders(session_id="")
    total_amount = sum(o.get("total", 0) for o in orders)
    unpaid_count = sum(1 for o in orders if not o.get("paid"))
    return {
        "count": len(orders),
        "total_revenue": total_amount,
        "unpaid": unpaid_count,
        "orders": orders
    }


@app.get("/api/orders/{session_id}")
def api_get_orders(session_id: str):
    """查询某个 session 的所有订单"""
    orders = list_orders(session_id=session_id)
    return {
        "session_id": session_id,
        "count": len(orders),
        "orders": orders
    }


@app.post("/api/orders/{order_id}/pay")
def api_pay_order(order_id: str):
    """模拟支付订单"""
    result = pay_order(order_id=order_id)
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"status": "error", "message": result}


@app.post("/api/orders/{session_id}/checkout")
def api_checkout_session(session_id: str):
    """按 session 结账：支付该会话所有未支付订单（小程序前端「去结账」按钮可调用）"""
    result = checkout_session(session_id=session_id)
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"status": "error", "message": result}

# ─── 菜单导入（店家后台用）──-

class MenuImportRequest(BaseModel):
    restaurant: str | None = None
    categories: list


@app.post("/api/menu/import")
def api_import_menu(req: MenuImportRequest):
    """导入新菜单，覆盖原有菜单文件（写入数据卷，持久化）"""
    try:
        with open(MENU_FILE, "w", encoding="utf-8") as f:
            json.dump(req.model_dump(exclude_none=True), f, ensure_ascii=False, indent=2)
        return {"status": "ok", "message": f"菜单已更新，共 {sum(len(c['items']) for c in req.categories)} 道菜"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")


# ─── 店家管理后台页面 ───

ADMIN_PATH = os.path.join(os.path.dirname(__file__), "admin.html")

@app.get("/admin")
def admin_page():
    """店家管理后台（订单看板 + 菜单管理 + 清台操作）"""
    if os.path.exists(ADMIN_PATH):
        return FileResponse(ADMIN_PATH, media_type="text/html")
    return HTMLResponse("<h1>管理后台未部署</h1><p>请确认 admin.html 文件存在</p>", status_code=404)


# ─── 清台 ───

@app.post("/api/orders/clear")
@app.delete("/api/orders/clear")
def api_clear_orders(session_id: str = Query(..., description="要清台的 session_id")):
    """清台：删除某个 session 的所有订单，同时清除该 session 的对话历史"""
    # 清除会话历史
    agent.clear_session(session_id)

    # 清除订单
    result = clear_orders(session_id=session_id)
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"status": "error", "message": result}


@app.post("/api/orders/clean-legacy")
def api_clean_legacy():
    """删除无 session_id 的历史遗留订单（管理员清理脏数据用）"""
    result = delete_legacy_orders()
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"status": "error", "message": result}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
