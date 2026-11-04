export function ClosetCard({ item, onOpen }) {
  const draft = item.status === "draft";
  return (
    <button
      type="button"
      className={`closet-card${draft ? " is-draft" : ""}`}
      aria-label={`${item.name}，${item.category}${draft ? "，草稿" : ""}`}
      onClick={() => onOpen?.(item.id)}
    >
      <div className="closet-photo">
        {item.photo_path ? (
          <img src={`/${item.photo_path}`} alt="" loading="lazy" />
        ) : (
          <span className="closet-placeholder">
            <strong>{item.category.slice(0, 1)}</strong>
            <span>无图</span>
          </span>
        )}
        {item.status !== "confirmed" && (
          <span className={`status-dot ${item.status}`} aria-hidden="true" />
        )}
        {draft && <span className="draft-tag">草稿</span>}
      </div>

      <div className="closet-body">
        <p className="closet-name">{item.name}</p>
        <p className="closet-meta">
          <i style={{ background: item.color_hex }} aria-hidden="true" />
          {item.category}
        </p>
      </div>
    </button>
  );
}
