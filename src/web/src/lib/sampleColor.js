// 取色是纯计算：输入一块像素，输出大写的 #RRGGBB。
export function toHex(r, g, b) {
  return (
    "#" +
    [r, g, b]
      .map((value) =>
        Math.max(0, Math.min(255, Math.round(value)))
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
      .toUpperCase()
  );
}

/** 对一块 ImageData 求平均色；没有像素时返回 null。 */
export function averageHex(imageData) {
  const { data } = imageData;
  const pixels = Math.floor(data.length / 4);
  if (pixels === 0) return null;
  let r = 0;
  let g = 0;
  let b = 0;
  for (let i = 0; i < data.length; i += 4) {
    r += data[i];
    g += data[i + 1];
    b += data[i + 2];
  }
  return toHex(r / pixels, g / pixels, b / pixels);
}
