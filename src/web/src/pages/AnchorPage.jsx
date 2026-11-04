import { useEffect, useState } from "react";
import { fetchItem } from "../api.js";
import { ContextBar } from "../components/ContextBar.jsx";
import { BackLink } from "../components/BackLink.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { OutfitResults } from "../components/OutfitResults.jsx";
import { OCCASIONS } from "../constants.js";
import { PAGE_SIZE, useOutfitBoard } from "../hooks/useOutfitBoard.js";
import { useWeather } from "../hooks/useWeather.js";
import {
  contextNote,
  hasNoLocation,
  weatherRain,
  weatherTemp,
} from "../lib/weather.js";
import {
  fitText,
  formalityText,
  layersLabel,
  seasonText,
  weightText,
  wornLabel,
} from "../lib/itemView.js";

function AnchorCard({ item }) {
  return (
    <section className="anchor-card" aria-label="锚定单品">
      <div className="anchor-thumb">
        {item.photo_path ? (
          <img src={`/${item.photo_path}`} alt="" />
        ) : (
          <span>{item.category.slice(0, 1)}</span>
        )}
      </div>
      <div className="anchor-meta">
        <p className="anchor-slot">{layersLabel(item)}</p>
        <p className="anchor-facts">
          {formalityText(item.formality)} · {fitText(item.fit)} ·{" "}
          {weightText(item.weight)}（{seasonText(item.weight)}）
        </p>
        <p className="anchor-worn">最近穿着 {wornLabel(item.last_worn_at)}</p>
      </div>
    </section>
  );
}

function AnchoredBoard({ itemId, onAdopt, onGaps, onSettings }) {
  const weatherState = useWeather();
  const weather = weatherState.weather;
  const board = useOutfitBoard({
    anchorId: itemId,
    onAdopt,
    weatherTemp: weatherTemp(weather),
    weatherReady: weatherState.ready,
    isRainy: weatherRain(weather),
  });
  const relaxed = Boolean(board.data && board.data.best_level > 0);

  return (
    <>
      <div className="top">
        <ContextBar
          occasions={OCCASIONS}
          occasion={board.occasion}
          onOccasion={board.handleOccasion}
          feelsLike={board.feelsLike}
          onStepTemp={board.stepTemp}
          weatherNote={contextNote(weather)}
          isManual={board.isManual}
          onResetTemp={board.resetTemp}
          needsLocation={hasNoLocation(weather)}
          onSettings={onSettings}
        />
      </div>

      <OutfitResults
        data={board.data}
        error={board.error}
        loading={board.loading}
        hidden={board.hidden}
        feedback={board.feedback}
        visibleCount={board.visibleCount}
        pageSize={PAGE_SIZE}
        baseIndex={board.batchOffset}
        onFeedback={board.handleFeedback}
        onRetry={board.retry}
        onMore={board.more}
        onGaps={onGaps}
        emptyTitle="这件衣服目前配不出合规组合"
        emptyDescription="换个体感温度或场合再试；也可能衣库里还缺能接住它的单品。"
        emptyActionLabel="看看缺口诊断"
        maxVisible={relaxed ? 3 : null}
        maxNote={
          relaxed
            ? "严格档配不出合规组合，这里是放宽后最靠前的 3 套。"
            : null
        }
      />
    </>
  );
}

export function AnchorPage({ itemId, onBack, onEdit, onGaps, onSettings }) {
  const [item, setItem] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);

    fetchItem(itemId, { signal: controller.signal })
      .then((payload) => {
        if (!active) return;
        setItem(payload);
        setLoadError(null);
      })
      .catch((err) => {
        if (!active || err.name === "AbortError") return;
        setLoadError(err);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [itemId, retryToken]);

  useEffect(() => {
    if (item) document.title = `用它搭配 ${item.name} · 个人穿搭助手`;
  }, [item]);

  const refreshItem = () => {
    fetchItem(itemId)
      .then(setItem)
      .catch(() => {
        // 采纳已经成功，刷新失败不值得弹错
      });
  };

  if (!item) {
    return (
      <>
        <header className="app-header">
          <div>
            <p className="eyebrow">锚定搭配</p>
            <h1>{loadError?.status === 404 ? "没找到" : "读单品"}</h1>
          </div>
          <BackLink onBack={onBack} label="详情" />
        </header>
        <main>
          {loading && !loadError ? (
            <div className="skeletons" aria-label="正在读取单品">
              <div className="skeleton" />
            </div>
          ) : loadError?.status === 404 ? (
            <EmptyState
              title="这件单品不存在"
              description="可能已经不在衣库里。回衣库看看。"
              actionLabel="回衣库"
              onAction={onBack}
            />
          ) : (
            <EmptyState
              title="请求没有成功"
              description={loadError?.message ?? "没读到这件单品"}
              actionLabel="重试"
              onAction={() => setRetryToken((value) => value + 1)}
            />
          )}
        </main>
      </>
    );
  }

  const draft = item.status === "draft";
  const archived = item.status === "archived";

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">锚定搭配 · {item.category}</p>
          <h1>{item.name}</h1>
        </div>
        <BackLink onBack={onBack} label="详情" />
      </header>

      <div className="anchor-head">
        <AnchorCard item={item} />
      </div>

      {draft ? (
        <main>
          <p className="detail-warn">还没补完，暂不参与搭配。</p>
          <div className="detail-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() => onEdit(item.id)}
            >
              先补完这件
            </button>
          </div>
        </main>
      ) : archived ? (
        <main>
          <p className="restore-note">已归档，不参与搭配。</p>
          <div className="detail-actions">
            <button type="button" className="btn-primary" onClick={onBack}>
              查看详情
            </button>
          </div>
        </main>
      ) : (
        <main>
          <AnchoredBoard
            itemId={item.id}
            onAdopt={refreshItem}
            onGaps={onGaps}
            onSettings={onSettings}
          />
        </main>
      )}
    </>
  );
}
