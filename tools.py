"""工具函数 — AI Agent 通过 Function Calling 调用的业务逻辑"""
import json
import os
import threading
from typing import Optional
from config import MENU_FILE, ORDERS_FILE

# 订单文件全局锁：orders.json 是全量读改写，两个不同 session 并发下单
# 会互相覆盖（丢订单）。agent.py 的分片锁只串行化同 session 请求，管不到跨 session。
_ORDERS_LOCK = threading.Lock()


def _orders_locked(fn):
    """订单读写函数的互斥装饰器：保证 read-modify-write 原子"""
    def wrapper(*args, **kwargs):
        with _ORDERS_LOCK:
            return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _load_json(path: str):
    """读 JSON。文件不存在或损坏时返回空默认值，绝不抛异常。

    历史教训：orders.json 曾因并发写/写入中断产生半文件，
    导致 json.load 抛 JSONDecodeError → create_order 整个挂掉。
    现在损坏时自动降级返回空，服务不中断，日志告警。
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    default = [] if "order" in path else {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        print(f"[STORAGE_WARN] {path} 损坏，已重置为默认值", flush=True)
        return default


def _save_json(path: str, data) -> None:
    """原子写：先写 .tmp 再 rename，避免写入中断产生半文件。

    os.replace 在同一文件系统内是原子操作，
    要么完整生效要么不生效，不会留半写状态。
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ─── 工具定义（给 LLM 的 Function Calling schema）───

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_menu",
            "description": "查询菜单，可按分类筛选（招牌必点/凉菜/热菜·川味/热菜·清淡/汤类/主食/饮品）或搜索菜品名",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "分类名称，不传则返回全部菜单",
                        "enum": ["招牌必点", "凉菜", "热菜·川味", "热菜·清淡", "汤类", "主食", "饮品"],
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（菜品名）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_dishes",
            "description": "根据口味偏好和过敏史推荐菜品",
            "parameters": {
                "type": "object",
                "properties": {
                    "preferences": {
                        "type": "string",
                        "description": "口味偏好，如：辣/不辣/清淡/酸甜等",
                    },
                    "allergens": {
                        "type": "string",
                        "description": "过敏原，如：花生/鸡蛋/海鲜等，没有则传空字符串",
                    },
                    "count": {
                        "type": "integer",
                        "description": "推荐数量，默认3",
                    },
                },
                "required": ["preferences"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "创建新订单（首次下单时使用）。customer_name 不是必填的，顾客没提供桌号就不用问，直接下单即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "顾客名或桌号，顾客没提供就传空字符串或不传",
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dish_name": {"type": "string", "description": "菜品名称，如：毛血旺、米饭"},
                                "quantity": {"type": "integer", "description": "数量，必须大于0"},
                            },
                            "required": ["dish_name", "quantity"],
                        },
                        "description": "点的菜品列表（菜名即可，不用ID）",
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_order",
            "description": "追加菜品到已有订单（加单时使用，不要用 create_order 创建新订单）。先从对话历史或之前 create_order 的返回中找到订单编号，然后传进来。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "已有订单的编号，如 ORD0001",
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dish_name": {"type": "string", "description": "要追加的菜品名称"},
                                "quantity": {"type": "integer", "description": "数量，必须大于0"},
                            },
                            "required": ["dish_name", "quantity"],
                        },
                        "description": "要追加的菜品列表",
                    },
                },
                "required": ["order_id", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_ingredient",
            "description": "查询菜品的食材信息和供应链追溯（MVP基础版）",
            "parameters": {
                "type": "object",
                "properties": {
                    "dish_name": {
                        "type": "string",
                        "description": "菜品名称",
                    },
                },
                "required": ["dish_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "checkout_session",
            "description": "结账/支付当前会话中所有未支付订单。仅在顾客明确说「去结账」「买单」「付款」「支付」时调用，调用后会将订单标记为已支付。",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "当前会话 ID，通常由系统自动传入",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_item",
            "description": "换菜：把订单里的一道菜换成另一道菜（顾客说「把A换成B」「A不要了换C」时必须用这个，绝不能用 add_to_order 加新菜凑数）",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "已有订单的编号，如 ORD0001",
                    },
                    "old_dish_name": {"type": "string", "description": "要换掉的菜品名称"},
                    "new_dish_name": {"type": "string", "description": "换成的新菜品名称"},
                    "quantity": {"type": "integer", "description": "新菜数量，默认1"},
                },
                "required": ["order_id", "old_dish_name", "new_dish_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_item",
            "description": "退菜：从订单中删除一道菜（顾客说「X不要了」「退掉X」时使用）",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "已有订单的编号，如 ORD0001",
                    },
                    "dish_name": {"type": "string", "description": "要退掉的菜品名称"},
                    "quantity": {"type": "integer", "description": "退几份，不传则整项删除"},
                },
                "required": ["order_id", "dish_name"],
            },
        },
    },
]


