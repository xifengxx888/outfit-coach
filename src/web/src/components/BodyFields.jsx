import { BODY_FIELDS, BODY_SOURCES } from "../lib/body.js";

export function BodyFields({ values, sources, onChange, onSourceChange }) {
  return (
    <div className="body-fields">
      {BODY_FIELDS.map((field) => (
        <div className="body-row" key={field.key}>
          <label className="body-label" htmlFor={`body-${field.key}`}>
            {field.label}
          </label>
          <span className="body-input">
            <input
              id={`body-${field.key}`}
              className="text-input"
              type="number"
              inputMode="numeric"
              step="1"
              min={field.min}
              max={field.max}
              placeholder="—"
              value={values[field.key] ?? ""}
              onChange={(event) => onChange(field.key, event.target.value)}
            />
            <span className="body-unit">{field.unit}</span>
          </span>
          <select
            className="body-source"
            aria-label={`${field.label}来源`}
            value={sources[field.key] ?? "estimated"}
            onChange={(event) => onSourceChange(field.key, event.target.value)}
          >
            {BODY_SOURCES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}
