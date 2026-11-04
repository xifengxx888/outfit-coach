import { useState } from "react";
import { fetchGeocode } from "../api.js";

/**
 * 地址搜索 + 候选确认。只负责「选中并交给父级」，
 * 保存地点还是留到 /setup 的「完成」或 /settings 的即时添加里做。
 */
export function LocationPicker({
  onPick,
  pickedLabel = null,
  buttonLabel = "使用此地点",
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [selected, setSelected] = useState(null);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const search = async (event) => {
    event.preventDefault();
    const value = query.trim();
    if (!value || searching) return;
    setSearching(true);
    setError(null);
    setResults(null);
    setSelected(null);
    try {
      const places = await fetchGeocode(value);
      setResults(places);
      if (places.length === 0) {
        setError("没搜到这个地名，换个写法试试；也可以先跳过");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSearching(false);
    }
  };

  const confirm = async () => {
    if (!selected || saving) return;
    setSaving(true);
    setError(null);
    try {
      await onPick(selected);
      setQuery("");
      setResults(null);
      setSelected(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="location-picker">
      <form className="search-row" onSubmit={search}>
        <input
          className="text-input"
          type="search"
          placeholder="输入城市，如 深圳"
          maxLength={60}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="地点名称"
        />
        <button
          type="submit"
          className="btn-secondary search-button"
          disabled={!query.trim() || searching}
        >
          {searching ? "搜索中" : "搜索"}
        </button>
      </form>

      {pickedLabel && <p className="picked-note">已选：{pickedLabel}</p>}

      {results && results.length > 0 && (
        <ul className="place-list">
          {results.map((place, index) => {
            const active = selected === place;
            return (
              <li key={`${place.name}-${place.lat}-${place.lon}-${index}`}>
                <button
                  type="button"
                  className={`place-row${active ? " is-on" : ""}`}
                  aria-pressed={active}
                  onClick={() => setSelected(place)}
                >
                  <span className="place-name">{place.name}</span>
                  <span className="place-sub">{place.display_name}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {selected && (
        <button
          type="button"
          className="btn-primary pick-confirm"
          onClick={confirm}
          disabled={saving}
        >
          {saving ? "保存中…" : buttonLabel}
        </button>
      )}

      {error && <p className="field-error">{error}</p>}
    </div>
  );
}