# ─── 工具实现 ───

def query_menu_list(category: Optional[str] = None, keyword: Optional[str] = None) -> list[dict]:
    """查询菜单，返回 list[dict]（供 HTTP API 使用）"""
    menu = _load_json(MENU_FILE)
    results = []
    for cat in menu.get("categories", []):
        if category and cat["name"] != category:
            continue
        for item in cat["items"]:
            if keyword and keyword not in item["name"]:
                continue
            results.append({
                "分类": cat["name"],
                "菜品": item["name"],
                "价格": f"¥{item['price']}",
                "辣度": item["spicy"],
                "食材": ", ".join(item["ingredients"]),
                "过敏原": ", ".join(item["allergens"]) if item["allergens"] else "无",
                "描述": item["description"],
            })
    return results


def _menu_empty() -> bool:
    """菜单是否尚未配置（空店态）"""
    menu = _load_json(MENU_FILE)
    return not menu.get("categories")


def get_menu(category: Optional[str] = None, keyword: Optional[str] = None) -> str:
    """查询菜单，返回 JSON 字符串（供 LLM Function Calling 使用）"""
    if _menu_empty():
        return "（本店菜单尚未配置。请礼貌告知顾客：菜单正在紧张整理中，稍后再来即可，暂时无法点餐。）"
    results = query_menu_list(category=category, keyword=keyword)
    if not results:
        return "没有找到匹配的菜品。"
    return json.dumps(results, ensure_ascii=False, indent=2)


def recommend_dishes(preferences: str, allergens: str = "", count: int = 3) -> str:
    if _menu_empty():
        return "（本店菜单尚未配置，无法推荐。请礼貌告知顾客菜单正在整理中。）"
    menu = _load_json(MENU_FILE)
    all_items = []
    for cat in menu.get("categories", []):
        for item in cat["items"]:
            all_items.append(item)

    # 根据口味和过敏原过滤
    if "不辣" in preferences:
        all_items = [i for i in all_items if i["spicy"] == "不辣"]
    if "辣" in preferences and "不辣" not in preferences:
        all_items = [i for i in all_items if i["spicy"] != "不辣"]

    if allergens:
        allergen_list = [a.strip() for a in allergens.replace("，", ",").split(",")]
        for a in allergen_list:
            all_items = [i for i in all_items if a not in i["allergens"]]

    # 按相关性简单排序（有描述的优先）
    all_items.sort(key=lambda x: len(x.get("description", "")), reverse=True)

    top = all_items[:count]
    if not top:
        return "抱歉，没有找到符合口味的菜品推荐。"

    results = []
    for item in top:
        # 找到分类名
        cat_name = ""
        for cat in menu["categories"]:
            if item in cat["items"]:
                cat_name = cat["name"]
                break
        results.append({
            "菜品": item["name"],
            "分类": cat_name,
            "价格": f"¥{item['price']}",
            "辣度": item["spicy"],
            "描述": item["description"],
        })

    return json.dumps(results, ensure_ascii=False, indent=2)


