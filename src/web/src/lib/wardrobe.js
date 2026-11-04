// 录入与衣库共用的展示口径。枚举值必须与 src/rules/types.py 对齐；
// 这里只放中文文案与分组，不复制校验规则（最终校验在服务端）。

export const CATEGORY_GROUPS = [
  {
    key: "top",
    label: "上装",
    // 连体装占 base_top + bottom，归上装更接近它替代的那件衣服
    categories: ["T恤", "衬衫", "卫衣", "毛衣", "针织", "连体装"],
  },
  { key: "bottom", label: "下装", categories: ["裤子", "牛仔裤", "短裤"] },
  { key: "shoes", label: "鞋", categories: ["鞋"] },
  {
    key: "outer",
    label: "外套",
    categories: ["外套", "夹克", "西装", "西装套装"],
  },
  { key: "accessory", label: "配饰", categories: ["配饰"] },
];

export const FILTERS = [
  { key: "all", label: "全部" },
  ...CATEGORY_GROUPS.map(({ key, label }) => ({ key, label })),
];

export const ALL_CATEGORIES = CATEGORY_GROUPS.flatMap((g) => g.categories);

export const CATEGORY_BY_KEY = Object.fromEntries(
  CATEGORY_GROUPS.flatMap((g) => g.categories.map((c) => [c, g.key])),
);

// 槽位由品类决定的品类，与服务端 CATEGORY_SLOTS 一致
export const CATEGORY_SLOTS = {
  连体装: ["base_top", "bottom"],
  西装套装: ["outer_layer", "bottom"],
};

export const LAYER_OPTIONS = [
  { value: "inner", label: "内搭" },
  { value: "mid", label: "中层" },
  { value: "outer", label: "外层" },
  { value: "bottom", label: "下装" },
  { value: "shoes", label: "鞋" },
  { value: "accessory", label: "配饰" },
];

const DEFAULT_LAYERS = {
  T恤: ["inner"],
  衬衫: ["inner"],
  卫衣: ["inner"],
  毛衣: ["inner"],
  针织: ["inner"],
  外套: ["outer"],
  夹克: ["outer"],
  西装: ["outer"],
  裤子: ["bottom"],
  牛仔裤: ["bottom"],
  短裤: ["bottom"],
  鞋: ["shoes"],
  配饰: ["accessory"],
};

export function defaultLayers(category) {
  if (!category || CATEGORY_SLOTS[category]) return [];
  return DEFAULT_LAYERS[category] ?? [];
}

export const FORMALITY_OPTIONS = [
  { value: 1, label: "运动" },
  { value: 2, label: "休闲" },
  { value: 3, label: "日常" },
  { value: 4, label: "商务休闲" },
  { value: 5, label: "正装" },
];

export const FIT_OPTIONS = [
  { value: "slim", label: "修身" },
  { value: "regular", label: "合身" },
  { value: "oversize", label: "宽松" },
];

export const PATTERN_OPTIONS = [
  { value: "solid", label: "纯色" },
  { value: "fine", label: "细纹" },
  { value: "bold", label: "大图案" },
];

export const WEIGHT_OPTIONS = [
  { value: "thin", label: "薄" },
  { value: "medium", label: "中" },
  { value: "thick", label: "厚" },
];

export const SEASON_BY_WEIGHT = {
  thin: "夏",
  medium: "春秋",
  thick: "冬",
};

export const MATERIAL_OPTIONS = [
  "棉",
  "羊毛",
  "针织",
  "牛仔",
  "皮革",
  "尼龙",
  "亚麻",
  "化纤",
  "麂皮",
  "帆布",
  "缎面",
  "橡胶",
  "防水涂层",
];

export const COLLAR_OPTIONS = ["圆领", "高领", "V领", "翻领", "连帽", "无领"];

