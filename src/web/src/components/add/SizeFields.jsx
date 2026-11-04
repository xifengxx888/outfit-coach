import { sizeFieldsOf, sizeKindOf } from "../../lib/wardrobe.js";

const TITLE = {
  top: "衣长、肩宽、胸宽必填 + 袖长选填",
  outer: "外套四项",
  bottom: "裤子四项",
  shoes: "鞋码一项",
};

const NOTE = {
  top: "全部平铺手量，单位 cm，保留 1 位小数。衣长、肩宽和胸宽决定上装合身判断，袖长可后补；缺衣长、肩宽或胸宽只能先存草稿。",
  outer: "全部平铺手量，单位 cm，保留 1 位小数。胸宽填平铺值，不乘 2。缺任何一项只能先存草稿。",
  bottom:
    "全部平铺手量，单位 cm，保留 1 位小数。腰围、臀围、裤口填平铺值，不乘 2。缺任何一项只能先存草稿。",
  shoes: "按欧码（EU）填鞋码，半码写 42.5。M1 只存档展示，不参与搭配判断。",
};

export function SizeFields({ form, setField }) {
  const fields = sizeFieldsOf(form.category);
  if (fields.length === 0) return null;

  const kind = sizeKindOf(form.category);
  const missing = fields
    .filter((field) => field.required !== false && !form[field.key])
    .map((field) => field.label);

  return (
    <section className="add-section" aria-labelledby="size-heading">
      <h2 id="size-heading" className="add-section-title">
        尺寸 <span>{TITLE[kind]}</span>
      </h2>
      <p className="section-note">{NOTE[kind]}</p>

      <div className="size-grid">
        {fields.map((field) => (
          <label className="size-cell" key={field.key}>
            <span className="size-label">
              {field.label}
              {field.required === false ? "（选填）" : ""}
            </span>
            <span className="size-input-wrap">
              <input
                className="text-input mono"
                type="number"
                inputMode="decimal"
                min={field.min}
                max={field.max}
                step={field.step}
                placeholder="—"
                value={form[field.key]}
                onChange={(event) => setField(field.key, event.target.value)}
              />
              <span className="size-unit">{field.unit}</span>
            </span>
            <span className="size-hint">{field.hint}</span>
          </label>
        ))}
      </div>

      {missing.length > 0 && (
        <p className="inline-warn">还差：{missing.join("、")}</p>
      )}
    </section>
  );
}
