export async function fetchOutfits({
  occasion,
  feelsLike,
  isRainy = false,
  limit = 10,
  offset = 0,
  anchorId = null,
  signal,
}) {
  const params = new URLSearchParams({
    occasion,
    feels_like: String(feelsLike),
    is_rainy: isRainy ? "true" : "false",
    limit: String(limit),
    offset: String(offset),
  });
  if (anchorId !== null) params.set("anchor_id", String(anchorId));
  let response;
  try {
    response = await fetch(`/api/outfits?${params.toString()}`, { signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error("网络不通，没取到搭配");
  }
  if (!response.ok) {
    throw new Error(`请求失败（${response.status}）`);
  }
  return response.json();
}

export async function fetchToday({
  occasion,
  feelsLike,
  isRainy = false,
  offset = 0,
  signal,
}) {
  const params = new URLSearchParams({
    occasion,
    feels_like: String(feelsLike),
    is_rainy: isRainy ? "true" : "false",
    offset: String(offset),
  });
  let response;
  try {
    response = await fetch(`/api/today?${params.toString()}`, { signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error("网络不通，没取到今天的建议");
  }
  if (!response.ok) {
    throw new Error(`请求失败（${response.status}）`);
  }
  return response.json();
}

export async function fetchGaps({ signal } = {}) {
  let response;
  try {
    response = await fetch("/api/gaps", { signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error("网络不通，没取到缺口诊断");
  }
  if (!response.ok) {
    throw new Error(`请求失败（${response.status}）`);
  }
  return response.json();
}

export async function sendFeedback({
  outfitHash,
  signal,
  garmentIds,
  garmentId = null,
  hitRules = [],
}) {
  let response;
  try {
    response = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        outfit_hash: outfitHash,
        signal,
        garment_ids: garmentIds,
        garment_id: signal === "veto_item" ? garmentId : null,
        hit_rules: hitRules,
      }),
    });
  } catch {
    throw new Error("网络不通，没记上");
  }
  if (!response.ok) {
    let detail = `没记上（${response.status}）`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // 响应不是 JSON，保留状态码提示
    }
    throw new Error(detail);
  }
  return response.json();
}

export async function fetchItems({ status = "all", signal } = {}) {
  const params = new URLSearchParams({ status });
  let response;
  try {
    response = await fetch(`/api/items?${params.toString()}`, { signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error("网络不通，没取到衣库");
  }
  if (!response.ok) {
    throw new Error(`请求失败（${response.status}）`);
  }
  return response.json();
}

export async function createItem(payload) {
  let response;
  try {
    response = await fetch("/api/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("网络不通，没存上，请检查服务是否在运行");
  }
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchItem(id, { signal } = {}) {
  let response;
  try {
    response = await fetch(`/api/items/${id}`, { signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error("网络不通，没取到这件单品");
  }
  if (!response.ok) {
    const error = new Error(await readError(response));
    error.status = response.status; // 详情页据此区分「不存在」与普通失败
    throw error;
  }
  return response.json();
}

export async function updateItem(id, payload) {
  let response;
  try {
    response = await fetch(`/api/items/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("网络不通，没存上，请检查服务是否在运行");
  }
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchWeather({ refresh = false, signal } = {}) {
  return getJson(
    `/api/weather${refresh ? "?refresh=1" : ""}`,
    "网络不通，没取到天气",
    { signal }
  );
}

export async function fetchSetup({ signal } = {}) {
  return getJson("/api/setup", "网络不通，没读到设置状态", { signal });
}

export async function skipSetup() {
  return sendJson("/api/setup/skip", "POST", undefined, "网络不通，没跳过设置");
}

export async function fetchProfile({ signal } = {}) {
  return getJson("/api/profile", "网络不通，没取到身材资料", { signal });
}

export async function saveProfile(payload) {
  return sendJson("/api/profile", "PUT", payload, "网络不通，没存上身材资料");
}

export async function fetchGeocode(query, { signal } = {}) {
  const params = new URLSearchParams({ q: query });
  return getJson(`/api/geocode?${params.toString()}`, "网络不通，没搜到地点", {
    signal,
  });
}

export async function fetchLocations({ signal } = {}) {
  return getJson("/api/locations", "网络不通，没取到地点", { signal });
}

export async function addLocation(payload) {
  return sendJson("/api/locations", "POST", payload, "网络不通，没加上地点");
}

export async function setDefaultLocation(id) {
  return sendJson(
    `/api/locations/${id}/default`,
    "POST",
    undefined,
    "网络不通，没切换默认地点"
  );
}

export async function refreshClimate(id) {
  return sendJson(
    `/api/locations/${id}/climate`,
    "POST",
    undefined,
    "网络不通，没取到气候数据"
  );
}

export async function fetchStats({ signal } = {}) {
  return getJson("/api/stats", "网络不通，没取到统计", { signal });
}

export async function fetchTheory({ signal } = {}) {
  return getJson("/api/theory", "网络不通，没取到搭配原理", { signal });
}

export async function downloadExport() {
  let response;
  try {
    response = await fetch("/api/export");
  } catch {
    throw new Error("网络不通，没取到导出文件");
  }
  if (!response.ok) {
    throw new Error(await readError(response, "导出失败，请稍后重试"));
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return {
    blob: await response.blob(),
    filename: match?.[1] ?? "wardrobe-export.zip",
  };
}

async function getJson(path, fallbackMessage, { signal } = {}) {
  let response;
  try {
    response = await fetch(path, { signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error(fallbackMessage);
  }
  if (!response.ok) {
    const error = new Error(
      await readError(response, `请求失败（${response.status}）`)
    );
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function sendJson(path, method, payload, fallbackMessage) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers:
        payload === undefined ? undefined : { "Content-Type": "application/json" },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
  } catch {
    throw new Error(fallbackMessage);
  }
  if (!response.ok) {
    const error = new Error(await readError(response));
    error.status = response.status;
    throw error;
  }
  return response.json();
}

// FastAPI 的 detail 可能是字符串，也可能是校验错误数组；
// 校验数组里英文的 "Field required" 对用户没意义，换成一句中文。
async function readError(response, fallback) {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      for (const entry of detail) {
        const msg = typeof entry?.msg === "string" ? entry.msg : "";
        if (msg.startsWith("Value error, ")) return msg.slice("Value error, ".length);
        if (msg && !/^(Field required|Input should|String should)/.test(msg)) {
          return msg;
        }
      }
    }
  } catch {
    // 响应不是 JSON，退回状态码提示
  }
  return fallback ?? `没存上（${response.status}），请检查填的内容`;
}


