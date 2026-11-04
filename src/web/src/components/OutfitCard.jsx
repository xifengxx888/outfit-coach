import { useState } from "react";
import { ExplanationPanel } from "./ExplanationPanel.jsx";
import { FeedbackBar } from "./FeedbackBar.jsx";

export function OutfitCard({
  outfit,
  index,
  feedback,
  onFeedback,
  onOpenItem,
  variant = "list",
}) {
  const [vetoMode, setVetoMode] = useState(false);
  const isToday = variant === "today";
  const adopted = feedback?.adopted;
  const leaving = feedback?.leaving;

  const vetoPiece = (pieceId) => {
    setVetoMode(false);
    onFeedback(outfit, "veto_item", pieceId);
  };

  return (
    <article
      className={[
        "outfit-card",
        adopted ? "is-adopted" : "",
        leaving ? "is-leaving" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="card-head">
        <div className="score-block">
          <span className="score">{outfit.score.toFixed(1)}</span>
          <span className="score-unit">分</span>
        </div>
        <div className="badges">
          <span className="rank">{isToday ? "今日" : `#${index + 1}`}</span>
          {outfit.level > 0 && (
            <span className="badge-relax">放宽 {outfit.level} 档</span>
          )}
        </div>
      </div>

      <div className="flatlay" role="list" aria-label="这套的单品">
        {outfit.items.map((piece) => (
          <figure className="piece" key={piece.id} role="listitem">
            <div className="piece-frame">
              {onOpenItem ? (
                <button
                  type="button"
                  className="piece-open"
                  onClick={() => onOpenItem(piece.id)}
                  aria-label={`查看${piece.name}`}
                >
                  {piece.photo_path ? (
                    <img
                      src={`/${piece.photo_path}`}
                      alt={piece.name}
                      loading="lazy"
                    />
                  ) : (
                    <span className="no-photo">无图</span>
                  )}
                </button>
              ) : piece.photo_path ? (
                <img
                  src={`/${piece.photo_path}`}
                  alt={piece.name}
                  loading="lazy"
                />
              ) : (
                <span className="no-photo">无图</span>
              )}
              {vetoMode && (
                <button
                  type="button"
                  className="piece-veto"
                  onClick={() => vetoPiece(piece.id)}
                  aria-label={`划掉${piece.name}`}
                  title={`划掉${piece.name}`}
                >
                  −
                </button>
              )}
            </div>
            <figcaption>
              <span className="slot">{piece.slot_label}</span>
              <span className="piece-name" title={piece.name}>
                {piece.name}
              </span>
              <span className="color-line">
                <i style={{ background: piece.color_hex }} aria-hidden="true" />
                {piece.color_hex}
              </span>
            </figcaption>
          </figure>
        ))}
      </div>

      {outfit.explanation ? (
        <ExplanationPanel
          explanation={outfit.explanation}
          defaultOpen={isToday}
        />
      ) : (
        <p className="reasons-fallback">{outfit.reason}</p>
      )}

      <FeedbackBar
        feedback={feedback}
        vetoMode={vetoMode}
        showExtras={!isToday}
        onAdopt={() => onFeedback(outfit, "adopt")}
        onSwap={() => onFeedback(outfit, "swap")}
        onFavorite={() => onFeedback(outfit, "favorite")}
        onToggleVeto={() => setVetoMode((on) => !on)}
      />
    </article>
  );
}

