"""Real-voice 20轮多轮回测：验证 AI 不再因历史压缩/限流回退。

每轮 POST /api/chat，记录回复 + 是否回退 + 耗时。
触发历史压缩阈值=24条消息，工具调用轮次会更快累加消息，
预计第8-12轮开始触发压缩。
"""
import json, time, urllib.request, urllib.error

BASE = "http://101.34.242.247:8080"
SID = "test_verify_20r_001"

# 20轮对话，覆盖点餐全流程
CASES = [
    "你好",                          # 1 寒暄
    "两个人吃饭",                     # 2 报人数
    "有什么不辣的菜推荐",              # 3 推荐+口味
    "来一份东坡肘子",                  # 4 下单
    "再来一份冬瓜排骨汤",              # 5 加单
    "我花生过敏",                      # 6 报过敏
    "推荐几个招牌菜",                  # 7 推荐
    "来一份辣子鸡",                    # 8 下单(含花生过敏原,应提醒)
    "把辣子鸡换成酸菜鱼",              # 9 换菜
    "我点了什么",                      # 10 查订单
    "麻婆豆腐来一份",                  # 11 下单
    "加两碗米饭",                      # 12 加单+数量
    "有什么汤",                        # 13 查菜单
    "推荐个主食",                      # 14 推荐
    "来一份担担面",                    # 15 下单
    "一共多少钱",                      # 16 问价格
    "两个人够吃吗",                    # 17 问份量
    "去结账",                          # 18 结账意图
    "你好",                            # 19 中途寒暄
    "谢谢",                            # 20 结束
]

FALLBACK_MARKERS = ["暂时无法回应", "无法回应", "让我想想", "AI 暂时"]

def call_chat(msg):
    payload = json.dumps({"session_id": SID, "message": msg}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read()).get("reply", ""), None
    except Exception as e:
        return "", f"请求失败: {type(e).__name__}: {str(e)[:80]}"

print(f"=== Real-voice 20轮回测 ===\n会话: {SID}\n")
ok, fail, fallback_count = 0, 0, 0
for i, msg in enumerate(CASES, 1):
    t0 = time.time()
    reply, err = call_chat(msg)
    dt = time.time() - t0
    if err:
        print(f"[{i:2d}] ❌ 请求失败 ({dt:.1f}s) | 顾客:{msg}\n     错误: {err}")
        fail += 1
        continue
    is_fallback = any(m in reply for m in FALLBACK_MARKERS)
    tag = "⚠️回退" if is_fallback else "✓"
    if is_fallback:
        fallback_count += 1
    else:
        ok += 1
    short = reply.replace("\n", " ")[:110]
    print(f"[{i:2d}] {tag} ({dt:.1f}s) | 顾客:{msg}\n     AI:{short}")
    time.sleep(0.5)  # 避免太快触发限流

print(f"\n=== 汇总 ===")
print(f"成功: {ok}/20 | 失败: {fail} | 回退: {fallback_count}")
print(f"结论: {'✅ 多轮对话稳定，未触发回退' if fallback_count == 0 and fail == 0 else '⚠️ 仍有回退/失败，需排查'}")
