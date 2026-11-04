import { useRef } from "react";
import { photoSrc } from "../../lib/photo.js";
import { MAX_PHOTOS } from "../../lib/wardrobe.js";

export function PhotoPicker({
  photos = [],
  existing = [],
  max = MAX_PHOTOS,
  busy,
  error,
  onAdd,
  onRemove,
}) {
  const cameraRef = useRef(null);
  const albumRef = useRef(null);
  const total = existing.length + photos.length;
  const full = total >= max;

  const handle = (event) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = ""; // 允许重新选同一张
    if (files.length) onAdd(files);
  };

  return (
    <section className="add-section" aria-labelledby="photo-heading">
      <h2 id="photo-heading" className="add-section-title">
        照片 <span>可选 · 最多 {max} 张</span>
      </h2>

      {total === 0 ? (
        <div className="photo-empty">
          <p>{busy ? "正在压缩照片…" : "拍一张平铺照，或者从相册里选。"}</p>
          <div className="photo-buttons">
            <button
              type="button"
              className="photo-btn"
              disabled={busy}
              onClick={() => cameraRef.current?.click()}
            >
              拍照
            </button>
            <button
              type="button"
              className="photo-btn"
              disabled={busy}
              onClick={() => albumRef.current?.click()}
            >
              从相册选
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="photo-grid" aria-label={`已选 ${total} 张，最多 ${max} 张`}>
            {existing.map((path, index) => (
              <figure className="photo-thumb is-locked" key={path}>
                <img src={photoSrc(path)} alt={`已存照片 ${index + 1}`} />
                {index === 0 && <figcaption>封面</figcaption>}
              </figure>
            ))}
            {photos.map((src, index) => {
              const position = existing.length + index + 1;
              return (
                <figure className="photo-thumb" key={`${position}-${src.slice(-24)}`}>
                  <img src={src} alt={`待保存照片 ${position}`} />
                  {position === 1 && <figcaption>封面</figcaption>}
                  <button
                    type="button"
                    className="photo-remove"
                    aria-label={`移除第 ${position} 张`}
                    onClick={() => onRemove(index)}
                  >
                    ×
                  </button>
                </figure>
              );
            })}
          </div>
          <p className="photo-count">
            {total}/{max}
            {existing.length > 0 && " · 已存照片不可删除"}
          </p>

          {full ? (
            <p className="fine">已到 {max} 张上限。想换图请先移除待保存的新图。</p>
          ) : (
            <div className="photo-buttons">
              <button
                type="button"
                className="photo-btn"
                disabled={busy}
                onClick={() => cameraRef.current?.click()}
              >
                {busy ? "正在压缩…" : "再拍一张"}
              </button>
              <button
                type="button"
                className="photo-btn"
                disabled={busy}
                onClick={() => albumRef.current?.click()}
              >
                从相册继续选
              </button>
            </div>
          )}
        </>
      )}

      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={handle}
      />
      <input
        ref={albumRef}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={handle}
      />

      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <p className="fine">
        第一张作为封面；照片只留在本机，不上传第三方。不拍也能入库。
      </p>
    </section>
  );
}
