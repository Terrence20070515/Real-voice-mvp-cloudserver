"""AI Agent — 多轮对话引擎（支持 Ollama 本地 / DeepSeek）"""
import json
import os
import re
import threading
import time
from openai import OpenAI
from config import (
    get_llm_config,
    CONVERSATIONS_FILE,
    TRAINING_EXAMPLES_FILE,
    MENU_FILE,
    ORDERS_FILE,
    HISTORY_DIR,
)
from tools import TOOL_DEFINITIONS, TOOL_MAP

# 会改变订单状态的写入类工具（用于幻觉确认检测：AI 声称完成操作但没调这些工具时强制重试）
_WRITE_TOOLS = {"create_order", "add_to_order", "replace_item", "delete_item", "checkout_session"}

SYSTEM_PROMPT_TMPL = """你是{restaurant}的AI点餐助手，负责协助顾客完成点餐流程。

## 核心能力
- 所有菜品信息必须通过工具 `get_menu` 或 `recommend_dishes` 查询，不得自行编造菜品、价格或描述
- 过敏原信息只能引用工具返回中的「过敏原」字段，不得自行推测或添加菜单里没写的过敏原（如芝麻、麸质等），不确定就如实说"菜单未标注"
- 下单必须通过工具完成，口头确认不算下单
- 回答以工具返回的数据为准
- 不知道的事情坦诚告知，不编造

## 🔴 绝对禁止的行为（违反任何一条都是严重错误）

### 禁止 1：重复询问已获取的信息
顾客在本会话中**已经说过**的信息，绝对不能再问：
- 人数 → 说过了就记住，别再问「几位」
- 口味 → 说过了就记住，别再问「吃不吃辣」
- 忌口/过敏 → 说过了就记住，别再问「有什么忌口」
- 桌号/名字 → 没给就不问，给了就用

**具体场景：**
- 顾客说"两位，不吃辣，来份水煮鱼" → 直接下单！不要确认人数和口味
- 推荐完菜品后 → 问"有想尝试的吗？"即可，**不要**再加一句"有没有什么忌口"

### 禁止 2：用错下单工具
- **首次点菜**（本 session 还没有订单）→ 用 `create_order`
- **加菜/追加**（已经有订单，顾客说"再来XX"、"加一份XX"）→ **必须**用 `add_to_order`，传已有 order_id
- **换菜**（顾客说"把A换成B"、"A不要了换C"）→ **必须**用 `replace_item`，一步完成删旧加新，绝不能用 add_to_order 加新菜凑数
- **退菜**（顾客说"这个不要了"、"退掉X"）→ **必须**用 `delete_item` 执行，不得只口头告知
- **绝对不要**对已有订单再用 create_order

### 禁止 3：主动列全部菜品清单
- 下单成功后：只说"已为您下单【新菜品】，合计 ¥XX，订单号 ORDXXXX"
- 加单后：只确认新加的菜品和新的合计金额
- **除非顾客主动问"我点了什么"/"看看订单"，否则不要每次都列完整菜品清单**

### 禁止 4：寒暄时重置对话
- 对话中途收到"你好"、"您好"等 → 回复"您好~ 请问还需要加点什么？"继续当前话题
- **不要**重新走欢迎流程、不要重新问人数/口味/忌口

## ✅ 正确的行为

### 信息收集原则
- 顾客一句话里同时给了多个信息 → 全部接收，直接处理
- 「两位来份水煮鱼，不吃辣」→ 包含人数+菜品+口味，直接下单
- 顾客只说菜品没说人数 → 直接下单，人数不是必填项
- **永远不要主动问桌号**

### 下单流程
1. 顾客提到菜品 → 查菜单确认 → 有订单则 add_to_order / 无订单则 create_order
2. 返回：订单号 + 合计金额（简短确认）
3. 问一句「还需要加点什么吗？」即可

### 结账流程
- 当顾客明确说「去结账」「买单」「付款」「支付」时，调用工具 `checkout_session` 完成支付，不要只列订单或让顾客点按钮
- 支付成功后，根据工具返回结果回复：「已为您结账，共支付 ¥XX，订单号 ...。欢迎下次光临！」
- 如果当前没有待支付订单，告知顾客「当前没有待支付订单」
- 结账时按会话状态中的订单列出全部菜品和金额，不得凭记忆总结，必须以订单列表为准

### 推荐流程
1. 顾客说需求 → 调 recommend_dishes → 展示推荐结果
2. 只需问「有想尝试的吗？」
3. 不要在推荐后再问口味/忌口（刚才已经说了）

## 语气
- 使用中文，简洁专业，不啰嗦
- 每次回复控制在 3-5 行以内，长列表用精简格式
- 避免过度热情（「太棒了！」、「绝了！」等）
"""


