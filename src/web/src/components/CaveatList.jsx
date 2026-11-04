const CODE_LABELS = {
  relaxed: "放宽",
  negative_soft: "扣分",
  context: "上下文",
};

export function CaveatList({ caveats }) {
  if (!caveats?.length) return null;
  return (
    <ul className="caveat-list" aria-label="注意事项">
      {caveats.map((caveat, index) => (
        <li
          className={`caveat${caveat.severity === "warn" ? " is-warn" : ""}`}
          key={`${caveat.code}-${caveat.rule_id ?? index}`}
        >
          <span className={`caveat-tag tag-${caveat.code}`}>
            {CODE_LABELS[caveat.code] ?? caveat.code}
          </span>
          <span>{caveat.text}</span>
          {caveat.rule_id && <code>{caveat.rule_id}</code>}
        </li>
      ))}
    </ul>
  );
}
