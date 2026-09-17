"""20个独立长链会话回测：每会话10轮完整流程 + 订单数据ground truth校验。

每会话流程：寒暄→人数口味→推荐→下单→加单→换菜→混合结账→查单→寒暄→结束
预期金额链：18 → 24 → 84(换菜) → 112(加汤+结账, paid=True)
会话正确 = 10轮无回退/误判 + 订单金额正确 + 订单项正确 + 已支付
"""
import json, time, urllib.request

BASE = "http://101.34.242.247:8080"

CASES = [
    "你好",
    "我们两个人，不能吃辣",
    "有什么不辣的推荐",
    "来一份皮蛋豆腐",
    "再来两碗米饭",
    "把皮蛋豆腐换成东坡肘子",
    "再加一份冬瓜排骨汤，结账吧",
    "我点了什么",
    "你好",
    "谢谢",
]
FALLBACK = ["暂时无法回应", "无法回应", "系统异常", "未能成功", "抱歉，下单", "让我想想", "数量必须是大于0的正整数"]
EXPECTED_FINAL = {"total": 112, "items": {"东坡肘子", "冬瓜排骨汤", "米饭"}, "paid": True}


def chat(sid, msg):
    p = json.dumps({"session_id": sid, "message": msg}).encode()
    r = urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/chat", data=p,
        headers={"Content-Type": "application/json"}, method="POST"), timeout=120)
    return json.loads(r.read()).get("reply", "")


def get_orders():
    d = json.loads(urllib.request.urlopen(BASE + "/api/orders/all", timeout=10).read())
    return d["orders"] if isinstance(d, dict) else d


N = 20
results = []
t_start = time.time()
for idx in range(1, N + 1):
    sid = f"lc20_{int(time.time())}_{idx:02d}"
    round_ok, round_bad = [], []
    for i, msg in enumerate(CASES, 1):
        try:
            reply = chat(sid, msg)
            bad = any(m in reply for m in FALLBACK)
        except Exception as e:
            reply, bad = f"（请求失败：{e}）", True
        (round_bad if bad else round_ok).append((i, msg, reply[:80]))
        time.sleep(0.3)
    # ground truth 校验
    orders = [o for o in get_orders() if o.get("session_id") == sid]
    final = next((o for o in orders if o.get("paid")), None)
    money_ok = bool(final) and final["total"] == EXPECTED_FINAL["total"]
    items_ok = bool(final) and {i["dish_name"] for i in final["items"]} == EXPECTED_FINAL["items"]
    session_ok = not round_bad and money_ok and items_ok
    tag = "✅" if session_ok else "❌"
    issue = ""
    if round_bad:
        issue = f"轮次异常: {[(i,m) for i,m,_ in round_bad]}"
    elif not money_ok:
        issue = f"金额错误: 实际{final['total'] if final else '无订单'} 应112"
    elif not items_ok:
        issue = f"菜品错误: 实际{({i['dish_name'] for i in final['items']})} 应{EXPECTED_FINAL['items']}"
    results.append({"idx": idx, "sid": sid, "ok": session_ok,
                    "rounds_ok": len(round_ok), "money_ok": money_ok,
                    "items_ok": items_ok, "issue": issue})
    print(f"[{idx:02d}] {tag} 轮次{len(round_ok)}/10 | 账目{'✓' if money_ok and items_ok else '✗'} | {issue}")
    time.sleep(0.3)

# ─── 汇总 ───
ok_n = sum(1 for r in results if r["ok"])
round_total = N * 10
round_pass = sum(r["rounds_ok"] for r in results)
money_n = sum(1 for r in results if r["money_ok"])
items_n = sum(1 for r in results if r["items_ok"])
print(f"\n{'=' * 52}")
print(f"=== 20会话长链回测报告（{round_total}条消息, 耗时{time.time()-t_start:.0f}s）===")
print(f"会话级准确率: {ok_n}/{N} = {ok_n/N:.0%}")
print(f"轮级成功率:   {round_pass}/{round_total} = {round_pass/round_total:.0%}")
print(f"结账金额正确: {money_n}/{N} = {money_n/N:.0%}")
print(f"订单项正确:   {items_n}/{N} = {items_n/N:.0%}")
print(f"回退/误判轮:  {round_total - round_pass}")
for r in results:
    if not r["ok"]:
        print(f"  ❌ 会话{r['idx']:02d}: {r['issue']}")