def _load_training_examples() -> str:
    """读取 data/training_examples.json，返回格式化的示例文本。
    
    你只需要修改那个 JSON 文件，就能"训练"AI 的回复风格和内容逻辑，
    完全不需要碰 Python 代码。
    """
    if not os.path.exists(TRAINING_EXAMPLES_FILE):
        return ""
    try:
        with open(TRAINING_EXAMPLES_FILE, encoding="utf-8") as f:
            examples = json.load(f)
        if not examples or not isinstance(examples, list):
            return ""
        lines = [
            "",
            "## 标准问答示例（仅参考回复风格，禁止照搬菜品）",
            "⚠️ 重要：以下示例里的菜名、价格、描述是历史菜单的快照，可能与当前菜单不符。",
            "  - 你只能参考示例的「说话方式、回复结构、语气」",
            "  - 实际推荐/下单必须调用 get_menu / recommend_dishes 查当前菜单",
            "  - 示例里出现的菜如果不在当前菜单中，绝对不能推荐给顾客",
            "  - 示例里的价格不得直接使用，必须以 get_menu 返回的价格为准",
        ]
        for i, ex in enumerate(examples, 1):
            user = ex.get("user", "")
            reply = ex.get("reply", "")
            if user and reply:
                lines.append(f"示例{i}：")
                lines.append(f"  顾客：{user}")
                lines.append(f"  助手：{reply}")
        return "\n".join(lines)
    except Exception:
        return ""


def _log_conversation(
    session_id: str,
    user_message: str,
    reply: str,
    tools_called: list[dict],
) -> None:
    """每次对话后，将 (session_id, 用户问, AI答, 调用了什么工具) 追加写入 conversations.json"""
    entry = {
        "session_id": session_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "user_message": user_message,
        "reply": reply,
        "tools_called": tools_called,
    }
    os.makedirs(os.path.dirname(CONVERSATIONS_FILE) or ".", exist_ok=True)
    history = []
    if os.path.exists(CONVERSATIONS_FILE):
        try:
            with open(CONVERSATIONS_FILE, encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, Exception):
            history = []
    history.append(entry)
    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


