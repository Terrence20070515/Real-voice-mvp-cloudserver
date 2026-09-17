# Real-voice · 川味小馆 AI 点餐助手

微信小程序 AI 点餐系统（FastAPI + DeepSeek Function Calling + 腾讯云 Docker）。
顾客自然语言点餐全流程，店家 Web 后台管理订单与菜单。

## 当前基线（2026-09-11 回测）

| 指标 | 数值 |
|------|------|
| 账目正确率 | 100%（20 独立会话 ground truth 校验） |
| 会话级准确率 | 95% |
| 回退/崩溃 | 200 条消息 0 次 |
| 示例池 | 525 条（自动迭代回灌中） |

## 目录结构

```
├── main.py              # FastAPI 路由（/api/chat、菜单、订单、示例池回灌接口）
├── agent.py             # AI 对话引擎（历史压缩+重试、意图硬兜底、幻觉确认检测）
├── tools.py             # 业务工具（菜单/下单/加单/换菜/退菜/结账）+ LLM 工具 schema
├── config.py            # 配置与路径（数据卷定位）
├── menu.json            # 菜单初始种子（容器启动时复制到数据卷）
├── admin.html           # 店家管理后台（订单看板/菜单管理/文本与图片导入）
├── Dockerfile           # 容器构建（单 worker）
├── deploy.py → tools/   # 自动化部署（paramiko，10 秒）
├── data/                # 运行时数据（gitignore，服务器数据卷为准）
│   └── training_examples.json   # 示例池（本地副本，服务器卷为 source of truth）
├── frontend/            # 微信小程序前端（菜单实时从 /api/menu 拉取）
├── ai_training/         # RLAIF 管线：selfplay.py（生成→评分→自动回灌）
├── tests/               # 回测脚本 + BACKTEST_GUIDE.md（队友从这里开始）
│   └── archive/         # 历史版本回测脚本
└── tools/               # deploy.py / gen_report.py
```

## 三份 menu.json 的说明（防混淆）

- **根目录 `menu.json`**：初始种子。容器启动时若数据卷无菜单则复制过去
- **数据卷 `data/menu.json`**（服务器 `/opt/real-voice/data/`）：**线上真身**，
  店家后台上传/AI 解析菜单都写这里，已 gitignore
- ~~`frontend/menu.json`~~ 已删除：前端菜单实时从 `/api/menu` 拉取，不存本地

## 部署

```bash
python3 tools/deploy.py   # paramiko 直连服务器：git reset → docker build/run → 健康检查，约 10 秒
```

手工方式：
```bash
cp .env.example .env   # 填 DEEPSEEK_API_KEY
docker build -t real-voice .
docker run -d --name real-voice -p 8080:8080 -v /opt/real-voice/data:/app/data --env-file .env --restart always real-voice
```

## 测试

```bash
python3 tests/backtest_20sessions.py --sessions 2   # 冒烟
python3 tests/backtest_20sessions.py --sessions 20  # 完整回测（约 20 分钟）
```

详见 `tests/BACKTEST_GUIDE.md`（三级校验说明 + 红线 + 报 bug 模板）。

## 持续改进闭环（RLAIF 管线）

```bash
cd ai_training
DEEPSEEK_API_KEY=sk-xxx python3 selfplay.py --sessions 8 --mode normal
```

模拟顾客对话 → judge 五维评分 → ≥4 分对话自动蒸馏回灌示例池 → 推送服务器。
`--mode hard` 为压力测试（挖 badcase）。

## 配置

- `PROVIDER`：deepseek / ollama
- `DEEPSEEK_API_KEY`、`MULTIMODAL_API_KEY`（图片识别菜单用）
- 详见 `.env.example`
