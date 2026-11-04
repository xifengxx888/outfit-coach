import { useEffect, useState } from "react";
import { addLocation, fetchSetup, saveProfile, skipSetup } from "../api.js";
import { BodyFields } from "../components/BodyFields.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { LocationPicker } from "../components/LocationPicker.jsx";
import { invalidateWeather } from "../hooks/useWeather.js";
import { bodyPayload, emptyBodyForm } from "../lib/body.js";

export function SetupPage({ onDone, onToday, onSettings }) {
  const [status, setStatus] = useState("loading");
  const [setupError, setSetupError] = useState(null);
  const [retryToken, setRetryToken] = useState(0);
  const [form, setForm] = useState(emptyBodyForm);
  const [picked, setPicked] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    setStatus("loading");
    fetchSetup()
      .then((info) => {
        if (!active) return;
        setStatus(info.needs_setup ? "ready" : "done");
      })
      .catch((err) => {
        if (!active) return;
        setSetupError(err.message);
        setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [retryToken]);

  const updateValue = (key, value) => {
    setForm((prev) => ({
      ...prev,
      values: { ...prev.values, [key]: value },
    }));
  };

  const updateSource = (key, value) => {
    setForm((prev) => ({
      ...prev,
      sources: { ...prev.sources, [key]: value },
    }));
  };

  const handleSkip = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await skipSetup();
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleFinish = async () => {
    if (saving) return;
    let payload;
    try {
      payload = bodyPayload(form.values, form.sources);
    } catch (err) {
      setError(err.message);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // 什么都没填就点「完成」：按跳过处理，否则下次进 /closet 还会被带回来
      if (Object.keys(payload).length === 0 && !picked) {
        await skipSetup();
        onDone();
        return;
      }
      if (Object.keys(payload).length > 0) await saveProfile(payload);
      if (picked) {
        await addLocation({
          name: picked.name,
          lat: picked.lat,
          lon: picked.lon,
        });
      }
      invalidateWeather();
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (status === "loading") {
    return (
      <>
        <header className="app-header">
          <div>
            <p className="eyebrow">首次设置</p>
            <h1>先把地点和身材填上</h1>
          </div>
        </header>
        <main>
          <div className="skeletons" aria-label="正在读取设置状态">
            <div className="skeleton" />
          </div>
        </main>
      </>
    );
  }

  if (status === "error") {
    return (
      <>
        <header className="app-header">
          <div>
            <p className="eyebrow">首次设置</p>
            <h1>读不到设置状态</h1>
          </div>
        </header>
        <main>
          <EmptyState
            title="请求没有成功"
            description={setupError}
            actionLabel="重试"
            onAction={() => setRetryToken((value) => value + 1)}
          />
        </main>
      </>
    );
  }

  if (status === "done") {
    return (
      <>
        <header className="app-header">
          <div>
            <p className="eyebrow">首次设置</p>
            <h1>已经设置过了</h1>
          </div>
        </header>
        <main className="setup-done">
          <p className="section-note">
            要改地点或身材，随时可以去「我的」。
          </p>
          <div className="setup-done-actions">
            <button type="button" className="btn-primary" onClick={onToday}>
              去今日
            </button>
            <button type="button" className="btn-secondary" onClick={onSettings}>
              我的
            </button>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">首次设置</p>
          <h1>先把地点和身材填上</h1>
        </div>
      </header>

      <main className="setup-main">
        <p className="setup-lead">
          两项都能跳过，之后在「我的」补。
        </p>

        <section className="setup-section">
          <h2>地点</h2>
          <p className="section-note">
            取实时体感与近十年气候；不填也能用，温度先手调。
          </p>
          <LocationPicker
            onPick={async (place) => {
              setPicked(place);
            }}
            pickedLabel={
              picked ? `${picked.name} · ${picked.display_name}` : null
            }
          />
        </section>

        <section className="setup-section">
          <h2>身材</h2>
          <p className="section-note">
            九项都可以空着。肩宽、胸围、臀围、臂长、身高已进入搭配；腰围、内长、颈围、体重先存着。
          </p>
          <BodyFields
            values={form.values}
            sources={form.sources}
            onChange={updateValue}
            onSourceChange={updateSource}
          />
        </section>
      </main>

      <div className="setup-actions">
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="setup-action-row">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleSkip}
            disabled={saving}
          >
            跳过
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleFinish}
            disabled={saving}
          >
            {saving ? "保存中…" : "完成"}
          </button>
        </div>
        <p className="save-hint">跳过后不会再自动进入这里；随时能在「我的」补。</p>
      </div>
    </>
  );
}
