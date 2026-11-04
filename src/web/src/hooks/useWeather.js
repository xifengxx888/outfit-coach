import { useCallback, useEffect, useState } from "react";
import { fetchWeather } from "../api.js";

const CACHE_TTL = 5 * 60 * 1000;
const TIMEOUT = 2500;

// 模块级缓存：同一次打开里，组合 / 今日 / 锚定只取一次天气。
let cached = null; // { at, weather }
let inflight = null;

/** 地点或默认地点变了之后调用；下次挂载会重新取。 */
export function invalidateWeather() {
  cached = null;
  inflight = null;
}

function loadWeather() {
  if (cached && Date.now() - cached.at < CACHE_TTL) {
    return Promise.resolve(cached.weather);
  }
  if (inflight) return inflight;

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT);
  inflight = fetchWeather({ signal: controller.signal })
    .then((weather) => {
      cached = { at: Date.now(), weather };
      return weather;
    })
    .finally(() => {
      window.clearTimeout(timer);
      inflight = null;
    });
  return inflight;
}

/**
 * 天气只是默认值：取不到也必须放行搭配，由体感温度回退到 22°C。
 * `ready` 表示请求已落定（成功或失败），搭配请求要等它。
 */
export function useWeather() {
  const [weather, setWeather] = useState(() => cached?.weather ?? null);
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(() => Boolean(cached));
  const [token, setToken] = useState(0);

  useEffect(() => {
    let active = true;
    if (!cached) setReady(false);

    loadWeather()
      .then((value) => {
        if (!active) return;
        setWeather(value);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setError(err.name === "AbortError" ? "天气没取到" : err.message);
      })
      .finally(() => {
        if (active) setReady(true);
      });

    return () => {
      active = false;
    };
  }, [token]);

  const refresh = useCallback(() => {
    invalidateWeather();
    setReady(false);
    setToken((value) => value + 1);
  }, []);

  return { weather, loading: !ready, ready, error, refresh };
}
