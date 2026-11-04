export function StyleLine({ style, detailed }) {
  return (
    <div className="style-line">
      <span className="style-label">{style.label}</span>
      <span
        className="infer-badge"
        title="按正式度、廓形、色彩与层次推断，不参与评分"
      >
        推断
      </span>
      {detailed && (
        <>
          <p className="style-basis">依据：{style.basis}</p>
          <p className="style-caveat">{style.caveat}</p>
        </>
      )}
    </div>
  );
}
