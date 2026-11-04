import { useEffect, useState } from "react";
import { fetchTheory } from "../api.js";
import { BackLink } from "../components/BackLink.jsx";
import { EmptyState } from "../components/EmptyState.jsx";

function TheoryCard({ principle }) {
  return (
    <article className="theory-card">
      <div className="theory-title-row">
        <h3>{principle.title}</h3>
        <span className={`status-tag status-${principle.status}`}>
          {principle.status_label}
        </span>
      </div>
      <p className="theory-claim">{principle.claim}</p>
      <dl className="theory-detail">
        <div>
          <dt>为什么</dt>
          <dd>{principle.why}</dd>
        </div>
        <div>
          <dt>怎么自己看</dt>
          <dd>{principle.how_to_judge}</dd>
        </div>
        <div>
          <dt>依据</dt>
          <dd>
            <span className={`grade-tag grade-${principle.grade}`}>
              {principle.grade}
            </span>{" "}
            {principle.grade_label} ·{" "}
            {principle.source_url ? (
              <a
                className="source-link"
                href={principle.source_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                {principle.source}
              </a>
            ) : (
              principle.source
            )}
          </dd>
        </div>
        <div>
          <dt>规则</dt>
          <dd className="rule-tags">
            {principle.rule_ids.map((ruleId) => (
              <code className="rule-tag" key={ruleId}>
                {ruleId}
              </code>
            ))}
          </dd>
        </div>
      </dl>
    </article>
  );
}

export function TheoryPage({ onBack }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);

    fetchTheory({ signal: controller.signal })
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
          <p className="eyebrow">静态知识库 · 只读</p>
          <h1>搭配原理</h1>
        </div>
        <BackLink onBack={onBack} label="我的" />
      </header>

      <main className="theory-main">
        {!data && error && (
          <EmptyState
            title="请求没有成功"
            description={error}
            actionLabel="重试"
            onAction={() => setRetryToken((value) => value + 1)}
          />
        )}

        {!data && !error && loading && (
          <div className="skeletons" aria-label="正在读取原理">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}

        {data && (
          <>
            <p className="theory-intro">
              解释只使用这里列出的原理；不在代码里的理论不教。依据按 A
              可测量科学、B 实验与标准、C 造型经验、D 数据不足分级。
            </p>

            {data.groups.map((group) => (
              <section
                className="theory-group"
                key={group.axis}
                aria-label={group.axis}
              >
                <h2>{group.axis}</h2>
                {group.principles.map((principle) => (
                  <TheoryCard principle={principle} key={principle.id} />
                ))}
              </section>
            ))}

            <section className="theory-group" aria-label="数据不足">
              <h2>数据不足，暂不计算</h2>
              <p className="theory-intro">
                这些说法保留在知识库里，但当前衣柜字段算不出来，不进入每日解释。
              </p>
              <ul className="unsupported-list">
                {data.unsupported.map((topic) => (
                  <li className="unsupported-card" key={topic.topic}>
                    <p className="unsupported-topic">{topic.topic}</p>
                    <p>{topic.why}</p>
                    <p className="unsupported-needed">
                      需要补：{topic.needed}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </main>
    </>
  );
}
