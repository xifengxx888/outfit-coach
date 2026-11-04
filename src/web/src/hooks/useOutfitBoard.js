import { useEffect, useRef, useState } from "react";
import { fetchOutfits, sendFeedback } from "../api.js";
import { MAX_TEMP, MIN_TEMP } from "../constants.js";

export const PAGE_SIZE = 5;
export const MAX_SHOWN = 10;

/**
 * 组合列表的共享状态机：组合页与锚定页必须走同一套请求、排序与反馈，
 * 否则两个入口会对同一批规则给出不同答案。
 *
 * 体感温度优先级：手动值 > 天气值 > 22°C。天气没落定前不发请求。
 */
export function useOutfitBoard({
  anchorId = null,
  onAdopt,
  weatherTemp = null,
  weatherReady = true,
  isRainy = false,
} = {}) {
  const [occasion, setOccasion] = useState("日常");
  const [manualTemp, setManualTemp] = useState(null);
  const effectiveTemp = manualTemp ?? weatherTemp ?? 22;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  const [batchOffset, setBatchOffset] = useState(0);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [feedback, setFeedback] = useState({});
  const [hidden, setHidden] = useState(() => new Set());
  const queryRef = useRef(0);
  // 换一批的 ignore 先攒着，等新一批真的取回来再记：
  // 请求失败时旧卡片还在屏幕上，不能把它们记成「没选」
  const shuffleRef = useRef(null);
  const adoptRef = useRef(onAdopt);
  adoptRef.current = onAdopt;

  useEffect(() => {
    if (!weatherReady) return undefined;
    const controller = new AbortController();
    let active = true;
    queryRef.current += 1;
    setLoading(true);

    fetchOutfits({
      occasion,
      feelsLike: effectiveTemp,
      isRainy,
      limit: MAX_SHOWN,
      offset: batchOffset,
      anchorId,
      signal: controller.signal,
    })
      .then((payload) => {
        if (!active) return;
        const ignored = shuffleRef.current;
        shuffleRef.current = null;
        setData(payload);
        setVisibleCount(PAGE_SIZE);
        setFeedback({});
        setHidden(new Set());
        setError(null);
        ignored?.forEach((entry) => {
          sendFeedback({ ...entry, signal: "ignore" }).catch(() => {
            // ignore 是弱信号，采集失败不值得打扰用户
          });
        });
      })
      .catch((err) => {
        if (!active || err.name === "AbortError") return;
        setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [
    occasion,
    effectiveTemp,
    isRainy,
    batchOffset,
    retryToken,
    anchorId,
    weatherReady,
  ]);

  const handleOccasion = (value) => {
    if (value === occasion) return;
    setOccasion(value);
    setBatchOffset(0); // 换条件就从第一页重新排
  };

  const stepTemp = (delta) => {
    setManualTemp(
      Math.min(MAX_TEMP, Math.max(MIN_TEMP, effectiveTemp + delta))
    );
    setBatchOffset(0);
  };

  const resetTemp = () => {
    setManualTemp(null);
    setBatchOffset(0);
  };

  const updateFeedback = (hash, patch) => {
    setFeedback((prev) => ({
      ...prev,
      [hash]: {
        adopted: false,
        favorited: false,
        pending: false,
        error: null,
        ...prev[hash],
        ...patch,
      },
    }));
  };

  const handleFeedback = async (outfit, signal, garmentId = null) => {
    const hash = outfit.hash;
    const current = feedback[hash] ?? {};
    if (current.pending) return;
    if (signal === "adopt" && current.adopted) return;
    if (signal === "favorite" && current.favorited) return;

    const generation = queryRef.current;
    updateFeedback(hash, { pending: true, error: null });

    try {
      await sendFeedback({
        outfitHash: hash,
        signal,
        garmentIds: outfit.items.map((piece) => piece.id),
        garmentId,
        hitRules: [...outfit.thumbs_up, ...outfit.thumbs_down],
      });
      if (queryRef.current !== generation) return;

      if (signal === "adopt") {
        updateFeedback(hash, { pending: false, adopted: true });
        adoptRef.current?.(outfit);
      } else if (signal === "favorite") {
        updateFeedback(hash, { pending: false, favorited: true });
      } else {
        // 再换 / 划掉：卡片先滑走，再把下一套顶上来
        updateFeedback(hash, { pending: false, leaving: true });
        window.setTimeout(() => {
          if (queryRef.current !== generation) return;
          setHidden((prev) => new Set(prev).add(hash));
        }, 180);
      }
    } catch (err) {
      if (queryRef.current !== generation) return;
      updateFeedback(hash, { pending: false, error: err.message });
    }
  };

  const outfits = data?.outfits ?? [];
  const visible = outfits.filter((outfit) => !hidden.has(outfit.hash));
  const shown = visible.slice(0, visibleCount);
  const canShuffle =
    Boolean(data?.has_more) && outfits.length > 0 && visible.length > 0;

  const handleShuffle = () => {
    if (loading) return;
    // 先记下当前展示过、但没做任何操作的卡片，等下一批取回来再补 ignore
    shuffleRef.current = shown
      .filter((outfit) => !feedback[outfit.hash])
      .map((outfit) => ({
        outfitHash: outfit.hash,
        garmentIds: outfit.items.map((piece) => piece.id),
        hitRules: [...outfit.thumbs_up, ...outfit.thumbs_down],
      }));
    // 整批换掉：按抓取量翻页，避免和未展开的第二排重复
    setBatchOffset((offset) => offset + MAX_SHOWN);
  };

  return {
    occasion,
    feelsLike: effectiveTemp,
    manualTemp,
    isManual: manualTemp !== null,
    data,
    error,
    loading,
    visibleCount,
    batchOffset,
    feedback,
    hidden,
    outfits,
    visible,
    shown,
    canShuffle,
    handleOccasion,
    stepTemp,
    resetTemp,
    handleFeedback,
    handleShuffle,
    retry: () => setRetryToken((value) => value + 1),
    more: () => setVisibleCount((count) => count + PAGE_SIZE),
  };
}
