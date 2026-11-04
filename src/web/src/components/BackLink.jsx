export function BackLink({ onBack, label }) {
  return (
    <button
      type="button"
      className="ghost-link"
      onClick={onBack}
      aria-label={`返回${label}`}
    >
      ‹ 返回{label}
    </button>
  );
}
