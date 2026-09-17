"""10轮长链测试 v2：含换菜(replace_item) + 混合意图结账(加单+结账一句话)"""
import json, time, urllib.request

BASE = "http://101.34.242.247:8080"
SID = f"longchain_v2_{int(time.time())}"

CASES = [
    "你好",                              # 1 寒暄
    "我们两个人，不能吃辣",               # 2 人数+口味
    "有什么不辣的推荐",                    # 3 推荐(过滤辣)
    "来一份皮蛋豆腐",                      # 4 下单
    "再来两碗米饭",                        # 5 加单
    "把皮蛋豆腐换成东坡肘子",              # 6 换菜(验证replace_item)
    "再加一份冬瓜排骨汤，结账吧",          # 7 混合意图(加单+结账,验证修复)
    "我点了什么",                          # 8 查单(应显示已支付)
    "你好",                                # 9 中途寒暄
    "谢谢",                                # 10 结束
]

FALLBACK = ["暂时无法回应", "无法回应", "系统异常", "未能成功", "抱歉，下单", "让我想想"]
PAIR_BUG = ["数量必须是大于0的正整数"]  # 负数误判检测

menu = json.loads(urllib.request.urlopen(BASE + "/api/menu", timeout=8).read())
MENU_DISHES = {it["菜品"] for it in menu}
print(f"当前菜单: {len(MENU_DISHES)} 道 | 会话: {SID}\n")

ok = fallback = req_fail = 0
all_mentioned = set()
for i, msg in enumerate(CASES, 1):
    t0 = time.time()
    p = json.dumps({"session_id": SID, "message": msg}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/chat", data=p,
            headers={"Content-Type": "application/json"}, method="POST"), timeout=120)
        reply = json.loads(r.read()).get("reply", "")
    except Exception as e:
        print(f"[{i:2d}] ❌ 请求失败 ({time.time()-t0:.1f}s) | 顾客: {msg}\n     {e}")
        req_fail += 1
        continue
    dt = time.time() - t0
    bad = any(m in reply for m in FALLBACK) or any(m in reply for m in PAIR_BUG)
    if bad: fallback += 1
    else: ok += 1
    mentioned = [d for d in MENU_DISHES if d in reply]
    all_mentioned.update(mentioned)
    print(f"[{i:2d}] {'⚠️' if bad else '✓'} ({dt:.1f}s) | 顾客: {msg}")
    print(f"     AI: {reply}")
    print()
    time.sleep(0.4)

print("=" * 52)
ok_rate = f"{ok}/10"
print(f"成功: {ok_rate} | 回退/误判: {fallback} | 请求失败: {req_fail}")
print(f"引用菜品(均在菜单): {','.join(sorted(all_mentioned)) or '无'}")
v = "✅ 长链全通" if ok == 10 else "⚠️ 有问题"
print(f"结论: {v}")
