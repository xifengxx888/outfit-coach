// 单品详情的展示口径：枚举值转中文、日期转人话。
import {
  CATEGORY_SLOTS,
  FIT_OPTIONS,
  FORMALITY_OPTIONS,
  LAYER_OPTIONS,
  PATTERN_OPTIONS,
  SEASON_BY_WEIGHT,
  WEIGHT_OPTIONS,
} from "./wardrobe.js";

const SLOT_LABELS = {
  outer_layer: "外层",
  mid_layer: "中层",
  base_top: "内搭",
  bottom: "下装",
  shoes: "鞋",
  accessory: "配饰",
};

export function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label ?? value ?? "未填";
}

export function formalityText(value) {
  return optionLabel(FORMALITY_OPTIONS, value);
}

export function fitText(value) {
  return optionLabel(FIT_OPTIONS, value);
}

export function patternText(value) {
  return optionLabel(PATTERN_OPTIONS, value);
}

export function weightText(value) {
  return optionLabel(WEIGHT_OPTIONS, value);
}

export function seasonText(value) {
  return SEASON_BY_WEIGHT[value] ?? "未填";
}

export function layersLabel(item) {
  const slots = CATEGORY_SLOTS[item.category];
  if (slots) return `由品类决定：${slots.map((slot) => SLOT_LABELS[slot]).join(" + ")}`;
  const labels = (item.layers ?? []).map((layer) => optionLabel(LAYER_OPTIONS, layer));
  return labels.length ? labels.join(" / ") : "未填";
}

export function slotText(item) {
  const slots = CATEGORY_SLOTS[item.category];
  if (slots) return slots.map((slot) => SLOT_LABELS[slot]).join(" + ");
  return layersLabel(item);
}

/** 日期只按日历天算，避免跨时区把「昨天」显示成「今天」。 */
export function wornLabel(iso) {
  if (!iso) return "还没记录";
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "还没记录";

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const worn = new Date(year, month - 1, day);
  const days = Math.round((today - worn) / 86400000);

  if (days <= 0) return "今天";
  if (days === 1) return "昨天";
  if (days < 30) return `${days} 天前`;
  return year === now.getFullYear()
    ? `${month} 月 ${day} 日`
    : `${year} 年 ${month} 月 ${day} 日`;
}