class DiningAgent:
    def __init__(self):
        cfg = get_llm_config()
        self.client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
        )
        self.model = cfg["model"]
        self.conversations: dict[str, list[dict]] = {}
        # 每个 session 关联的订单 ID 列表
        self.session_orders: dict[str, list[str]] = {}
        # 每个 session 的槽位状态表（人数/过敏/偏好等，从对话中实时提取）
        self.session_slots: dict[str, dict] = {}
        # 会话级分片锁：同一 session 的请求必须串行（见 _session_lock 说明）
        self._locks = [threading.Lock() for _ in range(self._LOCK_STRIPES)]

    # ── 并发保护 ──
    # 对抗测试发现：同一 session 并发请求会交错写入共享的会话历史
    # （_get_history 返回的是 self.conversations[session_id] 这个列表的**引用**），
    # 导致 LLM 读到别的请求的工具返回，回复里的订单号张冠李戴
    # （实测 3 并发：产生 3 个订单，却有 2 条回复报同一个订单号，另有订单号从未告知顾客）。
    # 这里用「分片锁」把同一 session 的请求串行化：
    # 固定若干把锁按 session_id 哈希分配，既解决问题，又避免为每个 session 建锁导致内存无限增长。
    _LOCK_STRIPES = 64

    def _session_lock(self, session_id: str) -> threading.Lock:
        return self._locks[hash(session_id) % self._LOCK_STRIPES]

    def _get_restaurant_name(self) -> str:
        """店名与菜单同源：实时读 menu.json 的 restaurant 字段。

        修复：此前店名硬编码「川味小馆」，import 换菜单后店名不跟随（队友实测 bug）。
        现每次创建新会话时读取，import 新菜单后的新会话立即使用新店名。
        """
        try:
            with open(MENU_FILE, encoding="utf-8") as f:
                name = (json.load(f).get("restaurant") or "").strip()
            return name or "本店"
        except Exception:
            return "本店"

    def _get_history(self, session_id: str) -> list[dict]:
        if session_id not in self.conversations:
            # 首次创建时动态加载 training examples 拼进 system prompt
            examples_text = _load_training_examples()
            prompt = SYSTEM_PROMPT_TMPL.format(restaurant=self._get_restaurant_name()) + examples_text
            self.conversations[session_id] = [{"role": "system", "content": prompt}]

            # 尝试从文件恢复对话历史（防止云托管实例重启/水平扩展导致内存丢失）
            self._restore_history(session_id)
            # 恢复订单关联
            self._restore_session_orders(session_id)
        return self.conversations[session_id]

    def _restore_history(self, session_id: str) -> None:
        """从文件恢复对话历史。云托管多实例时内存状态可能丢失。"""
        try:
            hist_file = os.path.join(HISTORY_DIR, f"{session_id}.json")
            if os.path.exists(hist_file):
                with open(hist_file, encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, list) and len(saved) > 1:
                    # 清理消息格式：确保每条消息都有 role 和 content
                    clean = []
                    for m in saved:
                        if not isinstance(m, dict):
                            continue
                        role = m.get("role")
                        if not role:
                            continue
                        # 确保有 content 字段（即使为 None）
                        if "content" not in m:
                            m["content"] = None
                        clean.append(m)
                    if len(clean) > 1:
                        self.conversations[session_id] = clean
        except Exception:
            pass

    def _save_history(self, session_id: str) -> None:
        """持久化对话历史到文件。"""
        try:
            os.makedirs(HISTORY_DIR, exist_ok=True)
            hist_file = os.path.join(HISTORY_DIR, f"{session_id}.json")
            history = self.conversations.get(session_id, [])
            # 确保所有消息都是可序列化的 dict（防止 OpenAI 对象混入）
            clean_history = []
            for m in history:
                if isinstance(m, dict):
                    clean_history.append(m)
                elif hasattr(m, "model_dump"):
                    clean_history.append(m.model_dump())
                else:
                    clean_history.append({"role": "assistant", "content": str(m)})
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump(clean_history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _restore_session_orders(self, session_id: str) -> None:
        """从 orders.json 恢复该 session 关联的订单 ID。

        云托管多实例部署时，内存中的 session_orders 可能丢失。
        此方法从持久化文件重建关联，确保上下文注入不缺订单信息。
        """
        if session_id in self.session_orders and self.session_orders[session_id]:
            return  # 已有数据，无需恢复
        try:
            if os.path.exists(ORDERS_FILE):
                with open(ORDERS_FILE, encoding="utf-8") as f:
                    all_orders = json.load(f)
                if isinstance(all_orders, list):
                    oids = [o["order_id"] for o in all_orders
                            if o.get("session_id") == session_id and o.get("order_id")]
                    if oids:
                        self.session_orders[session_id] = oids
        except Exception:
            pass

    # ─── 中文数字映射 ───
    _CN_NUM = {'一':1,'两':2,'俩':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}

    def _extract_slots(self, session_id: str, message: str) -> None:
        """从用户消息中提取关键信息，填入会话槽位表。

        纯正则提取，不调用 API，零延迟。提取到的信息累积存储，
        后出现的覆盖先前的（例如顾客改口「其实是三个人」）。
        """
        if session_id not in self.session_slots:
            self.session_slots[session_id] = {}
        slots = self.session_slots[session_id]

        # ── 1) 用餐人数 ──
        # "2位"、"两个人"、"六个人"、"我们四个"、"一人"
        m = re.search(r'(\d+)\s*(?:个?人|位)', message)
        if m:
            slots['diner_count'] = f"{m.group(1)}位"
        else:
            m = re.search(r'([一二两俩三四五六七八九十])\s*(?:个人|个|位|人)', message)
            if m:
                n = self._CN_NUM.get(m.group(1))
                if n:
                    slots['diner_count'] = f"{n}位"

        # ── 2) 过敏/忌口 ──
        # 用 {1,2} 限制匹配长度，避免吞掉 "我对花生" 这种前缀
        found = []
        for m in re.finditer(r'([\u4e00-\u9fff]{1,2})过敏', message):
            w = m.group(1)
            if w not in ('不过','没有','不会','有人','人对','我对','有对','会对'):
                found.append(f"{w}过敏")
        for m in re.finditer(r'不吃([\u4e00-\u9fff]{1,2})', message):
            found.append(f"不吃{m.group(1)}")
        for m in re.finditer(r'对([\u4e00-\u9fff]{1,2})过敏', message):
            found.append(f"{m.group(1)}过敏")
        if found:
            # 排除口味偏好词（"不吃辣" 不属于过敏）
            found = [a for a in found if '辣' not in a]
            cur = set(slots.get('allergies', '').split('、')) if slots.get('allergies') else set()
            cur.update(a for a in found if a)
            cur.discard('')
            slots['allergies'] = '、'.join(sorted(cur))

        # ── 3) 口味偏好 ──
        for pat, val in [
            (r'微辣', '微辣'), (r'不[太要]辣|不要辣', '不要辣'),
            (r'麻辣', '麻辣'), (r'中辣', '中辣'), (r'特辣', '特辣'),
            (r'清淡', '清淡'), (r'少辣', '少辣'),
            (r'不吃辣|不能吃辣', '不能吃辣'), (r'能吃辣|喜欢.?辣', '爱吃辣'),
        ]:
            if re.search(pat, message):
                slots['spicy_preference'] = val
                break

        # ── 4) 特殊需求 ──
        specs = []
        if re.search(r'快[一点些]|着急|赶时间', message):
            specs.append('催菜')
        if re.search(r'包间|包房|雅间', message):
            specs.append('要包间')
        if specs:
            cur_s = set(slots.get('specials', '').split('、')) if slots.get('specials') else set()
            cur_s.update(specs)
            cur_s.discard('')
            slots['specials'] = '、'.join(sorted(cur_s))

    def _build_session_context(self, session_id: str) -> str:
        """构建会话上下文状态表。

        将已提取的槽位（人数/过敏/偏好）+ 订单信息格式化为 Markdown 表格，
        注入到每条用户消息前。LLM 无需从长篇对话历史中回忆任何信息——
        所有关键状态都在这张表里。
        """
        slots = self.session_slots.get(session_id, {})
        order_ids = self.session_orders.get(session_id, [])

        # 收集订单详情
        orders_detail = []
        try:
            if order_ids and os.path.exists(ORDERS_FILE):
                with open(ORDERS_FILE, encoding="utf-8") as f:
                    all_orders = json.load(f)
                if isinstance(all_orders, list):
                    for oid in order_ids:
                        for o in all_orders:
                            if o.get("order_id") == oid:
                                items = o.get("items", [])
                                item_strs = [
                                    f"{it.get('dish_name','?')}×{it.get('quantity',1)}"
                                    for it in items
                                ]
                                total = o.get("total", 0)
                                status = "已支付" if o.get("paid") else "待支付"
                                orders_detail.append(
                                    f"{oid}：{'、'.join(item_strs)} = ¥{total}（{status}）"
                                )
                                break
        except Exception:
            orders_detail = [f"{oid}（详情暂不可用）" for oid in order_ids]

        # ── 构建自然语言状态摘要 ──
        lines = ["【当前会话状态】"]
        lines.append(f"用餐人数：{slots.get('diner_count', '未知')}")

        # 过敏信息加醒目标记，防止长上下文中被忽略
        allergies = slots.get('allergies', '无')
        if allergies and allergies != '无':
            lines.append(f"⚠️过敏/忌口：{allergies}（绝对禁止推荐含过敏原的菜品）")
        else:
            lines.append(f"过敏/忌口：无")

        lines.append(f"口味偏好：{slots.get('spicy_preference', '无特殊要求')}")

        specs = slots.get('specials', '')
        if specs:
            lines.append(f"特殊需求：{specs}")

        if orders_detail:
            for od in orders_detail:
                lines.append(f"已有订单：{od}")
        else:
            lines.append(f"已有订单：暂无")

        lines.append("规则：加单/换菜/退菜均在已有 order_id 上操作，不得新建订单；结账时按上方订单逐项核对，不得遗漏；⚠️过敏信息绝对不得违反，推荐菜品前必须检查是否含过敏原；已告知信息不得重复询问。")

        return "\n".join(lines)

    # ─── 辅助方法 ───

    def _finish_reply(self, history, session_id, message, reply, tools_called_info) -> str:
        """统一收尾：追加 assistant 回复 + 记日志 + 持久化"""
        history.append({"role": "assistant", "content": reply})
        _log_conversation(session_id, message, reply, tools_called_info)
        self._save_history(session_id)
        return reply

    def _run_checkout(self, session_id: str) -> str:
        """结账硬兜底：直接调用 checkout_session，绕开 LLM 记忆"""
        try:
            result = TOOL_MAP["checkout_session"](session_id=session_id)
            data = json.loads(result)
            if data.get("paid_orders"):
                return (
                    f"已为您结账，共支付 ¥{data['total']}，"
                    f"订单号 {', '.join(data['paid_orders'])}。欢迎下次光临！"
                )
            return data.get("message", "当前没有待支付订单。")
        except Exception:
            return "结账处理完成。"

    @staticmethod
    def _to_msg_dict(msg) -> dict:
        """将 OpenAI ChatCompletionMessage 转为纯 dict（可 JSON 序列化）"""
        msg_dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in msg.tool_calls
            ]
        return msg_dict

    def _execute_tool(self, tc, session_id: str) -> tuple[str, dict]:
        """执行一次工具调用。返回 (result, called_info)。
        🔒 异常兜底：工具抛异常时返回错误 JSON 给 LLM，绝不中断对话，
        否则 history 会留下"孤儿"assistant tool_calls 消息导致后续 400。
        """
        func_name = tc.function.name
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}

        called_info = {"name": func_name, "arguments": args}

        # 给 create_order / checkout_session 注入 session_id
        if func_name in ("create_order", "checkout_session"):
            args["session_id"] = session_id

        func = TOOL_MAP.get(func_name)
        if func:
            try:
                result = func(**args)
            except Exception as e:
                # 打到 stdout 便于 docker logs 排查（工具异常被吞的根因）
                print(f"[TOOL_ERR] {func_name}: {type(e).__name__}: {e}", flush=True)
                result = json.dumps({
                    "error": f"工具 {func_name} 执行失败: {type(e).__name__}: {str(e)[:100]}",
                    "arguments": args,
                    "hint": "请检查参数格式后重试，或改用其他方式处理",
                }, ensure_ascii=False)
            if func_name == "create_order":
                self._record_order(session_id, result)
        else:
            result = json.dumps({"error": f"未知工具: {func_name}"})

        return result, called_info

    # ─── LLM 调用：历史压缩 + 重试 + 错误分类 ───
    # 解决"动不动回退 AI 暂时无法回应"：
    #   1) 多轮对话 history 无限增长 → token 超 DeepSeek 上限 → 400
    #   2) DeepSeek 限流/超时 → 无重试直接兜底
    # 压缩：超阈值时保留 system + 最近 N 条，丢弃旧消息
    # 重试：限流/超时退避重试 2 次；context 超长则压缩后重试

    _COMPRESS_THRESHOLD = 24   # 消息条数超过此值触发压缩
    _COMPRESS_KEEP = 10        # 压缩后保留最近多少条

    def _compress_history(self, history: list[dict]) -> list[dict]:
        """压缩对话历史：保留 system + 最近 N 条，丢弃中间旧消息。

        OpenAI 工具调用要求 assistant(tool_calls) 紧跟 tool(role) 回复，
        所以压缩后起始位置不能落在孤立的 tool 消息上——
        遇到 tool 就往前补配对的 assistant tool_calls 消息。
        """
        if len(history) <= self._COMPRESS_THRESHOLD:
            return history
        system_msgs = [m for m in history if m.get("role") == "system"]
        recent = history[-self._COMPRESS_KEEP:]
        start_idx = len(history) - self._COMPRESS_KEEP
        while recent and recent[0].get("role") == "tool":
            prev_idx = start_idx - 1
            if prev_idx >= 0 and history[prev_idx].get("role") == "assistant" and history[prev_idx].get("tool_calls"):
                recent = [history[prev_idx]] + recent
                start_idx = prev_idx
            else:
                break
        return system_msgs + recent

    def _call_llm(self, history: list[dict], with_tools: bool = True, max_tokens: int = 2048):
        """调用 LLM，带历史压缩 + 重试 + 错误分类。

        - context 超长 → 压缩历史后重试
        - 限流/超时/连接错误 → 退避重试 2 次
        - 其他异常 → 直接抛（上层兜底）
        """
        kwargs = {
            "model": self.model,
            "messages": history,
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }
        if with_tools:
            kwargs["tools"] = TOOL_DEFINITIONS
            kwargs["tool_choice"] = "auto"

        last_err = None
        for attempt in range(3):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                # 1) 上下文超长 → 压缩历史后重试
                if any(k in err_str for k in ("context", "token", "too long", "maximum")):
                    history = self._compress_history(history)
                    kwargs["messages"] = history
                    continue
                # 2) 限流/超时/连接错误 → 退避重试
                if any(k in err_str for k in ("rate", "429", "timeout", "timed out", "connection", "api_error")):
                    if attempt < 2:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                # 3) 其他异常 → 不重试，直接抛
                raise
        raise last_err

    def chat(self, session_id: str, message: str) -> str:
        """对外入口：同一 session 的请求串行处理。

        并发保护的必要性见 _session_lock 的说明 —— 不加锁时，同一会话的并发请求
        会交错写入共享的会话历史，导致回复里报出别人的订单号。
        """
        with self._session_lock(session_id):
            return self._chat_locked(session_id, message)

    def _chat_locked(self, session_id: str, message: str) -> str:
        history = self._get_history(session_id)
        _msg = message.strip()

        # 0) 槽位提取：从用户消息中提取人数/过敏/偏好等，填入状态表
        self._extract_slots(session_id, _msg)

        # 1) 寒暄词 + 已有对话历史 → 直接返回续接回复
        _greetings = {"你好", "您好", "在吗", "有人吗", "嗨"}
        if _msg.lower() in {g.lower() for g in _greetings} and len(history) >= 3:
            _reply = "您好~ 请问还需要加点什么吗？或者有其他需要我帮忙的？"
            history.append({"role": "assistant", "content": _reply})
            _log_conversation(session_id, message, _reply, [])
            self._save_history(session_id)
            return _reply

        # 2) 负数数量检测 → 硬拦截
        _neg = re.search(r'[-——]\s*\d+\s*(份|个|碗|杯|瓶|盘|斤|套)', _msg)
        if _neg:
            _reply = f"您提到的数量「{_neg.group(0)}」似乎不太对哦——数量必须是大于0的正整数。您是想来几份呢？"
            history.append({"role": "assistant", "content": _reply})
            _log_conversation(session_id, message, _reply, [])
            self._save_history(session_id)
            return _reply

        # 2.5) 结账意图硬兜底（「多少」排除询问价格场景）
        # ⚠️ 混合意图放行：顾客一句话"加一份X，结账"时不能直接结账，
        #    否则加单被跳过（漏单）。有加单意图时交给 LLM 先加单再结账。
        _checkout_words = ["去结账", "买单", "付款", "支付", "结账"]
        _has_add_intent = bool(re.search(
            r"(加|来|点|上|要)\s*[一二两三四五六七八九十0-9]{0,2}\s*(份|个|碗|杯|瓶|听|盒|盘)", _msg))
        if any(w in _msg for w in _checkout_words) and "多少" not in _msg and not _has_add_intent:
            reply = self._run_checkout(session_id)
            history.append({"role": "user", "content": _msg})
            history.append({"role": "assistant", "content": reply})
            _log_conversation(
                session_id,
                message,
                reply,
                [{"name": "checkout_session", "arguments": {"session_id": session_id}}],
            )
            self._save_history(session_id)
            return reply

        # 3) 🔑 上下文注入：在用户消息前拼接会话状态
        context = self._build_session_context(session_id)
        if context:
            _msg = context + "\n\n---\n顾客消息: " + _msg

        # 下单意图检测（在 context 注入前的原始消息上判断）
        raw_msg = message.strip()
        order_intent = bool(re.search(
            r"(来|点|加|上|要)\s*[一二两三四五六七八九十0-9]{0,2}\s*(份|个|碗|杯|瓶|听|盒|盘)|下单|确认下单|就这些",
            raw_msg))

        history.append({"role": "user", "content": _msg})

        tools_called_info: list[dict] = []
        max_rounds = 3
        forced_order_retry = False

        for _round in range(max_rounds):
            try:
                response = self._call_llm(history, with_tools=True)
            except Exception as e:
                error_msg = f"（AI 暂时无法回应：{str(e)[:80]}）"
                return self._finish_reply(history, session_id, message, error_msg, tools_called_info)

            msg = response.choices[0].message

            if not msg.tool_calls:
                # 🔒 写入操作真实性检测（防幻觉确认）：
                # AI 回复声称"已下单/已加/已结账"但本轮对话从未调用过任何写入工具
                # → 用 tool_choice="required" 强制重试一次
                replied = msg.content or ""
                _confirm_words = ("已为您", "已下单", "已加", "已加入", "已取消", "已退", "订单号", "共支付", "合计")
                _wrote = any(c["name"] in _WRITE_TOOLS for c in tools_called_info)
                _lied = (not _wrote) and any(w in replied for w in _confirm_words)
                # 下单意图兜底：仅首轮响应且未执行过工具时触发
                needs_force = (_round == 0 and not tools_called_info and order_intent) or (_lied and not forced_order_retry)
                if needs_force:
                    forced_order_retry = True
                    history.append({"role": "user", "content": "（系统提示：你上一条回复声称已完成点餐操作，但实际没有调用任何写入工具。请立即调用正确的工具（create_order/add_to_order/replace_item/delete_item/checkout_session）执行操作。）"})
                    try:
                        forced = self.client.chat.completions.create(
                            model=self.model, messages=history,
                            tools=TOOL_DEFINITIONS, tool_choice="required",
                            temperature=0.2, max_tokens=2048,
                        )
                        msg = forced.choices[0].message
                        if not msg.tool_calls:
                            return self._finish_reply(history, session_id, message, msg.content, tools_called_info)
                    except Exception:
                        return self._finish_reply(history, session_id, message, msg.content, tools_called_info)
                else:
                    return self._finish_reply(history, session_id, message, msg.content, tools_called_info)

            # 将 OpenAI Message 对象转为 dict 再存入 history（可序列化）
            history.append(self._to_msg_dict(msg))
            for tc in msg.tool_calls:
                result, called = self._execute_tool(tc, session_id)
                tools_called_info.append(called)
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # 超了 max_rounds 还没出回复 → 强制让 LLM 总结
        try:
            response = self._call_llm(history, with_tools=False, max_tokens=1024)
            reply = response.choices[0].message.content
        except Exception:
            reply = "抱歉，让我想想。请问还有什么需要的吗？"

        return self._finish_reply(history, session_id, message, reply, tools_called_info)


    def _record_order(self, session_id: str, order_result: str) -> None:
        """从 create_order 的返回里提取订单 ID，关联到 session"""
        try:
            data = json.loads(order_result)
            order_id = data.get("order_id")
            if order_id:
                if session_id not in self.session_orders:
                    self.session_orders[session_id] = []
                self.session_orders[session_id].append(order_id)
        except (json.JSONDecodeError, TypeError):
            pass

    def get_session_orders(self, session_id: str) -> list[str]:
        """返回该 session 的所有订单 ID"""
        return self.session_orders.get(session_id, [])

    def clear_session(self, session_id: str) -> None:
        # 与 chat 共用同一把会话锁：避免「清空会话」和「正在进行的对话」互相踩踏
        with self._session_lock(session_id):
            if session_id in self.conversations:
                del self.conversations[session_id]
            if session_id in self.session_orders:
                del self.session_orders[session_id]
            if session_id in self.session_slots:
                del self.session_slots[session_id]
            # 清理持久化的对话历史文件
            try:
                hist_file = os.path.join(HISTORY_DIR, f"{session_id}.json")
                if os.path.exists(hist_file):
                    os.remove(hist_file)
            except Exception:
                pass
