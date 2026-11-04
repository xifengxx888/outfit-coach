import { useCallback, useEffect, useState } from "react";
import { fetchLocations, fetchProfile, fetchStats } from "../api.js";
import { EmptyState } from "../components/EmptyState.jsx";
import { BodySection } from "../components/settings/BodySection.jsx";
import { DataSection } from "../components/settings/DataSection.jsx";
import { LocationSection } from "../components/settings/LocationSection.jsx";
import { invalidateWeather } from "../hooks/useWeather.js";

const EXTRACT_ROWS = [
  { name: "手动录入", state: "M1 使用中", active: true },
  { name: "本地 VLM", state: "M2", active: false },
  { name: "云端 VLM", state: "M2，默认关闭", active: false },
];

export function SettingsPage({ onTheory }) {
  const [profile, setProfile] = useState(null);
  const [locations, setLocations] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([fetchProfile(), fetchLocations(), fetchStats()])
      .then(([nextProfile, nextLocations, nextStats]) => {
        if (!active) return;
        setProfile(nextProfile);
        setLocations(nextLocations);
        setStats(nextStats);
      })
      .catch((err) => {
        if (!active) return;
        setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [retryToken]);

  const reloadLocations = useCallback(async () => {
    const next = await fetchLocations();
    setLocations(next);
    // 地点变了，任何页面下次挂载都要重新取天气
    invalidateWeather();
    fetchStats().then(setStats).catch(() => {
      // 统计只是展示，刷新失败不打断地点操作
    });
  }, []);

  const ready = profile && locations && stats;

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">我的</p>
          <h1>地点 · 身材 · 数据</h1>
        </div>
      </header>

      <main className="settings-main">
        {!ready && error && (
          <EmptyState
            title="请求没有成功"
            description={error}
            actionLabel="重试"
            onAction={() => setRetryToken((value) => value + 1)}
          />
        )}

        {!ready && !error && (
          <div className="skeletons" aria-label="正在读取设置">
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}

        {ready && (
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

            <LocationSection locations={locations} onChanged={reloadLocations} />
            <BodySection profile={profile} onSaved={setProfile} />

            <section className="settings-section" aria-label="属性提取">
              <h2>属性提取</h2>
              <ul className="status-list">
                {EXTRACT_ROWS.map((row) => (
                  <li key={row.name} className="status-row">
                    <span>{row.name}</span>
                    <span className={row.active ? "status-on" : "status-off"}>
                      {row.state}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="section-note">
                现在全部靠手量；自动提取要等 M2，界面不放假开关。
              </p>
            </section>

            <DataSection stats={stats} />

            <section className="settings-section" aria-label="搭配原理">
              <h2>搭配原理</h2>
              <button type="button" className="settings-entry" onClick={onTheory}>
                <span>
                  <span className="settings-entry-title">18 条搭配原理</span>
                  <span className="settings-entry-note">
                    色彩、比例、层次、正式度的依据与来源
                  </span>
                </span>
                <span className="settings-entry-arrow" aria-hidden="true">
                  ›
                </span>
              </button>
            </section>

            <section className="settings-section" aria-label="关于">
              <h2>关于</h2>
              <dl className="about-list">
                <div>
                  <dt>版本</dt>
                  <dd>{stats.version}</dd>
                </div>
                <div>
                  <dt>规则</dt>
                  <dd>{stats.rules} 条</dd>
                </div>
                <div>
                  <dt>数据</dt>
                  <dd>本地 SQLite · Open-Meteo</dd>
                </div>
              </dl>
            </section>
          </>
        )}
      </main>
    </>
  );
}
