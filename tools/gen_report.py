"""生成 Real-voice 项目进展报告 PDF（给老师汇报用）"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                Table, TableStyle, HRFlowable)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont("CN", "/System/Library/Fonts/STHeiti Light.ttc", subfontIndex=0))

ACCENT = colors.HexColor("#c0392b")
DARK = colors.HexColor("#2c2c2c")
GRAY = colors.HexColor("#666666")

S_TITLE = ParagraphStyle("t", fontName="CN", fontSize=22, leading=30, textColor=ACCENT, alignment=1)
S_SUB = ParagraphStyle("s", fontName="CN", fontSize=12, leading=18, textColor=GRAY, alignment=1)
S_H1 = ParagraphStyle("h1", fontName="CN", fontSize=15, leading=22, textColor=DARK, spaceBefore=14, spaceAfter=6)
S_H2 = ParagraphStyle("h2", fontName="CN", fontSize=12.5, leading=19, textColor=ACCENT, spaceBefore=8, spaceAfter=4)
S_BODY = ParagraphStyle("b", fontName="CN", fontSize=10.5, leading=17, textColor=DARK, firstLineIndent=0, spaceAfter=4)
S_LI = ParagraphStyle("li", fontName="CN", fontSize=10.5, leading=17, textColor=DARK, leftIndent=14, spaceAfter=2)
S_CELL = ParagraphStyle("c", fontName="CN", fontSize=9.5, leading=14, textColor=DARK)
S_NOTE = ParagraphStyle("n", fontName="CN", fontSize=9.5, leading=15, textColor=GRAY, spaceAfter=3)


def table(data, widths=None):
    rows = [[Paragraph(c, S_CELL) for c in row] for row in data]
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fdf0ee")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ddd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


story = []
story.append(Spacer(1, 10 * mm))
story.append(Paragraph("Real-voice 川味小馆 AI 点餐助手", S_TITLE))
story.append(Paragraph("项目进展报告（2026 年 8 月 — 9 月）", S_TITLE))
story.append(Spacer(1, 6 * mm))
story.append(Paragraph("汇报人：章赵毅　|　技术负责：AI 工程组　|　报告日期：2026 年 9 月 13 日", S_SUB))
story.append(Spacer(1, 4 * mm))
story.append(HRFlowable(width="100%", thickness=1, color=ACCENT))
story.append(Spacer(1, 6 * mm))

story.append(Paragraph("一、项目概述", S_H1))
story.append(Paragraph(
    "Real-voice 是面向线下餐饮场景（川味小馆）的 AI 对话点餐助手。顾客通过微信小程序以自然语言完成"
    "查菜单、要推荐、下单、加单、换菜、退菜、结账等全流程；店家通过 Web 管理后台实时查看订单、管理菜单、"
    "一键导入菜单（文本/图片 AI 识别）。", S_BODY))
story.append(Paragraph(
    "技术架构：微信小程序前端 + FastAPI 后端（Docker 部署于腾讯云服务器）+ DeepSeek 大模型"
    "（Function Calling 驱动 8 个点餐工具）+ 文件级数据存储（原子写）。围绕模型能力建立了一套"
    "「模拟顾客对话生成 → LLM 评分 → 高分示例回灌」的数据驱动 Prompt 自动迭代机制。", S_BODY))

story.append(Paragraph("二、总体成果", S_H1))
story.append(table([
    ["指标", "8 月初", "当前（9 月 13 日）"],
    ["服务稳定性", "频繁出现「AI 暂时无法回应」", "200 条消息 0 回退、0 崩溃"],
    ["账目正确率", "换菜累加金额、加单丢失、结账翻倍", "100%（20 个独立会话实测，ground truth 校验）"],
    ["会话级准确率", "无度量体系", "95%（19/20，每会话 10 轮全流程）"],
    ["评测均分（judge 1-5 分）", "4.08", "4.25 – 4.50"],
    ["训练示例池", "436 条", "525 条（自动回灌）"],
    ["仓库与部署", "代码打包在 zip 内，手工部署", "源码化仓库 + 自动化部署（10 秒）"],
], widths=[110, 155, 220]))
story.append(Spacer(1, 3 * mm))

story.append(Paragraph("三、阶段工作详述", S_H1))

story.append(Paragraph("阶段一：云端部署与系统联调（8 月上旬）", S_H2))
story.append(Paragraph(
    "完成 v1.0.6 → v1.0.13 共 8 个版本的迭代，将后端容器化部署至腾讯云服务器（8080 端口），"
    "修复 404 路由、前端白屏、大消息 500、请求超时、菜单接口格式兼容等一批部署级问题，"
    "打通微信小程序与后端的完整链路，并建立云托管保活机制。", S_BODY))
story.append(Paragraph(
    "同期建成第一代评测闭环（DeepSeek 生成对话 → DeepSeek 考官 1-5 分打分 → 高分筛选回灌示例池），"
    "经多轮迭代沉淀 436 条训练示例，评分 4.08/5。", S_BODY))

story.append(Paragraph("阶段二：仓库工程化与稳定性根治（9 月 9 日）", S_H2))
story.append(Paragraph("1. 仓库源码化：代码从两个 zip 存档释放为标准源码仓库（后端 + 前端 + 测试 + 文档），"
                       "补充 .gitignore/.dockerignore，此后迭代全部走 git 版本管理（累计 30+ commits）。", S_LI))
story.append(Paragraph("2. 「AI 暂时无法回应」问题根治——这是上线以来投诉最多的稳定性问题。根因分析：多轮对话"
                       "历史无界增长超出模型上下文上限，且 API 异常无重试。修复方案：", S_LI))
story.append(Paragraph("· 历史压缩机制：对话超过 24 条消息自动压缩（保留系统提示 + 最近 10 条），处理工具调用消息的配对完整性；", S_LI))
story.append(Paragraph("· 错误分类重试：上下文超长自动压缩后重试，限流/超时按指数退避重试两次。", S_LI))
story.append(Paragraph("3. 结果：后续 200 条消息的回测中回退次数为 0。", S_LI))

story.append(Paragraph("阶段三：存储层加固与店家后台升级（9 月 10 日）", S_H2))
story.append(Paragraph("1. 订单文件损坏根治：排查出订单文件因并发写入产生半文件（JSON 解析失败导致下单功能整体不可用）。"
                       "修复：写入改为原子操作（先写临时文件再 rename），读取失败时自动降级为空并告警，服务不再中断。", S_LI))
story.append(Paragraph("2. 菜单文件移入数据卷：店家上传的菜单持久化保存，容器重启不丢失；菜单差异超过 20% 时自动"
                       "触发训练示例重新生成，保证示例池与当前菜单同步。", S_LI))
story.append(Paragraph("3. 店家后台三项升级：菜单页格式兼容修复（修复白屏）；文本智能解析（粘贴任意格式菜单文字，"
                       "AI 解析为结构化菜单一键导入）；图片识别导入（接入通义千问 VL 多模态模型，上传菜单照片自动识别）。", S_LI))

story.append(Paragraph("阶段四：核心链路缺陷清零（9 月 10-11 日）", S_H2))
story.append(Paragraph(
    "自建 self-play 评测管线（6 类顾客画像与真实后端进行全工具调用对话，LLM 考官五维评分），"
    "首轮评测即暴露 6 个系统性缺陷，全部定位并修复：", S_BODY))
story.append(table([
    ["缺陷", "根因", "修复"],
    ["换菜金额累加（越换越多）", "缺少换菜/退菜工具，模型被迫用加菜凑", "新增 replace_item / delete_item 工具"],
    ["换菜指引过时", "系统提示词仍指示旧方案", "提示词与新工具同步更新"],
    ["重复下单（结账金额翻倍）", "强制兜底逻辑触发条件过宽", "限定仅首轮响应且未执行过工具时触发"],
    ["订单幻觉", "模型口头确认但未调用工具", "幻觉确认检测：声称完成但未调写入工具时强制重试"],
    ["混合意图漏单（「加X，结账」）", "结账兜底拦截了加单请求", "混合意图放行给模型先加单再结账"],
    ["多实例状态不一致", "多 worker 进程内存态不共享", "改单 worker 部署"],
], widths=[120, 150, 165]))
story.append(Spacer(1, 2 * mm))

story.append(Paragraph("阶段五：示例池自动迭代闭环（9 月 11 日）", S_H2))
story.append(Paragraph(
    "第二代闭环完整跑通：AI 扮演 6 类顾客画像（直接点单/看推荐/家庭聚餐/先点后加/过敏顾客/简餐）与真实后端"
    "进行全工具调用对话 → LLM 考官按工具行为、信息准确、过敏安全、目标完成、沟通质量五个维度评分 → "
    "4 分以上对话自动蒸馏回灌示例池 → 通过管理接口推送到线上（合并去重、原子写）→ 新会话自动生效。", S_BODY))
story.append(Paragraph(
    "已完整运行 2 轮迭代：第一轮回灌 +76 条，第二轮回灌 +13 条，示例池 436 → 525 条；"
    "评测均分 4.25 / 4.50，合格率（≥4 分）75% → 88%。", S_BODY))

story.append(Paragraph("四、质量保障体系", S_H1))
story.append(Paragraph(
    "1. 自动化回测：20 个独立会话 × 10 轮完整流程（200 条消息），对照订单数据库硬校验金额与菜品，"
    "不依赖人工判断。基线：账目正确率 100%、会话级 95%、回退 0。", S_LI))
story.append(Paragraph("2. 回归评测：self-play 管线可随时以 normal（常规回归）/ hard（压力挖掘）两种模式运行，"
                       "评测数据全部落盘（JSONL），badcase 可精确回放。", S_LI))
story.append(Paragraph("3. 团队协作：测试脚本与指南已入库（tests/ 目录），队友零依赖即可参与后端回测，"
                       "bug 上报有标准化模板（会话 ID + 触发消息 + AI 回复 + 时间）。", S_LI))

story.append(Paragraph("五、下一步计划", S_H1))
story.append(table([
    ["事项", "说明", "状态"],
    ["过敏推荐强制过滤", "推荐环节对含过敏原菜品做硬过滤（当前仅提示）", "待开发"],
    ["图片识别菜单导入", "多模态模型接口已接通，待配置 API key 启用", "待配置"],
    ["模型微调（DPO）可行性", "基于 self-play 偏好数据对开源模型（Qwen2.5-7B）做 DPO 训练，"
     "预计单卡成本数十元；与指导老师讨论中", "可行性论证中"],
    ["HTTPS 与正式对外", "域名备案、证书、小程序合法域名配置", "规划中"],
], widths=[100, 260, 65]))
story.append(Spacer(1, 3 * mm))

story.append(Paragraph("六、说明", S_H1))
story.append(Paragraph(
    "本报告中所有数据均来自自动化回测与线上订单数据库的实际记录（20 个独立会话 / 200 条消息 / "
    "2 轮示例池自动迭代），评测脚本、对话日志与订单明细均已版本化存档，可随时复核。", S_BODY))
story.append(Spacer(1, 8 * mm))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#ddd")))
story.append(Paragraph("Real-voice 项目组　·　2026 年 9 月 13 日", S_NOTE))

OUT = "/Users/terrence/WorkBuddy/2026-08-09-18-51-47/Real-voice项目进展报告_2026-09.pdf"
doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                        topMargin=16 * mm, bottomMargin=16 * mm,
                        title="Real-voice 项目进展报告（2026.8-9）")
doc.build(story)
print("PDF 已生成:", OUT)
