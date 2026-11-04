import { useEffect, useState } from "react";
import { fetchToday, sendFeedback } from "../api.js";
import { ContextBar } from "../components/ContextBar.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { OutfitCard } from "../components/OutfitCard.jsx";
import { WeatherBar } from "../components/WeatherBar.jsx";
import { MAX_TEMP, MIN_TEMP, OCCASIONS } from "../constants.js";
import { useWeather } from "../hooks/useWeather.js";
import { weatherRain, weatherTemp } from "../lib/weather.js";

const DATE_LABEL = new Intl.DateTimeFormat("zh-CN", {
  month: "long",
  day: "numeric",
  weekday: "long",
});

/** 请求结束后清掉「正在离场 / 正在提交」标记，避免失败时卡片停在隐形状态。 */
function settleTransient(feedback) {
  let changed = false;
  const next = {};
  for (const [hash, value] of Object.entries(feedback)) {
    if (value.leaving || value.pending) {
      next[hash] = { ...value, leaving: false, pending: false };
      changed = true;
    }
  }
  return changed ? { ...feedback, ...next } : feedback;
}

export function TodayPage({ onOpenItem, onSettings, onGaps, onCloset }) {
  const weatherState = useWeather();
  const weather = weatherState.weather;
  const weatherValue = weatherTemp(weather);
  const isRainy = weatherRain(weather);
  const [occasion, setOccasion] = useState("日常");
  const [manualTemp, setManualTemp] = useState(null);
  const feelsLike = manualTemp ?? weatherValue ?? 22;
  // 再换：跳过今天已经看过的前几条
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  const [feedback, setFeedback] = useState({});

  useEffect(() => {
    if (!weatherState.ready) return undefined;
    const controller = new AbortController();
    let active = true;
    setLoading(true);

    fetchToday({
      occasion,
      feelsLike,
      isRainy,
      offset,
      signal: controller.signal,
    })
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setError(null);
        setFeedback(settleTransient);
      })
      .catch((err) => {
        if (!active || err.name === "AbortError") return;
        setError(err.message);
        setFeedback(settleTransient);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [occasion, feelsLike, isRainy, offset, retryToken, weatherState.ready]);

  const outfit = data?.outfits?.[0] ?? null;
  const current = outfit ? feedback[outfit.hash] ?? {} : {};
  // has_more 由后端按去重后的序列判断：false = 后面没有别的不同组合
  const hasMore = Boolean(data?.has_more);
  const candidateCount = data?.candidate_count ?? 0;

  const update = (hash, patch) => {
    setFeedback((prev) => ({
      ...prev,
      [hash]: {
        adopted: false,
        pending: false,
        leaving: false,
        error: null,
        ...prev[hash],
        ...patch,
      },
    }));
  };

  const act = async (signal) => {
    if (!outfit || current.pending || current.adopted) return;
    update(outfit.hash, { pending: true, error: null });
    try {
      await sendFeedback({
        outfitHash: outfit.hash,
        signal,
        garmentIds: outfit.items.map((piece) => piece.id),
        hitRules: [...outfit.thumbs_up, ...outfit.thumbs_down],
      });
      if (signal === "adopt") {
        update(outfit.hash, { pending: false, adopted: true });
      } else {
        update(outfit.hash, { pending: false, leaving: true });
        setOffset((value) => value + 1);
      }
    } catch (err) {
      update(outfit.hash, { pending: false, error: err.message });
    }
  };

  const changeOccasion = (value) => {
    if (value === occasion) return;
    setOccasion(value);
    setOffset(0);
  };

  const stepTemp = (delta) => {
    setManualTemp(Math.min(MAX_TEMP, Math.max(MIN_TEMP, feelsLike + delta)));
    setOffset(0);
  };

  const resetTemp = () => {
    setManualTemp(null);
    setOffset(0);
  };

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">今日建议 · {DATE_LABEL.format(new Date())}</p>
          <h1>穿这套就够</h1>
        </div>
        {data && <span className="wardrobe-count">{data.item_count} 件</span>}
      </header>

      <div className="top">
        <WeatherBar
          weather={weather}
          ready={weatherState.ready}
          error={weatherState.error}
          onSettings={onSettings}
        />
        <ContextBar
          occasions={OCCASIONS}
          occasion={occasion}
          onOccasion={changeOccasion}
          feelsLike={feelsLike}
          onStepTemp={stepTemp}
          isManual={manualTemp !== null}
          onResetTemp={resetTemp}
        />
      </div>

      <main className="today-main">
        {!data ? (
          error ? (
            <EmptyState
              title="请求没有成功"
              description={error}
              actionLabel="重试"
              onAction={() => setRetryToken((value) => value + 1)}
            />
          ) : loading ? (
            <div className="skeletons" aria-label="正在挑今天的搭配">
              <div className="skeleton" />
            </div>
          ) : null
        ) : (
          <>
            {error && (
              <div className="error-banner" role="alert">
                <span>{error}</span>
                <button
                  type="button"
                  className="error-retry"
                  onClick={() => setRetryToken((value) => value + 1)}
                >
                  重试
                </button>
              </div>
            )}

            {outfit ? (
              <>
                <div className="result-meta today-meta" aria-live="polite">
                  <span>今日第 {offset + 1} 套</span>
                  <span>{hasMore ? "再换还有别的" : "再换没有别的了"}</span>
                </div>
                <section className="outfit-list today-list" aria-label="今天的建议">
                  <OutfitCard
                    outfit={outfit}
                    index={offset}
                    feedback={current}
                    onFeedback={(_, signal) => act(signal)}
                    onOpenItem={onOpenItem}
                    variant="today"
                  />
                </section>
                <p className="note today-note">
                  {current.adopted
                    ? "已记下：今天穿这套。明天会从别的组合里挑。"
                    : hasMore
                      ? "一次只推一套，省得你挑。不合适就点「再换」。"
                      : "一次只推一套。这个条件下没有更多不同组合了，想换方向就改上面的天气或场合。"}
                </p>
              </>
            ) : offset > 0 ? (
              <EmptyState
                title="再换没有更多了"
                description={`已经看过 ${offset} 套，这个条件下没有别的组合。回到第一套，或者改改天气和场合。`}
                actionLabel="回到第一套"
                onAction={() => setOffset(0)}
              />
            ) : candidateCount === 0 ? (
              <EmptyState
                title="衣库还凑不齐一套"
                description="缺少某个槽位，比如没有下装或鞋。先补一件，再回来。"
                actionLabel="去衣库加一件"
                onAction={onCloset}
              />
            ) : (
              <EmptyState
                title="这个条件下配不出组合"
                description={
                  <>
                    枚举出 {candidateCount} 种槽位组合，但都过不了必选规则。
                    <br />
                    换个体感温度或场合，或者添几件衣服。
                  </>
                }
                actionLabel="看缺口诊断"
                onAction={onGaps}
              />
            )}
          </>
        )}
      </main>
    </>
  );
}
