import { useEffect, useState } from "react";
import { fetchItem, updateItem } from "../api.js";
import { BackLink } from "../components/BackLink.jsx";
import { EmptyState } from "../components/EmptyState.jsx";
import { AttributeFields } from "../components/add/AttributeFields.jsx";
import { PhotoPicker } from "../components/add/PhotoPicker.jsx";
import { SaveBar } from "../components/add/SaveBar.jsx";
import { SizeFields } from "../components/add/SizeFields.jsx";
import {
  applyCategoryChange,
  buildItemPayload,
  formFromItem,
  missingDims,
  missingRequired,
} from "../lib/itemForm.js";
import { preparePhoto } from "../lib/photo.js";
import { MAX_PHOTOS } from "../lib/wardrobe.js";

export function EditPage({ itemId, onBack, onSaved }) {
  const [item, setItem] = useState(null);
  const [form, setForm] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);

    fetchItem(itemId, { signal: controller.signal })
      .then((payload) => {
        if (!active) return;
        setItem(payload);
        setForm(formFromItem(payload));
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
    if (item) document.title = `编辑 ${item.name} · 个人穿搭助手`;
  }, [item]);

  if (!item || !form) {
    return (
      <>
        <header className="app-header">
          <div>
            <p className="eyebrow">编辑单品</p>
            <h1>{loadError?.status === 404 ? "没找到" : "读单品"}</h1>
          </div>
          <BackLink onBack={onBack} label="详情" />
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

  if (item.status === "archived") {
    return (
      <>
        <header className="app-header">
          <div>
            <p className="eyebrow">编辑单品</p>
            <h1>{item.name}</h1>
          </div>
          <BackLink onBack={onBack} label="详情" />
        </header>
        <main className="detail-main">
          <EmptyState
            title="已归档，不能直接编辑"
            description="先在详情页重新启用，再回来改属性。"
            actionLabel="查看详情"
            onAction={onBack}
          />
        </main>
      </>
    );
  }

  const setField = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));

  const existingPhotos =
    item.photos ?? (item.photo_path ? [item.photo_path] : []);
  const photoCount = existingPhotos.length + form.photos.length;
  const sampleSrc = form.photos[0] ?? existingPhotos[0] ?? "";

  const missing = missingRequired(form);
  const dimsMissing = missingDims(form);
  const requiredReady = missing.length === 0;
  const canConfirm = requiredReady && dimsMissing.length === 0;

  const hint = !requiredReady
    ? `还差：${missing.join("、")}`
    : !canConfirm
      ? `尺寸还差 ${dimsMissing.join("、")}。保存后会暂不参与搭配。`
      : photoCount === 0
        ? "没照片也能保存，衣库和组合卡会显示无图。"
        : null;

  const primaryLabel = !requiredReady
    ? "还有必填没填"
    : canConfirm
      ? item.status === "draft"
        ? "补完并参与搭配"
        : "保存修改"
      : "保存为草稿";

  const addPhotos = async (files) => {
    const room = MAX_PHOTOS - photoCount;
    if (room <= 0) {
      setPhotoError(`最多 ${MAX_PHOTOS} 张照片`);
      return;
    }
    setPhotoBusy(true);
    setPhotoError(
      files.length > room ? `最多 ${MAX_PHOTOS} 张照片，只加入前 ${room} 张` : null,
    );
    const prepared = [];
    try {
      for (const file of files.slice(0, room)) {
        prepared.push(await preparePhoto(file));
      }
    } catch (err) {
      setPhotoError(err.message);
    } finally {
      if (prepared.length) {
        setForm((current) => ({
          ...current,
          photos: [...current.photos, ...prepared].slice(0, room),
        }));
      }
      setPhotoBusy(false);
    }
  };

  const removePhoto = (index) => {
    setForm((current) => ({
      ...current,
      photos: current.photos.filter((_, position) => position !== index),
    }));
  };

  const submit = async () => {
    if (saving || !requiredReady) return;
    const status = canConfirm ? "confirmed" : "draft";
    setSaving(true);
    setSubmitError(null);
    try {
      onSaved(await updateItem(item.id, buildItemPayload(form, status)));
    } catch (err) {
      setSubmitError(err.message);
      setSaving(false);
    }
  };

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">编辑单品 · {item.status === "draft" ? "草稿" : "可搭配"}</p>
          <h1>{item.name}</h1>
        </div>
        <BackLink onBack={onBack} label="详情" />
      </header>

      <main className="add-main">
        <PhotoPicker
          photos={form.photos}
          existing={existingPhotos}
          busy={photoBusy}
          error={photoError}
          onAdd={addPhotos}
          onRemove={removePhoto}
        />

        <AttributeFields
          form={form}
          setField={setField}
          photoSrc={sampleSrc}
          onCategory={(category) =>
            setForm((current) => applyCategoryChange(current, category))
          }
        />
        <SizeFields form={form} setField={setField} />

        {submitError && (
          <div className="error-banner" role="alert">
            <span>{submitError}</span>
          </div>
        )}

        <SaveBar
          hint={hint}
          primaryLabel={primaryLabel}
          secondaryLabel={null}
          disabled={!requiredReady}
          saving={saving}
          onPrimary={submit}
          onSecondary={null}
        />
      </main>
    </>
  );
}
