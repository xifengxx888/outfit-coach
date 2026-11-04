import { useState } from "react";
import { addLocation, refreshClimate, setDefaultLocation } from "../../api.js";
import { LocationPicker } from "../LocationPicker.jsx";

export function LocationSection({ locations, onChanged }) {
  const [adding, setAdding] = useState(locations.length === 0);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);

  const handleAdd = async (place) => {
    setError(null);
    setNote(null);
    const created = await addLocation({
      name: place.name,
      lat: place.lat,
      lon: place.lon,
    });
    setAdding(false);
    setNote(
      created.climate_ready
        ? `已加上 ${created.name}，近十年气候就绪`
        : `已加上 ${created.name}，气候暂时没取到，可稍后重取`
    );
    await onChanged();
  };

  const handleDefault = async (id) => {
    setBusyId(id);
    setError(null);
    setNote(null);
    try {
      await setDefaultLocation(id);
      setNote("默认地点已切换，组合会按新地点取天气");
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleClimate = async (id) => {
    setBusyId(id);
    setError(null);
    setNote(null);
    try {
      const result = await refreshClimate(id);
      setNote(`气候已更新：${result.days} 天`);
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="settings-section" aria-label="地点">
      <div className="settings-head">
        <h2>地点</h2>
        {!adding && (
          <button
            type="button"
            className="ghost-link"
            onClick={() => setAdding(true)}
          >
            添加地点
          </button>
        )}
      </div>

      {locations.length === 0 ? (
        <p className="section-note">
          还没设地点。加一个，组合就会按当地天气给体感温度。
        </p>
      ) : (
        <ul className="loc-list">
          {locations.map((location) => (
            <li key={location.id} className="loc-row">
              <div className="loc-main">
                <span className="loc-name">{location.name}</span>
                {location.is_default ? (
                  <span className="loc-badge">默认</span>
                ) : (
                  <button
                    type="button"
                    className="ghost-link"
                    onClick={() => handleDefault(location.id)}
                    disabled={busyId === location.id}
                  >
                    设为默认
                  </button>
                )}
              </div>
              <div className="loc-sub">
                {location.climate_ready ? (
                  <span>近十年气候已就绪</span>
                ) : (
                  <button
                    type="button"
                    className="ghost-link"
                    onClick={() => handleClimate(location.id)}
                    disabled={busyId === location.id}
                  >
                    {busyId === location.id ? "重取中…" : "重取气候"}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {adding && (
        <div className="loc-add">
          <LocationPicker
            onPick={handleAdd}
            buttonLabel="添加这个地点"
          />
          {locations.length > 0 && (
            <button
              type="button"
              className="ghost-link"
              onClick={() => setAdding(false)}
            >
              收起
            </button>
          )}
        </div>
      )}

      {note && <p className="inline-note">{note}</p>}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
