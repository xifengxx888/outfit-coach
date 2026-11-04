import { ContextBar } from "../components/ContextBar.jsx";
import { OutfitResults } from "../components/OutfitResults.jsx";
import { PAGE_SIZE, useOutfitBoard } from "../hooks/useOutfitBoard.js";
import { useWeather } from "../hooks/useWeather.js";
import {
  contextNote,
  hasNoLocation,
  weatherRain,
  weatherTemp,
} from "../lib/weather.js";
import { OCCASIONS } from "../constants.js";

export function OutfitsPage({ onGaps, onOpenItem, onSettings }) {
  const weatherState = useWeather();
  const weather = weatherState.weather;
  const board = useOutfitBoard({
    weatherTemp: weatherTemp(weather),
    weatherReady: weatherState.ready,
    isRainy: weatherRain(weather),
  });

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">A 视图 · 平铺</p>
          <h1>今天能搭什么</h1>
        </div>
        {board.data && (
          <div className="header-actions">
            <span className="wardrobe-count">{board.data.item_count} 件</span>
            <button type="button" className="ghost-link" onClick={onGaps}>
              缺口
            </button>
          </div>
        )}
      </header>

      <div className="top">
        <ContextBar
          occasions={OCCASIONS}
          occasion={board.occasion}
          onOccasion={board.handleOccasion}
          feelsLike={board.feelsLike}
          onStepTemp={board.stepTemp}
          onShuffle={board.canShuffle ? board.handleShuffle : undefined}
          shuffleDisabled={board.loading}
          weatherNote={contextNote(weather)}
          isManual={board.isManual}
          onResetTemp={board.resetTemp}
          needsLocation={hasNoLocation(weather)}
          onSettings={onSettings}
        />
      </div>

      <main>
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
          onShuffle={board.handleShuffle}
          onMore={board.more}
          onGaps={onGaps}
          onOpenItem={onOpenItem}
        />
      </main>
    </>
  );
}
