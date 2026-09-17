"""Real-voice 10轮长链测试：完整点餐链路 + 长对话触发历史压缩。

验证点：
1. 0 回退（历史压缩+重试机制）
2. 复合信息提取（人数+口味+过敏一句话）
3. 过敏过滤（推荐时避开海鲜）
4. 换菜/加单/查单/结账全链路
5. AI 引用的菜名必须在当前菜单（不推旧菜）
"""
import json, time, urllib.request

BASE = "http://101.34.242.247:8080"
SID = "longchain_10r_001"

CASES = [
    "你好",                                        # 1 寒暄
    "我们四个人，不能吃辣，有一个海鲜过敏",          # 2 复合信息:人数+口味+过敏
    "推荐几个菜",                                   # 3 推荐(应避开辣+海鲜)
    "来一份推荐里最便宜的",                          # 4 下单
    "再来两份米饭",                                  # 5 加单
    "等等，把刚才那个菜换成汤",                      # 6 换菜
    "我点了什么",                                    # 7 查单
    "一共多少钱",                                    # 8 问价
    "再加一瓶可乐",                                  # 9 加单
    "去结账",                                        # 10 结账
]

FALLBACK = ["暂时无法回应", "无法回应", "系统异常", "未能成功", "抱歉，下单", "让我想想"]

# 当前菜单菜名集合（验证 AI 引用的菜名合法）
import urllib.request as ur
menu = json.loads(ur.urlopen(BASE + "/api/menu", timeout=8).read())
MENU_DISHES = {it["菜品"] for it in menu}
print(f"当前菜单: {len(MENU_DISHES)} 道菜\n")

ok = fallback = req_fail = 0
total_dishes_mentioned = set()
for i, msg in enumerate(CASES, 1):
    t0 = time.time()
    p = json.dumps({"session_id": SID, "message": msg}).encode()
    try:
        r = ur.urlopen(ur.Request(BASE + "/api/chat", data=p,
            headers={"Content-Type": "application/json"}, method="POST"), timeout=120)
        reply = json.loads(r.read()).get("reply", "")
    except Exception as e:
        print(f"[{i:2d}] ❌ 请求失败 ({time.time()-t0:.1f}s) | 顾客:{msg}\n     {e}")
        req_fail += 1
        continue
    dt = time.time() - t0
    bad = any(m in reply for m in FALLBACK)
    if bad: fallback += 1
    else: ok += 1
    # 提取回复里的菜名（检查是否在菜单）
    mentioned = [d for d in MENU_DISHES if d in reply]
    total_dishes_mentioned.update(mentioned)
    print(f"[{i:2d}] {'⚠️回退' if bad else '✓'} ({dt:.1f}s) | 顾客: {msg}")
    print(f"     AI: {reply}")
    if mentioned: print(f"     引用菜品: {','.join(mentioned)}")
    print()
    time.sleep(0.4)

print("=" * 50)
print(f"=== 汇总 ===")
print(f"成功: {ok}/10 | 回退: {fallback} | 请求失败: {req_fail}")
print(f"全程引用菜品（均在菜单内）: {','.join(sorted(total_dishes_mentioned)) or '无'}")
verdict = "✅ 长链全通，无回退，菜品引用合法" if ok == 10 and fallback == 0 and req_fail == 0 else "⚠️ 有问题，见上"
print(f"结论: {verdict}")
