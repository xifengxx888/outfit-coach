// 录入与编辑共用的表单口径。这里只做本地预检与请求体组装，
// 最终校验仍在服务端 `ItemIn`——两边不复制规则，只对齐字段名。
import {
  CATEGORY_SLOTS,
  defaultLayers,
  requiredSizeFieldsOf,
  sizeKindOf,
} from "./wardrobe.js";

export const DIM_KEYS = [
  "length_cm",
  "shoulder_cm",
  "chest_width_cm",
  "sleeve_cm",
  "waist_cm",
  "hip_cm",
  "leg_opening_cm",
  "shoe_size",
];

export const HEX = /^#[0-9a-fA-F]{6}$/;

export function blankForm() {
  return {
    name: "",
    category: "",
    layers: [],
    formality: 3,
    color_hex: "",
    fit: "",
    pattern: "",
    weight: "",
    material: "",
    collar: "",
    length_cm: "",
    shoulder_cm: "",
    chest_width_cm: "",
    sleeve_cm: "",
    waist_cm: "",
    hip_cm: "",
    leg_opening_cm: "",
    shoe_size: "",
    photos: [],
  };
}

export function formFromItem(item) {
  const form = blankForm();
  for (const key of Object.keys(form)) {
    if (key === "photos") continue;
    const value = item[key];
    if (value !== null && value !== undefined) form[key] = value;
  }
  form.layers = [...(item.layers ?? [])];
  return form;
}

export function toNumber(value) {
  return value === "" || value === null || value === undefined
    ? null
    : Number(value);
}

export function missingRequired(form) {
  const missing = [];
  if (!form.name.trim()) missing.push("名称");
  if (!form.category) missing.push("品类");
  if (
    form.category &&
    !CATEGORY_SLOTS[form.category] &&
    form.layers.length === 0
  ) {
    missing.push("层级");
  }
  if (!form.color_hex || !HEX.test(form.color_hex)) missing.push("颜色");
  if (!form.fit) missing.push("版型");
  if (!form.pattern) missing.push("图案");
  if (!form.weight) missing.push("厚度");
  return missing;
}

// 只算必填尺寸：上装的袖长是选填，缺了也能入库
export function missingDims(form) {
  return requiredSizeFieldsOf(form.category)
    .filter((field) => !form[field.key])
    .map((field) => field.label);
}

/** 换品类：同一量法保留尺寸；外套换裤子时「衣长」不是一回事，必须清空。 */
export function applyCategoryChange(form, category) {
  const sameKind = sizeKindOf(form.category) === sizeKindOf(category);
  const next = {
    ...form,
    category,
    layers: defaultLayers(category),
  };
  if (!sameKind) {
    for (const key of DIM_KEYS) next[key] = "";
  }
  return next;
}

export function buildItemPayload(form, status) {
  const payload = {
    name: form.name.trim(),
    category: form.category,
    layers: CATEGORY_SLOTS[form.category] ? [] : form.layers,
    formality: Number(form.formality),
    color_hex: form.color_hex.toUpperCase(),
    fit: form.fit,
    pattern: form.pattern,
    weight: form.weight,
    material: form.material || null,
    collar: form.collar || null,
    status,
  };
  for (const key of DIM_KEYS) payload[key] = toNumber(form[key]);
  if (form.photos.length) payload.photos_data = form.photos;
  return payload;
}
