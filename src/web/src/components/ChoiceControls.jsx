// 录入表单的通用控件。只用原生 button / select，键盘与无障碍直接可用。

export function Field({ label, required = false, hint, children }) {
  return (
    <div className="field">
      <div className="field-head">
        <span className="field-label">
          {label}
          {required && (
            <i className="req" aria-hidden="true">
              *
            </i>
          )}
        </span>
        {hint && <span className="field-hint">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => {
        const on = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            className={`seg${on ? " is-on" : ""}`}
            aria-pressed={on}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function ChoiceChips({ options, value, onChange, label, multiple = false }) {
  // options 可以是字符串，也可以是 { value, label }
  const valueOf = (option) => (typeof option === "string" ? option : option.value);
  const labelOf = (option) => (typeof option === "string" ? option : option.label);
  const isOn = (option) =>
    multiple ? value.includes(valueOf(option)) : value === valueOf(option);

  const toggle = (option) => {
    const picked = valueOf(option);
    if (!multiple) {
      onChange(picked);
      return;
    }
    onChange(
      value.includes(picked)
        ? value.filter((item) => item !== picked)
        : [...value, picked],
    );
  };

  return (
    <div className="chips-wrap" role="group" aria-label={label}>
      {options.map((option) => {
        const on = isOn(option);
        return (
          <button
            key={valueOf(option)}
            type="button"
            className={`pick-chip${on ? " is-on" : ""}`}
            aria-pressed={on}
            onClick={() => toggle(option)}
          >
            {labelOf(option)}
          </button>
        );
      })}
    </div>
  );
}

export function SelectField({
  options,
  value,
  onChange,
  label,
  extraOptions = ["不确定"],
}) {
  return (
    <select
      className="select"
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">未填</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
      {extraOptions.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}
