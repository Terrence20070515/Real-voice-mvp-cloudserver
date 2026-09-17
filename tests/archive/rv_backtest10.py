"""Real-voice 10轮回测：验证 orders.json 重置后下单恢复 + 全流程畅通。"""
import json, time, urllib.request

BASE = "http://101.34.242.247:8080"
SID = "test_10r_002"

CASES = [
    "你好",                    # 1 寒暄
    "两个人吃饭",              # 2 人数
    "有什么招牌菜推荐",        # 3 推荐
    "来一份水煮鱼",            # 4 下单(关键验证)
    "再来一份冬瓜排骨汤",      # 5 加单
    "我点了什么",              # 6 查单
    "加两碗米饭",              # 7 加单+数量
    "一共多少钱",              # 8 问价
    "去结账",                  # 9 结账
    "谢谢",                    # 10 结束
]

FALLBACK = ["暂时无法回应", "无法回应", "系统异常", "无法完成下单", "未能成功"]

print(f"=== Real-voice 10轮回测 ===\n会话: {SID}\n")
ok = fail = order_fail = 0
for i, msg in enumerate(CASES, 1):
    t0 = time.time()
    p = json.dumps({"session_id": SID, "message": msg}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/chat", data=p,
            headers={"Content-Type": "application/json"}, method="POST"), timeout=90)
        reply = json.loads(r.read()).get("reply", "")
    except Exception as e:
        print(f"[{i:2d}] ❌ 请求失败 | {msg}\n     {e}")
        fail += 1
        continue
    dt = time.time() - t0
    bad = any(m in reply for m in FALLBACK)
    is_order_step = msg in ("来一份水煮鱼", "再来一份冬瓜排骨汤", "加两碗米饭")
    if bad:
        tag = "⚠️" + ("下单失败" if is_order_step else "回退")
        if is_order_step: order_fail += 1
    else:
        tag = "✓"; ok += 1
    print(f"[{i:2d}] {tag} ({dt:.1f}s) | 顾客:{msg}\n     AI:{reply.replace(chr(10),' ')[:110]}")
    time.sleep(0.4)

print(f"\n=== 汇总 ===")
print(f"成功: {ok}/10 | 请求失败: {fail} | 下单失败: {order_fail}")
ord = "✅" if order_fail == 0 else f"⚠️ {order_fail}次下单失败"
print(f"下单: {ord}")
print(f"结论: {'✅ 全流程畅通，下单已恢复' if ok == 10 and order_fail == 0 else '⚠️ 仍有问题'}")
