"""FastAPI 后端：把规则求解结果暴露给前端。

读接口只把 `solve()` 的结果和单品字段摊平成 JSON，不做任何打分或过滤；
唯一的写接口是 `POST /api/items`，它只做校验与落库，不参与判断。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..db.connection import DEFAULT_DB_PATH, connect, open_db
from ..db.repo import (
    backfill_ignored_suggestions,
    get_item,
    get_profile,
    insert_item,
    load_items,
    load_recent_swaps,
    next_item_id,
    outfit_hash,
    record_feedback,
    update_item,
    upsert_daily_suggestion,
)
from ..rules import RULE_NAMES
from ..rules.explain import Explanation, explain
from ..rules.gaps import diagnose
from ..rules.rotation import SWAP_WINDOW_DAYS, Rotation, build_rotation, parse_day
from ..rules.solver import Assessment, SolveResult, solve
from ..rules.theory import (
    AXIS_LABELS,
    AXIS_ORDER,
    PRINCIPLES,
    STATUS_LABELS,
    UNSUPPORTED,
)
from ..rules.types import Context, Item
from .photos import PhotoError, save_photo
from .schemas import MAX_PHOTOS, ItemIn, ItemPatch
from .settings_routes import build_settings_router
from .weather import OpenMeteoClient

ROOT = Path(__file__).resolve().parents[2]
PIC_DIR = ROOT / "pic"
PHOTO_DIR = ROOT / "data" / "photos"
WEB_DIST = ROOT / "src" / "web" / "dist"


def _resolve_photo_dir(photo_dir: str | Path | None) -> Path:
    """参数优先，其次环境变量，最后项目内 `data/photos`。"""
    if photo_dir:
        return Path(photo_dir)
    env = os.environ.get("WARDROBE_PHOTO_DIR")
    return Path(env) if env else PHOTO_DIR


def _save_photos(data_urls: list[str], photo_dir: Path) -> list[str]:
    """逐张落盘并保持顺序；任一张失败就抛 400，已写文件保留。"""
    saved: list[str] = []
    for data in data_urls:
        try:
            saved.append(save_photo(data, photo_dir))
        except PhotoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    return saved

SLOT_LABELS = {
    "outer_layer": "外层",
    "mid_layer": "中层",
    "base_top": "内搭",
    "bottom": "下装",
    "shoes": "鞋",
    "accessory": "配饰",
}
DISPLAY_ORDER = ("outer_layer", "mid_layer", "base_top", "bottom", "shoes", "accessory")


class ItemOut(BaseModel):
    id: int
    name: str
    category: str
    color_hex: str
    photo_path: str | None
    formality: int
    weight: str
    layers: list[str]
    fit: str
    pattern: str
    material: str | None
    collar: str | None
    status: str
    last_worn_at: str | None


class ItemDetailOut(ItemOut):
    """详情多带尺寸、照片列表与季节；列表接口保持轻量。"""

    seasons: list[str]
    length_cm: float | None
    shoulder_cm: float | None
    chest_width_cm: float | None
    sleeve_cm: float | None
    waist_cm: float | None
    hip_cm: float | None
    leg_opening_cm: float | None
    shoe_size: float | None
    photos: list[str]


class OutfitPiece(ItemOut):
    slot: str
    slot_label: str


class ExplanationLineOut(BaseModel):
    principle_id: str
    rule_id: str
    title: str
    evidence: str
    why: str
    how_to_judge: str
    grade: str
    grade_label: str
    source: str
    source_url: str | None
    kind: Literal["principle", "baseline"] = "principle"


class CaveatOut(BaseModel):
    code: Literal["relaxed", "negative_soft", "context"]
    text: str
    rule_id: str | None = None
    severity: Literal["info", "warn"] = "info"


class StyleOut(BaseModel):
    label: str
    inferred: bool
    formality_band: str
    silhouette: str
    color_tendency: str
    basis: str
    caveat: str


class ExplanationOut(BaseModel):
    headline: str
    principles: list[ExplanationLineOut]
    caveats: list[CaveatOut]
    style: StyleOut
    data_gaps: list[str]
    version: str = "explain-v1"


class OutfitOut(BaseModel):
    hash: str
    score: float
    level: int
    relaxed_rules: list[str]
    reason: str
    explanation: ExplanationOut
    thumbs_up: list[str]
    thumbs_down: list[str]
    items: list[OutfitPiece]


class TheoryPrincipleOut(BaseModel):
    id: str
    title: str
    claim: str
    why: str
    how_to_judge: str
    rule_ids: list[str]
    grade: str
    grade_label: str
    source: str
    source_url: str | None
    status: str
    status_label: str


class TheoryGroupOut(BaseModel):
    axis: str
    principles: list[TheoryPrincipleOut]


class UnsupportedOut(BaseModel):
    topic: str
    why: str
    needed: str


class TheoryOut(BaseModel):
    groups: list[TheoryGroupOut]
    unsupported: list[UnsupportedOut]


class ContextOut(BaseModel):
    occasion: str
    feels_like: float
    is_rainy: bool = False
    height_cm: int | None = None


class OutfitsResponse(BaseModel):
    context: ContextOut
    item_count: int
    candidate_count: int
    level_counts: dict[str, int]
    best_level: int | None
    all_rejected: bool
    has_more: bool
    outfits: list[OutfitOut]


class FeedbackIn(BaseModel):
    """一次反馈。`garment_ids` 必须是这套组合的全部单品，用来复核 hash。"""

    outfit_hash: str = Field(pattern=r"^[0-9a-f]{16}$")
    signal: Literal["adopt", "favorite", "swap", "veto_item", "ignore"]
    garment_ids: list[int] = Field(min_length=1, max_length=12)
    garment_id: int | None = None
    hit_rules: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("garment_ids")
    @classmethod
    def _check_ids(cls, ids: list[int]) -> list[int]:
        if any(item_id <= 0 for item_id in ids):
            raise ValueError("garment_ids 必须是正整数")
        if len(set(ids)) != len(ids):
            raise ValueError("garment_ids 不能重复")
        return ids

    @field_validator("hit_rules")
    @classmethod
    def _check_rules(cls, rules: list[str]) -> list[str]:
        bad = [rule for rule in rules if rule not in RULE_NAMES]
        if bad:
            raise ValueError(f"未知规则 ID：{bad}")
        return rules


class FeedbackOut(BaseModel):
    id: int
    outfit_hash: str
    signal: str
    garment_id: int | None


def _item_out(item: Item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "color_hex": item.color_hex,
        "photo_path": item.photo_path,
        "formality": item.formality,
        "weight": item.weight,
        "layers": list(item.layers),
        "fit": item.fit,
        "pattern": item.pattern,
        "material": item.material,
        "collar": item.collar,
        "status": item.status,
        "last_worn_at": item.last_worn_at,
    }


ITEM_ATTR_FIELDS = (
    "name",
    "category",
    "layers",
    "formality",
    "color_hex",
    "fit",
    "pattern",
    "weight",
    "material",
    "collar",
    "length_cm",
    "shoulder_cm",
    "chest_width_cm",
    "sleeve_cm",
    "waist_cm",
    "hip_cm",
    "leg_opening_cm",
    "shoe_size",
)


def _item_fields(item: Item) -> dict:
    """把当前单品摊成 `ItemIn` 入参；编辑时补丁覆盖其中若干项。"""
    return {
        "name": item.name,
        "category": item.category,
        "layers": list(item.layers),
        "formality": item.formality,
        "color_hex": item.color_hex,
        "fit": item.fit,
        "pattern": item.pattern,
        "weight": item.weight,
        "material": item.material,
        "collar": item.collar,
        "length_cm": item.length_cm,
        "shoulder_cm": item.shoulder_cm,
        "chest_width_cm": item.chest_width_cm,
        "sleeve_cm": item.sleeve_cm,
        "waist_cm": item.waist_cm,
        "hip_cm": item.hip_cm,
        "leg_opening_cm": item.leg_opening_cm,
        "shoe_size": item.shoe_size,
    }


def _item_detail_out(item: Item) -> dict:
    return {
        **_item_out(item),
        "seasons": list(item.seasons),
        "length_cm": item.length_cm,
        "shoulder_cm": item.shoulder_cm,
        "chest_width_cm": item.chest_width_cm,
        "sleeve_cm": item.sleeve_cm,
        "waist_cm": item.waist_cm,
        "hip_cm": item.hip_cm,
        "leg_opening_cm": item.leg_opening_cm,
        "shoe_size": item.shoe_size,
        "photos": list(item.photos),
    }


def _patch_validation_error(exc: ValidationError) -> HTTPException:
    """把整表校验的中文错误原样交给前端；字段级英文错误给通用文案。"""
    for error in exc.errors():
        message = str(error.get("msg", ""))
        if message.startswith("Value error, "):
            return HTTPException(status_code=422, detail=message.removeprefix("Value error, "))
    return HTTPException(status_code=422, detail="单品字段不合法，请检查填写内容")


def _gap_digest(items: list[Item]) -> str:
    """判定相关的字段全进摘要；`last_worn_at`、照片路径等不影响诊断。"""
    rows = sorted(
        (
            item.id,
            item.name,
            item.category,
            tuple(item.layers),
            item.formality,
            item.color_hex,
            item.fit,
            item.pattern,
            item.weight,
            item.material,
            item.collar,
            item.length_cm,
            item.shoulder_cm,
            item.chest_width_cm,
            item.sleeve_cm,
            item.waist_cm,
            item.hip_cm,
            item.leg_opening_cm,
        )
        for item in items
    )
    return hashlib.sha1(repr(rows).encode("utf-8")).hexdigest()


def _piece_label(item: Item, slot: str) -> str:
    if item.category == "连体装":
        return "连体装"
    if item.category == "西装套装":
        return "套装"
    return SLOT_LABELS[slot]


def _explanation_out(explanation: Explanation) -> ExplanationOut:
    return ExplanationOut(
        headline=explanation.headline,
        principles=[
            ExplanationLineOut(
                principle_id=line.principle_id,
                rule_id=line.rule_id,
                title=line.title,
                evidence=line.evidence,
                why=line.why,
                how_to_judge=line.how_to_judge,
                grade=line.grade,
                grade_label=line.grade_label,
                source=line.source,
                source_url=line.source_url,
                kind=line.kind,
            )
            for line in explanation.principles
        ],
        caveats=[
            CaveatOut(
                code=caveat.code,
                text=caveat.text,
                rule_id=caveat.rule_id,
                severity=caveat.severity,
            )
            for caveat in explanation.caveats
        ],
        style=StyleOut(
            label=explanation.style.label,
            inferred=explanation.style.inferred,
            formality_band=explanation.style.formality_band,
            silhouette=explanation.style.silhouette,
            color_tendency=explanation.style.color_tendency,
            basis=explanation.style.basis,
            caveat=explanation.style.caveat,
        ),
        data_gaps=list(explanation.data_gaps),
        version=explanation.version,
    )


def _theory_out() -> TheoryOut:
    groups = [
        TheoryGroupOut(
            axis=AXIS_LABELS[axis],
            principles=[
                TheoryPrincipleOut(
                    id=principle.id,
                    title=principle.title,
                    claim=principle.claim,
                    why=principle.why,
                    how_to_judge=principle.how_to_judge,
                    rule_ids=list(principle.rule_ids),
                    grade=principle.grade,
                    grade_label=principle.grade_label,
                    source=principle.source,
                    source_url=principle.source_url,
                    status=principle.status,
                    status_label=STATUS_LABELS[principle.status],
                )
                for principle in PRINCIPLES
                if principle.axis == axis
            ],
        )
        for axis in AXIS_ORDER
    ]
    return TheoryOut(
        groups=[group for group in groups if group.principles],
        unsupported=[
            UnsupportedOut(topic=topic.topic, why=topic.why, needed=topic.needed)
            for topic in UNSUPPORTED
        ],
    )


def _outfit_out(assessment: Assessment, ctx: Context) -> OutfitOut:
    placement = assessment.candidate.placement
    seen: set[int] = set()
    pieces: list[dict] = []
    for slot in DISPLAY_ORDER:
        item = placement.get(slot)
        if item is None or item.id in seen:
            continue
        seen.add(item.id)
        pieces.append(
            {**_item_out(item), "slot": slot, "slot_label": _piece_label(item, slot)}
        )
    return OutfitOut(
        hash=outfit_hash(assessment.garment_ids),
        score=assessment.score,
        level=assessment.level,
        relaxed_rules=list(assessment.relaxed_rules),
        reason=assessment.reason,
        explanation=_explanation_out(explain(assessment, ctx)),
        thumbs_up=assessment.thumbs_up,
        thumbs_down=assessment.thumbs_down,
        items=pieces,
    )


def _outfits_response(
    result: SolveResult, items: list[Item], context: Context
) -> OutfitsResponse:
    height = int(context.height_cm) if context.height_cm is not None else None
    return OutfitsResponse(
        context=ContextOut(
            occasion=context.occasion,
            feels_like=context.feels_like if context.feels_like is not None else 22.0,
            is_rainy=context.is_rainy,
            height_cm=height,
        ),
        item_count=len(items),
        candidate_count=result.candidate_count,
        level_counts={str(k): v for k, v in sorted(result.level_counts.items())},
        best_level=result.best_level,
        all_rejected=result.all_rejected,
        has_more=result.has_more,
        outfits=[
            _outfit_out(assessment, context) for assessment in result.outfits
        ],
    )


def _local_today() -> date:
    """本地日期。测试里替换它来模拟「第二天」。"""
    return date.today()


def _today_rotation(conn, items: list[Item], today: date) -> Rotation:
    swaps = [
        (day, hash_value)
        for raw_day, hash_value in load_recent_swaps(conn, SWAP_WINDOW_DAYS)
        if (day := parse_day(raw_day)) is not None
    ]
    return build_rotation(items, swaps, today)


def create_app(
    db_path: str | Path | None = None,
    photo_dir: str | Path | None = None,
    weather_client: object | None = None,
    pic_dir: str | Path | None = None,
) -> FastAPI:
    resolved_db = Path(db_path or os.environ.get("WARDROBE_DB", DEFAULT_DB_PATH))
    resolved_photos = _resolve_photo_dir(photo_dir)
    resolved_pic = Path(pic_dir) if pic_dir is not None else PIC_DIR
    client = weather_client if weather_client is not None else OpenMeteoClient()
    open_db(resolved_db).close()  # 启动时确保表已建好
    resolved_photos.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="个人穿搭助手", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(
        build_settings_router(
            db_path=resolved_db,
            photo_dir=resolved_photos,
            pic_dir=resolved_pic,
            weather_client=client,
        )
    )

    def confirmed_items() -> list[Item]:
        conn = connect(resolved_db)
        try:
            return load_items(conn)
        finally:
            conn.close()

    def build_context(occasion: str, feels_like: float, is_rainy: bool) -> Context:
        conn = connect(resolved_db)
        try:
            profile = get_profile(conn)
        finally:
            conn.close()
        values = (profile or {}).get("values") or {}
        sources = (profile or {}).get("sources") or {}
        return Context(
            occasion=occasion,
            feels_like=feels_like,
            is_rainy=is_rainy,
            height_cm=values.get("height"),
            shoulder_cm=values.get("shoulder_width"),
            chest_cm=values.get("chest"),
            hip_cm=values.get("hip"),
            arm_cm=values.get("arm_length"),
            body_sources={k: v for k, v in sources.items() if v},
        )

    # 诊断是只读的，衣柜不变就复用；任意单品写入都会改变摘要并触发重算
    gap_cache: dict[str, dict] = {}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "db": str(resolved_db)}

    @app.get("/api/theory", response_model=TheoryOut)
    def api_theory() -> TheoryOut:
        """只读原理表：与 docs/11 和 theory.py 同源，不依赖用户数据。"""
        return _theory_out()

    @app.get("/api/gaps")
    def api_gaps() -> dict:
        items = confirmed_items()
        digest = _gap_digest(items)
        cached = gap_cache.get(digest)
        if cached is None:
            cached = diagnose(items)
            gap_cache.clear()
            gap_cache[digest] = cached
        return cached

    @app.get("/api/items", response_model=list[ItemOut])
    def api_items(
        status: str = Query("confirmed", pattern="^(confirmed|draft|archived|all)$"),
    ) -> list[dict]:
        conn = connect(resolved_db)
        try:
            items = load_items(conn, statuses=None if status == "all" else (status,))
        finally:
            conn.close()
        return [_item_out(item) for item in items]

    @app.post("/api/items", response_model=ItemOut, status_code=201)
    def api_create_item(payload: ItemIn) -> dict:
        """先存照片再写库：第一张作封面，其余进 `extra_photos`。

        多张中任意一张校验失败就返回 400；此前已写盘的图成为孤儿文件。
        删照片是红线，这里不清理，也不影响入库结果。
        """
        saved = _save_photos(payload.photos_data, resolved_photos)
        cover = saved[0] if saved else None
        extras = tuple(saved[1:])

        conn = connect(resolved_db)
        try:
            item = payload.to_item(next_item_id(conn), cover, extras)
            insert_item(conn, item)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=409, detail="编号冲突，请重试") from None
        finally:
            conn.close()
        return _item_out(item)

    @app.get("/api/items/{item_id}", response_model=ItemDetailOut)
    def api_item(item_id: int) -> dict:
        conn = connect(resolved_db)
        try:
            item = get_item(conn, item_id)
        finally:
            conn.close()
        if item is None:
            raise HTTPException(status_code=404, detail="单品不存在")
        return _item_detail_out(item)

    @app.patch("/api/items/{item_id}", response_model=ItemDetailOut)
    def api_update_item(item_id: int, payload: ItemPatch) -> dict:
        """编辑、草稿补完、归档与重新启用共用一个端点。

        属性补丁先合并到当前单品，再交给 `ItemIn` 做整表校验，避免前端
        与后端出现第二套品类/尺寸口径。归档是纯状态动作，不要求尺寸齐全。
        照片只追加：无封面时第一张补成封面，已有照片不替换、不删除。
        """
        sent = payload.model_fields_set
        attr_fields = sent & set(ITEM_ATTR_FIELDS)
        status = payload.status

        conn = connect(resolved_db)
        try:
            existing = get_item(conn, item_id)
            if existing is None:
                raise HTTPException(status_code=404, detail="单品不存在")
            if existing.status == "archived" and status not in ("confirmed", "draft"):
                raise HTTPException(status_code=400, detail="已归档的单品需要先重新启用")

            if status == "archived":
                if attr_fields or "photos_data" in sent:
                    raise HTTPException(status_code=400, detail="归档请求只能修改状态")
                updated = replace(existing, status="archived")
                update_item(conn, updated)
                conn.commit()
                return _item_detail_out(updated)

            target = status or existing.status
            data = _item_fields(existing)
            data["status"] = "draft" if target == "draft" else "confirmed"
            for field in attr_fields:
                data[field] = getattr(payload, field)
            try:
                validated = ItemIn.model_validate(data)
            except ValidationError as exc:
                raise _patch_validation_error(exc) from None

            new_photos = payload.photos_data or []
            if len(existing.photos) + len(new_photos) > MAX_PHOTOS:
                raise HTTPException(
                    status_code=422, detail=f"最多 {MAX_PHOTOS} 张照片"
                )
            saved = _save_photos(new_photos, resolved_photos)
            cover = existing.photo_path
            extras = list(existing.extra_photos)
            if cover is None and saved:
                cover, saved = saved[0], saved[1:]
            extras.extend(saved)

            item = replace(
                validated.to_item(item_id, cover, tuple(extras)),
                source=existing.source,
                last_worn_at=existing.last_worn_at,
                cutout_path=existing.cutout_path,
            )
            if update_item(conn, item) == 0:
                raise HTTPException(status_code=404, detail="单品不存在")
            conn.commit()
        finally:
            conn.close()
        return _item_detail_out(item)

    @app.get("/api/outfits", response_model=OutfitsResponse)
    def api_outfits(
        occasion: str = Query("日常", pattern="^(日常|旅游|见人)$"),
        feels_like: float = Query(15.0, ge=-50, le=60),
        is_rainy: bool = Query(False),
        limit: int = Query(10, ge=1, le=50),
        offset: int = Query(0, ge=0, le=1000),
        anchor_id: int | None = None,
    ) -> OutfitsResponse:
        items = confirmed_items()
        anchor: Item | None = None
        if anchor_id is not None:
            anchor = next((item for item in items if item.id == anchor_id), None)
            if anchor is None:
                raise HTTPException(status_code=404, detail="锚定单品不存在或尚未确认")

        context = build_context(occasion, feels_like, is_rainy)
        result = solve(
            items,
            context,
            limit=limit,
            anchor=anchor,
            offset=offset,
        )
        return _outfits_response(result, items, context)

    @app.get("/api/today", response_model=OutfitsResponse)
    def api_today(
        occasion: str = Query("日常", pattern="^(日常|旅游|见人)$"),
        feels_like: float = Query(15.0, ge=-50, le=60),
        is_rainy: bool = Query(False),
        offset: int = Query(0, ge=0, le=1000),
    ) -> OutfitsResponse:
        """每天一套。先生成、再记录展示，同一套在当天不会被重复推荐。

        `offset` 对应「再换」：今天展示的前几套依次跳过，但轮换修正不变。
        """
        today = _local_today()
        day = today.isoformat()
        conn = connect(resolved_db)
        try:
            # 昨天的建议如果没有任何反馈，补记一条 ignore 再删掉
            backfill_ignored_suggestions(conn, day)
            items = load_items(conn)
            rotation = _today_rotation(conn, items, today)
            conn.commit()
        finally:
            conn.close()

        context = build_context(occasion, feels_like, is_rainy)
        result = solve(
            items,
            context,
            limit=1,
            offset=offset,
            rotation=rotation,
        )
        if result.outfits:
            shown = result.outfits[0]
            conn = connect(resolved_db)
            try:
                upsert_daily_suggestion(
                    conn,
                    day,
                    outfit_hash(shown.garment_ids),
                    shown.garment_ids,
                    (*shown.thumbs_up, *shown.thumbs_down),
                )
                conn.commit()
            finally:
                conn.close()
        return _outfits_response(result, items, context)

    @app.post("/api/feedback", response_model=FeedbackOut, status_code=201)
    def api_feedback(payload: FeedbackIn) -> FeedbackOut:
        ids = sorted(payload.garment_ids)
        if outfit_hash(ids) != payload.outfit_hash:
            raise HTTPException(status_code=400, detail="outfit_hash 与单品集合不一致")
        if payload.signal == "veto_item":
            if payload.garment_id is None or payload.garment_id not in ids:
                raise HTTPException(
                    status_code=400, detail="划掉单品需要该组合内的 garment_id"
                )
        elif payload.garment_id is not None:
            raise HTTPException(
                status_code=400, detail="只有 veto_item 可以指定 garment_id"
            )

        conn = connect(resolved_db)
        try:
            missing = [
                item_id
                for item_id in ids
                if (item := get_item(conn, item_id)) is None
                or item.status != "confirmed"
            ]
            if missing:
                raise HTTPException(
                    status_code=400, detail=f"单品不存在或尚未确认：{missing}"
                )
            feedback_id = record_feedback(
                conn,
                payload.outfit_hash,
                payload.signal,
                garment_id=payload.garment_id,
                hit_rules=payload.hit_rules,
            )
            if payload.signal == "adopt":
                conn.executemany(
                    "UPDATE item SET last_worn_at = date('now', 'localtime') "
                    "WHERE id = ?",
                    [(item_id,) for item_id in ids],
                )
            conn.commit()
        finally:
            conn.close()

        return FeedbackOut(
            id=feedback_id,
            outfit_hash=payload.outfit_hash,
            signal=payload.signal,
            garment_id=payload.garment_id,
        )

    if resolved_pic.is_dir():
        app.mount("/pic", StaticFiles(directory=resolved_pic), name="pic")
    # 新录入的照片；必须在根路径静态挂载之前登记
    app.mount("/photos", StaticFiles(directory=resolved_photos), name="photos")
    if WEB_DIST.is_dir():
        # 前端路由要在静态挂载之前显式声明，否则刷新 /today 会 404
        index_html = WEB_DIST / "index.html"

        @app.get("/setup", include_in_schema=False)
        @app.get("/settings", include_in_schema=False)
        @app.get("/outfits", include_in_schema=False)
        @app.get("/today", include_in_schema=False)
        @app.get("/gaps", include_in_schema=False)
        @app.get("/closet", include_in_schema=False)
        @app.get("/add", include_in_schema=False)
        @app.get("/theory", include_in_schema=False)
        def spa_page() -> FileResponse:
            return FileResponse(index_html)

        # 带路径参数的详情/编辑/锚定同样要在静态挂载前登记，
        # 否则直接打开或刷新 /item/6 会被 StaticFiles 判成 404。
        @app.get("/item/{item_id}", include_in_schema=False)
        @app.get("/item/{item_id}/edit", include_in_schema=False)
        @app.get("/anchor/{item_id}", include_in_schema=False)
        def spa_item_page(item_id: int) -> FileResponse:
            return FileResponse(index_html)

        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app


app = create_app()
