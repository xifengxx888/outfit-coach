export function PrincipleLine({ line, detailed }) {
  return (
    <li className={`principle kind-${line.kind}`}>
      <div className="principle-title">
        <span>{line.title}</span>
        {line.kind === "baseline" && (
          <span className="kind-tag">结构底线</span>
        )}
        {detailed && (
          <span className={`grade-tag grade-${line.grade}`}>
            {line.grade} · {line.grade_label}
          </span>
        )}
      </div>
      <p className="principle-evidence">{line.evidence}</p>
      {detailed && (
        <div className="principle-detail">
          <p>
            <strong>为什么：</strong>
            {line.why}
          </p>
          <p>
            <strong>下次怎么看：</strong>
            {line.how_to_judge}
          </p>
          <p>
            <strong>依据：</strong>
            {line.grade_label} · 规则 <code>{line.rule_id}</code>
          </p>
          <p>
            <strong>来源：</strong>
            {line.source_url ? (
              <a
                className="source-link"
                href={line.source_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                {line.source}
              </a>
            ) : (
              line.source
            )}
          </p>
        </div>
      )}
    </li>
  );
}
