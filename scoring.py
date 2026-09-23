"""示例池评分门控：菜单导入/重生成后，筛选有代表性的示例，淘汰重复与低质。

三档 provider，按配置自动选择（供通用店家架构的示例自动迭代使用）：
1. TYPE_SAFE_API_KEY 配置 → TypeSafe Jev 合批打分（Score primitive，约 20 条/次调用）
2. 未配置 → DeepSeek 降级打分（单批 JSON 输出，现有 key 即可跑通）
3. DeepSeek 也不可用 → 返回 None，调用方全量保留（门控跳过，服务不受影响）

评分维度（每条示例 1-5 分）：
- 场景区分度：与其他示例是否高度重复（同一意图的不同措辞只留最好的）
- 信息价值：是否承载可复用的行为模式（下单/推荐/过敏处理/结账）
- 表达质量：简洁、专业、语气真实

门控：score >= GATE_SCORE 保留。阈值可用环境变量 EXAMPLE_GATE_SCORE 调整。
"""
import json
import os

import requests

TYPE_SAFE_KEY = os.getenv("TYPE_SAFE_API_KEY", "")
TYPE_SAFE_URL = os.getenv("TYPE_SAFE_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.getenv("JEV_MODEL", "jev-latest")
GATE_SCORE = float(os.getenv("EXAMPLE_GATE_SCORE", "3.0"))  # Jev 返回加权分（0-4 连续值），门控用 3.0=「合格以上」
JEV_BATCH = 20  # Jev 单次调用条数（控制 state 在 32k 内）

SCORE_CRITERIA = [
    "与其他示例高度重复，无额外信息（同一意图的雷同问法）",
    "有一定信息但场景与他人重叠",
    "覆盖常见场景，表达合格",
    "覆盖重要场景（下单/推荐/过敏处理/结账等）且表达优秀",
    "不可替代的关键场景 + 教科书级回复结构",
]


def score_examples(examples: list) -> list | None:
    """给示例打分并门控筛选。

    返回筛选后的示例列表；无法评分时返回 None（调用方应全量保留）。
    """
    if not examples:
        return examples
    if TYPE_SAFE_KEY:
        try:
            return _score_jev(examples)
        except Exception as e:
            print(f"[SCORE] Jev 打分失败，降级 DeepSeek: {e}", flush=True)
    llm_key = os.getenv("DEEPSEEK_API_KEY", "")
    if llm_key:
        try:
            return _score_deepseek(examples, llm_key)
        except Exception as e:
            print(f"[SCORE] DeepSeek 评分失败，全量保留: {e}", flush=True)
    return None


def _score_jev(examples: list) -> list:
    """TypeSafe Jev 合批打分（Score primitive）。

    注意：请求体字段名按 typesafe-jev skill 文档（state + typed questions）组织，
    首次联调时如与官方 SDK 序列化格式有出入，需对照 typesafe-sdk 源码微调。
    """
    scored = {}
    for batch_start in range(0, len(examples), JEV_BATCH):
        batch = list(enumerate(examples))[batch_start:batch_start + JEV_BATCH]
        state = json.dumps(
            [{"idx": i, "user": e.get("user", ""), "reply": e.get("reply", "")} for i, e in batch],
            ensure_ascii=False)
        questions = {
            f"ex_{i}": {
                "type": "score",
                "instructions": (
                    f"评估第 `ex[{i}].user` 与 `ex[{i}].reply` 这组餐厅点餐示例的价值："
                    "与其他示例是否重复、是否覆盖关键点餐场景、回复是否简洁专业"),
                "criteria": SCORE_CRITERIA,
            }
            for i, _ in batch
        }
        resp = requests.post(
            TYPE_SAFE_URL,
            headers={"Authorization": f"Bearer {TYPE_SAFE_KEY}", "Content-Type": "application/json"},
            json={"model": JEV_MODEL, "state": state, "questions": questions},
            timeout=120)
        resp.raise_for_status()
        data = resp.json()
        for i, _ in batch:
            ans = (data.get("answers") or {}).get(f"ex_{i}") or {}
            scored[i] = float(ans.get("score", 0))
    return _gate(examples, scored)


def _score_deepseek(examples: list, llm_key: str) -> list:
    """DeepSeek 降级打分：单批 JSON 输出（分批 40 条/次，控制单次输出规模）"""
    from openai import OpenAI
    client = OpenAI(api_key=llm_key, base_url="https://api.deepseek.com")
    scored = {}
    batch_size = 40
    items = list(enumerate(examples))
    for b in range(0, len(items), batch_size):
        batch = items[b:b + batch_size]
        listing = "\n".join(
            f"{i}. 顾客：{e.get('user','')[:60]} | 助手：{e.get('reply','')[:60]}"
            for i, e in batch)
        prompt = f"""以下是餐厅AI点餐助手训练示例池中的 {len(batch)} 条示例（编号即 id）。
给每条打 1-5 的价值分（只输出 JSON）：
5=不可替代的关键场景（下单/推荐/过敏处理/结账）且回复教科书级
4=覆盖重要场景、表达优秀
3=常见场景、表达合格
2=信息与他人高度重叠
1=重复雷同或低质

{listing}

输出：{{"scores": {{"<id>": <1-5>, ...}}}}，只输出 JSON。"""
        resp = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=2000,
            response_format={"type": "json_object"})
        try:
            data = json.loads(resp.choices[0].message.content.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            continue
        for k, v in (data.get("scores") or {}).items():
            try:
                scored[int(k)] = float(v)
            except (ValueError, TypeError):
                continue
    return _gate(examples, scored)


def _gate(examples: list, scored: dict) -> list:
    kept, dropped = [], 0
    for i, e in enumerate(examples):
        if scored.get(i, GATE_SCORE) >= GATE_SCORE:
            kept.append(e)
        else:
            dropped += 1
    print(f"[SCORE] 门控: {len(examples)} → {len(kept)} 条（淘汰 {dropped} 条低于 {GATE_SCORE} 分）", flush=True)
    return kept
