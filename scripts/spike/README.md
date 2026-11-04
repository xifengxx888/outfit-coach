# scripts/spike — M1 开工前一次性验证

这里的脚本**不进 `src/`**、不接数据库、不接前端、不走 CI。它们只做一件事：
在真实衣柜数据进来之前，把 `07` 的检查项跑成证据。**门槛通过后整体归档或删除。**

```bash
cd ~/claude/个人穿搭助手
```

## 文件

| 文件 | 用途 |
|---|---|
| `make_calibration_card.py` | 生成 A4 拍摄标定卡（ArUco + 100mm 尺 + 灰卡 + 6 色块） |
| `make_templates.py` | 生成 10 件属性模板（xlsx 带下拉 / csv 空白） |
| `items_demo.csv` | 14 件合成衣柜，验证常规求解路径 |
| `items_edge.csv` | 13 件合成衣柜，专用于触发低频规则 |
| `dryrun.py` | 槽位枚举 + 24 条规则 + 4 档放宽 + 去重 + 锚定 + 验收 |
| `calibration_card_a4.png/pdf` | 标定卡产物（300 DPI / A4） |
| `items_template.xlsx/csv` | 属性模板产物 |
| `dryrun_result.json` | 上次干跑完整结果（含每档新增与累计前 10） |
| `dryrun_edge_result.json` | 边界衣柜的干跑结果 |

## 1. 标定卡

```bash
uv run --python 3.12 --with opencv-contrib-python-headless --with pillow \
  scripts/spike/make_calibration_card.py
```

打印设置：**A4、100%（实际大小）、关闭「适合页面 / 缩放」**。
印完先量 100mm 校准尺和 ArUco 黑框外沿（应为 50.0mm，49.5–50.5mm 可接受）。
不对就重印，不要拿一张缩放过界的纸去拍照。

## 2. 属性模板

```bash
uv run --python 3.12 --with openpyxl scripts/spike/make_templates.py
```

- 主用 `items_template.xlsx`：三个工作表（填写 / 示例 / 填写说明），关键列有下拉。
- **填完直接保存 xlsx 就能跑，不用另存 CSV。** 需要 CSV 时再导出「CSV UTF-8」。
- 深蓝表头是必填，浅蓝是选填。干跑真正必需的只有 9 列：编号、名称、品类、层级、
  正式度、颜色HEX、版型、图案、厚度；材质与领型建议填（对应规则会生效），
  季节 / 照片文件名 / 备注这轮不用填。
- 尺寸：干跑只读「衣长」（外套 → R-PRP-04；三层上装 → R-LYR-02）。
  肩宽 / 胸宽 / 袖长 / 腰围本脚本不读，但 M1 建库要用，建议一次量全。
- 不会量、不会填：打开 `docs/08-量衣与填表教程.html`（离线单文件，含测量位置图、
  颜色取色器、字段速查与 10 件清单）。

## 3. 干跑

```bash
# 常规路径（合成数据，先验证脚本本身）
python3 scripts/spike/dryrun.py --items scripts/spike/items_demo.csv --feels-like 15

# 填完模板直接跑，不需要导出 CSV
python3 scripts/spike/dryrun.py --items scripts/spike/items_template.xlsx \
  --occasion 日常 --feels-like 22 --height 175

# 边界路径（降水 + 矮身高 + 低温）
python3 scripts/spike/dryrun.py --items scripts/spike/items_edge.csv \
  --feels-like 8 --rain --height 160 \
  --out scripts/spike/dryrun_edge_result.json

# 真实衣柜（已导出的 CSV）
python3 scripts/spike/dryrun.py --items scripts/spike/items.csv \
  --occasion 日常 --feels-like 15 --rain --height 175
```

参数：`--occasion 日常|旅游|见人`、`--feels-like`、`--rain`、`--height`、
`--anchors`（默认 5）、`--out`。

**CSV 只依赖 Python 标准库**；读 xlsx 需要 openpyxl（本机已装）。

### 输出怎么读

- **硬规则表**：`fail%` 是 strict 档下该条拦掉的候选比例。任何一条接近 100% 都要查。
- **软规则表**：`pass` 在软规则里表示「命中」——可能加分也可能扣分，看「平均分」正负；
  `skip` 表示数据不足，不参与评分（缺数据不算违规）。
- **各档结果**：`新增候选` = 本档才被放宽接纳的候选；`新增去重` 对它们单独去重；
  `累计候选 / 累计去重` = 放宽到该档时可见的总量（去重上限 N=10）。
- **每档前 10 套**：只列本档**新增**的组合，严格档不会和放宽档混排。
- **锚定测试**：只在「至少能进一套结果」的单品里抽样；配不出结果的单品单独列出，
  并给出主因。这是为了避免把「这件衣服在 15°C 不该穿」误判成「求解器坏了」。

### 验收口径（`07` 第 2 节）

| 检查 | 脚本字段 |
|---|---|
| 严格档 ≥1 套 | `checks.strict_ge_1` |
| 放宽到第 3 档去重 ≥10 套 | `checks.relaxed3_dedup_ge_10` |
| 可锚定池随机 5 件各 ≥3 套 | `checks.anchors_ge_3` |
| 没有硬规则 100% fail | `checks.no_rule_100pct_fail` |
| 求解 <200ms | `checks.under_200ms` |
| `reason` 可读 ≥80% | **人工判断**，脚本不代劳 |

## 4. spike 的实现口径（已回填 `02`）

下面这些原先只是干跑为了能跑而定的解释，**已全部写进 `02` / `06` / `07`**。
保留这张表是为了对账：`src/` 里的实现必须与本表一致；要改先改 `02`。

| 位置 | 当前 spike 口径 | 为什么 |
|---|---|---|
| `R-OCC-01` 检查范围 | 只看上装三层（base / mid / outer），不看裤子与鞋 | 否则 15°C 穿牛仔裤也会被判违规 |
| `R-OCC-03` 厚度映射 | thin=1 / medium=3 / thick=5，与 `target_warmth` 的 1–5.5 对齐 | `02` 只说「组合厚度均值」，没给映射 |
| `R-PRP-03` 宽窄对比 | `oversize` 对 `slim`（跨两级）；`regular` 与 `slim` 不算 | `02` 的原文是「上宽下窄 / 上窄下宽」 |
| `R-COL-01` 参与色 | 饱和度 ≥15 且非中性色，色系去重后 ≤3 | 低饱和色不应算作「主色」 |
| 藏青 / 卡其中性判定 | 藏青：195–245°、L≤38、S≤70；卡其：20–60°、S≤50、L 55–88 | `02` 只写「中性色」，没有阈值 |
| 组合排序 | **先按放宽档位，再按得分** | 否则放宽 2 档的高分组合会排在严格档前面 |
| 锚定测试池 | 只抽「至少能进一套结果」的单品 | 锚定测的是求解器，不是温度门槛 |