// 人工取色用的常用色板；不预选，未选就是空
export const COLOR_SWATCHES = [
  "#1d1b16",
  "#4a4a45",
  "#9a958a",
  "#e8e4d8",
  "#f4f1ea",
  "#2f4156",
  "#3f5d6b",
  "#2f5d4a",
  "#6b7f4a",
  "#a9482e",
  "#7c2f2f",
  "#c98b4b",
  "#96600f",
  "#d9c7a7",
  "#5b3f6b",
  "#b0838f",
];

const OUTER_CATEGORIES = new Set(["外套", "夹克", "西装", "西装套装"]);
const BOTTOM_CATEGORIES = new Set(["裤子", "牛仔裤", "短裤"]);
const SHOE_CATEGORIES = new Set(["鞋"]);
// 衣长/肩宽/胸宽决定合身判断，袖长只判长袖
const TOP_CATEGORIES = new Set(["T恤", "衬衫", "卫衣", "毛衣", "针织"]);

// 含封面在内，一件最多 6 张；首张作封面
export const MAX_PHOTOS = 6;

const CM_FIELD = { unit: "cm", step: 0.1, min: 0, max: 300 };

// 全部平铺直量、不乘 2；胸围/臀围/腰围/裤口由服务端 ×2 得围度
export const SIZE_FIELDS = {
  outer: [
    {
      key: "length_cm",
      label: "衣长",
      hint: "后领中点到下摆",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "shoulder_cm",
      label: "肩宽",
      hint: "两肩缝之间",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "chest_width_cm",
      label: "胸宽",
      hint: "腋下单面平量，不乘 2",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "sleeve_cm",
      label: "袖长",
      hint: "肩缝到袖口",
      required: true,
      ...CM_FIELD,
    },
  ],
  top: [
    {
      key: "length_cm",
      label: "衣长",
      hint: "后领中点到下摆",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "shoulder_cm",
      label: "肩宽",
      hint: "两肩缝之间",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "chest_width_cm",
      label: "胸宽",
      hint: "腋下单面平量，不乘 2",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "sleeve_cm",
      label: "袖长",
      hint: "肩缝到袖口，短袖不量",
      required: false,
      ...CM_FIELD,
    },
  ],
  bottom: [
    {
      key: "length_cm",
      label: "裤长",
      hint: "腰头到裤脚",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "waist_cm",
      label: "平铺腰围",
      hint: "腰头平量，不乘 2",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "hip_cm",
      label: "平铺臀围",
      hint: "最宽处平量，不乘 2",
      required: true,
      ...CM_FIELD,
    },
    {
      key: "leg_opening_cm",
      label: "裤口宽",
      hint: "裤脚平量，不乘 2",
      required: true,
      ...CM_FIELD,
    },
  ],
  shoes: [
    {
      key: "shoe_size",
      label: "鞋码",
      hint: "欧码，例 42；半码写 42.5",
      required: true,
      unit: "码",
      step: 0.5,
      min: 30,
      max: 50,
    },
  ],
};

export function sizeKindOf(category) {
  if (TOP_CATEGORIES.has(category)) return "top";
  if (OUTER_CATEGORIES.has(category)) return "outer";
  if (BOTTOM_CATEGORIES.has(category)) return "bottom";
  if (SHOE_CATEGORIES.has(category)) return "shoes";
  return null;
}

export function sizeFieldsOf(category) {
  const kind = sizeKindOf(category);
  return kind ? SIZE_FIELDS[kind] : [];
}

// 缺了就打草稿的字段；袖长这类选填项不拦入库
export function requiredSizeFieldsOf(category) {
  return sizeFieldsOf(category).filter((f) => f.required !== false);
}

// 详情展示：cm 保留 1 位小数，鞋码去掉多余的 .0
export function formatSize(field, value) {
  if (value === null || value === undefined || value === "") return null;
  if (field.unit === "码") return `${Number(value)} ${field.unit}`;
  return `${Number(value).toFixed(1)} ${field.unit}`;
}

export const SORT_OPTIONS = [
  { value: "recent", label: "最近录入" },
  { value: "least_worn", label: "最久没穿" },
];
