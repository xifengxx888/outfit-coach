const SLOT_LABELS = {
  base_top: "内搭",
  mid_layer: "中层",
  outer_layer: "外层",
  bottom: "下装",
  shoes: "鞋",
  accessory: "配饰",
};

const BAND_ORDER = ["cold", "cool", "warm", "hot"];
const WEIGHT_LABELS = { thin: "薄", medium: "中厚", thick: "厚" };

function Section({ title, aside, children }) {
  return (
    <section className="gap-section">
      <div className="gap-section-head">
        <h2>{title}</h2>
        {aside && <span>{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export function CoverageSection({ bands }) {
  const max = Math.max(10, ...bands.map((band) => band.valid_outfits));
  return (
    <Section title="温度覆盖" aside="每档 ≥10 套">
      <ul className="band-list">
        {bands.map((band) => {
          const low = band.valid_outfits < band.min;
          return (
            <li key={band.key} className={low ? "band-row is-low" : "band-row"}>
              <span className="band-label">{band.label}</span>
              <span className="band-track" aria-hidden="true">
                <span
                  className="band-fill"
                  style={{ width: `${(band.valid_outfits / max) * 100}%` }}
                />
                <span
                  className="band-tick"
                  style={{ left: `${(band.min / max) * 100}%` }}
                />
              </span>
              <span className="band-value">
                {band.valid_outfits} 套
                {low && <em>两周内会重复</em>}
              </span>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

export function BottleneckSection({ cards }) {
  return (
    <Section title="槽位瓶颈" aside={`${cards.length} / 2`}>
      {cards.length === 0 ? (
        <p className="gap-clear">没有件数或依赖度触发阈值的槽位。</p>
      ) : (
        <ul className="gap-cards">
          {cards.map((card) => (
            <li key={card.slots.join("-")} className="gap-card">
              <div className="gap-card-head">
                <strong>{card.labels.join(" / ")}</strong>
                <span>{card.item_count} 件</span>
              </div>
              <div className="gap-card-meta">
                <span>单件依赖 {Math.round(card.dependency * 100)}%</span>
                {card.driver_band && (
                  <span>最紧：{bandLabel(card.driver_band)}</span>
                )}
              </div>
              <p>{card.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function IsolatedSection({ items }) {
  return (
    <Section title="穿不进组合的单品" aside={`${items.length} / 3`}>
      {items.length === 0 ? (
        <p className="gap-clear">没有穿不进任何组合的单品。</p>
      ) : (
        <ul className="gap-cards">
          {items.map((item) => (
            <li key={item.item_id} className="gap-card">
              <div className="gap-card-head">
                <strong>{item.name}</strong>
                <span>{kindLabel(item.kind)}</span>
              </div>
              <p>{item.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function OccasionSection({ rows }) {
  return (
    <Section title="场合" aside="三个场合">
      <ul className="gap-cards">
        {rows.map((row) => {
          const gap = row.severity > 0;
          const [lo, hi] = row.target;
          return (
            <li
              key={row.occasion}
              className={gap ? "gap-card is-gap" : "gap-card"}
            >
              <div className="gap-card-head">
                <strong>{row.occasion}</strong>
                <span>
                  {gap ? "不达标" : "达标"} · {Math.round(row.fit_rate * 100)}%
                </span>
              </div>
              <div className="gap-card-meta">
                <span>最高正式度 {row.best_formality.toFixed(2)}</span>
                <span>
                  目标 {lo}–{hi}
                </span>
              </div>
              {gap && (
                <p>
                  卡住：
                  {row.blocked_slots.map((slot) => SLOT_LABELS[slot]).join(" / ") ||
                    "无"}
                  。至少需要正式度 ≥{lo} 的内搭 / 下装 / 鞋各一件。
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

export function FillSection({ fills, bands }) {
  const before = BAND_ORDER.map((key) => {
    const band = bands.find((row) => row.key === key);
    return band ? band.valid_outfits : 0;
  });
  return (
    <Section title="补齐模拟" aside="仅瓶颈槽位">
      {fills.length === 0 ? (
        <p className="gap-clear">瓶颈槽位补一件也解锁不了 5 套以上。</p>
      ) : (
        <ul className="gap-cards">
          {fills.map((fill) => {
            const after = BAND_ORDER.map(
              (key, index) => before[index] + (fill.unlock[key] ?? 0)
            );
            const signed = fill.total_unlock > 0 ? `+${fill.total_unlock}` : fill.total_unlock;
            return (
              <li key={fill.slot} className="gap-card fill-card">
                <div className="gap-card-head">
                  <strong>
                    若补一件{fill.name.replace("中性色", `中性色${WEIGHT_LABELS[fill.weight] ?? ""}`)}
                  </strong>
                  <span>合计 {signed} 套</span>
                </div>
                <p className="fill-numbers">
                  {before.join("/")} → {after.join("/")} 套
                  <small>（冷/凉/暖/热）</small>
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

function bandLabel(key) {
  return { cold: "冷天", cool: "凉天", warm: "暖天", hot: "热天" }[key] ?? key;
}

function kindLabel(kind) {
  return {
    hard: "完全配不进",
    edge: "出场率低",
    formality_island: "正式度孤岛",
  }[kind] ?? kind;
}
