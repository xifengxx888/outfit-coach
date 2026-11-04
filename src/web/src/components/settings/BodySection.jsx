import { useEffect, useState } from "react";
import { saveProfile } from "../../api.js";
import { bodyFormFromProfile, bodyPayload } from "../../lib/body.js";
import { BodyFields } from "../BodyFields.jsx";

export function BodySection({ profile, onSaved }) {
  const [form, setForm] = useState(() => bodyFormFromProfile(profile));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setForm(bodyFormFromProfile(profile));
  }, [profile]);

  const updateValue = (key, value) => {
    setSaved(false);
    setForm((prev) => ({
      ...prev,
      values: { ...prev.values, [key]: value },
    }));
  };

  const updateSource = (key, value) => {
    setSaved(false);
    setForm((prev) => ({
      ...prev,
      sources: { ...prev.sources, [key]: value },
    }));
  };

  const save = async () => {
    if (saving) return;
    let payload;
    try {
      payload = bodyPayload(form.values, form.sources);
    } catch (err) {
      setError(err.message);
      return;
    }
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const next = await saveProfile(payload);
      setSaved(true);
      onSaved?.(next);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="settings-section" aria-label="身材">
      <div className="settings-head">
        <h2>身材</h2>
        <button type="button" className="ghost-link" onClick={save} disabled={saving}>
          {saving ? "保存中…" : "保存身材"}
        </button>
      </div>
      <p className="section-note">
        空着不影响使用。肩宽、胸围、臀围、臂长、身高已进入搭配；腰围、内长、颈围、体重先存着。
      </p>
      <BodyFields
        values={form.values}
        sources={form.sources}
        onChange={updateValue}
        onSourceChange={updateSource}
      />
      {saved && <p className="inline-note">已保存</p>}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
