import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { PetSocket, type ServerEvent } from "../ws/client";
import { StreamingAudioPlayer } from "../audio/player";
import { CharacterStage } from "../character/live2d/CharacterStage";
import type { Live2DController } from "../character/live2d/controller";

const MODEL_URL = "/models/karla/karla.model3.json";
// 像素透明度阈值: 高于此值认为鼠标在角色上, 关闭穿透
const ALPHA_THRESHOLD = 10;

/**
 * 桌宠模式组件 — 透明窗口中只显示 Live2D 角色 + 浮动聊天气泡。
 *
 * 鼠标穿透采用混合模式:
 *   1. 默认不穿透, 前端 mousemove 检测像素 alpha
 *   2. 鼠标离开角色 → 开启穿透 → 通知 Rust 启动轮询
 *   3. Rust 轮询线程定期发 check-pixel 事件 → 前端检测 alpha → 回传
 *   4. Rust 发现光标在角色上 → 关闭穿透 → 前端重新接管
 */
export function PetApp() {
  const socketRef = useRef<PetSocket | null>(null);
  const playerRef = useRef<StreamingAudioPlayer | null>(null);
  const characterRef = useRef<Live2DController | null>(null);
  const [lastMessage, setLastMessage] = useState("");
  const [showBubble, setShowBubble] = useState(false);
  const streamingRef = useRef("");
  const bubbleTimer = useRef<number | null>(null);
  // 穿透状态: false = 不穿透 (默认, 前端接管), true = 穿透 (Rust 轮询)
  const clickThroughRef = useRef(false);

  useEffect(() => {
    const socket = new PetSocket();
    socketRef.current = socket;
    socket.connect();

    const player = new StreamingAudioPlayer();
    playerRef.current = player;

    const off = socket.onEvent((event: ServerEvent) => {
      switch (event.type) {
        case "token":
          streamingRef.current += event.text;
          setLastMessage(streamingRef.current);
          setShowBubble(true);
          break;
        case "expression":
          characterRef.current?.setEmotion(event.name);
          break;
        case "audio_chunk":
          player.pushChunk(event.data);
          break;
        case "audio_done":
          player.finish();
          break;
        case "message_done":
          streamingRef.current = "";
          if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
          bubbleTimer.current = window.setTimeout(() => setShowBubble(false), 5000);
          break;
        case "error":
          setLastMessage(`[错误] ${event.message}`);
          setShowBubble(true);
          break;
      }
    });

    const t = setInterval(() => socket.send({ type: "ping" }), 3000);
    socket.send({ type: "ping" });

    // ── 模式 A: 前端 mousemove 检测 (穿透关闭时) ──────────
    const onMouseMove = (e: MouseEvent) => {
      if (clickThroughRef.current) return; // 穿透中, 由 Rust 轮询处理
      const ctrl = characterRef.current;
      if (!ctrl) return;
      const alpha = ctrl.getPixelAlpha(e.clientX, e.clientY);
      if (alpha < ALPHA_THRESHOLD) {
        // 鼠标离开角色 → 开启穿透, 通知 Rust 启动轮询
        clickThroughRef.current = true;
        invoke("set_click_through", { ignore: true });
        invoke("start_click_through_polling");
      }
    };
    document.addEventListener("mousemove", onMouseMove);

    // ── 模式 B: 响应 Rust 轮询线程的像素检测请求 ──────────
    // 穿透开启后, Rust 每 80ms 发 check-pixel 事件 (携带光标相对坐标)
    // 前端用 gl.readPixels 检测 alpha 并回传
    const unlisten = listen<{ x: number; y: number }>("check-pixel", (event) => {
      const ctrl = characterRef.current;
      if (!ctrl) return;
      // Rust 传来的是物理像素坐标，需转为 CSS 像素
      const dpr = window.devicePixelRatio || 1;
      const canvas = ctrl.getCanvas();
      const rect = canvas.getBoundingClientRect();
      const screenX = rect.left + event.payload.x / dpr;
      const screenY = rect.top + event.payload.y / dpr;
      const alpha = ctrl.getPixelAlpha(screenX, screenY);
      invoke("report_alpha", { alpha });
      // 如果检测到角色, Rust 会关闭穿透, 前端自动重新接管 mousemove
      if (alpha > ALPHA_THRESHOLD) {
        clickThroughRef.current = false;
      }
    });

    return () => {
      off();
      clearInterval(t);
      socket.close();
      document.removeEventListener("mousemove", onMouseMove);
      unlisten.then((fn) => fn());
      if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
    };
  }, []);

  return (
    <div data-tauri-drag-region style={styles.container}>
      {/* Live2D 角色铺满整个透明窗口 */}
      <CharacterStage
        modelUrl={MODEL_URL}
        volumeSource={() => playerRef.current?.getVolume() ?? 0}
        onReady={(c) => {
          characterRef.current = c;
        }}
      />

      {/* 浮动聊天气泡 */}
      {showBubble && lastMessage && (
        <div style={styles.bubble}>
          {lastMessage}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    width: "100vw",
    height: "100vh",
    background: "transparent",
    position: "relative",
    overflow: "hidden",
  },
  bubble: {
    position: "absolute",
    top: 12,
    left: 12,
    right: 12,
    background: "rgba(30, 30, 30, 0.85)",
    color: "#eee",
    padding: "8px 12px",
    borderRadius: 12,
    fontSize: 14,
    lineHeight: 1.5,
    maxWidth: "90%",
    wordBreak: "break-word",
    backdropFilter: "blur(8px)",
    zIndex: 10,
    pointerEvents: "none",
  },
};
