import { formatSize, sizeFieldsOf } from "../lib/wardrobe.js";
import {
  fitText,
  formalityText,
  layersLabel,
  patternText,
  seasonText,
  weightText,
  wornLabel,
} from "../lib/itemView.js";

function AttrRow({ label, children }) {
  return (
    <div className="attr-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function ItemFacts({ item }) {
  const fields = sizeFieldsOf(item.category);

  return (
    <>
      <section className="detail-attrs" aria-labelledby="attrs-heading">
        <h2 id="attrs-heading">属性</h2>
        <dl>
          <AttrRow label="品类">{item.category}</AttrRow>
          <AttrRow label="层级">{layersLabel(item)}</AttrRow>
          <AttrRow label="正式度">{formalityText(item.formality)}</AttrRow>
          <AttrRow label="版型">{fitText(item.fit)}</AttrRow>
          <AttrRow label="图案">{patternText(item.pattern)}</AttrRow>
          <AttrRow label="厚度">
            {weightText(item.weight)} · {seasonText(item.weight)}
          </AttrRow>
          <AttrRow label="领型">{item.collar ?? "未填"}</AttrRow>
          <AttrRow label="材质">{item.material ?? "未填"}</AttrRow>
          <AttrRow label="颜色">
            <span className="color-line">
              <i style={{ background: item.color_hex }} aria-hidden="true" />
              {item.color_hex}
            </span>
          </AttrRow>
          <AttrRow label="最近穿着">{wornLabel(item.last_worn_at)}</AttrRow>
        </dl>
      </section>

      {fields.length > 0 && (
        <section className="detail-dims" aria-labelledby="dims-heading">
          <h2 id="dims-heading">尺寸</h2>
          <dl>
            {fields.map((field) => {
              const value = item[field.key];
              const optional = field.required === false;
              // 选填的空值不是缺数据，别标成待补
              if (value === null || value === undefined) {
                return (
                  <AttrRow key={field.key} label={field.label}>
                    {optional ? (
                      <span>未量（选填）</span>
                    ) : (
                      <span className="is-missing">未量</span>
                    )}
                  </AttrRow>
                );
              }
              return (
                <AttrRow key={field.key} label={field.label}>
                  {formatSize(field, value)}
                </AttrRow>
              );
            })}
          </dl>
        </section>
      )}
    </>
  );
}
