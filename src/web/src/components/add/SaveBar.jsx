export function SaveBar({ hint, primaryLabel, secondaryLabel, disabled, saving, onPrimary, onSecondary }) {
  return (
    <div className="save-bar">
      {hint && <p className="save-hint">{hint}</p>}
      <div className="save-actions">
        {secondaryLabel && (
          <button
            type="button"
            className="btn-secondary"
            disabled={disabled || saving}
            onClick={onSecondary}
          >
            {secondaryLabel}
          </button>
        )}
        <button
          type="button"
          className="btn-primary"
          disabled={disabled || saving}
          onClick={onPrimary}
        >
          {saving ? "保存中…" : primaryLabel}
        </button>
      </div>
    </div>
  );
}
