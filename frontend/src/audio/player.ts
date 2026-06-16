// 流式音频播放:把 WS 来的 base64 MP3 块边收边播。
// 用 MediaSource Extensions 追加 buffer;同时挂 AnalyserNode 暴露实时音量,
// 供阶段 3 Live2D/MMD 口型同步驱动。

function base64ToUint8(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const arr = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

export class StreamingAudioPlayer {
  private audio: HTMLAudioElement;
  private mediaSource: MediaSource | null = null;
  private sourceBuffer: SourceBuffer | null = null;
  private queue: Uint8Array<ArrayBuffer>[] = [];
  private ended = false;

  // 音量分析(口型同步用)
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private freqData: Uint8Array<ArrayBuffer> | null = null;

  constructor() {
    this.audio = new Audio();
    this.audio.autoplay = true;
  }

  /** 一段新回复的音频流开始前调用,重置 MediaSource。 */
  start(mime = 'audio/mpeg') {
    this.reset();
    this.ended = false;
    this.mediaSource = new MediaSource();
    this.audio.src = URL.createObjectURL(this.mediaSource);
    this.mediaSource.addEventListener('sourceopen', () => {
      if (!this.mediaSource) return;
      this.sourceBuffer = this.mediaSource.addSourceBuffer(mime);
      this.sourceBuffer.addEventListener('updateend', () => this.pump());
      this.pump();
    });
    this.ensureAnalyser();
  }

  /** 收到一块 base64 音频。 */
  pushChunk(b64: string) {
    this.queue.push(base64ToUint8(b64));
    this.pump();
  }

  /** 本段音频流结束。 */
  finish() {
    this.ended = true;
    this.pump();
  }

  /** 当前实时音量 0..1,供口型同步读取。 */
  getVolume(): number {
    if (!this.analyser || !this.freqData) return 0;
    this.analyser.getByteFrequencyData(this.freqData);
    let sum = 0;
    for (let i = 0; i < this.freqData.length; i++) sum += this.freqData[i];
    return sum / this.freqData.length / 255;
  }

  private pump() {
    const sb = this.sourceBuffer;
    if (!sb || sb.updating) return;
    if (this.queue.length > 0) {
      sb.appendBuffer(this.queue.shift()!);
      return;
    }
    if (this.ended && this.mediaSource?.readyState === 'open') {
      try {
        this.mediaSource.endOfStream();
      } catch {
        /* 已结束,忽略 */
      }
    }
  }

  private ensureAnalyser() {
    if (this.audioCtx) return;
    this.audioCtx = new AudioContext();
    const src = this.audioCtx.createMediaElementSource(this.audio);
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 256;
    this.freqData = new Uint8Array(new ArrayBuffer(this.analyser.frequencyBinCount));
    src.connect(this.analyser);
    this.analyser.connect(this.audioCtx.destination);
  }

  private reset() {
    this.queue = [];
    this.sourceBuffer = null;
    if (this.audio.src) URL.revokeObjectURL(this.audio.src);
    this.mediaSource = null;
  }
}
