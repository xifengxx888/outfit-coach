/** 九项身材字段与来源的唯一定义，/setup 与 /settings 共用。 */

export const BODY_FIELDS = [
  { key: "height", label: "身高", unit: "cm", min: 100, max: 250 },
  { key: "weight", label: "体重", unit: "kg", min: 25, max: 250 },
  { key: "shoulder_width", label: "肩宽", unit: "cm", min: 25, max: 80 },
  { key: "chest", label: "胸围", unit: "cm", min: 50, max: 180 },
  { key: "waist", label: "腰围", unit: "cm", min: 40, max: 180 },
  { key: "hip", label: "臀围", unit: "cm", min: 50, max: 200 },
  { key: "neck", label: "颈围", unit: "cm", min: 20, max: 70 },
  { key: "inseam", label: "内长", unit: "cm", min: 30, max: 130 },
  { key: "arm_length", label: "臂长", unit: "cm", min: 30, max: 100 },
];

export const BODY_SOURCES = [
  { value: "body", label: "手量" },
  { value: "garment", label: "量衣" },
  { value: "estimated", label: "估算" },
];

export function emptyBodyForm() {
  return {
    values: Object.fromEntries(BODY_FIELDS.map((field) => [field.key, ""])),
    sources: Object.fromEntries(
      BODY_FIELDS.map((field) => [field.key, "estimated"])
    ),
  };
}

export function bodyFormFromProfile(profile) {
  const form = emptyBodyForm();
  if (!profile) return form;
  for (const field of BODY_FIELDS) {
    const value = profile.values?.[field.key];
    form.values[field.key] = value === null || value === undefined ? "" : String(value);
    form.sources[field.key] = profile.sources?.[field.key] ?? "estimated";
  }
  return form;
}

/** 空值不提交；有值才带对应来源。范围与后端 PROFILE_RANGES 一致。 */
export function bodyPayload(values, sources) {
  const payload = {};
  for (const field of BODY_FIELDS) {
    const raw = String(values[field.key] ?? "").trim();
    if (raw === "") continue;
    const number = Number(raw);
    if (!Number.isInteger(number) || number < field.min || number > field.max) {
      throw new Error(
        `${field.label}请填 ${field.min}–${field.max} 之间的整数`
      );
    }
    payload[field.key] = number;
    payload[`${field.key}_source`] = sources[field.key] || "estimated";
  }
  return payload;
}
