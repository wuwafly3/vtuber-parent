import { useEffect, useRef, useState } from "react";
import { PetSocket, type ServerEvent } from "../ws/client";
import { StreamingAudioPlayer } from "../audio/player";
import { CharacterStage } from "../character/live2d/CharacterStage";
import type { Live2DController } from "../character/live2d/controller";

const MODEL_URL = "/models/karla/karla.model3.json";

interface ChatMessage {
  role: "user" | "pet";
  text: string;
  image?: string; // base64 data URL
}

/** 将 File 转为 base64 data URL */
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/** 限制图片最大尺寸，超过则缩放以减小 base64 体积 */
async function resizeIfTooLarge(file: File, maxDim = 1024): Promise<string> {
  const dataUrl = await fileToDataUrl(file);
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      if (img.width <= maxDim && img.height <= maxDim) {
        resolve(dataUrl);
        return;
      }
      const scale = maxDim / Math.max(img.width, img.height);
      const w = Math.round(img.width * scale);
      const h = Math.round(img.height * scale);
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => resolve(dataUrl);
    img.src = dataUrl;
  });
}

export function App() {
  const socketRef = useRef<PetSocket | null>(null);
  const playerRef = useRef<StreamingAudioPlayer | null>(null);
  const characterRef = useRef<Live2DController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  // 待发送的图片预览 (data URL)
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  // agent 工具执行状态 (null = 空闲)
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  // 当前正在流式接收的回复
  const streamingRef = useRef<string>("");

  useEffect(() => {
    const socket = new PetSocket();
    socketRef.current = socket;
    socket.connect();

    const player = new StreamingAudioPlayer();
    playerRef.current = player;

    const off = socket.onEvent((event: ServerEvent) => {
      switch (event.type) {
        case "pong":
          setConnected(true);
          break;
        case "token":
          streamingRef.current += event.text;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "pet") {
              last.text = streamingRef.current;
            } else {
              next.push({ role: "pet", text: streamingRef.current });
            }
            return next;
          });
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
          break;
        case "agent_status":
          if (event.status === "running") {
            setToolStatus(`正在使用 ${event.tool}...`);
          } else if (event.status === "done") {
            setToolStatus(null);
          }
          break;
        case "error":
          setMessages((prev) => [...prev, { role: "pet", text: `[错误] ${event.message}` }]);
          break;
      }
    });

    // 连通性探测
    const t = setInterval(() => socket.send({ type: "ping" }), 3000);
    socket.send({ type: "ping" });

    return () => {
      off();
      clearInterval(t);
      socket.close();
    };
  }, []);

  /** 处理选中的图片文件 */
  const handleImageFile = async (file: File) => {
    if (!file.type.startsWith("image/")) return;
    const dataUrl = await resizeIfTooLarge(file);
    setPendingImage(dataUrl);
  };

  /** 文件选择器变更 */
  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) await handleImageFile(file);
    // 清空以允许重复选同一文件
    e.target.value = "";
  };

  /** 粘贴事件: 捕获剪贴板中的图片 */
  const onPaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith("image/")) {
        e.preventDefault();
        const file = items[i].getAsFile();
        if (file) await handleImageFile(file);
        return;
      }
    }
  };

  const sendMessage = () => {
    const text = input.trim();
    if (!text && !pendingImage) return;
    const msg: ChatMessage = { role: "user", text: text || "[图片]" };
    if (pendingImage) msg.image = pendingImage;
    setMessages((prev) => [...prev, msg]);
    streamingRef.current = "";
    // 浏览器要求音频在用户手势内启动,这里 start() 重置音频流
    playerRef.current?.start();
    socketRef.current?.send({
      type: "user_message",
      text: text || "请描述这张图片",
      image: pendingImage ?? undefined,
    });
    setInput("");
    setPendingImage(null);
  };

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <span>桌宠控制台</span>
        <span style={{ ...styles.dot, background: connected ? "#3ddc84" : "#888" }} />
      </header>

      <div style={styles.stage}>
        <CharacterStage
          modelUrl={MODEL_URL}
          volumeSource={() => playerRef.current?.getVolume() ?? 0}
          onReady={(c) => {
            characterRef.current = c;
          }}
        />
      </div>

      <div style={styles.chat}>
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              ...styles.bubble,
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              background: m.role === "user" ? "#4a6cf7" : "#2a2a2a",
            }}
          >
            {m.image && (
              <img src={m.image} alt="用户上传" style={styles.chatImage} />
            )}
            {m.text && <div>{m.text}</div>}
          </div>
        ))}
      </div>

      {/* 图片预览条 */}
      {pendingImage && (
        <div style={styles.previewBar}>
          <img src={pendingImage} alt="待发送" style={styles.previewThumb} />
          <button
            style={styles.removeBtn}
            onClick={() => setPendingImage(null)}
            title="移除图片"
          >
            ✕
          </button>
        </div>
      )}

      {/* 工具执行状态提示 */}
      {toolStatus && (
        <div style={styles.toolBar}>
          <span style={styles.toolDot}>●</span>
          <span>{toolStatus}</span>
        </div>
      )}

      <div style={styles.inputRow}>
        {/* 隐藏的文件输入 */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          style={{ display: "none" }}
          onChange={onFileChange}
        />
        {/* 图片选择按钮 */}
        <button
          style={styles.imageBtn}
          onClick={() => fileInputRef.current?.click()}
          title="添加图片"
        >
          🖼
        </button>
        <input
          style={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          onPaste={onPaste}
          placeholder="跟桌宠说点什么... (可粘贴图片)"
        />
        <button style={styles.button} onClick={sendMessage}>
          发送
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    fontFamily: "system-ui, sans-serif",
    background: "#1a1a1a",
    color: "#eee",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "12px 16px",
    borderBottom: "1px solid #333",
    fontWeight: 600,
  },
  dot: { width: 10, height: 10, borderRadius: "50%" },
  stage: {
    height: "45vh",
    minHeight: 240,
    background: "radial-gradient(circle at 50% 40%, #2a2a3a 0%, #1a1a1a 70%)",
    borderBottom: "1px solid #333",
  },
  chat: {
    flex: 1,
    overflowY: "auto",
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  bubble: {
    maxWidth: "75%",
    padding: "8px 12px",
    borderRadius: 12,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  chatImage: {
    maxWidth: "100%",
    maxHeight: 200,
    borderRadius: 8,
    marginBottom: 4,
    display: "block",
  },
  previewBar: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 12px",
    borderTop: "1px solid #333",
    background: "#222",
  },
  previewThumb: {
    height: 48,
    borderRadius: 6,
    objectFit: "cover",
  },
  removeBtn: {
    background: "transparent",
    border: "1px solid #555",
    borderRadius: 4,
    color: "#aaa",
    cursor: "pointer",
    padding: "2px 6px",
    fontSize: 12,
  },
  inputRow: { display: "flex", gap: 8, padding: 12, borderTop: "1px solid #333" },
  imageBtn: {
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid #444",
    background: "#2a2a2a",
    cursor: "pointer",
    fontSize: 18,
    lineHeight: 1,
  },
  input: {
    flex: 1,
    padding: "10px 12px",
    borderRadius: 8,
    border: "1px solid #444",
    background: "#222",
    color: "#eee",
    outline: "none",
  },
  button: {
    padding: "10px 20px",
    borderRadius: 8,
    border: "none",
    background: "#4a6cf7",
    color: "#fff",
    cursor: "pointer",
  },
  toolBar: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 16px",
    background: "#1e2a3a",
    borderTop: "1px solid #333",
    color: "#7ab8ff",
    fontSize: 13,
  },
  toolDot: {
    animation: "pulse 1s infinite",
    fontSize: 10,
  },
};
