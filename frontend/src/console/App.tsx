import { useEffect, useRef, useState } from "react";
import { PetSocket, type ServerEvent } from "../ws/client";
import { StreamingAudioPlayer } from "../audio/player";
import { CharacterStage } from "../character/live2d/CharacterStage";
import type { Live2DController } from "../character/live2d/controller";

const MODEL_URL = "/models/karla/karla.model3.json";

interface ChatMessage {
  role: "user" | "pet";
  text: string;
}

export function App() {
  const socketRef = useRef<PetSocket | null>(null);
  const playerRef = useRef<StreamingAudioPlayer | null>(null);
  const characterRef = useRef<Live2DController | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
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

  const sendMessage = () => {
    const text = input.trim();
    if (!text) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    streamingRef.current = "";
    // 浏览器要求音频在用户手势内启动,这里 start() 重置音频流
    playerRef.current?.start();
    socketRef.current?.send({ type: "user_message", text });
    setInput("");
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
            {m.text}
          </div>
        ))}
      </div>

      <div style={styles.inputRow}>
        <input
          style={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder="跟桌宠说点什么..."
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
  inputRow: { display: "flex", gap: 8, padding: 12, borderTop: "1px solid #333" },
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
};