@_orders_locked
def create_order(items=None, customer_name: str = "", session_id: str = "") -> str:
    # 🔒 参数校验：LLM 传参不可信，坏参数返回友好错误，绝不抛异常
    if items is None or not isinstance(items, list) or not items:
        return json.dumps(
            {"error": "items 参数必须是菜品数组（如 [{'dish_name': '水煮鱼', 'quantity': 1}]），不能为空"},
            ensure_ascii=False,
        )
    for entry in items:
        if not isinstance(entry, dict):
            return json.dumps({"error": f"items 中的元素必须是对象，收到 {type(entry).__name__}"}, ensure_ascii=False)
        if "dish_name" not in entry or not entry["dish_name"]:
            return json.dumps({"error": "items 中的每个菜品必须有 dish_name 字段"}, ensure_ascii=False)

    menu = _load_json(MENU_FILE)
    # 菜名→菜品映射
    dish_map = {}
    for cat in menu.get("categories", []):
        for item in cat.get("items", []):
            dish_map[item["name"]] = item

    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        orders = []

    order_items = []
    total = 0
    errors = []
    for entry in items:
        name = entry.get("dish_name", "")
        dish = dish_map.get(name)
        if not dish:
            # 模糊匹配
            for dname, ditem in dish_map.items():
                if name in dname or dname in name:
                    dish = ditem
                    break
        if not dish:
            errors.append(f"「{name}」未在菜单中找到")
            continue
        qty = entry.get("quantity", 1)
        # 数量合法性校验：必须为正整数
        if not isinstance(qty, int) or qty <= 0:
            errors.append(f"「{name}」的数量无效（quantity={qty}，必须为正整数）")
            continue
        subtotal = dish["price"] * qty
        order_items.append({
            "dish_id": dish["id"],
            "dish_name": dish["name"],
            "quantity": qty,
            "unit_price": dish["price"],
            "subtotal": subtotal,
        })
        total += subtotal

    if errors:
        return f"以下菜品有问题：{'；'.join(errors)}。请核对后再下单。"

    customer = customer_name or "顾客"
    # 🔒 订单号基于现有最大编号生成，防重复（历史并发期曾产生重复 ORD0083）
    try:
        max_no = max(
            int(str(o.get("order_id", ""))[3:])
            for o in orders
            if str(o.get("order_id", "")).startswith("ORD")
            and str(o["order_id"])[3:].isdigit()
        )
    except ValueError:
        max_no = len(orders)
    order = {
        "order_id": f"ORD{max_no + 1:04d}",
        "session_id": session_id,
        "customer": customer,
        "items": order_items,
        "total": total,
        "status": "已确认",
        "paid": False,
    }
    orders.append(order)
    _save_json(ORDERS_FILE, orders)
    return json.dumps(order, ensure_ascii=False, indent=2)


@_orders_locked
def add_to_order(order_id: str, items: list[dict]) -> str:
    """追加菜品到已有订单（加单时使用）"""
    menu = _load_json(MENU_FILE)
    dish_map = {}
    for cat in menu["categories"]:
        for item in cat["items"]:
            dish_map[item["name"]] = item

    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        orders = []

    # 找目标订单
    target = None
    for o in orders:
        if o.get("order_id") == order_id:
            target = o
            break

    if not target:
        return f"未找到订单 {order_id}，可能已被清台。请重新下单（使用 create_order）。"

    errors = []
    new_items = []
    for entry in items:
        name = entry.get("dish_name", "")
        dish = dish_map.get(name)
        if not dish:
            for dname, ditem in dish_map.items():
                if name in dname or dname in name:
                    dish = ditem
                    break
        if not dish:
            errors.append(f"「{name}」未在菜单中找到")
            continue
        qty = entry.get("quantity", 1)
        if not isinstance(qty, int) or qty <= 0:
            errors.append(f"「{name}」的数量无效（quantity={qty}，必须为正整数）")
            continue

        # 检查是否已有同名菜品 → 合并数量
        existing = None
        for ei in target["items"]:
            if ei.get("dish_name") == dish["name"]:
                existing = ei
                break

        if existing:
            existing["quantity"] += qty
            existing["subtotal"] = dish["price"] * existing["quantity"]
        else:
            new_items.append({
                "dish_id": dish["id"],
                "dish_name": dish["name"],
                "quantity": qty,
                "unit_price": dish["price"],
                "subtotal": dish["price"] * qty,
            })

    if errors:
        return f"以下菜品有问题：{'；'.join(errors)}。请核对后再加单。"

    target["items"].extend(new_items)
    target["total"] = sum(i["subtotal"] for i in target["items"])

    _save_json(ORDERS_FILE, orders)
    return json.dumps(target, ensure_ascii=False, indent=2)


