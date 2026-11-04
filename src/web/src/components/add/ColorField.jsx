import { useState } from "react";
import { COLOR_SWATCHES } from "../../lib/wardrobe.js";
import { PhotoSampler } from "./PhotoSampler.jsx";

const HEX = /^#[0-9a-fA-F]{6}$/;

export function ColorField({ value, onChange, photoSrc = "" }) {
  const [sampling, setSampling] = useState(false);
  const invalid = Boolean(value) && !HEX.test(value);
  const valid = HEX.test(value) ? value.toUpperCase() : "#808080";

  return (
    <>
      <div className="color-row">
        <span
          className={`color-preview${value ? "" : " is-empty"}`}
          style={HEX.test(value) ? { background: value } : undefined}
          aria-hidden="true"
        >
          {value ? "" : "未选"}
        </span>
        <input
          className={`text-input mono${invalid ? " is-invalid" : ""}`}
          type="text"
          inputMode="text"
          maxLength={7}
          placeholder="#1D1B16"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-label="颜色 HEX"
        />
      </div>

      <div className="color-tools">
        <label className="color-native">
          <span
            className="color-native-dot"
            style={{ background: valid }}
            aria-hidden="true"
          />
          调色板
          <input
            type="color"
            value={valid}
            onChange={(event) => onChange(event.target.value.toUpperCase())}
            aria-label="打开系统调色板"
          />
        </label>
        <button
          type="button"
          className="color-pick"
          disabled={!photoSrc}
          title={photoSrc ? "从照片点选取色" : "先选一张照片"}
          onClick={() => setSampling(true)}
        >
          从照片取色
        </button>
      </div>

      <div className="swatches" aria-label="常用颜色">
        {COLOR_SWATCHES.map((hex) => (
          <button
            key={hex}
            type="button"
            className={`swatch${
              value.toLowerCase() === hex ? " is-on" : ""
            }`}
            style={{ background: hex }}
            title={hex}
            aria-label={`选 ${hex}`}
            onClick={() => onChange(hex.toUpperCase())}
          />
        ))}
      </div>

      {invalid && (
        <p className="field-error">颜色要写成 #RRGGBB，例如 #1D1B16</p>
      )}

      {sampling && (
        <PhotoSampler
          src={photoSrc}
          onPick={onChange}
          onClose={() => setSampling(false)}
        />
      )}
    </>
  );
}
