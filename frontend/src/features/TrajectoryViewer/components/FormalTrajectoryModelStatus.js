import Button from "@/components/buttons/Button";

export default function FormalTrajectoryModelStatus({
  overlay,
  playing,
  modelCount,
}) {
  return (
    <>
      <span role="status">
        {overlay.loading ? "模型載入中…" : modelCount
          ? `${playing ? "本輪模型" : "模型疊加"}：${overlay.loaded} / ${modelCount} 輪`
          : "此輪尚無已完成的模型。"}
        {overlay.unavailable > 0 ? ` · ${overlay.unavailable} 輪缺少毫米座標定位，暫不疊加。` : ""}
        {overlay.failed > 0 ? ` · ${overlay.failed} 輪載入失敗。` : ""}
      </span>
      {overlay.error ? <span className="text-rose-200">{overlay.error}</span> : null}
      {!overlay.loading && modelCount > 0 ? (
        <Button
          onClick={overlay.retry}
          className="min-h-8 px-2 text-xs"
        >
          重新載入模型
        </Button>
      ) : null}
    </>
  );
}
