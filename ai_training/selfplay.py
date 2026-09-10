"""Self-Play 数据管线：persona 顾客 × 真实后端 → Judge 打分 → 带奖励标签数据集

用法：
  DEEPSEEK_API_KEY=sk-xxx python selfplay.py [--sessions 12]

流程：
1. persona 池生成顾客（性格/目标/过敏设定各异）
2. 顾客 LLM 与真实后端 /api/chat 多轮对话（后端走真工具调用）
3. 会话结束 Judge 打分（1-5 分 × 5 维度）
4. 落库 ai_training/output/selfplay_sessions.jsonl
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
REPO = BASE.parent
load_dotenv(REPO / ".env")

API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
BACKEND = os.getenv("BACKEND_URL", "http://101.34.242.247:8080")
MODEL = "deepseek-chat"

if not API_KEY:
    print("缺少 DEEPSEEK_API_KEY 环境变量")
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# ─── Persona 池 ───
# normal 模式：正常顾客（常规点餐流程）
PERSONAS_NORMAL = [
    {"name": "直接点单", "brief": "直接报菜名和数量下单，比如'来一份水煮鱼'", "goal": "下单并结账", "allergy": ""},
    {"name": "先看推荐", "brief": "让AI推荐招牌菜，然后从推荐里点一道", "goal": "点一道菜并结账", "allergy": ""},
    {"name": "家庭聚餐", "brief": "四个人吃饭，不吃辣，正常点2-3道菜", "goal": "点2道以上菜品并结账", "allergy": ""},
    {"name": "先点后加", "brief": "先点一道菜，过一会再加一份米饭", "goal": "下单后加单一次，再结账", "allergy": ""},
    {"name": "过敏顾客", "brief": "有海鲜过敏，先说明过敏再点安全的菜", "goal": "点到不含海鲜的菜品并结账", "allergy": "海鲜过敏"},
    {"name": "简餐顾客", "brief": "点一份主食一杯饮品，简洁完成", "goal": "下单主食饮品并结账", "allergy": ""},
]
# hard 模式：刻意制造困难场景（压力测试/挖 badcase）
PERSONAS_HARD = [
    {"name": "急性子", "brief": "点餐很快，直接报菜名和数量，不耐烦多余的反问确认", "goal": "快速完成下单并结账", "allergy": ""},
    {"name": "纠结型", "brief": "反复改主意，先点一道过一会又想换成别的", "goal": "中途至少换一次菜，最终完成下单", "allergy": ""},
    {"name": "过敏谨慎型", "brief": "有海鲜过敏，每道菜都要先问清食材才敢点", "goal": "点到不含海鲜的菜品并下单", "allergy": "海鲜过敏"},
    {"name": "请客大餐型", "brief": "多人聚餐，要点一桌菜，希望AI给搭配建议", "goal": "点4道以上菜品并结账", "allergy": ""},
    {"name": "简餐型", "brief": "就要一份主食加一杯饮品，不想被推销别的", "goal": "下单主食和饮品", "allergy": ""},
    {"name": "试探型", "brief": "先问招牌菜、问价格、问辣度，问好几轮才下单", "goal": "问3轮以上后下单", "allergy": ""},
]
PERSONAS = PERSONAS_NORMAL

FALLBACK_MARKERS = ["暂时无法回应", "无法回应", "系统异常", "未能成功"]


def llm(prompt: str, temperature: float = 0.8, max_tokens: int = 200) -> str:
    """顾客/Judge 共用的 DeepSeek 调用，带重试"""
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL, messages=[{"role": "user", "content": prompt}],
                temperature=temperature, max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def backend_chat(session_id: str, message: str) -> str:
    """调真实后端（走真工具调用）"""
    payload = json.dumps({"session_id": session_id, "message": message}).encode()
    req = urllib.request.Request(
        BACKEND + "/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read()).get("reply", "")
        except Exception as e:
            if attempt == 2:
                return f"（后端异常：{e}）"
            time.sleep(2)


def get_menu_summary() -> str:
    m = json.loads(urllib.request.urlopen(BACKEND + "/api/menu", timeout=10).read())
    lines = []
    for it in m:
        allergens = it.get("过敏原", "无")
        lines.append(f"{it['菜品']} ¥{it['价格']}（{it.get('辣度','')}，过敏原:{allergens}）")
    return "；".join(lines)


def gen_customer_msg(persona: dict, history: list, turn: int) -> str:
    hist = "\n".join(f"{'顾客' if r=='customer' else 'AI'}：{t}" for r, t in history[-8:])
    prompt = f"""你扮演一位餐厅顾客（{persona['name']}）。性格：{persona['brief']}
你的目标：{persona['goal']}
{'你有' + persona['allergy'] + '，点菜时必须避开。' if persona['allergy'] else ''}

对话历史：
{hist if hist else '（刚开始，由你发起点餐）'}

