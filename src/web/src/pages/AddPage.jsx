import { useState } from "react";
import { createItem } from "../api.js";
import { preparePhoto } from "../lib/photo.js";
import {
  applyCategoryChange,
  blankForm,
  buildItemPayload,
  missingDims,
  missingRequired,
} from "../lib/itemForm.js";
import { AttributeFields } from "../components/add/AttributeFields.jsx";
import { BackLink } from "../components/BackLink.jsx";
import { PhotoPicker } from "../components/add/PhotoPicker.jsx";
import { SaveBar } from "../components/add/SaveBar.jsx";
import { SizeFields } from "../components/add/SizeFields.jsx";
import { MAX_PHOTOS } from "../lib/wardrobe.js";

export function AddPage({ onCloset, onBack }) {
  const [form, setForm] = useState(blankForm);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState(null);
  const [created, setCreated] = useState(null);

  const setField = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));

  const onCategory = (category) => {
    setForm((current) => applyCategoryChange(current, category));
  };

  const addPhotos = async (files) => {
    const room = MAX_PHOTOS - form.photos.length;
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
          photos: [...current.photos, ...prepared].slice(0, MAX_PHOTOS),
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

  const missing = missingRequired(form);
  const dimsMissing = missingDims(form);

  const requiredReady = missing.length === 0;
  const canConfirm = requiredReady && dimsMissing.length === 0;
  const canDraft = requiredReady;

  const hint = !requiredReady
    ? `还差：${missing.join("、")}`
    : !canConfirm
      ? `尺寸还差 ${dimsMissing.join("、")}，只能先存草稿（暂不参与搭配）。`
      : form.photos.length
        ? null
        : "没照片也能入库，衣库里会显示无图。";

  const primaryLabel = !requiredReady
    ? "还有必填没填"
    : canConfirm
      ? form.photos.length
        ? "保存并入库"
        : "无图入库"
      : "保存为草稿";

  const submit = async (status) => {
    if (saving) return;
    if (status !== "draft" && !canConfirm) return;
    if (!canDraft) return;

    const payload = buildItemPayload(form, status);

    setSaving(true);
    setSubmitError(null);
    try {
      setCreated(await createItem(payload));
      window.scrollTo(0, 0);
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const restart = () => {
    setForm(blankForm());
    setCreated(null);
    setSubmitError(null);
    setPhotoError(null);
    window.scrollTo(0, 0);
  };

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">录入 · 约 30 秒</p>
          <h1>{created ? (created.status === "confirmed" ? "已入库" : "已存草稿") : "加一件"}</h1>
        </div>
        <BackLink onBack={onBack} label="衣库" />
      </header>

      {created ? (
        <main className="add-success">
          <div className={`success-mark ${created.status}`} aria-hidden="true">
            {created.status === "confirmed" ? "✓" : "…"}
          </div>
          <h2>{created.name}</h2>
          <p>
            {created.status === "confirmed"
              ? "已确认，会参与搭配求解。"
              : "属性齐了，但尺寸还没量全。暂不参与搭配，也不会出现在组合里。"}
          </p>
          <div className="success-actions">
            <button type="button" className="btn-secondary" onClick={restart}>
              继续录入
            </button>
            <button type="button" className="btn-primary" onClick={onCloset}>
              查看衣库
            </button>
          </div>
        </main>
      ) : (
        <main className="add-main">
          <PhotoPicker
            photos={form.photos}
            busy={photoBusy}
            error={photoError}
            onAdd={addPhotos}
            onRemove={removePhoto}
          />
          <AttributeFields
            form={form}
            setField={setField}
            onCategory={onCategory}
            photoSrc={form.photos[0] ?? ""}
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
            secondaryLabel={canConfirm ? "存草稿" : null}
            disabled={!canDraft}
            saving={saving}
            onPrimary={() => submit(canConfirm ? "confirmed" : "draft")}
            onSecondary={() => submit("draft")}
          />
        </main>
      )}
    </>
  );
}
