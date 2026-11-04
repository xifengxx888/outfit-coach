-- M1 数据库 schema（SQLite）
--
-- 六张表：item / profile / location / climate_profile / feedback / daily_suggestion。
-- body_photo、item_pair_stat、tag 属于 M2 以后的功能，本阶段不建。
--
-- 约定：
-- 1. 数组字段（layers / seasons / hit_rules）用 JSON 文本存，CHECK 保证是数组
-- 2. 色彩派生列（hue_family / lightness / saturation / warmth）由 color_hex 算出后写入，
--    规则引擎仍然只认 color_hex——派生列只用于查询与展示
-- 3. 时间统一存文本：日期 YYYY-MM-DD，时间 datetime('now') 的 UTC 格式
-- 4. draft / archived 单品不参与求解，由仓储层过滤，不在这里删数据

CREATE TABLE IF NOT EXISTS item (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    photo_path      TEXT,
    extra_photos    TEXT    NOT NULL DEFAULT '[]'
                        CHECK (json_valid(extra_photos) AND json_type(extra_photos) = 'array'),
    cutout_path     TEXT,
    category        TEXT    NOT NULL CHECK (category IN (
                        'T恤', '衬衫', '卫衣', '毛衣', '针织', '外套', '夹克', '西装',
                        '裤子', '牛仔裤', '短裤', '鞋', '配饰', '连体装', '西装套装')),
    layers          TEXT    NOT NULL DEFAULT '[]'
                        CHECK (json_valid(layers) AND json_type(layers) = 'array'),
    formality       INTEGER NOT NULL CHECK (formality BETWEEN 1 AND 5),
    color_hex       TEXT    NOT NULL CHECK (
                        color_hex GLOB
                        '#[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]'),
    hue_family      TEXT    NOT NULL CHECK (hue_family IN (
                        '红', '橙', '黄', '绿', '青', '蓝', '紫', '中性')),
    lightness       REAL    NOT NULL CHECK (lightness BETWEEN 0 AND 100),
    saturation      REAL    NOT NULL CHECK (saturation BETWEEN 0 AND 100),
    warmth          TEXT    NOT NULL CHECK (warmth IN ('cool', 'warm', 'neutral')),
    fit             TEXT    NOT NULL CHECK (fit IN ('slim', 'regular', 'oversize')),
    pattern         TEXT    NOT NULL CHECK (pattern IN ('solid', 'fine', 'bold')),
    collar          TEXT,
    material        TEXT,
    weight          TEXT    NOT NULL CHECK (weight IN ('thin', 'medium', 'thick')),
    length_cm       REAL    CHECK (length_cm IS NULL OR length_cm > 0),
    shoulder_cm     REAL    CHECK (shoulder_cm IS NULL OR shoulder_cm > 0),
    chest_width_cm  REAL    CHECK (chest_width_cm IS NULL OR chest_width_cm > 0),
    sleeve_cm       REAL    CHECK (sleeve_cm IS NULL OR sleeve_cm > 0),
    waist_cm        REAL    CHECK (waist_cm IS NULL OR waist_cm > 0),
    hip_cm          REAL    CHECK (hip_cm IS NULL OR hip_cm > 0),
    leg_opening_cm  REAL    CHECK (leg_opening_cm IS NULL OR leg_opening_cm > 0),
    shoe_size       REAL    CHECK (shoe_size IS NULL OR shoe_size > 0),
    seasons         TEXT    NOT NULL DEFAULT '[]'
                        CHECK (json_valid(seasons) AND json_type(seasons) = 'array'),
    status          TEXT    NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'confirmed', 'archived')),
    source          TEXT    NOT NULL DEFAULT 'manual'
                        CHECK (source IN ('vlm', 'manual')),
    last_worn_at    TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_item_status ON item (status);
CREATE INDEX IF NOT EXISTS idx_item_category ON item (category);
CREATE INDEX IF NOT EXISTS idx_item_last_worn ON item (last_worn_at);

-- 身材：单行表。*_source 记录每项数据的来源（量人 / 量衣 / 估算）。
CREATE TABLE IF NOT EXISTS profile (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    height          INTEGER,
    weight          INTEGER,
    shoulder_width  INTEGER,
    chest           INTEGER,
    waist           INTEGER,
    hip             INTEGER,
    neck            INTEGER,
    inseam          INTEGER,
    arm_length      INTEGER,
    height_source   TEXT CHECK (height_source IN ('body', 'garment', 'estimated')),
    weight_source   TEXT CHECK (weight_source IN ('body', 'garment', 'estimated')),
    shoulder_width_source TEXT CHECK (shoulder_width_source IN ('body', 'garment', 'estimated')),
    chest_source    TEXT CHECK (chest_source IN ('body', 'garment', 'estimated')),
    waist_source    TEXT CHECK (waist_source IN ('body', 'garment', 'estimated')),
    hip_source      TEXT CHECK (hip_source IN ('body', 'garment', 'estimated')),
    neck_source     TEXT CHECK (neck_source IN ('body', 'garment', 'estimated')),
    inseam_source   TEXT CHECK (inseam_source IN ('body', 'garment', 'estimated')),
    arm_length_source TEXT CHECK (arm_length_source IN ('body', 'garment', 'estimated')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS location (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    lat         REAL    NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon         REAL    NOT NULL CHECK (lon BETWEEN -180 AND 180),
    is_default  INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 同一时刻只允许一个默认地点；换默认地点要在事务里先清后设。
CREATE UNIQUE INDEX IF NOT EXISTS idx_location_one_default
    ON location (is_default) WHERE is_default = 1;

-- 一个地点一年只抓一次，永久缓存（02 第二节）。
CREATE TABLE IF NOT EXISTS climate_profile (
    location_id INTEGER NOT NULL REFERENCES location (id) ON DELETE CASCADE,
    month       INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    day         INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
    temp_avg    REAL    NOT NULL,
    fetched_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (location_id, month, day)
);

CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    outfit_hash TEXT    NOT NULL,
    signal      TEXT    NOT NULL CHECK (signal IN (
                    'adopt', 'favorite', 'swap', 'veto_item', 'ignore')),
    garment_id  INTEGER REFERENCES item (id),
    hit_rules   TEXT    NOT NULL DEFAULT '[]'
                    CHECK (json_valid(hit_rules) AND json_type(hit_rules) = 'array'),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    -- garment_id 只在 veto_item 时填，且必须填
    CHECK (
        (signal = 'veto_item' AND garment_id IS NOT NULL)
        OR (signal <> 'veto_item' AND garment_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_feedback_hash ON feedback (outfit_hash);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback (created_at);

-- 当天展示过的建议。一天一行，点「再换」时覆盖。
-- 次日首次生成建议时，若该 hash 当天没有任何反馈，就补记一条 ignore，然后删除本行。
CREATE TABLE IF NOT EXISTS daily_suggestion (
    day          TEXT    PRIMARY KEY,
    outfit_hash  TEXT    NOT NULL,
    garment_ids  TEXT    NOT NULL
                     CHECK (json_valid(garment_ids) AND json_type(garment_ids) = 'array'),
    hit_rules    TEXT    NOT NULL DEFAULT '[]'
                     CHECK (json_valid(hit_rules) AND json_type(hit_rules) = 'array'),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
