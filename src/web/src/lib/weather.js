/** 天气的展示口径集中在这里，组合、今日、锚定三处不各写一套文案。 */

export function weatherTemp(weather) {
  return typeof weather?.feels_like === "number" ? weather.feels_like : null;
}

export function weatherRain(weather) {
  return Boolean(weather?.is_rainy);
}

export function hasNoLocation(weather) {
  return weather?.source === "none" && weather?.location === null;
}

/** ContextBar 右侧的一行来源说明。 */
export function contextNote(weather) {
  if (!weather) return null;
  if (weather.source === "none") {
    return weather.location ? "天气没取到 · 体感可手调" : "还没设置地点";
  }
  if (weather.source === "climate") {
    return weather.is_apparent === false
      ? "离线 · 近十年同期均温"
      : "离线 · 近十年同期体感";
  }
  const where = weather.location?.name;
  if (!where) return null;
  const condition = weather.condition ?? "天气未知";
  return weather.is_apparent === false
    ? `${where} · ${condition} · 气温`
    : `${where} · ${condition} · 天气体感`;
}

/** 温度展示：整数不带小数，非整数保留一位，和 ContextBar 口径一致。 */
export function formatTemp(value) {
  if (typeof value !== "number") return null;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** 今日页天气条的整句文案。 */
export function barText(weather) {
  if (!weather) return null;
  if (weather.source === "none") {
    return weather.location ? "天气没取到 · 体感可手调" : "还没设置地点";
  }
  const temp = formatTemp(weather.feels_like);
  const value = temp ? `${temp}°` : null;
  if (weather.source === "climate") {
    const metric = weather.is_apparent === false ? "同期均温" : "同期体感";
    return `离线 · 近十年${metric}${value ? ` ${value}` : ""}`;
  }
  const where = weather.location?.name ?? "";
  const condition = weather.condition ?? "天气未知";
  const metric = weather.is_apparent === false ? "气温" : "体感";
  return [where, condition, value ? `${metric} ${value}` : metric]
    .filter(Boolean)
    .join(" · ");
}
