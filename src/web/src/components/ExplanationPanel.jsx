import { useId, useState } from "react";
import { CaveatList } from "./CaveatList.jsx";
import { PrincipleLine } from "./PrincipleLine.jsx";
import { StyleLine } from "./StyleLine.jsx";

const COMPACT_LINES = 2;

export function ExplanationPanel({ explanation, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const { principles, caveats, data_gaps: gaps, style } = explanation;
  const shown = open ? principles : principles.slice(0, COMPACT_LINES);
  const noteCount = caveats.length + gaps.length;

  return (
    <section className="explanation" aria-label="搭配解释">
      <p className="explanation-headline">{explanation.headline}</p>
      {style && <StyleLine style={style} detailed={open} />}

      <ul className="principle-list">
        {shown.map((line) => (
          <PrincipleLine key={line.principle_id} line={line} detailed={open} />
        ))}
      </ul>

      <button
        type="button"
        className="explain-toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "收起" : `为什么${noteCount ? ` · ${noteCount} 条注意` : ""}`}
      </button>

      <div id={panelId}>
        {open && (
          <>
            <CaveatList caveats={caveats} />
            {gaps.length > 0 && (
              <div className="data-gaps">
                <p className="data-gaps-title">这套还没用上的数据</p>
                <ul>
                  {gaps.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
