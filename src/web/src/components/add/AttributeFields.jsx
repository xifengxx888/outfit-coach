import { ChoiceChips, Field, Segmented, SelectField } from "../ChoiceControls.jsx";
import {
  ALL_CATEGORIES,
  CATEGORY_SLOTS,
  COLLAR_OPTIONS,
  FIT_OPTIONS,
  FORMALITY_OPTIONS,
  LAYER_OPTIONS,
  MATERIAL_OPTIONS,
  PATTERN_OPTIONS,
  SEASON_BY_WEIGHT,
  WEIGHT_OPTIONS,
} from "../../lib/wardrobe.js";
import { ColorField } from "./ColorField.jsx";

export function AttributeFields({ form, setField, onCategory, photoSrc = "" }) {
  const slotByCategory = Boolean(CATEGORY_SLOTS[form.category]);

  return (
    <section className="add-section" aria-labelledby="attr-heading">
      <h2 id="attr-heading" className="add-section-title">
        属性
      </h2>

      <Field label="名称" required>
        <input
          className="text-input"
          type="text"
          maxLength={60}
          placeholder="例：深蓝牛仔外套"
          value={form.name}
          onChange={(event) => setField("name", event.target.value)}
        />
      </Field>

      <Field label="品类" required>
        <ChoiceChips
          options={ALL_CATEGORIES}
          value={form.category}
          onChange={onCategory}
          label="品类"
        />
      </Field>

      {form.category && !slotByCategory && (
        <Field label="层级" required hint="可多选，表示能当其中任一层">
          <ChoiceChips
            options={LAYER_OPTIONS}
            value={form.layers}
            onChange={(value) => setField("layers", value)}
            label="层级"
            multiple
          />
        </Field>
      )}

      {slotByCategory && (
        <p className="inline-note">
          {form.category}的槽位由品类决定，不用选层级。
        </p>
      )}

      <Field label="正式度" required>
        <Segmented
          options={FORMALITY_OPTIONS}
          value={form.formality}
          onChange={(value) => setField("formality", value)}
          label="正式度"
        />
      </Field>

      <Field label="版型" required>
        <Segmented
          options={FIT_OPTIONS}
          value={form.fit}
          onChange={(value) => setField("fit", value)}
          label="版型"
        />
      </Field>

      <Field
        label="颜色"
        required
        hint="16 色预设、系统调色板，或从照片点选"
      >
        <ColorField
          value={form.color_hex}
          onChange={(hex) => setField("color_hex", hex)}
          photoSrc={photoSrc}
        />
      </Field>

      <Field label="图案" required>
        <Segmented
          options={PATTERN_OPTIONS}
          value={form.pattern}
          onChange={(value) => setField("pattern", value)}
          label="图案"
        />
      </Field>

      <Field
        label="厚度"
        required
        hint={form.weight ? `季节：${SEASON_BY_WEIGHT[form.weight]}` : undefined}
      >
        <Segmented
          options={WEIGHT_OPTIONS}
          value={form.weight}
          onChange={(value) => setField("weight", value)}
          label="厚度"
        />
      </Field>

      <Field label="领型" hint="不适用 / 不确定会存为空">
        <SelectField
          options={COLLAR_OPTIONS}
          value={form.collar}
          onChange={(value) => setField("collar", value)}
          label="领型"
          extraOptions={["不适用", "不确定"]}
        />
      </Field>

      <Field label="材质" hint="不确定会存为空，相关规则跳过">
        <SelectField
          options={MATERIAL_OPTIONS}
          value={form.material}
          onChange={(value) => setField("material", value)}
          label="材质"
        />
      </Field>
    </section>
  );
}
