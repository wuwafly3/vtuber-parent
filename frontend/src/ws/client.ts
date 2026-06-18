// 与后端 app/ws/protocol.py 对应的事件类型。

export type ServerEvent =
  | { type: "token"; text: string }
  | { type: "message_done"; text: string }
  | { type: "audio_chunk"; data: string; format: string }
  | { type: "audio_done" }
  | { type: "expression"; name: string }
  | { type: "motion"; name: string }
  | { type: "agent_status"; tool: string; status: string; detail: string }
  | { type: "action_request"; action_id: string; description: string; payload: Record<string, unknown> }
  | { type: "error"; message: string }
  | { type: "pong" };

export type ClientEvent =
  | { type: "user_message"; text: string; image?: string; session_id?: string }
  | { type: "confirm_action"; action_id: string; approved: boolean }
  | { type: "ping" };

type Handler = (event: ServerEvent) => void;

export class PetSocket {
  private ws: WebSocket | null = null;
  private handlers = new Set<Handler>();
  private url: string;
  private reconnectTimer: number | null = null;

  constructor(url = `ws://127.0.0.1:8000/ws`) {
    this.url = url;
  }

  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (e) => {
      const event = JSON.parse(e.data) as ServerEvent;
      this.handlers.forEach((h) => h(event));
    };
    this.ws.onclose = () => {
      // 简单重连
      this.reconnectTimer = window.setTimeout(() => this.connect(), 1500);
    };
  }

  onEvent(handler: Handler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  send(event: ClientEvent) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(event));
    }
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  close() {
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}
