import { useState } from "react";
import { downloadExport } from "../../api.js";

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function DataSection({ stats }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const [error, setError] = useState(null);

  const exportZip = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const { blob, filename } = await downloadExport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNote(`已导出 ${filename}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="settings-section" aria-label="数据">
      <div className="settings-head">
        <h2>数据</h2>
        <button
          type="button"
          className="ghost-link"
          onClick={exportZip}
          disabled={busy}
        >
          {busy ? "导出中…" : "导出 ZIP"}
        </button>
      </div>

      {stats && (
        <dl className="stat-grid">
          <div>
            <dt>单品</dt>
            <dd>{stats.items.total} 件</dd>
          </div>
          <div>
            <dt>照片</dt>
            <dd>{stats.photos.count} 张</dd>
          </div>
          <div>
            <dt>数据库</dt>
            <dd>{formatBytes(stats.db_bytes)}</dd>
          </div>
          <div>
            <dt>照片占用</dt>
            <dd>{formatBytes(stats.photos.bytes)}</dd>
          </div>
        </dl>
      )}

      <p className="section-note">
        导出含数据库快照、照片清单（路径与校验和）和说明文件，不含照片文件本身。
      </p>
      {note && <p className="inline-note">{note}</p>}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
