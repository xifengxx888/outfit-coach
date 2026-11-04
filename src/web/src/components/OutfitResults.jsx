import { EmptyState } from "./EmptyState.jsx";
import { OutfitCard } from "./OutfitCard.jsx";
import { RelaxBanner } from "./RelaxBanner.jsx";

export function OutfitResults({
  data,
  error,
  loading,
  hidden,
  feedback,
  visibleCount,
  pageSize,
  baseIndex = 0,
  onFeedback,
  onRetry,
  onShuffle,
  onMore,
  onGaps,
  onOpenItem,
  emptyTitle = "这个条件下配不出组合",
  emptyDescription = "换个体感温度或场合再试，或者看看衣柜里缺什么。",
  emptyActionLabel = "看看缺口诊断",
  maxVisible = null,
  maxNote = null,
}) {
  const outfits = data?.outfits ?? [];
  const visible = outfits.filter((outfit) => !hidden.has(outfit.hash));
  const cap = maxVisible ?? visibleCount;
  const shown = visible.slice(0, cap);
  const relaxedSomewhere = visible.some((outfit) => outfit.level > 0);

  if (!data) {
    if (error) {
      return (
        <EmptyState
          title="请求没有成功"
          description={error}
          actionLabel="重试"
          onAction={onRetry}
        />
      );
    }
    return loading ? (
      <div className="skeletons" aria-label="正在求解">
        <div className="skeleton" />
        <div className="skeleton" />
      </div>
    ) : null;
  }

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button type="button" className="error-retry" onClick={onRetry}>
            重试
          </button>
        </div>
      )}

      <div className="result-meta" aria-live="polite">
        <span>
          {data.item_count} 件单品，{data.candidate_count} 种槽位组合
        </span>
        <span>
          {outfits.length === 0
            ? "没有可展示的组合"
            : visible.length > 0
              ? `展示 ${shown.length} / ${visible.length} 套`
              : "这一批都换掉了"}
        </span>
      </div>

      <RelaxBanner
        bestLevel={data.best_level}
        relaxedSomewhere={relaxedSomewhere}
      />

      {outfits.length === 0 ? (
        <EmptyState
          title={emptyTitle}
          description={emptyDescription}
          actionLabel={emptyActionLabel}
          onAction={onGaps}
        />
      ) : visible.length === 0 ? (
        <EmptyState
          title="这一批都换掉了"
          description={
            data.has_more
              ? "当前展示的几套都处理完了，换一批新的。"
              : "重新求解会把当前条件下的组合再排一遍。"
          }
          actionLabel={data.has_more && onShuffle ? "换一批" : "重新求解"}
          onAction={data.has_more && onShuffle ? onShuffle : onRetry}
        />
      ) : (
        <>
          <section className="outfit-list" aria-label="组合列表">
            {shown.map((outfit) => (
              <OutfitCard
                key={outfit.hash}
                outfit={outfit}
                index={baseIndex + outfits.indexOf(outfit)}
                feedback={feedback[outfit.hash]}
                onFeedback={onFeedback}
                onOpenItem={onOpenItem}
              />
            ))}
          </section>

          {!maxVisible && shown.length < visible.length && (
            <button type="button" className="more-button" onClick={onMore}>
              再看 {pageSize} 套
            </button>
          )}
        </>
      )}

      {visible.length > 0 && (
        <p className="note">
          {maxNote ??
            "按「放宽档位 → 规则得分」排序；放宽会扣分，档位标在卡片上。"}
        </p>
      )}
    </>
  );
}
