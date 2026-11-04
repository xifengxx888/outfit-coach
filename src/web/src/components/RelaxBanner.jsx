export function RelaxBanner({ bestLevel, relaxedSomewhere }) {
  if (!relaxedSomewhere) return null;

  const message =
    bestLevel > 0
      ? `没有完全合规的搭配，以下为放宽 ${bestLevel} 档后的结果。`
      : "部分组合需要放宽才能成立，已标在对应卡片上。";

  return (
    <div className="relax-banner" role="status">
      {message}
    </div>
  );
}
