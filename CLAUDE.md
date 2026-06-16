# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

3D AI Desktop Pet (桌宠) — a floating desktop companion with AI chat, TTS voice, and Live2D character animation. Currently at Phase 3 of a 7-phase roadmap (agent tool-calling and vector memory are stubbed placeholders).

## Commands

### Backend (Python, managed with `uv`)

```bash
cd backend
uv sync                                        # install / sync dependencies
cp .env.example .env                           # first-time setup — fill in API keys
uv run uvicorn app.main:app --reload           # dev server on :8000
uv run pytest                                  # run all tests
uv run pytest tests/test_streaming.py          # run a single test file
curl http://127.0.0.1:8000/health              # smoke test
```

### Frontend (Node/npm, Vite)

```bash
cd frontend
npm install               # install dependencies
npm run dev               # dev server on :5173 (proxies /ws → backend :8000)
npm run build             # TypeScript check + Vite build → dist/
npm run preview           # preview the production build
```

## Architecture

### Communication Flow

```
Browser (React)  ←→  WebSocket /ws  ←→  FastAPI (Python)  →  LLM API (OpenAI-compat)
                                                            →  TTS API (DashScope CosyVoice-v2)
```

All real-time communication is a single WebSocket connection. Events are JSON with a `type` discriminator defined in `backend/app/ws/protocol.py` and mirrored in `frontend/src/ws/`.

### Backend (`backend/app/`)

| Module | Role |
|---|---|
| `main.py` | FastAPI app + `/ws` WebSocket endpoint; orchestrates the pipeline |
| `llm/service.py` | OpenAI-compatible streaming client, provider-agnostic via `base_url` |
| `llm/streaming.py` | Incremental processors: `EmotionParser` extracts `[emotion:xxx]` tags; `SentenceSplitter` chunks tokens into sentences for TTS |
| `llm/session.py` | In-memory conversation history (capped at 20 turns) |
| `tts/dashscope_tts.py` | DashScope CosyVoice-v2 streaming TTS; SDK callback bridged to asyncio Queue |
| `config.py` | Pydantic Settings from `.env` |
| `agent/`, `memory/` | **Stubs only** (Phase 4/5) — only `__init__.py` |

**Streaming pipeline in `main.py`**: LLM token stream → `EmotionParser` (fires `expression` events) → `SentenceSplitter` (queues complete sentences) → TTS synthesis → `audio_chunk` events. An asyncio Queue serializes TTS requests so audio order is preserved without blocking the token stream.

### Frontend (`frontend/src/`)

| Module | Role |
|---|---|
| `ws/client.ts` | `PetSocket` class — WebSocket with auto-reconnect and typed event dispatch |
| `audio/player.ts` | MediaSource Extensions for progressive MP3; `AnalyserNode` exposes volume (0–1) for lip-sync |
| `character/live2d/controller.ts` | Cubism 4 model via `pixi-live2d-display`; maps 7 emotion names → model expressions; drives lip-sync from audio volume |
| `console/App.tsx` | Main UI — chat bubbles, Live2D stage (45 vh), connection status |

Live2D Cubism Core is loaded via a `<script>` tag pointing to `/lib/live2dcubismcore.min.js` (not an npm package). The `pixi-live2d-display` library requires `window.PIXI` to be set before import — see `main.tsx` for the initialization order.

### WebSocket Event Protocol

**Client → Server**: `user_message`, `ping`, `confirm_action` (future)

**Server → Client**: `token`, `message_done`, `expression`, `audio_chunk`, `audio_done`, `agent_status`, `action_request` (future), `error`, `pong`

## Key Configuration (`.env`)

```
LLM_BASE_URL=        # OpenAI-compatible endpoint
LLM_API_KEY=
LLM_MODEL=           # e.g. qwen-plus, gpt-4o-mini
DASHSCOPE_API_KEY=   # Alibaba DashScope for TTS
TTS_VOICE=           # default: longxiaochun_v2
SYSTEM_PROMPT=       # character persona
```

## Live2D / PixiJS Notes

- React `StrictMode` double-invokes effects and causes a blank canvas with `pixi-live2d-display`. The app intentionally omits `<StrictMode>` (see memory for details).
- Live2D model files live in `frontend/public/models/` and `live2d_by_booru/`.
- Expression names in the model's `.model3.json` must match the mapping in `controller.ts`.
