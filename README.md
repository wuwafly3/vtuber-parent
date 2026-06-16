# 3D AI 桌宠

桌面悬浮的 AI 桌宠:Python 后端(LLM + Agent + TTS + 记忆)+ Web 前端(角色渲染 + 控制台),2D(Live2D)→ 3D(MMD)迭代,最终用 Electron 做透明无边框悬浮窗。

## 开发进度

- [x] 阶段 0 — 骨架:FastAPI + WebSocket,Vite+React 控制台,config
- [x] 阶段 1 — LLM 流式对话(qwen3.6 / 情绪标签 / 句子切分 / 多轮会话)
- [x] 阶段 2 — TTS(DashScope cosyvoice-v2 预置音色 / 逐句流式 / 前端边收边播)
- [x] 阶段 3 — Live2D 角色(卡拉模型 / 口型同步 / 16表情映射 / 待机眨眼)
- [ ] 阶段 4 — Agent(工具调用 + computer use,默认确认)
- [ ] 阶段 4 — Agent(工具调用 + computer use,默认确认)
- [ ] 阶段 5 — 持久化记忆(SQLite + 向量召回)
- [ ] 阶段 6 — Electron 桌面壳(透明窗 + 点击穿透 + 托盘)
- [ ] 阶段 7 — 3D MMD 迭代

## 运行

### 后端
```bash
cd backend
cp .env.example .env   # 填入 LLM / DashScope key
uv sync
uv run uvicorn app.main:app --reload
```
- 健康检查:http://127.0.0.1:8000/health
- WebSocket:ws://127.0.0.1:8000/ws
- 测试:`uv run pytest`

### 前端
```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

## 架构

```
Electron 壳 (透明无边框 + 点击穿透)
  ├── 角色窗口 (Live2D → MMD)
  └── 控制台窗口 (聊天/设置/记忆/声音)
        │  WebSocket (带 type 的 JSON 事件流)
Python 后端 (FastAPI)
  ├── LLM Service   (openai SDK, 任意 base_url)
  ├── Agent Loop    (function calling + computer use)
  ├── TTS Service   (DashScope cosyvoice-v2 克隆+流式)
  └── Memory Store  (SQLite + 向量召回)
```

WS 事件协议定义在 `backend/app/ws/protocol.py`,前端对应类型在 `frontend/src/ws/client.ts`。
