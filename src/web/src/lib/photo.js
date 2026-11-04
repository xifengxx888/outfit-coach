// 照片在本地压缩后再上传。用 <img> 解码而不是 createImageBitmap：
// 浏览器会按 EXIF 方向渲染，画到 canvas 上方向才是正的。
const MAX_EDGE = 1600;
const JPEG_QUALITY = 0.85;
const MAX_FILE_BYTES = 40 * 1024 * 1024;

export function photoSrc(path) {
  if (!path) return "";
  return path.startsWith("data:") ? path : `/${path}`;
}

export function preparePhoto(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("没有选到照片"));
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      reject(new Error("这张照片太大，请先在相册里压缩再选"));
      return;
    }

    const url = URL.createObjectURL(file);
    const img = new Image();

    const fail = () => {
      URL.revokeObjectURL(url);
      reject(new Error("这张图读不出来，请在相册里导出为 JPG 再选"));
    };

    img.onload = () => {
      try {
        const scale = Math.min(
          1,
          MAX_EDGE / Math.max(img.naturalWidth, img.naturalHeight),
        );
        const width = Math.max(1, Math.round(img.naturalWidth * scale));
        const height = Math.max(1, Math.round(img.naturalHeight * scale));
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("浏览器不支持图片处理");
        // JPEG 没有透明通道，先铺白底，避免 PNG 的透明区变黑
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL("image/jpeg", JPEG_QUALITY));
      } catch (err) {
        reject(new Error(err.message || "照片处理失败，请换一张"));
      } finally {
        URL.revokeObjectURL(url);
      }
    };

    img.onerror = fail;
    img.src = url;
  });
}
