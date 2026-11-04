export function EmptyState({ title, description, actionLabel, onAction }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {description && <p>{description}</p>}
      {actionLabel && onAction && (
        <button type="button" className="empty-action" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
