import { useEffect, useMemo, useState } from "react";
import { fetchItems } from "../api.js";
import { ClosetCard } from "../components/ClosetCard.jsx";
import { Segmented } from "../components/ChoiceControls.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { CATEGORY_BY_KEY, FILTERS, SORT_OPTIONS } from "../lib/wardrobe.js";

function sortItems(items, sort) {
  const copy = [...items];
  if (sort === "least_worn") {
    // 从没穿过（null）排最前，其次按日期升序；同日按新录入优先
    copy.sort((a, b) => {
      const left = a.last_worn_at ?? "";
      const right = b.last_worn_at ?? "";
      if (left !== right) return left < right ? -1 : 1;
      return b.id - a.id;
    });
  } else {
    copy.sort((a, b) => b.id - a.id);
  }
  return copy;
}

export function ClosetPage({ onAdd, onOpenItem }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("recent");
  const [archivedOpen, setArchivedOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);

    fetchItems({ status: "all", signal: controller.signal })
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

  const groups = useMemo(() => {
    const visible = (data ?? []).filter(
      (item) => filter === "all" || CATEGORY_BY_KEY[item.category] === filter,
    );
    return {
      total: visible.length,
      drafts: sortItems(
        visible.filter((item) => item.status === "draft"),
        sort,
      ),
      confirmed: sortItems(
        visible.filter((item) => item.status === "confirmed"),
        sort,
      ),
      archived: sortItems(
        visible.filter((item) => item.status === "archived"),
        sort,
      ),
    };
  }, [data, filter, sort]);

  const hasAnyItems = Boolean(data && data.length > 0);

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">你的衣柜 · 全部单品</p>
          <h1>衣库</h1>
        </div>
        <span className="wardrobe-count">
          {data ? `${data.length} 件` : "…"}
        </span>
      </header>

      <main className="closet-main">
        {!data && error && (
          <EmptyState
            title="请求没有成功"
            description={error}
            actionLabel="重试"
            onAction={() => setRetryToken((value) => value + 1)}
          />
        )}

        {!data && !error && loading && (
          <div className="closet-grid" aria-label="正在读取衣库">
            <div className="closet-skeleton" />
            <div className="closet-skeleton" />
            <div className="closet-skeleton" />
            <div className="closet-skeleton" />
          </div>
        )}

        {data && data.length === 0 && (
          <EmptyState
            title="衣库还是空的"
            description="先录一件常穿的。照片可以跳过，属性填齐就能参与搭配。"
            actionLabel="录入第一件"
            onAction={onAdd}
          />
        )}

        {hasAnyItems && (
          <>
            <div className="filter-scroll" role="group" aria-label="按品类筛选">
              {FILTERS.map((entry) => {
                const on = filter === entry.key;
                return (
                  <button
                    key={entry.key}
                    type="button"
                    className={`filter-chip${on ? " is-on" : ""}`}
                    aria-pressed={on}
                    onClick={() => setFilter(entry.key)}
                  >
                    {entry.label}
                  </button>
                );
              })}
            </div>

            <div className="closet-sort">
              <span>排序</span>
              <Segmented
                options={SORT_OPTIONS}
                value={sort}
                onChange={setSort}
                label="排序"
              />
            </div>

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

            {groups.total === 0 ? (
              <EmptyState
                title="这个分类还没有衣服"
                description="换一个分类，或者先录一件。"
                actionLabel="查看全部"
                onAction={() => setFilter("all")}
              />
            ) : (
              <>
                {groups.drafts.length > 0 && (
                  <section className="closet-group">
                    <div className="closet-group-head">
                      <h2>待补完 · 暂不参与搭配</h2>
                      <span>{groups.drafts.length} 件</span>
                    </div>
                    <div className="closet-grid">
                      {groups.drafts.map((item) => (
                        <ClosetCard key={item.id} item={item} onOpen={onOpenItem} />
                      ))}
                    </div>
                  </section>
                )}

                {groups.confirmed.length > 0 && (
                  <section className="closet-group">
                    <div className="closet-group-head">
                      <h2>可搭配</h2>
                      <span>{groups.confirmed.length} 件</span>
                    </div>
                    <div className="closet-grid">
                      {groups.confirmed.map((item) => (
                        <ClosetCard key={item.id} item={item} onOpen={onOpenItem} />
                      ))}
                    </div>
                  </section>
                )}

                {groups.archived.length > 0 && (
                  <section className="closet-group closet-archived">
                    <button
                      type="button"
                      className="archive-toggle"
                      aria-expanded={archivedOpen}
                      onClick={() => setArchivedOpen((open) => !open)}
                    >
                      <span>已归档 {groups.archived.length} 件</span>
                      <span>{archivedOpen ? "收起" : "展开"}</span>
                    </button>
                    {archivedOpen && (
                      <div className="closet-grid">
                        {groups.archived.map((item) => (
                          <ClosetCard key={item.id} item={item} onOpen={onOpenItem} />
                        ))}
                      </div>
                    )}
                  </section>
                )}
              </>
            )}

            <button type="button" className="fab" onClick={onAdd}>
              <span aria-hidden="true">＋</span> 录入
            </button>
          </>
        )}
      </main>
    </>
  );
}
