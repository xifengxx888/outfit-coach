import { useEffect, useState } from "react";
import { fetchGaps } from "../api.js";
import { EmptyState } from "../components/EmptyState.jsx";
import { BackLink } from "../components/BackLink.jsx";
import {
  BottleneckSection,
  CoverageSection,
  FillSection,
  IsolatedSection,
  OccasionSection,
} from "../components/GapSections.jsx";

export function GapsPage({ onBack, onAdd }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);

    fetchGaps({ signal: controller.signal })
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setError(null);
      })
      .catch((err) => {
        if (!active || err.name === "AbortError") return;
        setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [retryToken]);

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">全衣柜 · 四档温度</p>
          <h1>缺口诊断</h1>
        </div>
        <div className="header-actions">
          {data && (
            <span className="wardrobe-count">{data.basis.item_count} 件</span>
          )}
          <BackLink onBack={onBack} label="组合" />
        </div>
      </header>

      <main>
        {!data && error && (
          <EmptyState
            title="请求没有成功"
            description={error}
            actionLabel="重试"
            onAction={() => setRetryToken((value) => value + 1)}
          />
        )}

        {!data && !error && loading && (
          <div className="skeletons" aria-label="正在诊断">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}

        {data && !data.basis.sufficient && (
          <EmptyState
            title="先录几件再看"
            description={`当前只有 ${data.basis.item_count} 件确认单品。少于 5 件时，「缺什么」的答案是「缺一切」，看不出具体缺口。`}
            actionLabel="去录入"
            onAction={onAdd}
          />
        )}

        {data && data.basis.sufficient && (
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

            {hasNoGaps(data) ? (
              <EmptyState
                title="四个温度带都能穿"
                description="也没有配不上的单品。等衣柜有变化再回来看。"
                actionLabel="回到组合"
                onAction={onBack}
              />
            ) : (
              <>
                <CoverageSection bands={data.basis.bands} />
                <BottleneckSection cards={data.bottlenecks} />
                <IsolatedSection items={data.isolated} />
                <OccasionSection rows={data.occasions} />
                <FillSection fills={data.fills} bands={data.basis.bands} />

                <p className="note">
                  只统计严格档、与组合页同一套去重；放宽档不参与诊断。
                </p>
              </>
            )}
          </>
        )}
      </main>
    </>
  );
}

function hasNoGaps(data) {
  return (
    data.basis.bands.every((band) => band.valid_outfits >= band.min) &&
    data.bottlenecks.length === 0 &&
    data.isolated.length === 0 &&
    data.occasions.every((row) => row.severity === 0) &&
    data.fills.length === 0
  );
}
