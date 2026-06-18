// Live2D 角色控制器 (框架无关)。
// 用 pixi-live2d-display 加载 Cubism 4 模型,处理:
//   - 待机自动眨眼
//   - 表情切换 (ExpressionEvent → 模型表情)
//   - 口型同步:每帧用外部音量源驱动 ParamMouthOpenY
// Cubism Core 由 index.html 的 <script> 提供 (window.Live2DCubismCore)。

import * as PIXI from "pixi.js";
import { Live2DModel } from "pixi-live2d-display/cubism4";

// pixi-live2d-display 需要把 PIXI 暴露到全局以注册 ticker/插件
(window as any).PIXI = PIXI;

// 后端情绪标签 → 模型内表情名 (卡拉模型的 16 个 exp3)
const EMOTION_TO_EXPRESSION: Record<string, string> = {
  neutral: "kongbai",
  happy: "aixinyan",
  sad: "lei",
  angry: "duzui",
  surprised: "xingxingyan",
  shy: "lianhong",
  thinking: "han",
};

const MOUTH_PARAM = "ParamMouthOpenY";

export class Live2DController {
  private app: PIXI.Application;
  private model: Live2DModel | null = null;
  private volumeSource: (() => number) | null = null;
  private blinkTimer = 0;
  private nextBlinkAt = 2;
  private destroyed = false;
  private canvas: HTMLCanvasElement;

  constructor(container: HTMLElement) {
    // 自己创建 canvas:StrictMode 双挂载时 React 会复用同一个 DOM 节点,
    // 而被销毁的 WebGL 上下文无法在同一 canvas 上重建 → 第二次挂载拿到死上下文。
    // 每个控制器实例用自己的 canvas,销毁时一并移除,保证上下文干净。
    this.canvas = document.createElement("canvas");
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.display = "block";
    container.appendChild(this.canvas);

    this.app = new PIXI.Application({
      view: this.canvas,
      resizeTo: container,
      backgroundAlpha: 0, // 透明背景,为阶段 6 桌面悬浮窗铺路
      antialias: true,
      preserveDrawingBuffer: true, // readPixels 需要保留 backbuffer 内容
      sharedTicker: false,
      // 禁用 PixiJS 事件系统: Live2D 内部节点缺少 isInteractive,
      // 会导致 EventBoundary 报错。桌宠拖拽由 Tauri 层处理。
      eventFeatures: {
        click: false,
        move: false,
        wheel: false,
        globalMove: false,
      },
    });
  }

  async load(modelUrl: string): Promise<void> {
    const model = await Live2DModel.from(modelUrl, { autoInteract: false });
    // 加载是异步的:期间组件可能已卸载并 destroy(StrictMode 双挂载),此时跳过
    if (this.destroyed) {
      model.destroy();
      return;
    }
    this.model = model;
    model.autoUpdate = false; // 改由本控制器 onTick 驱动,不依赖 PIXI 共享 ticker
    this.app.stage.addChild(model as unknown as PIXI.DisplayObject);
    this.fit();
    this.app.ticker.add(this.onTick);
  }

  /** 把模型缩放并居中到画布。 */
  fit(): void {
    if (!this.model) return;
    const { width, height } = this.app.renderer;
    const scale = Math.min(width / this.model.width, height / this.model.height) * 0.95;
    this.model.scale.set(scale);
    this.model.x = width / 2;
    this.model.y = height / 2;
    this.model.anchor.set(0.5, 0.5);
  }

  /** 注入音量源 (0..1),用于口型同步。 */
  setVolumeSource(fn: () => number): void {
    this.volumeSource = fn;
  }

  /** 切换表情。传入后端情绪标签。 */
  setEmotion(emotion: string): void {
    if (!this.model) return;
    const expr = EMOTION_TO_EXPRESSION[emotion];
    if (expr) {
      try {
        this.model.expression(expr);
      } catch {
        /* 该模型无此表情,忽略 */
      }
    }
  }

  private onTick = (): void => {
    if (!this.model) return;
    const core = this.model.internalModel.coreModel as any;
    const deltaMS = this.app.ticker.deltaMS;
    const dt = deltaMS / 1000;

    // 先推进模型自身的动作/表情/物理 (autoUpdate 已关,需手动驱动),
    // 再在其结果上叠加口型与眨眼覆盖,最后由 PIXI 渲染。
    this.model.update(deltaMS);

    // 口型:音量驱动 (带轻微平滑)
    if (this.volumeSource) {
      const v = Math.min(1, this.volumeSource() * 1.8);
      const cur = core.getParameterValueById(MOUTH_PARAM);
      core.setParameterValueById(MOUTH_PARAM, cur + (v - cur) * 0.5);
    }

    // 待机眨眼:tick 驱动,blinkPhase 0..1 时眼睛闭合再睁开
    this.blinkTimer += dt;
    if (this.blinkPhase > 0) {
      this.blinkPhase -= dt / 0.12; // 一次眨眼约 0.12s
      // 三角波:0→闭→开
      const open = Math.abs(this.blinkPhase - 0.5) * 2;
      core.setParameterValueById("ParamEyeLOpen", open);
      core.setParameterValueById("ParamEyeROpen", open);
      if (this.blinkPhase <= 0) {
        core.setParameterValueById("ParamEyeLOpen", 1);
        core.setParameterValueById("ParamEyeROpen", 1);
      }
    } else if (this.blinkTimer >= this.nextBlinkAt) {
      this.blinkPhase = 1;
      this.blinkTimer = 0;
      this.nextBlinkAt = 2 + Math.random() * 4;
    }
  };

  private blinkPhase = 0;

  /**
   * 检测指定屏幕坐标处的像素透明度。
   * 返回 0~255, 0 = 完全透明 (角色外), 255 = 完全不透明 (角色上)。
   * 用于鼠标穿透: 透明区域穿透, 不透明区域接收点击。
   */
  getPixelAlpha(screenX: number, screenY: number): number {
    if (!this.model) return 0;

    const rect = this.canvas.getBoundingClientRect();
    const x = screenX - rect.left;
    const y = screenY - rect.top;

    // 超出 canvas 范围 = 透明
    if (x < 0 || y < 0 || x >= rect.width || y >= rect.height) return 0;

    // 从 WebGL canvas 读取像素 (需要 devicePixelRatio 校正)
    const dpr = window.devicePixelRatio || 1;
    const px = Math.floor(x * dpr);
    const py = Math.floor(y * dpr);

    const renderer = this.app.renderer;
    if (renderer.width <= px || renderer.height <= py) return 0;

    const gl = (renderer as any).gl as WebGLRenderingContext | undefined;
    if (!gl) return 0;
    const pixel = new Uint8Array(4);
    // WebGL 坐标系 Y 轴翻转
    gl.readPixels(px, renderer.height - py, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
    return pixel[3]; // alpha channel
  }

  /** 获取 canvas DOM 元素, 供外部添加事件监听。 */
  getCanvas(): HTMLCanvasElement {
    return this.canvas;
  }

  destroy(): void {
    this.destroyed = true;
    this.app.ticker.remove(this.onTick);
    this.app.destroy(true, { children: true });
    this.canvas.remove();
  }
}
