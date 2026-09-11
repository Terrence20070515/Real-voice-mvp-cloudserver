# Real-voice 后端测试指南（队友版）

## 后端地址

```
http://101.34.242.247:8080
```

无需鉴权，直接调。店家后台：http://101.34.242.247:8080/admin

## API 速查

### 1. 健康检查
```bash
curl http://101.34.242.247:8080/health
# {"service":"Real Voice MVP","status":"running","version":"1.0.14"}
```

### 2. 菜单（扁平数组）
```bash
curl http://101.34.242.247:8080/api/menu
# [{"菜品":"水煮鱼","价格":"¥68","辣度":"麻辣","过敏原":"鱼类",...}, ...]
```

### 3. AI 对话（核心接口）
```bash
curl -X POST http://101.34.242.247:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"你的测试会话名","message":"来一份水煮鱼"}'
# {"reply":"已为您下单【水煮鱼】1份，合计 ¥68，订单号 ORD0045..."}
```
- `session_id` 隔离会话状态：同一 sid 多轮共享上下文，不同 sid 互不影响
- AI 内部走 Function Calling（查菜单/下单/加单/换菜/退菜/结账）

### 4. 订单查询（ground truth 校验用）
```bash
curl http://101.34.242.247:8080/api/orders/all
# {"count":N,"orders":[{"order_id":"ORD0045","session_id":"...","items":[...],"total":68,"paid":false}]}
```

## 跑现成回测

```bash
# 20个独立长链会话（下单→加单→换菜→混合结账→查单），自动对照订单数据校验
python3 tests/backtest_20sessions.py --base http://101.34.242.247:8080
```
无第三方依赖，python3.8+ 直接跑，约 20 分钟。

## ⚠️ 注意事项

1. **session_id 必须带你的名字前缀**：如 `teammate_zhang_test01`。不带前缀的
   会话可能和别人的测试混淆（会话历史按 sid 持久化恢复）
2. 测试订单会留在订单表里（`paid` 标记），**不要清别人的数据**；大批量
   测试后在群里说一声，统一清理
3. 不要往 `/api/menu/import` 传菜单——那会改线上菜单（有 >20% 差异自动
   重新生成训练示例的机制，动了全队都在测的菜单会被打）
4. 单条 AI 回复耗时 1-4 秒属正常（LLM 推理+工具调用），别并发轰炸
5. 观察到 bug 时，记下 `session_id` + 那句话 + AI 回复 + 时间，报给我们排查
   （对话日志在后端 `data/conversations.json`，可回放）
