# Real-voice · 川味小馆 AI 点餐助手

微信小程序 AI 点餐后端（FastAPI + DeepSeek）。

## 结构

```
.
├── main.py              # FastAPI 路由（HTTP API + admin 页面）
├── agent.py             # AI 对话引擎（多轮对话 + 工具调用）
├── tools.py             # 业务逻辑（菜单/订单/支付）+ LLM 工具 schema
├── config.py            # 配置 + 路径管理（统一）
├── menu.json            # 菜单数据
├── admin.html           # 店家管理后台
├── Dockerfile           # 云部署
├── data/                # 运行时数据（orders/sessions/conversations，已 gitignore）
│   └── training_examples.json   # AI 回复风格训练样本
└── frontend/           # 微信小程序前端
```

## 部署

```bash
cp .env.example .env  # 填 DEEPSEEK_API_KEY
docker build -t real-voice .
docker run -d --name real-voice -p 8080:8080 -v /opt/real-voice/data:/app/data --restart always real-voice
```

## 配置

- `PROVIDER`：deepseek / ollama
- `DEEPSEEK_API_KEY`：DeepSeek API Key
- 详见 `.env.example`
