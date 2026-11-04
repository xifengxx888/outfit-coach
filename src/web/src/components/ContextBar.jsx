import { formatTemp } from "../lib/weather.js";

export function ContextBar({
  occasions,
  occasion,
  onOccasion,
  feelsLike,
  onStepTemp,
  onShuffle,
  shuffleDisabled = false,
  weatherNote = null,
  isManual = false,
  onResetTemp,
  needsLocation = false,
  onSettings,
}) {
  return (
    <div className="context">
      <div className="context-row">
        <div className="chips" role="group" aria-label="场合">
          {occasions.map((item) => (
            <button
              key={item}
              type="button"
              className={`chip${item === occasion ? " chip-active" : ""}`}
              aria-pressed={item === occasion}
              onClick={() => onOccasion(item)}
            >
              {item}
            </button>
          ))}
        </div>

        {onShuffle && (
          <button
            type="button"
            className="shuffle"
            onClick={onShuffle}
            disabled={shuffleDisabled}
          >
            换一批
          </button>
        )}
      </div>

      <div className="context-row context-row-temp">
        <div className="temp" role="group" aria-label="体感温度">
          <button
            type="button"
            className="temp-step"
            onClick={() => onStepTemp(-1)}
            aria-label="体感温度降低一度"
          >
            −
          </button>
          <span className="temp-value">
            {formatTemp(feelsLike)}
            <small>°C</small>
          </span>
          <button
            type="button"
            className="temp-step"
            onClick={() => onStepTemp(1)}
            aria-label="体感温度升高一度"
          >
            +
          </button>
        </div>
        <div className="context-weather">
          {isManual ? (
            <button
              type="button"
              className="weather-reset"
              onClick={onResetTemp}
            >
              已手动调整 · 恢复天气
            </button>
          ) : (
            weatherNote && <p className="context-hint">{weatherNote}</p>
          )}
          {needsLocation && onSettings && (
            <button type="button" className="weather-link" onClick={onSettings}>
              设置地点
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
