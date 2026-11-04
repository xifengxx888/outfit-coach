import { useEffect, useState } from "react";
import { fetchItem, updateItem } from "../api.js";
import { BackLink } from "../components/BackLink.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { ItemFacts } from "../components/ItemFacts.jsx";
import { formFromItem, missingDims } from "../lib/itemForm.js";
import { wornLabel } from "../lib/itemView.js";
import { photoSrc } from "../lib/photo.js";

export function ItemDetailPage({ itemId, onBack, onEdit, onAnchor, backLabel = "衣库" }) {
  const [item, setItem] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [activePhoto, setActivePhoto] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);

    fetchItem(itemId, { signal: controller.signal })
      .then((payload) => {
        if (!active) return;
        setItem(payload);
        setLoadError(null);
      })
      .catch((err) => {
        if (!active || err.name === "AbortError") return;
        setLoadError(err);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [itemId, retryToken]);

  useEffect(() => {
    if (item) document.title = `${item.name} · 个人穿搭助手`;
  }, [item]);

  if (!item) {
    return (
      <>
        <header className="app-header">
          <div>
            <p className="eyebrow">单品详情</p>
            <h1>{loadError?.status === 404 ? "没找到" : "读单品"}</h1>
          </div>
          <BackLink onBack={onBack} label={backLabel} />
        </header>
        <main className="detail-main">
          {loading && !loadError ? (
            <div className="skeletons" aria-label="正在读取单品">
              <div className="skeleton" />
            </div>
          ) : loadError?.status === 404 ? (
            <EmptyState
              title="这件单品不存在"
              description="可能已经不在衣库里。回衣库看看。"
              actionLabel="回衣库"
              onAction={onBack}
            />
          ) : (
            <EmptyState
              title="请求没有成功"
              description={loadError?.message ?? "没读到这件单品"}
              actionLabel="重试"
              onAction={() => setRetryToken((value) => value + 1)}
            />
          )}
        </main>
      </>
    );
  }

  const draft = item.status === "draft";
  const archived = item.status === "archived";
  const dimsToFill = missingDims(formFromItem(item));
  const badge = draft ? "草稿" : archived ? "已归档" : null;
  const photos = item.photos ?? (item.photo_path ? [item.photo_path] : []);
  const shown = Math.min(activePhoto, Math.max(photos.length - 1, 0));

  const archive = async () => {
    if (saving) return;
    setSaving(true);
    setActionError(null);
    try {
      await updateItem(item.id, { status: "archived" });
      onBack();
    } catch (err) {
      setActionError(err.message);
      setSaving(false);
    }
  };

  const restore = async () => {
    if (saving) return;
    setSaving(true);
    setActionError(null);
    try {
      const status = dimsToFill.length ? "draft" : "confirmed";
      setItem(await updateItem(item.id, { status }));
    } catch (err) {
      setActionError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">
            {item.category} · 最近穿着 {wornLabel(item.last_worn_at)}
          </p>
          <h1>{item.name}</h1>
        </div>
        <BackLink onBack={onBack} label={backLabel} />
      </header>

      <main className="detail-main">
        <div className="detail-photo">
          {photos.length > 0 ? (
            <img src={photoSrc(photos[shown])} alt={item.name} />
          ) : (
            <span className="detail-placeholder" aria-label="暂无照片">
              <strong>{item.category.slice(0, 1)}</strong>
              <span>暂无照片</span>
            </span>
          )}
        </div>

        {photos.length > 1 && (
          <div className="detail-thumbs" aria-label="照片列表">
            {photos.map((path, index) => (
              <button
                key={path}
                type="button"
                className={`detail-thumb${index === shown ? " is-on" : ""}`}
                aria-pressed={index === shown}
                aria-label={`查看第 ${index + 1} 张照片`}
                onClick={() => setActivePhoto(index)}
              >
                <img src={photoSrc(path)} alt="" />
                {index === 0 && <span>封面</span>}
              </button>
            ))}
          </div>
        )}

        {(badge || photos.length === 0) && (
          <div className="detail-badges">
            {badge && (
              <span className={`detail-badge${draft ? " is-draft" : " is-archived"}`}>
                {badge}
              </span>
            )}
            {photos.length === 0 && <span className="detail-badge">无照片</span>}
          </div>
        )}

        {draft && (
          <p className="detail-warn">
            {dimsToFill.length
              ? `尺寸还差 ${dimsToFill.join("、")}。补完并保存后才会参与搭配。`
              : "还是草稿。确认后才会参与搭配。"}
          </p>
        )}

        {archived && (
          <p className="restore-note">已归档，不参与搭配。照片不会被删除。</p>
        )}

        <ItemFacts item={item} />

        {actionError && (
          <div className="error-banner" role="alert">
            <span>{actionError}</span>
          </div>
        )}

        <div className="detail-actions">
          {archived ? (
            <button
              type="button"
              className="btn-primary"
              disabled={saving}
              onClick={restore}
            >
              {saving ? "正在启用…" : "重新启用"}
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn-primary"
                disabled={saving}
                onClick={() => (draft ? onEdit(item.id) : onAnchor(item.id))}
              >
                {draft ? "补完属性" : "用它搭配"}
              </button>
              {!draft && (
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={saving}
                  onClick={() => onEdit(item.id)}
                >
                  编辑
                </button>
              )}
            </>
          )}

          {!archived && (
            <button
              type="button"
              className="ghost-link is-danger"
              disabled={saving}
              onClick={() => {
                setConfirming(true);
                setActionError(null);
              }}
            >
              归档
            </button>
          )}
        </div>

        {confirming && (
          <div className="confirm-box" role="alertdialog" aria-label="确认归档">
            <p>归档后不参与搭配。照片不会删除。</p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn-secondary"
                disabled={saving}
                onClick={() => setConfirming(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn-primary is-danger"
                disabled={saving}
                onClick={archive}
              >
                {saving ? "归档中…" : "确认归档"}
              </button>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
