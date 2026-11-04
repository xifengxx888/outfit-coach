const EMPTY = { adopted: false, favorited: false, pending: false, error: null };

export function FeedbackBar({
  feedback = EMPTY,
  vetoMode,
  showExtras = true,
  onAdopt,
  onSwap,
  onFavorite,
  onToggleVeto,
}) {
  const { adopted, favorited, pending, error } = feedback;
  const busy = pending;

  if (vetoMode) {
    return (
      <div className="feedback feedback-veto">
        <p className="veto-hint">点单品右上角的 −，把它从这套里划掉</p>
        <button type="button" className="fb-button" onClick={onToggleVeto}>
          取消
        </button>
      </div>
    );
  }

  return (
    <div className="feedback">
      <div className="feedback-actions" role="group" aria-label="这套怎么样">
        <button
          type="button"
          className={`fb-button fb-primary${adopted ? " is-done" : ""}`}
          onClick={onAdopt}
          disabled={busy || adopted}
          aria-pressed={adopted}
        >
          {adopted ? "已穿 · 今天" : "今天穿这套"}
        </button>
        <button
          type="button"
          className="fb-button"
          onClick={onSwap}
          disabled={busy || adopted}
        >
          再换
        </button>
        {showExtras && (
          <>
            <button
              type="button"
              className={`fb-button fb-icon${favorited ? " is-on" : ""}`}
              onClick={onFavorite}
              disabled={busy || favorited}
              aria-pressed={favorited}
              aria-label={favorited ? "已收藏" : "收藏这套"}
              title={favorited ? "已收藏" : "收藏"}
            >
              {favorited ? "♥" : "♡"}
            </button>
            <button
              type="button"
              className="fb-button"
              onClick={onToggleVeto}
              disabled={busy || adopted}
            >
              划掉一件
            </button>
          </>
        )}
      </div>
      {error && (
        <p className="feedback-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
