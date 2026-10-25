"""Real Voice MVP — 后端 API"""
import json
import os
import re
import threading
import time as _time

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import requests

from agent import DiningAgent
from tools import query_menu_list, list_orders, pay_order, clear_orders, delete_legacy_orders, checkout_session
from config import MENU_FILE, TRAINING_EXAMPLES_FILE, VOICES_DIR

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
    # 通用店家架构：后端以「空店」状态启动（无菜单、无示例）。
    # 菜单由店家通过 admin 后台导入后自动生成；/api/menu/reset 可一键回到空店态。
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
    return {"service": "Real Voice MVP", "status": "running", "version": "1.0.15"}


@app.get("/api/menu")
def api_menu(
    category: str | None = Query(default=None, description="按分类筛选"),
    keyword: str | None = Query(default=None, description="按菜名搜索"),
):
    """查询菜单，返回 list[dict]（每项带「店名」，前端可动态显示店名）"""
    items = query_menu_list(category=category, keyword=keyword)
    if items:
        restaurant = ""
        try:
            menu = json.load(open(MENU_FILE, encoding="utf-8"))
            restaurant = (menu.get("restaurant") or "").strip()
        except Exception:
            restaurant = ""
        if restaurant:
            for it in items:
                it["店名"] = restaurant
    return items


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


def _asr_transcribe(audio: bytes, filename: str = "voice.mp3", content_type: str = "audio/mpeg") -> str:
    """调 ASR 服务把音频转文字（SiliconFlow SenseVoice，OpenAI 兼容格式）。"""
    api_key = os.getenv("ASR_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="语音识别未配置：请设置 ASR_API_KEY 环境变量")
    if not audio:
        raise HTTPException(status_code=400, detail="音频内容为空")
    if len(audio) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="音频超过 8MB 上限")
    base = os.getenv("ASR_BASE_URL", "https://api.siliconflow.cn/v1")
    model = os.getenv("ASR_MODEL", "FunAudioLLM/SenseVoiceSmall")
    try:
        resp = requests.post(
            f"{base}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, audio, content_type)},
            data={"model": model},
            timeout=60,
        )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()
    except requests.HTTPError as e:
        detail = e.response.text[:150] if e.response is not None else str(e)
        raise HTTPException(status_code=502, detail=f"ASR 服务错误: {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"语音识别失败: {e}")


@app.post("/api/asr")
def api_asr(file: UploadFile = File(...)):
    """语音转文字：录音文件上传 → ASR 服务 → 文本（纯转写接口）。"""
    return {"text": _asr_transcribe(file.file.read(), file.filename or "voice.mp3",
                                    file.content_type or "audio/mpeg")}


@app.post("/api/voice")
def api_voice(
    file: UploadFile = File(...),
    session_id: str = Form(""),
    duration_ms: int = Form(0),
):
    """微信式语音消息：存原声（供回放）→ ASR 转文字（供 LLM 理解）。

    返回 {text, voice_url, duration}——前端以语音气泡展示原声，文字交给 AI 处理。
    """
    audio = file.file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="音频内容为空")
    if len(audio) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="音频超过 8MB 上限")
    sid = "".join(ch for ch in session_id if ch.isalnum() or ch in "_-")[:60] or "unknown"
    ts = int(_time.time() * 1000)
    vdir = os.path.join(VOICES_DIR, sid)
    os.makedirs(vdir, exist_ok=True)
    fname = f"{ts}.mp3"
    with open(os.path.join(vdir, fname), "wb") as f:
        f.write(audio)
    text = _asr_transcribe(audio, file.filename or "voice.mp3", file.content_type or "audio/mpeg")
    duration_sec = max(1, round(duration_ms / 1000))
    return {"text": text, "voice_url": f"/api/voice/file/{sid}/{fname}", "duration": duration_sec}


@app.get("/api/voice/file/{session_id}/{filename}")
def api_voice_file(session_id: str, filename: str):
    """语音消息回放（音频文件静态服务，路径白名单校验防穿越）。"""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,60}", session_id) or not re.fullmatch(r"\d{13,15}\.mp3", filename):
        raise HTTPException(status_code=400, detail="非法路径")
    path = os.path.join(VOICES_DIR, session_id, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="语音不存在")
    return FileResponse(path, media_type="audio/mpeg")