def _find_dish(dish_map: dict, name: str):
    """精确匹配 → 模糊匹配，返回菜品或 None"""
    dish = dish_map.get(name)
    if dish:
        return dish
    for dname, ditem in dish_map.items():
        if name in dname or dname in name:
            return ditem
    return None


def _find_order(orders: list, order_id: str):
    for o in orders:
        if o.get("order_id") == order_id:
            return o
    return None


@_orders_locked
def replace_item(order_id: str, old_dish_name: str, new_dish_name: str, quantity: int = 1) -> str:
    """换菜：删除旧菜 + 加入新菜，重算合计（一次原子操作，不会越换越多）"""
    menu = _load_json(MENU_FILE)
    dish_map = {}
    for cat in menu.get("categories", []):
        for item in cat["items"]:
            dish_map[item["name"]] = item

    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        orders = []
    target = _find_order(orders, order_id)
    if not target:
        return f"未找到订单 {order_id}。请先确认订单号。"

    if target.get("paid"):
        return f"订单 {order_id} 已支付，无法换菜。"

    old_dish = _find_dish(dish_map, old_dish_name)
    new_dish = _find_dish(dish_map, new_dish_name)
    if not new_dish:
        return f"新菜品「{new_dish_name}」未在菜单中找到，请核对。"

    # 定位旧菜（精确→模糊）
    old_entry = None
    for ei in target["items"]:
        if ei.get("dish_name") == old_dish_name:
            old_entry = ei
            break
    if not old_entry and old_dish:
        for ei in target["items"]:
            if old_dish["name"] in ei.get("dish_name", "") or ei.get("dish_name", "") in old_dish["name"]:
                old_entry = ei
                break
    if not old_entry:
        return f"订单 {order_id} 中没有「{old_dish_name}」，当前菜品：{'、'.join(i['dish_name'] for i in target['items'])}。请核对。"

    if not isinstance(quantity, int) or quantity <= 0:
        quantity = 1

    # 删旧菜
    target["items"].remove(old_entry)
    # 加新菜（同名合并）
    existing = None
    for ei in target["items"]:
        if ei.get("dish_name") == new_dish["name"]:
            existing = ei
            break
    if existing:
        existing["quantity"] += quantity
        existing["subtotal"] = new_dish["price"] * existing["quantity"]
    else:
        target["items"].append({
            "dish_id": new_dish["id"],
            "dish_name": new_dish["name"],
            "quantity": quantity,
            "unit_price": new_dish["price"],
            "subtotal": new_dish["price"] * quantity,
        })
    target["total"] = sum(i["subtotal"] for i in target["items"])

    _save_json(ORDERS_FILE, orders)
    return json.dumps(target, ensure_ascii=False, indent=2)


@_orders_locked
def delete_item(order_id: str, dish_name: str, quantity: int = None) -> str:
    """退菜：删除订单中的一道菜（quantity 不传整项删，传了减数量）"""
    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        orders = []
    target = _find_order(orders, order_id)
    if not target:
        return f"未找到订单 {order_id}。请先确认订单号。"

    if target.get("paid"):
        return f"订单 {order_id} 已支付，无法退菜。"

    old_entry = None
    for ei in target["items"]:
        if ei.get("dish_name") == dish_name:
            old_entry = ei
            break
    if not old_entry:
        for ei in target["items"]:
            if dish_name in ei.get("dish_name", "") or ei.get("dish_name", "") in dish_name:
                old_entry = ei
                break
    if not old_entry:
        return f"订单 {order_id} 中没有「{dish_name}」，当前菜品：{'、'.join(i['dish_name'] for i in target['items'])}。请核对。"

    if quantity is not None and isinstance(quantity, int) and 0 < quantity < old_entry["quantity"]:
        old_entry["quantity"] -= quantity
        old_entry["subtotal"] = old_entry["unit_price"] * old_entry["quantity"]
    else:
        target["items"].remove(old_entry)
    target["total"] = sum(i["subtotal"] for i in target["items"])

    _save_json(ORDERS_FILE, orders)
    return json.dumps(target, ensure_ascii=False, indent=2)


