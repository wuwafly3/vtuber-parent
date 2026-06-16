import { useEffect, useRef } from "react";
import { Live2DController } from "./controller";

interface Props {
  modelUrl: string;
  // 口型同步音量源 (0..1)
  volumeSource?: () => number;
  // 注册控制器实例,供父组件调用 setEmotion
  onReady?: (controller: Live2DController) => void;
}

export function CharacterStage({ modelUrl, volumeSource, onReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let controller: Live2DController | null = null;
    let disposed = false;

    (async () => {
      controller = new Live2DController(container);
      try {
        await controller.load(modelUrl);
        if (disposed) return;
        if (volumeSource) controller.setVolumeSource(volumeSource);
        onReady?.(controller);
      } catch (e) {
        console.error("Live2D 模型加载失败:", e);
      }
    })();

    return () => {
      disposed = true;
      controller?.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelUrl]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", display: "block" }}
    />
  );
}