@app.post("/api/tts")
def api_tts(req: dict):
    """文字转语音：回复文本 → TTS → mp3 音频（语音播报模式用）。

    与 ASR 共用 SiliconFlow key；CosyVoice2 按字符计费，点餐短回复成本可忽略。
    """
    api_key = os.getenv("ASR_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="语音服务未配置：请设置 ASR_API_KEY")
    text = (req.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本为空")
    if len(text) > 500:
        text = text[:500]  # 点餐回复短文本，截断防滥用
    base = os.getenv("ASR_BASE_URL", "https://api.siliconflow.cn/v1")
    tts_model = os.getenv("TTS_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
    voice = os.getenv("TTS_VOICE", f"{tts_model}:anna")  # 预置女声音色，适合服务场景
    try:
        resp = requests.post(
            f"{base}/audio/speech",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": tts_model, "input": text, "voice": voice, "response_format": "mp3"},
            timeout=25,  # TTS 超时快速降级：超时则前端静默回退文字回复（SiliconFlow 免费通道排队慢）
        )
        resp.raise_for_status()
        return Response(content=resp.content, media_type="audio/mpeg")
    except requests.HTTPError as e:
        detail = e.response.text[:150] if e.response is not None else str(e)
        raise HTTPException(status_code=502, detail=f"TTS 服务错误: {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"语音合成失败: {e}")


@app.post("/api/menu/import")
def api_import_menu(req: MenuImportRequest):
    """导入新菜单，覆盖原有菜单文件（写入数据卷，持久化）。

    菜单差异 >20%（Jaccard 距离）时自动后台重新生成训练示例，
    保证 training_examples 和当前菜单同步，AI 不被旧示例带偏。
    """
    try:
        # 读旧菜单算差异
        old_menu = {}
        if os.path.exists(MENU_FILE):
            try:
                with open(MENU_FILE, encoding="utf-8") as f:
                    old_menu = json.load(f)
            except Exception:
                old_menu = {}
        new_menu = req.model_dump(exclude_none=True)
        with open(MENU_FILE, "w", encoding="utf-8") as f:
            json.dump(new_menu, f, ensure_ascii=False, indent=2)

        diff = _menu_diff_ratio(old_menu, new_menu)
        msg = f"菜单已更新，共 {sum(len(c['items']) for c in req.categories)} 道菜"
        # 差异 >20% → 后台线程重生成训练示例（不阻塞响应）
        if diff > 0.2:
            threading.Thread(
                target=_regenerate_training_examples, args=(new_menu,), daemon=True
            ).start()
            msg += f"（菜单变化 {diff:.0%}，正在后台重新生成训练示例，约 2 分钟后生效）"
        return {"status": "ok", "message": msg, "menu_diff": round(diff, 3)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")


@app.post("/api/menu/reset")
def api_menu_reset():
    """重置到空店态：清空菜单与示例池（切换店家演示用）。

    重置后 agent 自动进入「菜单尚未配置」模式；导入新菜单即完成新店家初始化。
    """
    try:
        for f in (MENU_FILE, TRAINING_EXAMPLES_FILE):
            if os.path.exists(f):
                os.remove(f)
        return {"status": "ok", "message": "已重置为空店态：菜单与示例池已清空，等待导入新菜单"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置失败: {e}")


def _menu_diff_ratio(old_menu: dict, new_menu: dict) -> float:
    """新旧菜单菜品差异率（Jaccard 距离）：1 - |交集| / |并集|"""
    def dish_names(m: dict) -> set:
        names = set()
        for c in (m.get("categories") or []):
            for it in (c.get("items") or []):
                if it.get("name"):
                    names.add(it["name"])
        return names
    old_n, new_n = dish_names(old_menu), dish_names(new_menu)
    union = old_n | new_n
    if not union:
        return 0.0
    return 1 - len(old_n & new_n) / len(union)


def _regenerate_training_examples(new_menu: dict) -> None:
    """后台：基于新菜单用 LLM 重生成 training_examples.json。

    6 大场景 × 12 条 = 72 条，reply 里引用的菜名/价格全部来自新菜单。
    原子写落库，失败不影响服务（旧示例继续用，有版本警告兜底）。
    """
    try:
        cfg = get_llm_config()
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

        # 菜品清单文本（含价格/辣度/过敏原，供生成引用）
        dish_lines = []
        for c in new_menu.get("categories", []):
            for it in c.get("items", []):
                allergens = "、".join(it.get("allergens", [])) or "无"
                dish_lines.append(
                    f"{it.get('name','?')} ¥{it.get('price',0)}"
                    f"（{it.get('spicy','不辣')}，过敏原:{allergens}）"
                )
        menu_text = "\n".join(dish_lines)

        scenarios = [
            "欢迎与寒暄（含对话中途寒暄不重置话题）、询问推荐（喜辣/不辣/有忌口各一条）",
            "推荐菜品（含避开过敏原的示例）、询问招牌菜、询问汤类和主食",
            "一句话下单（含人数+菜品+口味全信息）、只说菜名直接下单",
            "加单（再来一份）、换菜（A换成B）、退菜（不要了）",
            "查订单（我点了什么）、问总价、问几人份量够不够",
            "结账（去结账/买单）、催菜、要包间、感谢结束",
        ]

        all_examples = []
        for i, scene in enumerate(scenarios):
            prompt = f"""基于以下菜单，生成本批点餐场景示例问答。

菜单（菜名和价格必须从这里引用，不得编造）：
{menu_text}

本批场景：{scene}

要求：
- 生成 12 条示例，每条格式 {{"user":"顾客的话","reply":"助手回复"}}
- reply 里引用的菜名和价格必须来自上面菜单，菜不在菜单里就绝对不能出现
- 语气简洁专业，每次回复 3-5 行以内，不啰嗦，可用 1️⃣2️⃣ 编号或适度 emoji
- 下单/加单成功要报订单号（用 ORD1001、ORD1002 这类占位）和合计金额（按菜单价格算对）
- 过敏相关示例要体现"识别过敏原→避开"的逻辑
- 只输出 JSON 数组，不要 markdown 代码块，不要解释"""

            resp = client.chat.completions.create(
                model=cfg["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=3000,
            )
            content = resp.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            batch = json.loads(content)
            if isinstance(batch, list):
                all_examples.extend(
                    {"user": b.get("user", ""), "reply": b.get("reply", "")}
                    for b in batch if b.get("user") and b.get("reply")
                )
            print(f"[TRAINING] 批次{i+1}/6 完成，累计 {len(all_examples)} 条", flush=True)

        if not all_examples:
            print("[TRAINING] 生成结果为空，保留旧示例", flush=True)
            return
        # 🔒 评分门控：Jev 打分优先，DeepSeek 降级，都不可用时全量保留
        import scoring
        gated = scoring.score_examples(all_examples)
        if gated is not None:
            all_examples = gated
        # 原子写落库
        os.makedirs(os.path.dirname(TRAINING_EXAMPLES_FILE), exist_ok=True)
        tmp = TRAINING_EXAMPLES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(all_examples, f, ensure_ascii=False, indent=2)
        os.replace(tmp, TRAINING_EXAMPLES_FILE)
        print(f"[TRAINING] 重生成完成: {len(all_examples)} 条，已落库", flush=True)
    except Exception as e:
        print(f"[TRAINING] 重生成失败（保留旧示例）: {e}", flush=True)


# ─── 菜单智能解析（文本/图片 → 结构化菜单）───
# 让 admin 后台不用手写 JSON，粘菜单文字或拍菜单图片一键导入

from openai import OpenAI
from config import get_llm_config

PARSE_PROMPT = """你是菜单解析助手。把用户给的菜单内容解析成严格 JSON。

输出格式（只输出 JSON，不要 markdown 代码块，不要任何解释）：
{
  "restaurant": "餐厅名（从内容提取，没有写'餐厅'）",
  "categories": [
    {
      "name": "分类名（招牌必点/凉菜/热菜·川味/热菜·清淡/汤类/主食/饮品，按内容归并）",
      "items": [
        {
          "id": "分类拼音首字母+两位序号，如 s01/c02",
          "name": "菜名",
          "price": 纯数字,
          "spicy": "不辣/微辣/中辣/麻辣/特辣",
          "ingredients": ["食材1","食材2"],
          "allergens": ["过敏原，含花生/鸡蛋/鱼/海鲜/大豆/牛奶等才标，否则空数组"],
          "description": "一句话描述，原文没有就根据菜名推断"
        }
      ]
    }
  ]
}

规则：
- 价格提取纯数字："68元"/"¥68"/"68" 都成 68
- 辣度从菜名/描述推断：水煮鱼/麻婆豆腐/辣子鸡→麻辣，酸菜鱼→中辣，清蒸鱼/糖醋里脊→不辣
- 过敏原只在菜品确实含时标，否则空数组
- 只输出 JSON，不要代码块标记"""


def _call_llm_parse(messages: list) -> dict:
    """调 LLM 解析菜单文本/图片，返回结构化 dict"""
    cfg = get_llm_config()
    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    last_err = None
    for attempt in range(2):
        try:
            kwargs = {
                "model": cfg["model"],
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 4096,
            }
            # DeepSeek 支持 JSON 输出格式
            if "deepseek" in cfg["model"]:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content.strip()
            # 去掉可能的 markdown 代码块
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except Exception as e:
            last_err = e
            if attempt == 0:
                _time.sleep(1)
                continue
    raise HTTPException(status_code=500, detail=f"LLM 解析失败: {last_err}")


class ParseTextRequest(BaseModel):
    text: str


@app.post("/api/menu/parse-text")
def api_parse_menu_text(req: ParseTextRequest):
    """文本 → 结构化菜单（用 DeepSeek 解析，现有 key 即可用）

    admin 后台粘菜单文字，一键解析成结构化 JSON 返回。
    前端拿到后再调 /api/menu/import 落库。
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    messages = [
        {"role": "system", "content": PARSE_PROMPT},
        {"role": "user", "content": f"解析这个菜单：\n{text}"},
    ]
    return _call_llm_parse(messages)


class ParseImageRequest(BaseModel):
    image: str  # base64 编码（可带 data:image/...;base64, 前缀）


@app.post("/api/menu/parse-image")
def api_parse_menu_image(req: ParseImageRequest):
    """图片 → 结构化菜单（通义千问 VL，需配置 MULTIMODAL_API_KEY）

    admin 后台上传菜单图片，多模态模型识别菜品→结构化 JSON。
    未配多模态 key 时返回 503 提示。
    """
    from config import get_multimodal_config
    mm_cfg = get_multimodal_config()
    if not mm_cfg:
        raise HTTPException(status_code=503, detail="未配置多模态模型 key（MULTIMODAL_API_KEY），图片识别不可用。在 .env 配 MULTIMODAL_API_KEY 后可用。")

    image_data = req.image.strip()
    # 补全 data URL 前缀（前端传纯 base64 也兼容）
    if not image_data.startswith("data:"):
        image_data = f"data:image/jpeg;base64,{image_data}"

    messages = [
        {"role": "system", "content": PARSE_PROMPT},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": image_data}},
            {"type": "text", "text": "解析图片里的菜单内容，严格按 JSON 格式输出。识别每道菜的名称、价格、辣度（从菜名/标签推断）、食材、过敏原、描述。"},
        ]},
    ]

    client = OpenAI(api_key=mm_cfg["api_key"], base_url=mm_cfg["base_url"])
    try:
        resp = client.chat.completions.create(
            model=mm_cfg["model"],
            messages=messages,
            temperature=0.1,
            max_tokens=4096,
        )
        content = resp.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="模型输出不是合法 JSON，请换张更清晰的菜单图重试")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片识别失败: {e}")


# ─── RLAIF 闭环：示例池回灌接口 ───

@app.post("/api/training/import")
def api_training_import(req: dict):
    """高分示例回灌（selfplay distill 推送）：按顾客消息去重后合并进示例池。

    body: {"token": "...", "examples": [{"user": "...", "reply": "..."}]}
    原子写落库，新会话自动加载新示例（无需重启）。
    """
    token = os.getenv("ADMIN_TOKEN", "rv-distill-2026")
    if req.get("token") != token:
        raise HTTPException(status_code=403, detail="token 错误")
    examples = req.get("examples")
    if not isinstance(examples, list):
        raise HTTPException(status_code=400, detail="examples 必须是数组")

    cur = []
    if os.path.exists(TRAINING_EXAMPLES_FILE):
        try:
            with open(TRAINING_EXAMPLES_FILE, encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = []
    seen = {e.get("user", "").strip() for e in cur if isinstance(e, dict)}
    added = 0
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        u = (ex.get("user") or "").strip()
        r = (ex.get("reply") or "").strip()
        if not u or not r or u in seen:
            continue
        seen.add(u)
        cur.append({"user": u, "reply": r})
        added += 1
    if added:
        tmp = TRAINING_EXAMPLES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        os.replace(tmp, TRAINING_EXAMPLES_FILE)
    return {"status": "ok", "added": added, "total": len(cur)}


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
