import { useEffect, useRef, useState } from "react";
import { averageHex } from "../../lib/sampleColor.js";

// 点按位置取 5×5 像素的平均色，抵消照片噪点
const RADIUS = 2;

export function PhotoSampler({ src, onPick, onClose }) {
  const canvasRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const [sample, setSample] = useState(null);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onLoad = (event) => {
    const img = event.currentTarget;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) throw new Error("no 2d context");
      ctx.drawImage(img, 0, 0);
      canvasRef.current = canvas;
      setReady(true);
      setError(null);
    } catch {
      setError("照片像素读不出来，请用调色板或手动填 HEX");
    }
  };

  const onTap = (event) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.round(
      ((event.clientX - rect.left) / rect.width) * canvas.width,
    );
    const y = Math.round(
      ((event.clientY - rect.top) / rect.height) * canvas.height,
    );
    const left = Math.max(0, x - RADIUS);
    const top = Math.max(0, y - RADIUS);
    const right = Math.min(canvas.width, x + RADIUS + 1);
    const bottom = Math.min(canvas.height, y + RADIUS + 1);
    try {
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      const hex = averageHex(
        ctx.getImageData(left, top, right - left, bottom - top),
      );
      if (hex) setSample(hex);
    } catch {
      setError("这张图不允许读取像素，请用调色板或手动填 HEX");
    }
  };

  return (
    <div
      className="sampler-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="从照片取色"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="sampler-panel">
        <header className="sampler-head">
          <div>
            <h2>从照片取色</h2>
            <p className="fine">点一下想取的位置，取周围 5×5 像素的平均色。</p>
          </div>
          <button type="button" className="ghost-link" onClick={onClose}>
            关闭
          </button>
        </header>

        {error ? (
          <p className="field-error" role="alert">
            {error}
          </p>
        ) : (
          <img
            className="sampler-image"
            src={src}
            alt="取色用照片"
            draggable={false}
            onLoad={onLoad}
            onClick={onTap}
          />
        )}

        <div className="sampler-foot">
          <div className="sampler-readout">
            <span
              className={`color-preview${sample ? "" : " is-empty"}`}
              style={sample ? { background: sample } : undefined}
              aria-hidden="true"
            >
              {sample ? "" : "未取"}
            </span>
            <span className="mono sampler-hex">{sample ?? "点照片上的颜色"}</span>
          </div>
          <div className="sampler-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              取消
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!sample}
              onClick={() => {
                if (sample) onPick(sample);
                onClose();
              }}
            >
              用这个颜色
            </button>
          </div>
        </div>
        {!ready && !error && <p className="fine">照片加载中…</p>}
      </div>
    </div>
  );
}