def list_orders(session_id: str = "") -> list[dict]:
    """查询某个 session 的所有订单。不传 session_id 返回全部（管理员用）"""
    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        return []
    if not session_id:
        # 查全部：返回所有订单（含历史脏数据，前端负责过滤展示）
        return orders
    # 只返回该 session 的精确匹配订单，不混入无 session_id 的历史数据
    return [o for o in orders if o.get("session_id") == session_id]


def delete_legacy_orders() -> str:
    """删除没有 session_id 的历史遗留订单（管理员清理用）"""
    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        return json.dumps({"removed": 0, "remaining": 0}, ensure_ascii=False)
    before = len(orders)
    cleaned = [o for o in orders if o.get("session_id")]
    removed = before - len(cleaned)
    _save_json(ORDERS_FILE, cleaned)
    return json.dumps({"removed": removed, "remaining": len(cleaned)}, ensure_ascii=False)


def pay_order(order_id: str) -> str:
    """模拟支付：把订单标记为已支付"""
    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        orders = []
    for o in orders:
        if o.get("order_id") == order_id:
            o["paid"] = True
            o["status"] = "已支付"
            _save_json(ORDERS_FILE, orders)
            return json.dumps({
                "order_id": order_id,
                "status": "已支付",
                "total": o.get("total", 0),
                "message": "支付成功"
            }, ensure_ascii=False, indent=2)
    return json.dumps({"error": f"未找到订单 {order_id}"}, ensure_ascii=False)


def clear_orders(session_id: str = "") -> str:
    """清台：删除某 session 的所有订单。不传 session_id 则清空全部（慎用）"""
    if not session_id:
        # 全部清空
        _save_json(ORDERS_FILE, [])
        return json.dumps({"cleared": "all", "message": "已清空所有订单"}, ensure_ascii=False)

    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        orders = []
    before = len(orders)
    orders = [o for o in orders if o.get("session_id") != session_id]
    after = len(orders)
    removed = before - after
    _save_json(ORDERS_FILE, orders)
    return json.dumps(
        {"cleared": session_id, "removed": removed, "remaining": after, "message": f"已清除 {removed} 笔订单"},
        ensure_ascii=False,
    )


def trace_ingredient(dish_name: str) -> str:
    menu = _load_json(MENU_FILE)
    for cat in menu["categories"]:
        for item in cat["items"]:
            if dish_name in item["name"]:
                info = {
                    "菜品": item["name"],
                    "食材": ", ".join(item["ingredients"]),
                    "过敏原": ", ".join(item["allergens"]) if item["allergens"] else "无",
                    "溯源信息": "（MVP版）食材采购自本地供应商，具体批次信息待完善",
                }
                return json.dumps(info, ensure_ascii=False, indent=2)
    return f"未找到菜品「{dish_name}」，请确认名称是否正确。"


@_orders_locked
def checkout_session(session_id: str = "") -> str:
    """结账：把当前 session 下所有未支付订单标记为已支付"""
    if not session_id:
        return json.dumps({"error": "缺少 session_id，无法结账"}, ensure_ascii=False)

    orders = _load_json(ORDERS_FILE)
    if not isinstance(orders, list):
        orders = []

    paid_orders = []
    total = 0
    for o in orders:
        if o.get("session_id") == session_id and not o.get("paid"):
            o["paid"] = True
            o["status"] = "已支付"
            paid_orders.append(o.get("order_id"))
            total += o.get("total", 0)

    if not paid_orders:
        return json.dumps(
            {"message": "当前没有待支付订单", "paid_orders": [], "total": 0},
            ensure_ascii=False,
        )

    _save_json(ORDERS_FILE, orders)
    return json.dumps(
        {
            "status": "已支付",
            "paid_orders": paid_orders,
            "total": total,
            "message": f"支付成功，共支付 ¥{total}",
        },
        ensure_ascii=False,
        indent=2,
    )


# ─── 函数映射（name → callable） ───

TOOL_MAP = {
    "get_menu": get_menu,
    "recommend_dishes": recommend_dishes,
    "create_order": create_order,
    "add_to_order": add_to_order,
    "replace_item": replace_item,
    "delete_item": delete_item,
    "trace_ingredient": trace_ingredient,
    "checkout_session": checkout_session,
}
