import { barText, hasNoLocation } from "../lib/weather.js";

export function WeatherBar({ weather, ready, error, onSettings }) {
  if (!ready) {
    return (
      <div className="weather-bar is-muted" aria-live="polite">
        正在取天气…
      </div>
    );
  }

  const text = barText(weather) ?? (error ? "天气没取到 · 体感可手调" : null);
  if (!text) return null;

  const rainy = Boolean(weather?.is_rainy);

  return (
    <div className="weather-bar" aria-live="polite">
      <span className={`weather-dot${rainy ? " is-rain" : ""}`} aria-hidden="true" />
      <span className="weather-text">
        {text}
        {rainy ? " · 有降水" : ""}
      </span>
      {hasNoLocation(weather) && onSettings && (
        <button type="button" className="weather-link" onClick={onSettings}>
          去设置
        </button>
      )}
    </div>
  );
}