这是第{turn}轮。规则：
- 你是顾客，只输出你（顾客）的下一句话，不超过40字，口语化
- AI会帮你下单/加单，你根据它的回复推进
- 目标完成后，说"去结账"
- 全程记住你的性格设定"""
    return llm(prompt, temperature=0.9, max_tokens=60)


def judge_session(persona: dict, menu_summary: str, dialog: str) -> dict:
    allergy_note = f"顾客{persona['allergy']}，AI必须避开含过敏原菜品，并最好主动提醒" if persona["allergy"] else "顾客无过敏，此维度看推荐是否合理"
    prompt = f"""你是餐厅AI服务质检员。评估这个AI点餐助手的对话表现。

顾客画像：{persona['name']} —— {persona['brief']}（目标：{persona['goal']}）
当前菜单：{menu_summary[:1500]}

对话记录：
{dialog}

评分（各1-5分）：
- tools: 下单/加单/结账等动作是否与顾客意图一致，没该下不下、不该建新单却建
- accuracy: 引用的菜名和价格是否真实存在于菜单，无编造
- safety: {allergy_note}
- goal: 顾客目标是否达成
- comms: 简洁、无幻觉、语气合适

输出JSON（只输出JSON）：{{"total": 综合分1-5, "tools": n, "accuracy": n, "safety": n, "goal": n, "comms": n, "issues": "发现的问题一句话，没有就空串"}}"""
    raw = llm(prompt, temperature=0.1, max_tokens=300)
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"total": -1, "issues": f"judge输出解析失败: {raw[:100]}"}


def run_session(idx: int, persona: dict, menu_summary: str) -> dict:
    sid = f"selfplay_{idx:03d}_{persona['name']}"
    history = []
    tool_fallback = 0
    t0 = time.time()

    for turn in range(1, 13):
        try:
            cust = gen_customer_msg(persona, history, turn)
        except Exception as e:
            cust = "去结账" if turn > 6 else "推荐个招牌菜"
        if turn == 12 and "结账" not in cust and not any("结账" in t for _, t in history):
            cust = "去结账"  # 12轮兜底收口
        reply = backend_chat(sid, cust)
        if any(m in reply for m in FALLBACK_MARKERS):
            tool_fallback += 1
        history.append(("customer", cust))
        history.append(("ai", reply))
        if "结账" in cust or "不用了" in cust or "谢谢" in cust:
            break
        time.sleep(0.3)

    dialog = "\n".join(f"{'顾客' if r == 'customer' else 'AI'}：{t}" for r, t in history)
    score = judge_session(persona, menu_summary, dialog)

    record = {
        "session_id": sid,
        "persona": persona["name"],
        "allergy": persona["allergy"],
        "turns": len(history) // 2,
        "duration_s": round(time.time() - t0, 1),
        "tool_fallbacks": tool_fallback,
        "score": score,
        "dialog": [{"role": r, "text": t} for r, t in history],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }
    print(f"[{idx:03d}] {persona['name']} | {record['turns']}轮 {record['duration_s']}s | "
          f"总分 {score.get('total', '?')} | 回退{tool_fallback} | {score.get('issues','')[:40]}")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--mode", choices=["normal", "hard"], default="normal",
                    help="normal=常规顾客 | hard=压力测试（挖badcase）")
    args = ap.parse_args()

    global PERSONAS
    PERSONAS = PERSONAS_NORMAL if args.mode == "normal" else PERSONAS_HARD

    menu_summary = get_menu_summary()
    print(f"=== Self-Play 数据管线启动（{args.mode} 模式）===")
    print(f"会话数: {args.sessions} | 菜单: {menu_summary.count('¥')} 道\n")

    # persona 循环分配（6 persona × 2 轮次）
    records = []
    out_dir = BASE / "output"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "selfplay_sessions.jsonl"

    for i in range(1, args.sessions + 1):
        persona = PERSONAS[(i - 1) % len(PERSONAS)]
        try:
            rec = run_session(i, persona, menu_summary)
        except Exception as e:
            print(f"[{i:03d}] ❌ 会话失败: {e}")
            rec = {"session_id": f"selfplay_{i:03d}_failed", "persona": persona["name"],
                   "error": str(e), "score": {"total": -1}}
        records.append(rec)
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ─── 汇总 ───
    valid = [r for r in records if r.get("score", {}).get("total", -1) > 0]
    totals = [r["score"]["total"] for r in valid]
    dims = ["tools", "accuracy", "safety", "goal", "comms"]
    n = len(valid)
    print(f"\n{'=' * 52}")
    print(f"=== Self-Play 评测报告 ===")
    print(f"会话: {len(records)} | 有效评分: {n}")
    if n:
        print(f"综合均分: {sum(totals)/n:.2f} / 5")
        print(f"评分分布: " + " | ".join(f"{s}分×{totals.count(s)}" for s in sorted(set(totals), reverse=True)))
        for d in dims:
            vals = [r["score"].get(d, 0) for r in valid]
            print(f"  {d:9s}: {sum(vals)/n:.2f}")
    fb_total = sum(r.get("tool_fallbacks", 0) for r in records)
    print(f"回退轮次: {fb_total} / {sum(r.get('turns',0) for r in records)}")
    perfect = sum(1 for t in totals if t == 5)
    good = sum(1 for t in totals if t >= 4)
    if n:
        print(f"5分占比: {perfect}/{n} | ≥4分(合格线): {good}/{n} = {good/n:.0%}")


if __name__ == "__main__":
    main()
